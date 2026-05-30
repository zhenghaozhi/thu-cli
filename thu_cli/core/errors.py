"""所有异常类，集中在 core 层以便上层统一 catch。

层级：

    ThuCliError                  根
    ├─ AuthError                 任何认证 / 协议失败的基类
    │   ├─ BadCredentials        账号或密码错（用户应重输账密）
    │   ├─ CaptchaRequired       需要图形验证码且未提供 on_captcha
    │   ├─ SessionExpired        cookie 失效（service 层 with_reauth 自动重试）
    │   ├─ TwoFactorPending      2FA 已发送，等用户输验证码（两阶段登录使用）
    │   └─ TwoFactorFailed       验证码错或过期
    └─ LearnError                网络学堂域错误（解析失败 / 操作失败）

CLI 层只 catch ``ThuCliError`` 一次顶层，按类型映射 exit code 与文案。
"""
from __future__ import annotations

from enum import Enum


class ThuCliError(Exception):
    """所有 thu-cli 业务异常的根。第三方 catch 这一个即可。"""


# ---------------- auth 域 ----------------
class AuthError(ThuCliError):
    """认证/协议失败的基类。未知失败也走这里。"""


class BadCredentials(AuthError):
    """账号或密码错；调用方应重新提示用户输账密。"""


class TwoFactorFailed(AuthError):
    """2FA 验证码不对或过期；调用方应重新提示用户输码（不重发）。"""


class CaptchaRequired(AuthError):
    """需要图形验证码且未提供 ``on_captcha`` 回调。

    ``image_bytes`` 是 captcha.jpg 字节流；CLI 可保存到本地再读。
    """

    def __init__(self, msg: str = "captcha required", *, image_bytes: bytes = b""):
        super().__init__(msg)
        self.image_bytes = image_bytes


class SessionExpired(AuthError):
    """已登录但 cookie 失效（运行中检测到）。

    Service 层 ``with_reauth`` 看到这个会触发一次重 bootstrap + 重试。
    """


class TwoFactorPending(AuthError):
    """2FA 验证码已发送；调用方决定如何 persist 和 resume 这个状态。

    用于两阶段登录：``thu auth login --stage send`` 抛出后由 CLI 写 stage.json，
    之后 ``thu auth login --stage verify --code XXXXXX`` 恢复。
    """

    def __init__(
        self,
        *,
        choice: str,
        cookies: list[dict],
        step_idx: int,
        debug_dir: str | None,
        realm_id: str = "learn",
    ) -> None:
        super().__init__(f"2FA pending: choice={choice}")
        self.choice = choice
        self.cookies = cookies
        self.step_idx = step_idx
        self.debug_dir = debug_dir
        self.realm_id = realm_id

    def to_dict(self) -> dict:
        return {
            "choice": self.choice,
            "cookies": self.cookies,
            "step_idx": self.step_idx,
            "debug_dir": self.debug_dir,
            "realm_id": self.realm_id,
        }


# ---------------- learn 域 ----------------
class LearnFailReason(str, Enum):
    INVALID_RESPONSE = "invalid_response"
    OPERATION_FAILED = "operation_failed"


class LearnError(ThuCliError):
    """学堂域错误。``reason`` 描述失败种类；``payload`` 是原始服务端响应（debug 用）。"""

    def __init__(
        self,
        reason: LearnFailReason,
        message: str | None = None,
        *,
        payload: object | None = None,
    ):
        self.reason = reason
        self.payload = payload
        super().__init__(message or reason.value)


__all__ = [
    "AuthError",
    "BadCredentials",
    "CaptchaRequired",
    "LearnError",
    "LearnFailReason",
    "SessionExpired",
    "ThuCliError",
    "TwoFactorFailed",
    "TwoFactorPending",
]
