"""``services`` — 业务编排层。在 ``sdk`` 之上叠加：

    - profile / 路径解析（依赖 ``config``）
    - ``SsoSession`` lazy bootstrap + 自动重登
    - 跨课程并发 fanout + warning 收集
    - 统一返回形状 ``Listing[T]`` / ``CourseScopedListing[T]``

只被 ``cli`` 引用；``sdk`` 不依赖本层（架构约束，``tests/architecture.py`` 钉死）。

外部 SDK 用户若不需要这些便利，可以跳过本层直接构造 ``SsoSession`` + ``XxxClient``。

公开接口：
    BaseService                共用 ensure_sso / with_reauth / fanout_parallel
    Listing / CourseScopedListing / ServiceWarning
    AuthService                profile / 登录用例
    LearnService               网络学堂业务服务
    InfoService                信息门户业务服务
"""
from __future__ import annotations

from .auth import (
    AuthHint,
    AuthService,
    AuthStatus,
    FileState,
    LocalAuthState,
    LoginResult,
    LogoutResult,
    ProfileRow,
    RemoteServiceState,
)
from .base import (
    BaseService,
    CourseScopedListing,
    Listing,
    ServiceWarning,
)
from .info import InfoService
from .learn import (
    AnnouncementDetail,
    AnnouncementListing,
    ContentListing,
    CourseFileListing,
    CourseListing,
    DiscussionListing,
    DownloadResult,
    FileCategoryListing,
    HomeworkListing,
    HomeworkSubmitResult,
    LearnService,
    QuestionListing,
    QuestionnaireListing,
    UserInfoResult,
)

__all__ = [
    "AnnouncementDetail",
    "AnnouncementListing",
    "AuthHint",
    "AuthService",
    "AuthStatus",
    "BaseService",
    "ContentListing",
    "CourseFileListing",
    "CourseListing",
    "CourseScopedListing",
    "DiscussionListing",
    "DownloadResult",
    "FileCategoryListing",
    "FileState",
    "HomeworkListing",
    "HomeworkSubmitResult",
    "InfoService",
    "LearnService",
    "Listing",
    "LocalAuthState",
    "LoginResult",
    "LogoutResult",
    "ProfileRow",
    "QuestionListing",
    "QuestionnaireListing",
    "RemoteServiceState",
    "ServiceWarning",
    "UserInfoResult",
]
