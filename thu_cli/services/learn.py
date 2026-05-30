"""Profile-aware Web Learning use cases."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.errors import SessionExpired
from ..sdk.auth import AuthInteraction, AuthNetwork, AuthPolicy
from ..sdk.learn import (
    Announcement,
    AnsweredQuestion,
    ContentKind,
    Course,
    CourseContentBundle,
    CourseFile,
    Discussion,
    FileCategory,
    Homework,
    LearnClient,
    Questionnaire,
    UserInfo,
    semester_from_course_id,
)
from .base import (
    BaseService,
    CourseScopedListing,
    ServiceWarning,
)

AnnouncementListing = CourseScopedListing[Announcement]
CourseFileListing = CourseScopedListing[CourseFile]
DiscussionListing = CourseScopedListing[Discussion]
FileCategoryListing = CourseScopedListing[FileCategory]
HomeworkListing = CourseScopedListing[Homework]
QuestionListing = CourseScopedListing[AnsweredQuestion]
QuestionnaireListing = CourseScopedListing[Questionnaire]


@dataclass(frozen=True)
class CourseListing:
    """Course listing where the payload is already the course list."""
    user: str
    semester: str
    courses: list[Course]
    warnings: list[ServiceWarning] = field(default_factory=list)


@dataclass(frozen=True)
class UserInfoResult:
    user: str
    info: UserInfo


@dataclass(frozen=True)
class AnnouncementDetail:
    user: str
    semester: str
    courses: list[Course]
    announcement: Announcement | None
    warnings: list[ServiceWarning] = field(default_factory=list)


@dataclass(frozen=True)
class ContentListing:
    user: str
    semester: str
    courses: list[Course]
    bundles: list[CourseContentBundle]
    warnings: list[ServiceWarning] = field(default_factory=list)

    def by_course(self) -> dict[str, CourseContentBundle]:
        return {bundle.course_id: bundle for bundle in self.bundles}

    def flattened(self) -> list[tuple[str, Any]]:
        rows: list[tuple[str, Any]] = []
        for bundle in self.bundles:
            for kind, items in bundle.contents.items():
                rows.extend((kind.value, item) for item in items)
        return rows


@dataclass(frozen=True)
class DownloadResult:
    user: str
    path: Path
    source_name: str


@dataclass(frozen=True)
class HomeworkSubmitResult:
    user: str
    homework_id: str
    content_length: int
    attachment: Path | None
    remove_attachment: bool


class LearnService(BaseService):
    """Student-side Web Learning service."""

    def user_info(
        self,
        user: str | None = None,
        *,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> UserInfoResult:
        def call(force_login: bool) -> UserInfoResult:
            selected, sso = self.ensure_sso(
                user, interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            return UserInfoResult(selected, LearnClient(sso).user_info())

        return self.with_reauth(call)

    def list_courses(
        self,
        user: str | None = None,
        *,
        semester: str | None = None,
        all_terms: bool = False,
        include_time_locations: bool = False,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> CourseListing:
        def call(force_login: bool) -> CourseListing:
            selected, sso = self.ensure_sso(
                user, interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            client = LearnClient(sso)
            if all_terms:
                return CourseListing(
                    selected, "all",
                    client.list_courses(
                        all_terms=True,
                        include_time_locations=include_time_locations,
                    ),
                )
            sid = semester or client.current_semester()
            return CourseListing(
                selected, sid,
                client.list_courses(semester=sid, include_time_locations=include_time_locations),
            )

        return self.with_reauth(call)

    def list_announcements(
        self,
        user: str | None = None,
        *,
        semester: str | None = None,
        all_terms: bool = False,
        course_id: str | None = None,
        unread_only: bool = False,
        include_content: bool = False,
        allow_failure: bool = True,
        max_workers: int = 1,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> AnnouncementListing:
        def call(force_login: bool) -> AnnouncementListing:
            selected, sso = self.ensure_sso(
                user, interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            client = LearnClient(sso)
            label, courses = self._resolve_courses(
                client, semester=semester, all_terms=all_terms, course_id=course_id,
            )
            if include_content:
                items, warnings = self.fanout_parallel(
                    courses,
                    lambda c: client.list_course_announcements(c.id, course=c),
                    context_of=lambda c: c.id,
                    label_of=lambda c: c.name or c.id,
                    allow_failure=allow_failure,
                    max_workers=max_workers,
                )
                if unread_only:
                    items = [a for a in items if a.unread is not False]
                items.sort(key=lambda a: a.published_at, reverse=True)
            else:
                items = client.list_announcement_summaries(
                    [c.id for c in courses], unread_only=unread_only,
                )
                warnings = []
            return AnnouncementListing(selected, label, courses, items, warnings)

        return self.with_reauth(call)

    def get_announcement(
        self,
        user: str | None,
        announcement_id: str,
        *,
        semester: str | None = None,
        all_terms: bool = False,
        course_id: str | None = None,
        include_attachments: bool = False,
        allow_failure: bool = True,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> AnnouncementDetail:
        def call(force_login: bool) -> AnnouncementDetail:
            selected, sso = self.ensure_sso(
                user, interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            client = LearnClient(sso)
            label, courses = self._resolve_courses(
                client, semester=semester, all_terms=all_terms, course_id=course_id,
            )
            warnings: list[ServiceWarning] = []
            for course in courses:
                try:
                    announcement = client.get_announcement(
                        course.id, announcement_id, course=course,
                        include_attachments=include_attachments,
                    )
                except SessionExpired:
                    raise
                except Exception as e:
                    if not allow_failure:
                        raise
                    warnings.append(ServiceWarning(course.id, f"{course.name or course.id}: {e}"))
                    continue
                if announcement:
                    return AnnouncementDetail(selected, label, courses, announcement, warnings)
            return AnnouncementDetail(selected, label, courses, None, warnings)

        return self.with_reauth(call)

    def list_files(
        self,
        user: str | None = None,
        *,
        semester: str | None = None,
        all_terms: bool = False,
        course_id: str | None = None,
        category_id: str | None = None,
        allow_failure: bool = True,
        max_workers: int = 1,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> CourseFileListing:
        if category_id and not course_id:
            raise ValueError("category_id requires course_id")

        def call(force_login: bool) -> CourseFileListing:
            selected, sso = self.ensure_sso(
                user, interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            client = LearnClient(sso)
            label, courses = self._resolve_courses(
                client, semester=semester, all_terms=all_terms, course_id=course_id,
            )
            items, warnings = self.fanout_parallel(
                courses,
                lambda c: client.list_course_files(c.id, course=c, category_id=category_id),
                context_of=lambda c: c.id,
                label_of=lambda c: c.name or c.id,
                allow_failure=allow_failure,
                max_workers=max_workers,
            )
            items.sort(key=lambda item: item.uploaded_at, reverse=True)
            return CourseFileListing(selected, label, courses, items, warnings)

        return self.with_reauth(call)

    def list_file_categories(
        self,
        user: str | None = None,
        *,
        semester: str | None = None,
        all_terms: bool = False,
        course_id: str | None = None,
        allow_failure: bool = True,
        max_workers: int = 1,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> FileCategoryListing:
        def call(force_login: bool) -> FileCategoryListing:
            selected, sso = self.ensure_sso(
                user, interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            client = LearnClient(sso)
            label, courses = self._resolve_courses(
                client, semester=semester, all_terms=all_terms, course_id=course_id,
            )
            items, warnings = self.fanout_parallel(
                courses,
                lambda c: client.list_file_categories(c.id),
                context_of=lambda c: c.id,
                label_of=lambda c: c.name or c.id,
                allow_failure=allow_failure,
                max_workers=max_workers,
            )
            items.sort(key=lambda item: (item.course_id, item.created_at, item.title))
            return FileCategoryListing(selected, label, courses, items, warnings)

        return self.with_reauth(call)

    def list_homeworks(
        self,
        user: str | None = None,
        *,
        semester: str | None = None,
        all_terms: bool = False,
        course_id: str | None = None,
        include_detail: bool = False,
        allow_failure: bool = True,
        max_workers: int = 1,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> HomeworkListing:
        def call(force_login: bool) -> HomeworkListing:
            selected, sso = self.ensure_sso(
                user, interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            client = LearnClient(sso)
            label, courses = self._resolve_courses(
                client, semester=semester, all_terms=all_terms, course_id=course_id,
            )
            items, warnings = self.fanout_parallel(
                courses,
                lambda c: client.list_course_homeworks(c.id, course=c, include_detail=include_detail),
                context_of=lambda c: c.id,
                label_of=lambda c: c.name or c.id,
                allow_failure=allow_failure,
                max_workers=max_workers,
            )
            items.sort(key=lambda item: item.deadline)
            return HomeworkListing(selected, label, courses, items, warnings)

        return self.with_reauth(call)

    def list_discussions(
        self,
        user: str | None = None,
        *,
        semester: str | None = None,
        all_terms: bool = False,
        course_id: str | None = None,
        allow_failure: bool = True,
        max_workers: int = 1,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> DiscussionListing:
        def call(force_login: bool) -> DiscussionListing:
            selected, sso = self.ensure_sso(
                user, interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            client = LearnClient(sso)
            label, courses = self._resolve_courses(
                client, semester=semester, all_terms=all_terms, course_id=course_id,
            )
            items, warnings = self.fanout_parallel(
                courses,
                lambda c: client.list_course_discussions(c.id, course=c),
                context_of=lambda c: c.id,
                label_of=lambda c: c.name or c.id,
                allow_failure=allow_failure,
                max_workers=max_workers,
            )
            items.sort(key=lambda item: item.last_replied_at, reverse=True)
            return DiscussionListing(selected, label, courses, items, warnings)

        return self.with_reauth(call)

    def list_questions(
        self,
        user: str | None = None,
        *,
        semester: str | None = None,
        all_terms: bool = False,
        course_id: str | None = None,
        allow_failure: bool = True,
        max_workers: int = 1,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> QuestionListing:
        def call(force_login: bool) -> QuestionListing:
            selected, sso = self.ensure_sso(
                user, interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            client = LearnClient(sso)
            label, courses = self._resolve_courses(
                client, semester=semester, all_terms=all_terms, course_id=course_id,
            )
            items, warnings = self.fanout_parallel(
                courses,
                lambda c: client.list_answered_questions(c.id, course=c),
                context_of=lambda c: c.id,
                label_of=lambda c: c.name or c.id,
                allow_failure=allow_failure,
                max_workers=max_workers,
            )
            items.sort(key=lambda item: item.last_replied_at, reverse=True)
            return QuestionListing(selected, label, courses, items, warnings)

        return self.with_reauth(call)

    def list_questionnaires(
        self,
        user: str | None = None,
        *,
        semester: str | None = None,
        all_terms: bool = False,
        course_id: str | None = None,
        include_detail: bool = False,
        allow_failure: bool = True,
        max_workers: int = 1,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> QuestionnaireListing:
        def call(force_login: bool) -> QuestionnaireListing:
            selected, sso = self.ensure_sso(
                user, interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            client = LearnClient(sso)
            label, courses = self._resolve_courses(
                client, semester=semester, all_terms=all_terms, course_id=course_id,
            )
            items, warnings = self.fanout_parallel(
                courses,
                lambda c: client.list_questionnaires(c.id, course=c, include_detail=include_detail),
                context_of=lambda c: c.id,
                label_of=lambda c: c.name or c.id,
                allow_failure=allow_failure,
                max_workers=max_workers,
            )
            items.sort(key=lambda item: item.end_at, reverse=True)
            return QuestionnaireListing(selected, label, courses, items, warnings)

        return self.with_reauth(call)

    def list_contents(
        self,
        user: str | None = None,
        *,
        semester: str | None = None,
        all_terms: bool = False,
        course_id: str | None = None,
        kinds: list[ContentKind | str] | None = None,
        include_homework_detail: bool = False,
        include_questionnaire_detail: bool = False,
        allow_failure: bool = True,
        max_workers: int = 1,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> ContentListing:
        def call(force_login: bool) -> ContentListing:
            selected, sso = self.ensure_sso(
                user, interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            client = LearnClient(sso)
            label, courses = self._resolve_courses(
                client, semester=semester, all_terms=all_terms, course_id=course_id,
            )
            bundles, warnings = self.fanout_parallel(
                courses,
                lambda c: [
                    client.list_course_contents(
                        c.id, course=c, kinds=kinds,
                        include_homework_detail=include_homework_detail,
                        include_questionnaire_detail=include_questionnaire_detail,
                    )
                ],
                context_of=lambda c: c.id,
                label_of=lambda c: c.name or c.id,
                allow_failure=allow_failure,
                max_workers=max_workers,
            )
            return ContentListing(selected, label, courses, bundles, warnings)

        return self.with_reauth(call)

    def download_course_file(
        self,
        user: str | None,
        file_id: str,
        *,
        course_id: str | None = None,
        semester: str | None = None,
        all_terms: bool = False,
        dest_dir: str | Path = "downloads",
        allow_failure: bool = True,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> DownloadResult:
        def call(force_login: bool) -> DownloadResult:
            selected, sso = self.ensure_sso(
                user, interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            client = LearnClient(sso)
            _, courses = self._resolve_courses(
                client, semester=semester, all_terms=all_terms, course_id=course_id,
            )
            for course in courses:
                try:
                    item = client.get_course_file(course.id, file_id, course=course)
                except SessionExpired:
                    raise
                except Exception:
                    if not allow_failure:
                        raise
                    continue
                if item:
                    path = client.download_remote_file(item.remote_file, dest_dir)
                    return DownloadResult(selected, path, item.title)
            raise FileNotFoundError(file_id)

        return self.with_reauth(call)

    def download_announcement_attachments(
        self,
        user: str | None,
        announcement_id: str,
        *,
        course_id: str | None = None,
        semester: str | None = None,
        all_terms: bool = False,
        dest_dir: str | Path = "downloads",
        allow_failure: bool = True,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> list[DownloadResult]:
        def call(force_login: bool) -> list[DownloadResult]:
            selected, sso = self.ensure_sso(
                user, interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            client = LearnClient(sso)
            _, courses = self._resolve_courses(
                client, semester=semester, all_terms=all_terms, course_id=course_id,
            )
            for course in courses:
                try:
                    announcement = client.get_announcement(
                        course.id, announcement_id, course=course, include_attachments=True,
                    )
                except SessionExpired:
                    raise
                except Exception:
                    if not allow_failure:
                        raise
                    continue
                if announcement:
                    results: list[DownloadResult] = []
                    for f in announcement.attachments:
                        path = client.download_remote_file(f, dest_dir)
                        results.append(DownloadResult(selected, path, f.name))
                    return results
            raise FileNotFoundError(announcement_id)

        return self.with_reauth(call)

    def download_homework_files(
        self,
        user: str | None,
        homework_id: str,
        *,
        course_id: str | None = None,
        semester: str | None = None,
        all_terms: bool = False,
        dest_dir: str | Path = "downloads",
        allow_failure: bool = True,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> list[DownloadResult]:
        def call(force_login: bool) -> list[DownloadResult]:
            selected, sso = self.ensure_sso(
                user, interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            client = LearnClient(sso)
            _, courses = self._resolve_courses(
                client, semester=semester, all_terms=all_terms, course_id=course_id,
            )
            for course in courses:
                try:
                    homework = client.get_homework(
                        course.id, homework_id, course=course, include_detail=True,
                    )
                except SessionExpired:
                    raise
                except Exception:
                    if not allow_failure:
                        raise
                    continue
                if homework:
                    results: list[DownloadResult] = []
                    for f in homework.downloadable_files():
                        path = client.download_remote_file(f, dest_dir)
                        results.append(DownloadResult(selected, path, f.name))
                    return results
            raise FileNotFoundError(homework_id)

        return self.with_reauth(call)

    def submit_homework(
        self,
        user: str | None,
        homework_id: str,
        *,
        content: str = "",
        attachment: str | Path | None = None,
        remove_attachment: bool = False,
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
    ) -> HomeworkSubmitResult:
        """Submit homework without automatic retry after auth loss."""
        def call(force_login: bool) -> HomeworkSubmitResult:
            selected, sso = self.ensure_sso(
                user, interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            client = LearnClient(sso)
            client.submit_homework(
                homework_id, content=content, attachment=attachment,
                remove_attachment=remove_attachment,
            )
            return HomeworkSubmitResult(
                user=selected,
                homework_id=homework_id,
                content_length=len(content),
                attachment=Path(attachment) if attachment else None,
                remove_attachment=remove_attachment,
            )

        return self.with_reauth(call, safe_to_retry=False)

    def _resolve_courses(
        self,
        client: LearnClient,
        *,
        semester: str | None,
        all_terms: bool,
        course_id: str | None,
    ) -> tuple[str, list[Course]]:
        if semester and all_terms:
            raise ValueError("semester and all_terms are mutually exclusive")
        if course_id and not semester and not all_terms:
            semester = semester_from_course_id(course_id)
        if all_terms:
            label = "all"
            courses = client.list_courses(all_terms=True)
        else:
            label = semester or client.current_semester()
            courses = client.list_courses(semester=label)
        if course_id:
            courses = [c for c in courses if c.id == course_id]
        return label, courses


__all__ = [
    "AnnouncementDetail",
    "AnnouncementListing",
    "ContentListing",
    "CourseFileListing",
    "CourseListing",
    "DiscussionListing",
    "DownloadResult",
    "FileCategoryListing",
    "HomeworkListing",
    "HomeworkSubmitResult",
    "LearnService",
    "QuestionListing",
    "QuestionnaireListing",
    "UserInfoResult",
]
