"""Python CLI and SDK for Tsinghua SSO, Web Learning, and info portal."""
from __future__ import annotations

from .core.errors import (
    AuthError,
    BadCredentials,
    CaptchaRequired,
    LearnError,
    LearnFailReason,
    SessionExpired,
    ThuCliError,
    TwoFactorFailed,
    TwoFactorPending,
)
from .sdk.auth import (
    AuthInteraction,
    AuthNetwork,
    AuthPolicy,
    Device,
    SsoSession,
)
from .sdk.info import (
    Calendar,
    InfoClient,
    TimetableEvent,
    Transcript,
    TranscriptCourse,
    TranscriptSummary,
)
from .sdk.learn import (
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
from .sdk.transport import RemoteFile
from .services.auth import AuthService
from .services.base import BaseService, CourseScopedListing, Listing, ServiceWarning
from .services.info import InfoService
from .services.learn import LearnService

__all__ = [
    "Announcement",
    "AnnouncementAttachment",
    "AnsweredQuestion",
    "AuthError",
    "AuthInteraction",
    "AuthNetwork",
    "AuthPolicy",
    "AuthService",
    "BadCredentials",
    "BaseService",
    "Calendar",
    "CaptchaRequired",
    "ContentKind",
    "Course",
    "CourseContentBundle",
    "CourseFile",
    "CourseScopedListing",
    "Device",
    "Discussion",
    "FileCategory",
    "Homework",
    "InfoClient",
    "InfoService",
    "LearnClient",
    "LearnError",
    "LearnFailReason",
    "LearnService",
    "Listing",
    "Questionnaire",
    "QuestionnaireOption",
    "QuestionnaireQuestion",
    "RemoteFile",
    "SemesterInfo",
    "ServiceWarning",
    "SessionExpired",
    "SsoSession",
    "ThuCliError",
    "TimetableEvent",
    "Transcript",
    "TranscriptCourse",
    "TranscriptSummary",
    "TwoFactorFailed",
    "TwoFactorPending",
    "UserInfo",
]
__version__ = "0.2.0"
