"""``InfoService`` — profile-aware 信息门户 + zhjw 用例。

包装 ``InfoClient``，提供：
    - WEBVPN_REALM + 对应 CampusApp 的 lazy bootstrap（继承 ``BaseService``）
    - ``with_reauth`` 在 SessionExpired 时自动重 bootstrap
    - dataclass 返回（与 sdk.info 一致；不额外再包一层 ``Listing[T]`` —— info 域
      没有 "学期+课程" 概念，纯粹的单值返回）
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..config import profiles
from ..core.apps import (
    INFO_PORTAL,
    TIMETABLE_BKS,
    TIMETABLE_YJS,
    TRANSCRIPT_BKS,
    TRANSCRIPT_YJS,
)
from ..core.realms import WEBVPN_REALM
from ..sdk.auth import AuthInteraction, AuthNetwork, AuthPolicy
from ..sdk.info import Calendar, InfoClient, TimetableEvent, Transcript, TranscriptCourse
from .base import BaseService


class InfoService(BaseService):
    """Webvpn-backed 信息门户 + zhjw 客户端。SessionExpired 自动重试一次。"""

    # ---------------- calendar ----------------
    def get_calendar(
        self,
        user: str | None = None,
        *,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> Calendar:
        def call(force_login: bool) -> Calendar:
            selected, sso = self.ensure_sso(
                user,
                realms=(WEBVPN_REALM,),
                interaction=interaction,
                network=network,
                policy=policy,
                force_login=force_login,
            )
            self.ensure_app_and_save(selected, sso, INFO_PORTAL,
                                     interaction=interaction, policy=policy)
            return InfoClient(sso).get_calendar()

        return self.with_reauth(call)

    # ---------------- transcript ----------------
    def get_transcript(
        self,
        user: str | None = None,
        *,
        graduate: bool | None = None,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> list[TranscriptCourse]:
        graduate = self._resolve_graduate(user, graduate)
        app = TRANSCRIPT_YJS if graduate else TRANSCRIPT_BKS

        def call(force_login: bool) -> list[TranscriptCourse]:
            selected, sso = self.ensure_sso(
                user,
                realms=(WEBVPN_REALM,),
                interaction=interaction,
                network=network,
                policy=policy,
                force_login=force_login,
            )
            self.ensure_app_and_save(selected, sso, app, interaction=interaction, policy=policy)
            return InfoClient(sso).get_transcript(graduate=graduate)

        return self.with_reauth(call)

    def get_transcript_detail(
        self,
        user: str | None = None,
        *,
        graduate: bool | None = None,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> Transcript:
        graduate = self._resolve_graduate(user, graduate)
        app = TRANSCRIPT_YJS if graduate else TRANSCRIPT_BKS

        def call(force_login: bool) -> Transcript:
            selected, sso = self.ensure_sso(
                user,
                realms=(WEBVPN_REALM,),
                interaction=interaction,
                network=network,
                policy=policy,
                force_login=force_login,
            )
            self.ensure_app_and_save(selected, sso, app, interaction=interaction, policy=policy)
            return InfoClient(sso).get_transcript_detail(graduate=graduate)

        return self.with_reauth(call)

    # ---------------- timetable ----------------
    def get_timetable(
        self,
        user: str | None = None,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        graduate: bool | None = None,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> list[TimetableEvent]:
        """``start_date`` / ``end_date`` 任一为 None 时默认本学期；调一次 calendar 取范围。"""
        graduate = self._resolve_graduate(user, graduate)
        app = TIMETABLE_YJS if graduate else TIMETABLE_BKS
        need_calendar = start_date is None or end_date is None

        def call(force_login: bool) -> list[TimetableEvent]:
            nonlocal start_date, end_date
            selected, sso = self.ensure_sso(
                user,
                realms=(WEBVPN_REALM,),
                interaction=interaction,
                network=network,
                policy=policy,
                force_login=force_login,
            )
            if need_calendar:
                self.ensure_app_and_save(selected, sso, INFO_PORTAL,
                                         interaction=interaction, policy=policy)
                cal = InfoClient(sso).get_calendar()
                if start_date is None:
                    start_date = cal.first_day
                if end_date is None:
                    first = datetime.strptime(cal.first_day, "%Y-%m-%d")
                    last = first + timedelta(days=7 * cal.week_count - 1)
                    end_date = last.strftime("%Y-%m-%d")
            self.ensure_app_and_save(selected, sso, app, interaction=interaction, policy=policy)
            return InfoClient(sso).get_timetable(start_date, end_date, graduate=graduate)

        return self.with_reauth(call)

    # ---------------- internal ----------------
    def _resolve_graduate(self, user: str | None, graduate: bool | None) -> bool:
        """``graduate=None`` 时按 profile 的 student-type 决定（默认 undergraduate）。"""
        if graduate is not None:
            return graduate
        selected = self._resolve_user(user)
        return profiles.get_student_type(selected) == "graduate"


__all__ = ["InfoService"]

