"""Shared service infrastructure."""
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
    """Warning collected while fetching one item in a fanout."""
    context: str
    message: str


@dataclass(frozen=True)
class Listing(Generic[T]):
    """Generic listing shape for services without course scope."""
    user: str
    items: list[T]
    warnings: list[ServiceWarning] = field(default_factory=list)


@dataclass(frozen=True)
class CourseScopedListing(Generic[T]):
    """Listing shape for Web Learning data scoped by semester and course."""
    user: str
    semester: str
    courses: list
    items: list[T]
    warnings: list[ServiceWarning] = field(default_factory=list)

    def as_listing(self) -> Listing[T]:
        return Listing(user=self.user, items=list(self.items), warnings=list(self.warnings))

    def course_by_id(self) -> dict[str, Any]:
        return {course.id: course for course in self.courses}

    def by_course(self) -> dict[str, list[T]]:
        """Group items by their ``course_id`` attribute."""
        grouped: dict[str, list[T]] = {course.id: [] for course in self.courses}
        for item in self.items:
            grouped.setdefault(getattr(item, "course_id", ""), []).append(item)
        return grouped


class BaseService:
    """Authentication, retry, and fanout helpers for profile-aware services."""

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
        """Resolve profile paths, load cached session, and bootstrap realms."""
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
        """Bootstrap one CampusApp and persist cookies/timestamps."""
        sso.ensure_app(app, interaction=interaction, policy=policy)
        sso.save(profiles.profile_paths(selected).session)

    def with_reauth(
        self,
        call: Callable[[bool], T],
        *,
        safe_to_retry: bool = True,
    ) -> T:
        """Run once, reauth on ``SessionExpired``, then retry when safe."""
        try:
            return call(False)
        except SessionExpired:
            if not safe_to_retry:
                raise
            return call(True)

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
        """Fetch each entity, collecting per-entity failures as warnings."""
        if not entities:
            return [], []
        worker_count = max(1, min(max_workers, len(entities)))
        items: list[T] = []
        warnings: list[ServiceWarning] = []
        if worker_count == 1:
            # Avoid thread overhead for the default serial path.
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
