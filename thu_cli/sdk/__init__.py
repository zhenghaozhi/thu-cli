"""``sdk`` — 协议引擎层。把清华各内网协议变成 Python 对象。

只依赖 ``core`` + ``requests`` + ``beautifulsoup4`` + ``gmssl``。**不**依赖 services /
config / cli。外部 SDK 用户最少只要拷 ``core/`` + ``sdk/`` 两个目录即可独立运行。

公共对象：
    SsoSession                 SSO 会话；管理 cookies / 多 realm / 多 app bootstrap
    Device                     设备指纹（持久化在 device.json）
    AuthInteraction            五个交互回调的容器（密码/2FA/验证码/信任设备）
    AuthNetwork / AuthPolicy   网络选项 / 登录策略
    LearnClient(sso)           网络学堂客户端 + dataclass
    InfoClient(sso)            信息门户 + zhjw 客户端 + dataclass
    RemoteFile                 通用 "远端可下载文件" 对象
"""
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
