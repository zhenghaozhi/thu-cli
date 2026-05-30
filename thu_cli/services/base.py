"""跨服务共享的应用层基础设施：``BaseService`` + ``Listing[T]`` + ``with_reauth``。

依赖方向：``services`` → ``sdk`` + ``config``；不反向。具体 service 继承 ``BaseService``。
"""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Generic, TypeVar

from ..config import profiles
from ..core.apps import CampusApp
from ..core.errors import SessionExpired
from ..core.realms import LEARN_REALM, Realm
from ..sdk.auth import (
    AuthInteraction,
    AuthNetwork,
    AuthPolicy,
    Device,
    SsoSession,
)

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True)
class ServiceWarning:
    """跨服务通用 warning。

    ``context`` 是失败上下文标识（learn 通常是 course_id；info/sports 可以是各自实体 id）；
    ``message`` 是给人看的描述。
    """
    context: str
    message: str


@dataclass(frozen=True)
class Listing(Generic[T]):
    """通用 listing：``user`` + ``items`` + ``warnings`` 三段。

    info / sports / cloud / git 这些无 "学期+课程" 概念的服务用这个；learn 用更
    具体的 ``CourseScopedListing[T]``。
    """
    user: str
    items: list[T]
    warnings: list[ServiceWarning] = field(default_factory=list)


@dataclass(frozen=True)
class CourseScopedListing(Generic[T]):
    """learn 专属 listing：在 ``user/items/warnings`` 之上额外带 ``semester`` / ``courses``。

    用**组合**而不是继承自 ``Listing[T]`` — 通用 Listing 不应该被 learn 语义污染。
    需要把它当 ``Listing[T]`` 用时调 ``as_listing()``。
    """
    user: str
    semester: str
    courses: list  # list[Course]；避免在 base 引入 learn 类型
    items: list[T]
    warnings: list[ServiceWarning] = field(default_factory=list)

    def as_listing(self) -> Listing[T]:
        return Listing(user=self.user, items=list(self.items), warnings=list(self.warnings))

    def course_by_id(self) -> dict[str, Any]:
        return {course.id: course for course in self.courses}

    def by_course(self) -> dict[str, list[T]]:
        """按 ``course_id`` 把 items 分桶；要求每个 item 有 ``course_id`` 属性。"""
        grouped: dict[str, list[T]] = {course.id: [] for course in self.courses}
        for item in self.items:
            grouped.setdefault(getattr(item, "course_id", ""), []).append(item)
        return grouped


class BaseService:
    """所有 profile-aware service 共用的认证 / 并发 / 重试基础设施。

    具体 service 继承本类并直接用 ``ensure_sso`` / ``with_reauth`` / ``fanout_parallel``。
    """

    # ---------------- 路径 ----------------
    def captcha_path(self, user: str | None = None) -> Path:
        selected = self._resolve_user(user)
        return profiles.profile_paths(selected).captcha

    def _resolve_user(self, user: str | None) -> str:
        from ..core.errors import AuthError
        try:
            resolved = profiles.resolve_user(user)
        except ValueError as e:
            raise AuthError(str(e)) from e
        if not resolved:
            raise AuthError("no current profile")
        return resolved

    # ---------------- 认证（headless friendly） ----------------
    def ensure_sso(
        self,
        user: str | None = None,
        *,
        realms: tuple[Realm, ...] = (LEARN_REALM,),
        interaction: AuthInteraction | None = None,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
        force_login: bool = False,
    ) -> tuple[str, SsoSession]:
        """解析 profile 路径，load 缓存 session，按需 bootstrap requested realms。

        实现 SDK 用户可绕过本方法：直接 ``SsoSession(...)`` + ``ensure_realm(...)`` 即可。
        本方法仅是 CLI 用的便利层（profile + path resolution）。
        """
        selected = self._resolve_user(user)
        profiles.add_profile(selected, make_current=False)
        paths = profiles.profile_paths(selected)

        network = network or AuthNetwork()
        eff_policy = policy or AuthPolicy()
        if force_login and not eff_policy.force_login:
            eff_policy = replace(eff_policy, force_login=True)

        device = Device.load_or_create(paths.device)
        sso = SsoSession.load(
            paths.session,
            device=device,
            verify_tls=network.verify_tls,
            trust_env=network.trust_env,
            debug_dir=network.debug_dir,
            captcha_path=paths.captcha,
            on_event=network.on_event,
        )
        if sso is None or sso.username != selected or eff_policy.force_login:
            sso = SsoSession(
                device=device,
                verify_tls=network.verify_tls,
                trust_env=network.trust_env,
                debug_dir=network.debug_dir,
                captcha_path=paths.captcha,
                on_event=network.on_event,
            )
            sso.username = selected

        for realm in realms:
            sso.ensure_realm(realm, interaction=interaction, policy=eff_policy)

        sso.save(paths.session)
        return selected, sso

    def ensure_app_and_save(
        self,
        selected: str,
        sso: SsoSession,
        app: CampusApp,
        *,
        interaction: AuthInteraction | None = None,
        policy: AuthPolicy | None = None,
    ) -> None:
        """Bootstrap 一个 CampusApp 并持久化 cookies + 时间戳。"""
        sso.ensure_app(app, interaction=interaction, policy=policy)
        sso.save(profiles.profile_paths(selected).session)

    # ---------------- 重试 ----------------
    def with_reauth(
        self,
        call: Callable[[bool], T],
        *,
        safe_to_retry: bool = True,
    ) -> T:
        """先 ``call(False)``；遇 ``SessionExpired`` 则 ``call(True)`` 重跑一次。

        - 读操作：默认 ``safe_to_retry=True``（什么都不传），自动重登重试。
        - 写操作：调用方应自己判断。如果 SDK 保证 ``SessionExpired`` 只会在副作用 POST
          之前抛（thu-cli 目前所有 sdk.learn 写路径都满足），传 True 安全；如果存在
          "请求已发出但响应解析失败" 的可能，必须 ``safe_to_retry=False``。

        ``call(force_login)`` 应自己组装 ``AuthPolicy(force_login=...)`` 或透传给
        ``ensure_sso(force_login=...)``。
        """
        try:
            return call(False)
        except SessionExpired:
            if not safe_to_retry:
                raise
            return call(True)

    # ---------------- 跨实体 fanout（默认串行） ----------------
    def fanout_parallel(
        self,
        entities: list[E],
        fetch: Callable[[E], list[T]],
        *,
        context_of: Callable[[E], str],
        label_of: Callable[[E], str] | None = None,
        allow_failure: bool = True,
        max_workers: int = 1,
    ) -> tuple[list[T], list[ServiceWarning]]:
        """对 entities 跑 fetch；单元素失败收成 ``ServiceWarning``。

        **默认串行（``max_workers=1``）**。``requests.Session`` 不是 fully thread-safe
        （cookies / headers / redirect cache 是共享可变状态），跨课程共享同一个
        ``SsoSession.http`` 在 ``max_workers>1`` 下可能出现偶发竞态。调用方可以显式
        传 ``max_workers=N`` 来 opt-in 并发，前提是自己已确认或不在乎这个风险。

        ``SessionExpired`` 不计入 warning，直接透传 — 上层 ``with_reauth`` 负责重试。
        """
        if not entities:
            return [], []
        worker_count = max(1, min(max_workers, len(entities)))
        items: list[T] = []
        warnings: list[ServiceWarning] = []
        if worker_count == 1:
            # 串行路径：跳过 ThreadPoolExecutor，避免每条命令都付线程开销
            for entity in entities:
                try:
                    items.extend(fetch(entity))
                except SessionExpired:
                    raise
                except Exception as e:
                    if not allow_failure:
                        raise
                    label = label_of(entity) if label_of else context_of(entity)
                    warnings.append(ServiceWarning(context_of(entity), f"{label}: {e}"))
            return items, warnings
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(fetch, entity): entity for entity in entities}
            for future in as_completed(futures):
                entity = futures[future]
                try:
                    items.extend(future.result())
                except SessionExpired:
                    raise
                except Exception as e:
                    if not allow_failure:
                        raise
                    label = label_of(entity) if label_of else context_of(entity)
                    warnings.append(ServiceWarning(context_of(entity), f"{label}: {e}"))
        return items, warnings


__all__ = [
    "BaseService",
    "CourseScopedListing",
    "Listing",
    "ServiceWarning",
]
