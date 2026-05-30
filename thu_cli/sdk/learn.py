"""HTTP client for Tsinghua Web Learning.

Public surface:

    LearnClient(sso)                                wraps ``SsoSession`` for learn APIs
    LearnClient.user_info()                         basic user info
    LearnClient.current_semester() / list_semesters
    LearnClient.list_courses(...)
    LearnClient.list_course_announcements(...)
    LearnClient.list_course_files(...)
    LearnClient.list_course_homeworks(...)
    LearnClient.submit_homework(...)
    LearnClient.list_course_discussions(...)
    LearnClient.list_answered_questions(...)
    LearnClient.list_questionnaires(...)
    LearnClient.download_remote_file(...)
Shared protocol utilities live in ``sdk.transport``; this module keeps only
learn-specific behavior.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, replace
from enum import Enum
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..core.endpoints import (
    LEARN_ANNOUNCEMENTS,
    LEARN_COURSE_ANNOUNCEMENTS,
    LEARN_DOMAIN,
    LEARN_HOMEPAGE,
    LEARN_HOMEWORK_DETAIL,
    LEARN_HOMEWORK_GRADED,
    LEARN_HOMEWORK_NEW,
    LEARN_HOMEWORK_SUBMIT,
    LEARN_HOMEWORK_SUBMITTED,
    LEARN_QNR_DETAIL,
    LEARN_QNR_ENDED,
    LEARN_QNR_ONGOING,
    LEARN_SEMESTER,
    LEARN_SEMESTERS,
    learn_announcement_view_url,
    learn_answered_question_list_url,
    learn_answered_question_url,
    learn_course_file_categories_url,
    learn_course_file_download_url,
    learn_course_file_list_url,
    learn_course_files_by_category_url,
    learn_course_time_location_url,
    learn_course_url,
    learn_courses_by_semester_url,
    learn_discussion_list_url,
    learn_discussion_url,
    learn_homework_download_url,
    learn_homework_page_url,
    learn_homework_submit_url,
    learn_preview_url,
    learn_questionnaire_url,
)
from ..core.errors import LearnError, LearnFailReason, SessionExpired
from ._literals import (
    LEARN_EXPIRED_MARKER,
    LEARN_OPEN_TIME_VALUE,
    LEARN_SUCCESS_SUFFIX,
    SERVER_NO,
    SERVER_YES,
)
from .auth import SsoSession
from .transport import (
    RemoteFile,
    csrf_params,
    display_size,
    display_time,
    json_or_expired,
    raise_if_unauthenticated,
    stream_download,
)

logger = logging.getLogger("thu_cli.sdk.learn")


def _csrf(http: requests.Session) -> dict[str, str]:
    return csrf_params(http, domain=LEARN_DOMAIN)


def _require_success(payload: Any, context: str) -> Any:
    if isinstance(payload, dict) and payload.get("result") == "success":
        return payload
    msg = payload.get("msg") if isinstance(payload, dict) else None
    raise LearnError(
        LearnFailReason.OPERATION_FAILED,
        f"{context} failed: {msg or '<no message>'}",
        payload=payload,
    )


def semester_from_course_id(course_id: str) -> str | None:
    """Infer semester from a ``wlkcid`` prefix such as ``2025-2026-215...``."""
    parts = course_id.split("-", 2)
    if len(parts) != 3 or not parts[2]:
        return None
    term = parts[2][0]
    if term not in {"1", "2", "3"}:
        return None
    return f"{parts[0]}-{parts[1]}-{term}"


def _text(raw: dict, key: str) -> str:
    return unescape(str(raw.get(key) or ""))


def _int(raw: dict, key: str) -> int:
    try:
        return int(raw.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", SERVER_YES}


def _falsey(value: Any) -> bool:
    return str(value).strip().lower() in {"0", "false", "no", SERVER_NO}


def _decode_announcement_html(raw: dict) -> str | None:
    encoded = raw.get("ggnr")
    if encoded:
        try:
            return base64.b64decode(str(encoded)).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            logger.debug("failed to decode announcement ggnr", exc_info=True)
    escaped = raw.get("ggnrStr")
    return unescape(str(escaped)) if escaped else None


def _html_to_text(content_html: str | None) -> str | None:
    if not content_html:
        return None
    text = BeautifulSoup(content_html, "html.parser").get_text("\n", strip=True)
    return text or None


def _attachment_names(raw: dict) -> list[str]:
    value = raw.get("fjmc") or raw.get("fjbt")
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _trimmed_text(node: Any) -> str | None:
    if node is None:
        return None
    text = node.get_text(" ", strip=True)
    return text or None


def _decode_base64_html(value: Any) -> str | None:
    if not value:
        return None
    try:
        return base64.b64decode(str(value)).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        logger.debug("failed to decode base64 html", exc_info=True)
        return None


def _page_list_data(course_id: str) -> dict[str, str]:
    return {"aoData": json.dumps([{"name": "wlkcid", "value": course_id}], ensure_ascii=False)}


def _questionnaire_detail_data(course_id: str, questionnaire_id: str) -> dict[str, str]:
    return {"wlkcid": course_id, "wjid": questionnaire_id}


def _announcement_ao_data(course_id: str, start: int, length: int) -> list[dict[str, Any]]:
    return [
        {"name": "sEcho", "value": 1},
        {"name": "iDisplayStart", "value": start},
        {"name": "iDisplayLength", "value": length},
        {"name": "sSearch", "value": ""},
        {"name": "wlkcid", "value": course_id},
    ]


class ContentKind(str, Enum):
    ANNOUNCEMENT = "announcement"
    FILE = "file"
    HOMEWORK = "homework"
    DISCUSSION = "discussion"
    QUESTION = "question"
    QUESTIONNAIRE = "questionnaire"


class AnnouncementAttachment(RemoteFile):
    pass


@dataclass(frozen=True)
class UserInfo:
    name: str
    department: str


@dataclass(frozen=True)
class SemesterInfo:
    id: str
    start_at: str
    end_at: str
    start_year: int
    end_year: int
    term: str
    raw: dict

    @classmethod
    def from_raw(cls, raw: dict) -> SemesterInfo:
        term_id = _text(raw, "id")
        xnxq = _text(raw, "xnxq") or term_id
        parts = xnxq.split("-")
        start_year = _int({"value": parts[0] if parts else ""}, "value")
        end_year = _int({"value": parts[1] if len(parts) > 1 else ""}, "value")
        term = parts[2] if len(parts) > 2 else (term_id.rsplit("-", 1)[-1] if "-" in term_id else "")
        return cls(
            id=term_id,
            start_at=_text(raw, "kssj"),
            end_at=_text(raw, "jssj"),
            start_year=start_year,
            end_year=end_year,
            term=term,
            raw=raw,
        )


@dataclass(frozen=True)
class Course:
    id: str
    semester_id: str
    code: str
    class_no: str
    name: str
    english_name: str
    teacher: str
    schedule: str
    raw: dict
    time_locations: tuple[str, ...] = ()

    @property
    def url(self) -> str:
        return learn_course_url(self.id)

    def with_time_locations(self, values: list[str] | tuple[str, ...]) -> Course:
        return replace(self, time_locations=tuple(str(v) for v in values if v))

    @classmethod
    def from_raw(cls, raw: dict) -> Course:
        class_no = raw.get("kxhnumber")
        if class_no is None:
            class_no = raw.get("kxh")
        return cls(
            id=_text(raw, "wlkcid"),
            semester_id=_text(raw, "xnxq"),
            code=_text(raw, "kch"),
            class_no=unescape(str(class_no or "")),
            name=_text(raw, "zywkcm") or _text(raw, "kcm"),
            english_name=_text(raw, "ywkcm"),
            teacher=_text(raw, "jsm"),
            schedule=_text(raw, "sjddb"),
            raw=raw,
        )


@dataclass(frozen=True)
class Announcement:
    id: str
    course_id: str
    course_name: str | None
    semester_id: str | None
    title: str
    publisher: str
    published_at: str
    unread: bool | None
    important: bool
    expired: bool | None
    content_html: str | None
    content_text: str | None
    attachment_names: list[str]
    raw: dict
    attachments: tuple[AnnouncementAttachment, ...] = ()

    @property
    def has_content(self) -> bool:
        return bool(self.content_html or self.content_text)

    @classmethod
    def from_raw(cls, raw: dict, *, course: Course | None = None) -> Announcement:
        content_html = _decode_announcement_html(raw)
        course_id = _text(raw, "wlkcid") or (course.id if course else "")
        course_name = _text(raw, "wlkcm") or (course.name if course else None)
        sfyd = raw.get("sfyd")
        unread = None
        if sfyd not in (None, ""):
            unread = _falsey(sfyd)
        elif raw.get("ydsj") == "":
            unread = True

        expired = None
        if raw.get("sfgq") not in (None, ""):
            expired = str(raw.get("sfgq")) == LEARN_EXPIRED_MARKER

        return cls(
            id=_text(raw, "ggid") or _text(raw, "id"),
            course_id=course_id,
            course_name=course_name,
            semester_id=(course.semester_id if course else None) or semester_from_course_id(course_id),
            title=_text(raw, "bt"),
            publisher=_text(raw, "fbrxm") or _text(raw, "fbr"),
            published_at=_text(raw, "fbsjStr") or _text(raw, "fbsj"),
            unread=unread,
            important=_truthy(raw.get("sfqd")),
            expired=expired,
            content_html=content_html,
            content_text=_html_to_text(content_html),
            attachment_names=_attachment_names(raw),
            raw=raw,
        )

    def with_attachments(self, attachments: list[AnnouncementAttachment]) -> Announcement:
        return replace(self, attachments=tuple(attachments))


@dataclass(frozen=True)
class FileCategory:
    id: str
    course_id: str
    title: str
    created_at: str
    raw: dict

    @classmethod
    def from_raw(cls, raw: dict, *, course_id: str) -> FileCategory:
        return cls(
            id=_text(raw, "kjflid"),
            course_id=course_id,
            title=_text(raw, "bt"),
            created_at=display_time(raw.get("czsj")),
            raw=raw,
        )


@dataclass(frozen=True)
class CourseFile:
    id: str
    file_id: str
    course_id: str
    course_name: str | None
    title: str
    description: str
    size: str
    file_type: str
    uploaded_at: str
    important: bool
    is_new: bool
    download_count: int
    raw: dict
    category_id: str = ""
    category_title: str | None = None

    @property
    def remote_file(self) -> RemoteFile:
        return RemoteFile(
            id=self.file_id,
            name=self.title,
            download_url=learn_course_file_download_url(self.file_id),
            preview_url=learn_preview_url(self.file_id, module="mk_kcwj"),
            size=self.size or None,
        )

    @classmethod
    def from_raw(cls, raw: dict, *, course: Course | None = None) -> CourseFile:
        file_id = _text(raw, "wjid")
        return cls(
            id=_text(raw, "kjxxid") or file_id,
            file_id=file_id,
            course_id=_text(raw, "wlkcid") or (course.id if course else ""),
            course_name=(course.name if course else None),
            title=_text(raw, "bt"),
            description=_text(raw, "ms"),
            size=_text(raw, "fileSize"),
            file_type=_text(raw, "wjlx"),
            uploaded_at=_text(raw, "scsj"),
            important=_truthy(raw.get("sfqd")),
            is_new=_truthy(raw.get("isNew")),
            download_count=int(raw.get("xzcs") or 0),
            raw=raw,
            category_id=_text(raw, "kjflid"),
        )

    @classmethod
    def from_category_raw(
        cls,
        raw: list[Any],
        *,
        course_id: str,
        category: FileCategory | None = None,
        course: Course | None = None,
    ) -> CourseFile:
        def cell(index: int) -> str:
            try:
                return unescape(str(raw[index] or ""))
            except IndexError:
                return ""

        file_id = cell(7)
        title = cell(1)
        size = display_size(cell(9))
        return cls(
            id=cell(0) or file_id,
            file_id=file_id,
            course_id=course_id,
            course_name=(course.name if course else None),
            title=title,
            description=cell(5),
            size=size,
            file_type=cell(13),
            uploaded_at=cell(6),
            important=cell(2) == "1",
            is_new=cell(8) == "1",
            download_count=0,
            raw={"row": raw},
            category_id=category.id if category else "",
            category_title=category.title if category else None,
        )


@dataclass(frozen=True)
class Homework:
    id: str
    base_id: str
    course_id: str
    course_name: str | None
    title: str
    deadline: str
    late_deadline: str
    submitted: bool
    graded: bool
    submit_time: str
    grade: str
    grade_level: str
    graded_at: str
    grader: str
    grade_comment: str
    completion_type: str
    submission_type: str
    late_submission: bool
    description_html: str | None
    description_text: str | None
    attachments: tuple[RemoteFile, ...]
    answer_attachments: tuple[RemoteFile, ...]
    submitted_attachments: tuple[RemoteFile, ...]
    grade_attachments: tuple[RemoteFile, ...]
    raw: dict

    @property
    def url(self) -> str:
        return learn_homework_page_url(self.course_id, self.id)

    @property
    def submit_url(self) -> str:
        return learn_homework_submit_url(self.course_id, self.id)

    @classmethod
    def from_raw(
        cls,
        raw: dict,
        *,
        course: Course | None = None,
        submitted: bool,
        graded: bool,
    ) -> Homework:
        course_id = _text(raw, "wlkcid") or (course.id if course else "")
        description_html = _decode_base64_html(raw.get("nr"))
        return cls(
            id=_text(raw, "xszyid"),
            base_id=_text(raw, "zyid"),
            course_id=course_id,
            course_name=(course.name if course else None),
            title=_text(raw, "bt"),
            deadline=_text(raw, "jzsjStr") or _text(raw, "jzsj"),
            late_deadline=_text(raw, "bjjzsjStr") or _text(raw, "bjjzsj"),
            submitted=submitted,
            graded=graded,
            submit_time=_text(raw, "scsjStr") or ("" if raw.get("scsj") is None else _text(raw, "scsj")),
            grade="" if raw.get("cj") is None else str(raw.get("cj")),
            grade_level=_text(raw, "cj"),
            graded_at=_text(raw, "pysj"),
            grader=_text(raw, "jsm"),
            grade_comment=_text(raw, "pynr"),
            completion_type=_text(raw, "zywcfs"),
            submission_type=_text(raw, "zytjfs"),
            late_submission=_truthy(raw.get("sfbj")),
            description_html=description_html,
            description_text=_html_to_text(description_html),
            attachments=(),
            answer_attachments=(),
            submitted_attachments=(),
            grade_attachments=(),
            raw=raw,
        )

    def with_detail(
        self,
        *,
        description_html: str | None = None,
        attachments: list[RemoteFile] | None = None,
        answer_attachments: list[RemoteFile] | None = None,
        submitted_attachments: list[RemoteFile] | None = None,
        grade_attachments: list[RemoteFile] | None = None,
    ) -> Homework:
        html = description_html or self.description_html
        return replace(
            self,
            description_html=html,
            description_text=_html_to_text(html),
            attachments=tuple(attachments or self.attachments),
            answer_attachments=tuple(answer_attachments or self.answer_attachments),
            submitted_attachments=tuple(submitted_attachments or self.submitted_attachments),
            grade_attachments=tuple(grade_attachments or self.grade_attachments),
        )

    def downloadable_files(self) -> list[RemoteFile]:
        files: list[RemoteFile] = []
        files.extend(self.attachments)
        files.extend(self.answer_attachments)
        files.extend(self.submitted_attachments)
        files.extend(self.grade_attachments)
        return files


@dataclass(frozen=True)
class Discussion:
    id: str
    course_id: str
    course_name: str | None
    board_id: str
    title: str
    publisher: str
    published_at: str
    last_replier: str
    last_replied_at: str
    visit_count: int
    reply_count: int
    raw: dict

    @property
    def url(self) -> str:
        return learn_discussion_url(self.course_id, self.board_id, self.id)

    @classmethod
    def from_raw(cls, raw: dict, *, course: Course | None = None) -> Discussion:
        course_id = _text(raw, "wlkcid") or (course.id if course else "")
        return cls(
            id=_text(raw, "id"),
            course_id=course_id,
            course_name=(course.name if course else None),
            board_id=_text(raw, "bqid"),
            title=_text(raw, "bt"),
            publisher=_text(raw, "fbrxm") or _text(raw, "fbr"),
            published_at=_text(raw, "fbsj"),
            last_replier=_text(raw, "zhhfrxm"),
            last_replied_at=_text(raw, "zhhfsj"),
            visit_count=_int(raw, "djs"),
            reply_count=_int(raw, "hfcs"),
            raw=raw,
        )


@dataclass(frozen=True)
class AnsweredQuestion:
    id: str
    course_id: str
    course_name: str | None
    title: str
    question_text: str
    publisher: str
    published_at: str
    last_replier: str
    last_replied_at: str
    visit_count: int
    reply_count: int
    raw: dict

    @property
    def url(self) -> str:
        return learn_answered_question_url(self.course_id, self.id)

    @classmethod
    def from_raw(cls, raw: dict, *, course: Course | None = None) -> AnsweredQuestion:
        course_id = _text(raw, "wlkcid") or (course.id if course else "")
        return cls(
            id=_text(raw, "id"),
            course_id=course_id,
            course_name=(course.name if course else None),
            title=_text(raw, "bt"),
            question_text=_html_to_text(_decode_base64_html(raw.get("wtnr"))) or "",
            publisher=_text(raw, "fbrxm") or _text(raw, "fbr"),
            published_at=_text(raw, "fbsj"),
            last_replier=_text(raw, "zhhfrxm"),
            last_replied_at=_text(raw, "zhhfsj"),
            visit_count=_int(raw, "djs"),
            reply_count=_int(raw, "hfcs"),
            raw=raw,
        )


@dataclass(frozen=True)
class QuestionnaireOption:
    id: str
    index: int
    title: str


@dataclass(frozen=True)
class QuestionnaireQuestion:
    id: str
    index: int
    kind: str
    required: bool
    title: str
    score: int | None
    options: tuple[QuestionnaireOption, ...] = ()

    @classmethod
    def from_raw(cls, raw: dict) -> QuestionnaireQuestion:
        options = tuple(
            QuestionnaireOption(
                id=_text(item, "xxid"),
                index=_int(item, "xxbh"),
                title=_text(item, "xxbt"),
            )
            for item in (raw.get("list") or [])
            if isinstance(item, dict)
        )
        score: int | None = None
        if raw.get("wtfz") not in (None, ""):
            score = _int(raw, "wtfz")
        return cls(
            id=_text(raw, "wtid"),
            index=_int(raw, "wtbh"),
            kind=_text(raw, "type"),
            required=_truthy(raw.get("require")),
            title=_text(raw, "wtbt"),
            score=score,
            options=options,
        )


@dataclass(frozen=True)
class Questionnaire:
    id: str
    course_id: str
    course_name: str | None
    kind: str
    title: str
    start_at: str
    end_at: str
    uploaded_at: str
    uploader: str
    submitted_at: str
    questions: tuple[QuestionnaireQuestion, ...]
    raw: dict

    @property
    def url(self) -> str:
        return learn_questionnaire_url(self.course_id, self.id, self.kind)

    @classmethod
    def from_raw(
        cls,
        raw: dict,
        *,
        course: Course | None = None,
        questions: list[QuestionnaireQuestion] | None = None,
    ) -> Questionnaire:
        course_id = _text(raw, "wlkcid") or (course.id if course else "")
        return cls(
            id=_text(raw, "wjid"),
            course_id=course_id,
            course_name=(course.name if course else None),
            kind=_text(raw, "wjlx") or "wj",
            title=_text(raw, "wjbt"),
            start_at=_text(raw, "kssj"),
            end_at=_text(raw, "jssj"),
            uploaded_at=_text(raw, "scsj"),
            uploader=_text(raw, "scrxm") or _text(raw, "scr"),
            submitted_at=_text(raw, "tjsj"),
            questions=tuple(questions or []),
            raw=raw,
        )


@dataclass(frozen=True)
class CourseContentBundle:
    course_id: str
    course_name: str | None
    contents: dict[ContentKind, list[Any]]

    def get(self, kind: ContentKind | str) -> list[Any]:
        return self.contents[ContentKind(kind)]


class LearnClient:
    """Web Learning client; callers must bootstrap ``LEARN_REALM`` first."""

    def __init__(self, sso: SsoSession):
        self.sso = sso

    @property
    def http(self) -> requests.Session:
        return self.sso.http

    def user_info(self) -> UserInfo:
        r = self.http.get(
            LEARN_HOMEPAGE,
            params=_csrf(self.http),
            timeout=30,
            allow_redirects=False,
        )
        self.sso.dump_response("learn_user_info", r)
        raise_if_unauthenticated(r, context="learn homepage")
        soup = BeautifulSoup(r.text, "html.parser")
        name = soup.select_one("a.user-log")
        department = soup.select_one(".fl.up-img-info p:nth-child(2) label")
        return UserInfo(
            name=name.get_text(" ", strip=True) if name else "",
            department=department.get_text(" ", strip=True) if department else "",
        )

    def current_semester(self) -> str:
        r = self.http.get(LEARN_SEMESTER, params=_csrf(self.http),
                          timeout=30, allow_redirects=False)
        self.sso.dump_response("learn_semester", r)
        payload = json_or_expired(r)
        return str(payload["result"]["id"])

    def current_semester_info(self) -> SemesterInfo:
        r = self.http.get(LEARN_SEMESTER, params=_csrf(self.http),
                          timeout=30, allow_redirects=False)
        self.sso.dump_response("learn_semester_info", r)
        payload = json_or_expired(r)
        if not isinstance(payload, dict) or payload.get("message") != "success":
            raise LearnError(
                LearnFailReason.INVALID_RESPONSE,
                "learn current semester returned an invalid payload",
                payload=payload,
            )
        result = payload.get("result")
        if not isinstance(result, dict):
            raise LearnError(
                LearnFailReason.INVALID_RESPONSE,
                "learn current semester result is not an object",
                payload=payload,
            )
        return SemesterInfo.from_raw(result)

    def list_semesters(self) -> list[str]:
        r = self.http.get(LEARN_SEMESTERS, params=_csrf(self.http),
                          timeout=30, allow_redirects=False)
        self.sso.dump_response("learn_semesters", r)
        data = json_or_expired(r)
        if not isinstance(data, list):
            raise SessionExpired(f"learn semesters returned non-list: {type(data).__name__}")
        semesters: list[str] = []
        seen: set[str] = set()
        for item in data:
            if not item:
                continue
            s = str(item)
            if s not in seen:
                semesters.append(s)
                seen.add(s)
        return semesters

    def list_courses_raw(
        self,
        semester: str | None = None,
        *,
        all_terms: bool = False,
    ) -> list[dict]:
        if semester and all_terms:
            raise ValueError("semester and all_terms are mutually exclusive")
        if all_terms:
            logger.info("list_courses_raw: scanning all semesters")
            courses: list[dict] = []
            for sid in self.list_semesters():
                rows = self._list_courses_by_semester_raw(sid)
                if rows:
                    courses.extend(rows)
            logger.info("list_courses_raw: %d courses across all semesters", len(courses))
            return courses
        sid = semester or self.current_semester()
        rows = self._list_courses_by_semester_raw(sid)
        logger.info("list_courses_raw: %d courses in %s", len(rows), sid)
        return rows

    def _list_courses_by_semester_raw(self, semester: str) -> list[dict]:
        r = self.http.post(learn_courses_by_semester_url(semester), data={},
                           params=_csrf(self.http),
                           timeout=30, allow_redirects=False)
        self.sso.dump_response("learn_courses", r)
        payload = json_or_expired(r)
        if not isinstance(payload, dict) or payload.get("message") != "success":
            raise LearnError(
                LearnFailReason.INVALID_RESPONSE,
                "learn courses returned an invalid payload",
                payload=payload,
            )
        result = payload.get("resultList")
        if not isinstance(result, list):
            raise LearnError(
                LearnFailReason.INVALID_RESPONSE,
                "learn courses resultList is not a list",
                payload=payload,
            )
        return result

    def list_courses(
        self,
        semester: str | None = None,
        *,
        all_terms: bool = False,
        include_time_locations: bool = False,
    ) -> list[Course]:
        courses = [Course.from_raw(row) for row in self.list_courses_raw(
            semester=semester,
            all_terms=all_terms,
        )]
        if include_time_locations:
            courses = [self.enrich_course_time_locations(c) for c in courses]
        return courses

    def course_time_locations(self, course_id: str) -> list[str]:
        r = self.http.get(
            learn_course_time_location_url(course_id),
            params=_csrf(self.http),
            timeout=30,
            allow_redirects=False,
        )
        self.sso.dump_response("learn_course_time_location", r)
        payload = json_or_expired(r)
        if not isinstance(payload, list):
            raise LearnError(
                LearnFailReason.INVALID_RESPONSE,
                "learn course time/location returned non-list",
                payload=payload,
            )
        return [str(item) for item in payload if item]

    def enrich_course_time_locations(self, course: Course) -> Course:
        try:
            return course.with_time_locations(self.course_time_locations(course.id))
        except LearnError:
            logger.debug("failed to fetch course time/location for %s", course.id, exc_info=True)
            return course

    def list_announcement_summaries(
        self,
        course_ids: list[str],
        *,
        unread_only: bool = False,
        page_size: int = 100,
        max_pages: int = 50,
    ) -> list[Announcement]:
        if not course_ids:
            return []
        announcements: list[Announcement] = []
        for page in range(1, max_pages + 1):
            rows = self._list_announcement_summary_page(
                course_ids, page=page, length=page_size, unread_only=unread_only,
            )
            announcements.extend(Announcement.from_raw(row) for row in rows)
            if len(rows) < page_size:
                break
        logger.info("list_announcement_summaries: %d announcements", len(announcements))
        return announcements

    def _list_announcement_summary_page(
        self,
        course_ids: list[str],
        *,
        page: int,
        length: int,
        unread_only: bool,
    ) -> list[dict]:
        data: list[tuple[str, str]] = [
            ("kssj", LEARN_OPEN_TIME_VALUE),
            ("jssj", LEARN_OPEN_TIME_VALUE),
            ("sfdwc", SERVER_YES if unread_only else ""),
        ]
        data.extend(("wlkcids[]", cid) for cid in course_ids)
        r = self.http.post(
            LEARN_ANNOUNCEMENTS,
            params={**_csrf(self.http), "page": page, "length": length},
            data=data,
            timeout=30,
            allow_redirects=False,
        )
        self.sso.dump_response("learn_announcements", r)
        payload = _require_success(json_or_expired(r), "learn announcements")
        return payload.get("object") or []

    def list_course_announcements(
        self,
        course_id: str,
        *,
        course: Course | None = None,
        page_size: int = 100,
    ) -> list[Announcement]:
        announcements: list[Announcement] = []
        start = 0
        total: int | None = None
        while total is None or start < total:
            obj = self._list_course_announcement_page(course_id, start=start, length=page_size)
            total = int(obj.get("iTotalRecords") or 0)
            rows = obj.get("aaData") or []
            announcements.extend(Announcement.from_raw(row, course=course) for row in rows)
            if not rows:
                break
            start += len(rows)
        logger.info(
            "list_course_announcements: %d announcements in %s", len(announcements), course_id,
        )
        return announcements

    def _list_course_announcement_page(
        self, course_id: str, *, start: int, length: int,
    ) -> dict:
        r = self.http.post(
            LEARN_COURSE_ANNOUNCEMENTS,
            params=_csrf(self.http),
            data={"aoData": json.dumps(
                _announcement_ao_data(course_id, start, length), ensure_ascii=False,
            )},
            timeout=30,
            allow_redirects=False,
        )
        self.sso.dump_response("learn_course_announcements", r)
        payload = _require_success(json_or_expired(r), "learn course announcements")
        return payload.get("object") or {}

    def get_announcement(
        self,
        course_id: str,
        announcement_id: str,
        *,
        course: Course | None = None,
        include_attachments: bool = False,
    ) -> Announcement | None:
        for announcement in self.list_course_announcements(course_id, course=course):
            if announcement.id == announcement_id:
                if include_attachments:
                    return announcement.with_attachments(
                        self.announcement_attachments(course_id, announcement_id),
                    )
                return announcement
        return None

    def announcement_attachments(
        self, course_id: str, announcement_id: str,
    ) -> list[AnnouncementAttachment]:
        """Parse attachment metadata from the HTML detail page."""
        r = self.http.get(
            learn_announcement_view_url(course_id, announcement_id),
            params=_csrf(self.http),
            timeout=30,
            allow_redirects=False,
        )
        self.sso.dump_response("learn_announcement_view", r)
        raise_if_unauthenticated(r, context="learn announcement detail")
        soup = BeautifulSoup(r.text, "html.parser")
        attachments: list[AnnouncementAttachment] = []
        for link in soup.select("#attachment a[href], .ml-10[href]"):
            href = link.get("href")
            if not href:
                continue
            parsed = urlparse(href)
            query = parse_qs(parsed.query)
            file_id = (query.get("wjid") or query.get("fileId") or [""])[0]
            name = link.get_text(" ", strip=True)
            if not file_id or not name:
                continue
            container = link.find_parent("div")
            size = _trimmed_text(container.select_one("span[class^='color']")) if container else None
            download_url = (
                href if href.startswith("http")
                else urljoin(learn_announcement_view_url(course_id, announcement_id), href)
            )
            attachments.append(
                AnnouncementAttachment(
                    id=file_id,
                    name=name,
                    download_url=download_url,
                    preview_url=learn_preview_url(file_id),
                    size=size,
                )
            )
        return attachments

    def list_course_files(
        self,
        course_id: str,
        *,
        course: Course | None = None,
        category_id: str | None = None,
    ) -> list[CourseFile]:
        if category_id:
            category = self.get_file_category(course_id, category_id)
            return self.list_course_files_by_category(
                course_id, category_id, category=category, course=course,
            )
        r = self.http.get(
            learn_course_file_list_url(course_id),
            params=_csrf(self.http),
            timeout=30,
            allow_redirects=False,
        )
        self.sso.dump_response("learn_course_files", r)
        payload = _require_success(json_or_expired(r), "learn course files")
        rows = payload.get("object") or []
        if not isinstance(rows, list):
            raise LearnError(
                LearnFailReason.INVALID_RESPONSE,
                "learn course files object is not a list",
                payload=payload,
            )
        return [CourseFile.from_raw(row, course=course) for row in rows]

    def list_file_categories(self, course_id: str) -> list[FileCategory]:
        r = self.http.get(
            learn_course_file_categories_url(course_id),
            params=_csrf(self.http),
            timeout=30,
            allow_redirects=False,
        )
        self.sso.dump_response("learn_file_categories", r)
        payload = _require_success(json_or_expired(r), "learn file categories")
        rows = (payload.get("object") or {}).get("rows") or []
        if not isinstance(rows, list):
            raise LearnError(
                LearnFailReason.INVALID_RESPONSE,
                "learn file categories rows is not a list",
                payload=payload,
            )
        return [FileCategory.from_raw(row, course_id=course_id) for row in rows]

    def get_file_category(self, course_id: str, category_id: str) -> FileCategory | None:
        for category in self.list_file_categories(course_id):
            if category.id == category_id:
                return category
        return None

    def list_course_files_by_category(
        self,
        course_id: str,
        category_id: str,
        *,
        category: FileCategory | None = None,
        course: Course | None = None,
    ) -> list[CourseFile]:
        r = self.http.get(
            learn_course_files_by_category_url(course_id, category_id),
            params=_csrf(self.http),
            timeout=30,
            allow_redirects=False,
        )
        self.sso.dump_response("learn_course_files_by_category", r)
        payload = _require_success(json_or_expired(r), "learn course files by category")
        rows = payload.get("object") or []
        if not isinstance(rows, list):
            raise LearnError(
                LearnFailReason.INVALID_RESPONSE,
                "learn course files by category object is not a list",
                payload=payload,
            )
        return [
            CourseFile.from_category_raw(row, course_id=course_id, category=category, course=course)
            for row in rows
            if isinstance(row, list)
        ]

    def get_course_file(
        self, course_id: str, file_id: str, *, course: Course | None = None,
    ) -> CourseFile | None:
        for item in self.list_course_files(course_id, course=course):
            if item.file_id == file_id or item.id == file_id:
                return item
        return None

    def list_course_discussions(
        self, course_id: str, *, course: Course | None = None,
    ) -> list[Discussion]:
        r = self.http.get(
            learn_discussion_list_url(course_id),
            params=_csrf(self.http),
            timeout=30,
            allow_redirects=False,
        )
        self.sso.dump_response("learn_course_discussions", r)
        payload = _require_success(json_or_expired(r), "learn course discussions")
        rows = (payload.get("object") or {}).get("resultsList") or []
        if not isinstance(rows, list):
            raise LearnError(
                LearnFailReason.INVALID_RESPONSE,
                "learn course discussions resultsList is not a list",
                payload=payload,
            )
        return [Discussion.from_raw(row, course=course) for row in rows]

    def list_answered_questions(
        self, course_id: str, *, course: Course | None = None,
    ) -> list[AnsweredQuestion]:
        r = self.http.get(
            learn_answered_question_list_url(course_id),
            params=_csrf(self.http),
            timeout=30,
            allow_redirects=False,
        )
        self.sso.dump_response("learn_answered_questions", r)
        payload = _require_success(json_or_expired(r), "learn answered questions")
        rows = (payload.get("object") or {}).get("resultsList") or []
        if not isinstance(rows, list):
            raise LearnError(
                LearnFailReason.INVALID_RESPONSE,
                "learn answered questions resultsList is not a list",
                payload=payload,
            )
        return [AnsweredQuestion.from_raw(row, course=course) for row in rows]

    def list_questionnaires(
        self,
        course_id: str,
        *,
        course: Course | None = None,
        include_detail: bool = False,
    ) -> list[Questionnaire]:
        rows: list[Questionnaire] = []
        for url in (LEARN_QNR_ONGOING, LEARN_QNR_ENDED):
            rows.extend(self._list_questionnaires_at(
                url, course_id, course=course, include_detail=include_detail,
            ))
        rows.sort(key=lambda item: (item.end_at, item.title))
        return rows

    def _list_questionnaires_at(
        self,
        url: str,
        course_id: str,
        *,
        course: Course | None,
        include_detail: bool,
    ) -> list[Questionnaire]:
        r = self.http.post(
            url,
            params=_csrf(self.http),
            data=_page_list_data(course_id),
            timeout=30,
            allow_redirects=False,
        )
        self.sso.dump_response("learn_questionnaires", r)
        payload = _require_success(json_or_expired(r), "learn questionnaires")
        rows = (payload.get("object") or {}).get("aaData") or []
        if not isinstance(rows, list):
            raise LearnError(
                LearnFailReason.INVALID_RESPONSE,
                "learn questionnaires aaData is not a list",
                payload=payload,
            )
        questionnaires: list[Questionnaire] = []
        for row in rows:
            questions = (
                self.questionnaire_questions(course_id, _text(row, "wjid"))
                if include_detail else []
            )
            questionnaires.append(Questionnaire.from_raw(row, course=course, questions=questions))
        return questionnaires

    def questionnaire_questions(
        self, course_id: str, questionnaire_id: str,
    ) -> list[QuestionnaireQuestion]:
        r = self.http.post(
            LEARN_QNR_DETAIL,
            params=_csrf(self.http),
            data=_questionnaire_detail_data(course_id, questionnaire_id),
            timeout=30,
            allow_redirects=False,
        )
        self.sso.dump_response("learn_questionnaire_detail", r)
        payload = json_or_expired(r)
        if not isinstance(payload, list):
            raise LearnError(
                LearnFailReason.INVALID_RESPONSE,
                "learn questionnaire detail is not a list",
                payload=payload,
            )
        return [QuestionnaireQuestion.from_raw(row) for row in payload if isinstance(row, dict)]

    def list_course_contents(
        self,
        course_id: str,
        *,
        course: Course | None = None,
        kinds: list[ContentKind | str] | None = None,
        include_homework_detail: bool = False,
        include_questionnaire_detail: bool = False,
    ) -> CourseContentBundle:
        selected = [ContentKind(kind) for kind in (kinds or list(ContentKind))]
        contents: dict[ContentKind, list[Any]] = {}
        for kind in selected:
            if kind is ContentKind.ANNOUNCEMENT:
                contents[kind] = self.list_course_announcements(course_id, course=course)
            elif kind is ContentKind.FILE:
                contents[kind] = self.list_course_files(course_id, course=course)
            elif kind is ContentKind.HOMEWORK:
                contents[kind] = self.list_course_homeworks(
                    course_id, course=course, include_detail=include_homework_detail,
                )
            elif kind is ContentKind.DISCUSSION:
                contents[kind] = self.list_course_discussions(course_id, course=course)
            elif kind is ContentKind.QUESTION:
                contents[kind] = self.list_answered_questions(course_id, course=course)
            elif kind is ContentKind.QUESTIONNAIRE:
                contents[kind] = self.list_questionnaires(
                    course_id, course=course, include_detail=include_questionnaire_detail,
                )
        return CourseContentBundle(
            course_id=course_id,
            course_name=course.name if course else None,
            contents=contents,
        )

    def list_course_homeworks(
        self,
        course_id: str,
        *,
        course: Course | None = None,
        include_detail: bool = False,
    ) -> list[Homework]:
        rows: list[Homework] = []
        for url, submitted, graded in [
            (LEARN_HOMEWORK_NEW, False, False),
            (LEARN_HOMEWORK_SUBMITTED, True, False),
            (LEARN_HOMEWORK_GRADED, True, True),
        ]:
            rows.extend(self._list_course_homeworks_at(
                url, course_id, course=course, submitted=submitted, graded=graded,
            ))
        rows.sort(key=lambda item: (item.deadline, item.title))
        if include_detail:
            rows = [self.enrich_homework_detail(item) for item in rows]
        return rows

    def _list_course_homeworks_at(
        self,
        url: str,
        course_id: str,
        *,
        course: Course | None,
        submitted: bool,
        graded: bool,
    ) -> list[Homework]:
        r = self.http.post(
            url,
            params=_csrf(self.http),
            data=_page_list_data(course_id),
            timeout=30,
            allow_redirects=False,
        )
        self.sso.dump_response("learn_course_homeworks", r)
        payload = _require_success(json_or_expired(r), "learn course homeworks")
        rows = (payload.get("object") or {}).get("aaData") or []
        if not isinstance(rows, list):
            raise LearnError(
                LearnFailReason.INVALID_RESPONSE,
                "learn course homeworks aaData is not a list",
                payload=payload,
            )
        return [
            self._homework_from_raw(row, course=course, submitted=submitted, graded=graded)
            for row in rows
        ]

    def _homework_from_raw(
        self, raw: dict, *, course: Course | None, submitted: bool, graded: bool,
    ) -> Homework:
        homework = Homework.from_raw(raw, course=course, submitted=submitted, graded=graded)
        submitted_file = self._submitted_homework_file(homework)
        if submitted_file:
            return homework.with_detail(submitted_attachments=[submitted_file])
        return homework

    def _submitted_homework_file(self, homework: Homework) -> RemoteFile | None:
        attachment_id = _text(homework.raw, "zyfjid")
        if not attachment_id:
            return None
        name = _text(homework.raw, "wjmc") or attachment_id
        size = str(homework.raw.get("wjdx") or "") or None
        return RemoteFile(
            id=attachment_id,
            name=name,
            download_url=learn_homework_download_url(homework.course_id, attachment_id),
            preview_url=learn_preview_url(attachment_id, module="mk_kczy"),
            size=size,
        )

    def get_homework(
        self,
        course_id: str,
        homework_id: str,
        *,
        course: Course | None = None,
        include_detail: bool = False,
    ) -> Homework | None:
        for homework in self.list_course_homeworks(course_id, course=course):
            if homework.id == homework_id or homework.base_id == homework_id:
                return self.enrich_homework_detail(homework) if include_detail else homework
        return None

    def enrich_homework_detail(self, homework: Homework) -> Homework:
        description_html = homework.description_html
        if homework.base_id:
            r = self.http.post(
                LEARN_HOMEWORK_DETAIL,
                params=_csrf(self.http),
                data={"id": homework.base_id},
                timeout=30,
                allow_redirects=False,
            )
            self.sso.dump_response("learn_homework_detail", r)
            payload = _require_success(json_or_expired(r), "learn homework detail")
            if payload.get("msg"):
                description_html = unescape(str(payload.get("msg")))

        page_files = self._homework_page_files(homework)
        submitted = list(homework.submitted_attachments)
        known_ids = {item.id for item in submitted}
        for f in page_files:
            if f.id not in known_ids:
                submitted.append(f)
        return homework.with_detail(
            description_html=description_html,
            submitted_attachments=submitted,
        )

    def submit_homework(
        self,
        homework_id: str,
        *,
        content: str = "",
        attachment: str | Path | None = None,
        remove_attachment: bool = False,
    ) -> None:
        data = {
            "xszyid": homework_id,
            "zynr": content,
            "isDeleted": "1" if remove_attachment else "0",
        }
        files: list[tuple[str, tuple[str | None, Any]]] = []
        fh = None
        if attachment:
            path = Path(attachment)
            fh = path.open("rb")
            files.append(("fileupload", (path.name, fh)))
        else:
            files.append(("fileupload", (None, "undefined")))
        try:
            r = self.http.post(
                LEARN_HOMEWORK_SUBMIT,
                params=_csrf(self.http),
                data=data,
                files=files,
                timeout=60,
                allow_redirects=False,
            )
        finally:
            if fh:
                fh.close()
        self.sso.dump_response("learn_homework_submit", r)
        payload = _require_success(json_or_expired(r), "learn homework submit")
        if not str(payload.get("msg") or "").endswith(LEARN_SUCCESS_SUFFIX):
            logger.debug("homework submit success without success msg: %s", payload)

    def _homework_page_files(self, homework: Homework) -> list[RemoteFile]:
        r = self.http.get(
            homework.url,
            params=_csrf(self.http),
            timeout=30,
            allow_redirects=False,
        )
        self.sso.dump_response("learn_homework_page", r)
        raise_if_unauthenticated(r, context="learn homework detail")
        soup = BeautifulSoup(r.text, "html.parser")
        files: list[RemoteFile] = []
        for link in soup.select("a[href]"):
            href = link.get("href") or ""
            if "fileId=" not in href and "downloadFile" not in href:
                continue
            query = parse_qs(urlparse(href).query)
            file_id = (query.get("fileId") or [""])[0]
            if not file_id:
                continue
            name = link.get_text(" ", strip=True) or file_id
            download_url = ""
            if query.get("downloadUrl"):
                download_url = urljoin(homework.url, query["downloadUrl"][0])
            elif "downloadFile" in href:
                download_url = href if href.startswith("http") else urljoin(homework.url, href)
            else:
                download_url = learn_homework_download_url(homework.course_id, file_id)
            files.append(RemoteFile(
                id=file_id,
                name=name,
                download_url=download_url,
                preview_url=learn_preview_url(file_id, module="mk_kczy"),
            ))
        return files

    def download_remote_file(
        self,
        remote_file: RemoteFile,
        dest_dir: str | Path = "downloads",
        *,
        filename: str | None = None,
    ) -> Path:
        try:
            return stream_download(
                self.http,
                remote_file,
                dest_dir,
                csrf_domain=LEARN_DOMAIN,
                dump=self.sso.dump_response,
                filename=filename,
            )
        except RuntimeError as e:
            raise LearnError(LearnFailReason.OPERATION_FAILED, str(e)) from e


__all__ = [
    "Announcement",
    "AnnouncementAttachment",
    "AnsweredQuestion",
    "ContentKind",
    "Course",
    "CourseContentBundle",
    "CourseFile",
    "Discussion",
    "FileCategory",
    "Homework",
    "LearnClient",
    "Questionnaire",
    "QuestionnaireOption",
    "QuestionnaireQuestion",
    "SemesterInfo",
    "UserInfo",
    "semester_from_course_id",
]
