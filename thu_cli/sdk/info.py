"""HTTP client for the info portal and zhjw services.

``InfoClient`` assumes the caller has bootstrapped the required CampusApp
(``INFO_PORTAL``, ``TRANSCRIPT_*``, or ``TIMETABLE_*``). The service layer owns
bootstrap and SessionExpired retry policy.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

from ..core.endpoints import (
    INFO_CALENDAR_URL,
    INFO_CSRF_COOKIE_URL,
    ZHJW_TIMETABLE_BKS_PREFIX,
    ZHJW_TIMETABLE_MIDDLE,
    ZHJW_TIMETABLE_SUFFIX,
    ZHJW_TIMETABLE_YJS_PREFIX,
    ZHJW_TRANSCRIPT_BKS_URL,
    ZHJW_TRANSCRIPT_YJS_URL,
)
from ..core.errors import SessionExpired
from ._literals import (
    INFO_AVERAGE_GPA_PREFIX,
    INFO_LOGIN_FORM_MARKER,
    INFO_NON_GPA_GRADES,
    INFO_TOTAL_CREDIT_LABEL,
)
from .auth import SsoSession
from .transport import json_or_expired

logger = logging.getLogger("thu_cli.sdk.info")

@dataclass(frozen=True)
class Calendar:
    """Current-semester academic calendar."""
    first_day: str
    semester_id: str
    week_count: int


@dataclass(frozen=True)
class TranscriptCourse:
    """One row from a zhjw transcript table."""
    course_code: str
    name: str
    credit: float
    grade: str
    point: float
    semester: str
    raw: list[str]


@dataclass(frozen=True)
class TranscriptSummary:
    """Transcript summary from the server plus local cross-checks."""
    official_gpa: float | None
    official_total_credit: float | None
    calculated_gpa: float | None
    total_credit: float
    gpa_credit: float
    course_count: int
    raw: dict[str, str]


@dataclass(frozen=True)
class Transcript:
    """Full transcript: course rows and summary."""
    courses: list[TranscriptCourse]
    summary: TranscriptSummary


@dataclass(frozen=True)
class TimetableEvent:
    """One event from the zhjw timetable feed."""
    title: str
    date: str
    begin: str
    end: str
    location: str
    kind: str
    raw: dict[str, Any]

def _get_info_csrf(http) -> str:
    """Fetch the info portal XSRF token through the webvpn cookie bridge."""
    r = http.get(INFO_CSRF_COOKIE_URL, timeout=30)
    m = re.search(r"XSRF-TOKEN=([^;]+);", r.text + ";")
    if not m:
        raise SessionExpired(f"info portal XSRF-TOKEN not found: {r.text[:200]!r}")
    return m.group(1)


def _parse_float(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _clean_label(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("\xa0", "")).rstrip(":：")


def _extract_transcript_summary(
    soup: BeautifulSoup,
) -> tuple[float | None, float | None, dict[str, str]]:
    raw: dict[str, str] = {}
    official_gpa: float | None = None
    official_total_credit: float | None = None
    for row in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
        for idx in range(0, len(cells) - 1, 2):
            label = _clean_label(cells[idx])
            value = cells[idx + 1].strip()
            if not label or not value:
                continue
            if label == INFO_TOTAL_CREDIT_LABEL and official_total_credit is None:
                raw[label] = value
                official_total_credit = _parse_float(value)
            if label.startswith(INFO_AVERAGE_GPA_PREFIX) and official_gpa is None:
                raw[label] = value
                official_gpa = _parse_float(value)
    return official_gpa, official_total_credit, raw


def _is_gpa_course(course: TranscriptCourse, point_text: str) -> bool:
    if course.credit <= 0 or not point_text.strip():
        return False
    grade = course.grade.strip().upper()
    non_gpa_grades = {"P", "NP", "W", "I", "EX", *INFO_NON_GPA_GRADES}
    return grade not in non_gpa_grades

class InfoClient:
    """Info portal and zhjw client."""

    def __init__(self, sso: SsoSession) -> None:
        self.sso = sso

    @property
    def http(self):
        return self.sso.http

    def get_csrf(self) -> str:
        """Expose the info portal CSRF token for custom API calls."""
        return _get_info_csrf(self.http)

    def get_calendar(self) -> Calendar:
        csrf = _get_info_csrf(self.http)
        r = self.http.get(f"{INFO_CALENDAR_URL}?_csrf={csrf}", timeout=30)
        self.sso.dump_response("info_calendar", r)
        payload = json_or_expired(r)
        obj = (payload or {}).get("object") or {}
        first_day = str(obj.get("jyzdyt") or "")
        # Historical thu-info-lib quirk: this semester starts on Monday.
        if first_day == "2023-06-27":
            first_day = "2023-06-26"
        semester_id = str(obj.get("xnxq") or "")
        suffix = semester_id[-1] if semester_id else ""
        week_count = 12 if suffix == "3" else 18
        return Calendar(first_day=first_day, semester_id=semester_id, week_count=week_count)

    def get_transcript(self, *, graduate: bool = False) -> list[TranscriptCourse]:
        """Return only courses; use ``get_transcript_detail()`` for GPA summary."""
        return self.get_transcript_detail(graduate=graduate).courses

    def get_transcript_detail(self, *, graduate: bool = False) -> Transcript:
        """Return the full transcript across all semesters."""
        url = (ZHJW_TRANSCRIPT_YJS_URL if graduate
               else f"{ZHJW_TRANSCRIPT_BKS_URL}&flag=di1")
        r = self.http.get(url, timeout=30)
        self.sso.dump_response("info_transcript", r)
        if r.status_code != 200:
            raise SessionExpired(f"transcript GET failed: status={r.status_code}")
        html = r.content.decode("gb2312", errors="replace")
        if "loginForm" in html or INFO_LOGIN_FORM_MARKER in html:
            raise SessionExpired("transcript page redirected to login")
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("[cellspacing='1']")
        if table is None:
            raise SessionExpired(
                f"transcript page has no [cellspacing=1] table; html[:200]={html[:200]!r}"
            )
        official_gpa, official_total_credit, raw_summary = _extract_transcript_summary(soup)

        if graduate:
            min_cells = 14
            course_code_i = 0
            name_i, credit_i, grade_i, point_i, semester_i = 3, 5, 9, 11, 13
        else:
            min_cells = 6
            course_code_i = 0
            name_i, credit_i, grade_i, point_i, semester_i = 1, 2, 3, 4, 5

        courses: list[TranscriptCourse] = []
        point_texts: list[str] = []
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < min_cells:
                continue
            texts = [c.get_text(strip=True) for c in cells]
            credit = _parse_float(texts[credit_i]) or 0.0
            point_text = texts[point_i]
            point = _parse_float(point_text) or 0.0
            courses.append(TranscriptCourse(
                course_code=texts[course_code_i],
                name=texts[name_i],
                credit=credit,
                grade=texts[grade_i],
                point=point,
                semester=texts[semester_i],
                raw=texts,
            ))
            point_texts.append(point_text)

        total_credit = sum(c.credit for c in courses)
        gpa_credit = 0.0
        weighted = 0.0
        for course, point_text in zip(courses, point_texts, strict=True):
            if _is_gpa_course(course, point_text):
                gpa_credit += course.credit
                weighted += course.credit * course.point
        calculated_gpa = weighted / gpa_credit if gpa_credit > 0 else None
        return Transcript(
            courses=courses,
            summary=TranscriptSummary(
                official_gpa=official_gpa,
                official_total_credit=official_total_credit,
                calculated_gpa=calculated_gpa,
                total_credit=total_credit,
                gpa_credit=gpa_credit,
                course_count=len(courses),
                raw=raw_summary,
            ),
        )

    def get_timetable(
        self,
        start_date: str,
        end_date: str,
        *,
        graduate: bool = False,
    ) -> list[TimetableEvent]:
        """Return timetable events for the inclusive YYYY-MM-DD date range."""
        prefix = ZHJW_TIMETABLE_YJS_PREFIX if graduate else ZHJW_TIMETABLE_BKS_PREFIX
        url = (prefix + start_date.replace("-", "")
               + ZHJW_TIMETABLE_MIDDLE + end_date.replace("-", "")
               + ZHJW_TIMETABLE_SUFFIX)
        r = self.http.get(url, timeout=30)
        self.sso.dump_response("info_timetable", r)
        if r.status_code != 200:
            raise SessionExpired(f"timetable GET failed: status={r.status_code}")
        text = r.text.strip()
        if not text.startswith("m"):
            raise SessionExpired(f"timetable response not JSONP: {text[:200]!r}")
        lbracket = text.find("[")
        rbracket = text.rfind("]")
        if lbracket == -1 or rbracket == -1 or lbracket >= rbracket:
            return []
        inner = text[lbracket:rbracket + 1]
        if not inner.strip().strip("[]").strip():
            return []
        try:
            items = json.loads(inner)
        except json.JSONDecodeError as e:
            raise SessionExpired(
                f"timetable JSON parse failed: {e}; body={text[:300]!r}"
            ) from e
        events: list[TimetableEvent] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            events.append(TimetableEvent(
                title=str(item.get("nr") or ""),
                date=str(item.get("nq") or ""),
                begin=str(item.get("kssj") or "").replace("：", ":"),
                end=str(item.get("jssj") or "").replace("：", ":"),
                location=str(item.get("dd") or ""),
                kind=str(item.get("fl") or ""),
                raw=item,
            ))
        return events


__all__ = [
    "Calendar",
    "InfoClient",
    "TimetableEvent",
    "Transcript",
    "TranscriptCourse",
    "TranscriptSummary",
]
