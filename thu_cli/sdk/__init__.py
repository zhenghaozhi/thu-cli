"""Protocol-engine layer for Tsinghua services."""
from __future__ import annotations

from .auth import (
    AuthInteraction,
    AuthNetwork,
    AuthPolicy,
    Device,
    SsoSession,
    dump_cookies,
    load_cookies,
)
from .info import (
    Calendar,
    InfoClient,
    TimetableEvent,
    Transcript,
    TranscriptCourse,
    TranscriptSummary,
)
from .learn import (
    Announcement,
    AnnouncementAttachment,
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
    QuestionnaireOption,
    QuestionnaireQuestion,
    SemesterInfo,
    UserInfo,
)
from .transport import (
    RemoteFile,
    csrf_params,
    json_or_expired,
    raise_if_unauthenticated,
    stream_download,
)

__all__ = [
    "Announcement", "AnnouncementAttachment", "AnsweredQuestion",
    "AuthInteraction", "AuthNetwork", "AuthPolicy",
    "Calendar", "ContentKind", "Course", "CourseContentBundle", "CourseFile",
    "Device", "Discussion", "FileCategory", "Homework",
    "InfoClient", "LearnClient",
    "Questionnaire", "QuestionnaireOption", "QuestionnaireQuestion",
    "RemoteFile", "SemesterInfo", "SsoSession",
    "TimetableEvent", "Transcript", "TranscriptCourse", "TranscriptSummary",
    "UserInfo",
    # extension-author helpers — useful when writing new clients on top of SsoSession
    "csrf_params", "dump_cookies", "json_or_expired", "load_cookies",
    "raise_if_unauthenticated", "stream_download",
]
