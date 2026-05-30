"""Profile-aware authentication use cases."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import profiles
from ..config.profiles import normalize_user
from ..core.apps import (
    INFO_PORTAL,
    TIMETABLE_BKS,
    TIMETABLE_YJS,
    TRANSCRIPT_BKS,
    TRANSCRIPT_YJS,
    CampusApp,
)
from ..core.errors import AuthError, SessionExpired, TwoFactorPending
from ..core.realms import LEARN_REALM, REALMS, WEBVPN_REALM
from ..sdk.auth import (
    AuthInteraction,
    AuthNetwork,
    AuthPolicy,
    Device,
    SsoSession,
    load_cookies,
)


@dataclass(frozen=True)
class FileState:
    state: str
    detail: str | None = None

    @property
    def present(self) -> bool:
        return self.state == "present"

    def label(self) -> str:
        return f"{self.state} ({self.detail})" if self.detail else self.state


@dataclass(frozen=True)
class RemoteServiceState:
    name: str
    state: FileState


@dataclass(frozen=True)
class LocalAuthState:
    device: FileState
    session: FileState
    stage: FileState
    session_data: dict | None = None
    stage_data: dict | None = None


@dataclass(frozen=True)
class AuthHint:
    kind: str
    user: str | None = None


@dataclass(frozen=True)
class AuthStatus:
    current_user: str | None
    selected_user: str
    student_type: str
    device: FileState
    session: FileState
    stage: FileState
    remote: FileState
    remote_services: tuple[RemoteServiceState, ...]
    hint: AuthHint | None
    exit_code: int


@dataclass(frozen=True)
class ProfileRow:
    current: bool
    user: str
    student_type: str
    device: FileState
    session: FileState
    stage: FileState


@dataclass(frozen=True)
class LogoutResult:
    user: str
    removed: tuple[str, ...]
    device_kept: bool


@dataclass(frozen=True)
class LoginResult:
    user: str
    session_path: Path
    stage_pending: bool = False
    twofa_skipped: bool = False

def _read_json_object(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_json_object(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _student_apps(student_type: str) -> tuple[CampusApp, CampusApp]:
    if student_type == "graduate":
        return TRANSCRIPT_YJS, TIMETABLE_YJS
    return TRANSCRIPT_BKS, TIMETABLE_BKS


def _remote_service_names(student_type: str) -> tuple[str, ...]:
    transcript, timetable = _student_apps(student_type)
    return ("learn", "webvpn", "info", transcript.id, timetable.id)

class AuthService:
    """Bridge between local profiles and ``SsoSession``."""

    def resolve_user(self, user: str | None = None) -> str:
        try:
            resolved = profiles.resolve_user(user)
        except ValueError as e:
            raise AuthError(str(e)) from e
        if not resolved:
            raise AuthError("no current profile")
        return resolved

    def use_profile(self, user: str) -> str:
        return profiles.set_current_user(user)

    def add_profile(self, user: str, *, make_current: bool = False) -> str:
        return profiles.add_profile(user, make_current=make_current)

    def remove_profile(self, user: str, *, delete_data: bool = False) -> bool:
        return profiles.remove_profile(user, delete_data=delete_data)

    def list_profiles(self) -> list[str]:
        return profiles.list_profiles()

    def current_user(self) -> str | None:
        return profiles.get_current_user()

    def captcha_path(self, user: str | None = None) -> Path:
        return profiles.profile_paths(self.resolve_user(user)).captcha

    def get_student_type(self, user: str | None = None) -> str:
        return profiles.get_student_type(self.resolve_user(user))

    def set_student_type(self, user: str, student_type: str) -> None:
        profiles.set_student_type(normalize_user(user), student_type)

    def _prewarm_known_services(
        self,
        selected: str,
        sso: SsoSession,
        *,
        interaction: AuthInteraction | None,
        policy: AuthPolicy,
    ) -> None:
        """Best-effort bootstrap for read-only services supported today."""
        student_type = profiles.get_student_type(selected)
        transcript_app, timetable_app = _student_apps(student_type)
        session_path = profiles.profile_paths(selected).session

        steps: tuple[tuple[str, Any], ...] = (
            ("webvpn", lambda p: sso.ensure_realm(WEBVPN_REALM, interaction=interaction, policy=p)),
            ("info_portal", lambda p: sso.ensure_app(INFO_PORTAL, interaction=interaction, policy=p)),
            (transcript_app.id, lambda p: sso.ensure_app(transcript_app, interaction=interaction, policy=p)),
            (timetable_app.id, lambda p: sso.ensure_app(timetable_app, interaction=interaction, policy=p)),
        )

        sso.save(session_path)

        for name, fn in steps:
            try:
                fn(policy)
            except SessionExpired:
                try:
                    fn(replace(policy, force_login=True))
                except Exception as e:
                    if sso.on_event is not None:
                        sso.on_event("warning", f"prewarm {name} failed: {e}")
            except Exception as e:
                if sso.on_event is not None:
                    sso.on_event("warning", f"prewarm {name} skipped: {e}")
            sso.save(session_path)

    def local_auth_state(self, user: str) -> LocalAuthState:
        paths = profiles.profile_paths(user)
        session_data = _read_json_object(paths.session)
        stage_data = _read_json_object(paths.stage)

        device_state = FileState("present" if paths.device.exists() else "none")
        if session_data is not None:
            session_state = FileState("present", session_data.get("username") or "<unknown>")
        else:
            session_state = FileState("unreadable" if paths.session.exists() else "none")

        if stage_data is not None:
            user_label = stage_data.get("user") or "<unknown>"
            choice = stage_data.get("choice") or "<unknown>"
            stage_state = FileState("present", f"{user_label}, {choice}")
        else:
            stage_state = FileState("unreadable" if paths.stage.exists() else "none")

        return LocalAuthState(
            device=device_state,
            session=session_state,
            stage=stage_state,
            session_data=session_data,
            stage_data=stage_data,
        )

    def profile_rows(self) -> list[ProfileRow]:
        current = self.current_user()
        rows: list[ProfileRow] = []
        for user in self.list_profiles():
            state = self.local_auth_state(user)
            rows.append(ProfileRow(
                current=(user == current),
                user=user,
                student_type=profiles.get_student_type(user),
                device=state.device,
                session=state.session,
                stage=state.stage,
            ))
        return rows

    def login(
        self,
        user: str,
        *,
        interaction: AuthInteraction,
        network: AuthNetwork | None = None,
        policy: AuthPolicy | None = None,
        student_type: str | None = None,
        stage: str | None = None,
        code: str | None = None,
        force: bool = False,
    ) -> LoginResult:
        """Run login, including two-stage 2FA state persistence."""
        network = network or AuthNetwork()
        policy = policy or AuthPolicy()
        if force:
            policy = replace(policy, force_login=True)
        selected = profiles.set_current_user(user)
        if student_type is not None:
            profiles.set_student_type(selected, student_type)
        paths = profiles.profile_paths(selected)

        if stage == "verify":
            if not paths.stage.exists():
                raise AuthError(f"stage file not found: {paths.stage}")
            if not code:
                raise AuthError("missing verification code")
            state = _read_json_object(paths.stage)
            if not state:
                raise AuthError(f"stage file unreadable: {paths.stage}")
            if state.get("user") != selected:
                raise AuthError(
                    f"stage belongs to {state.get('user') or '<unknown>'}; "
                    f"current profile is {selected}"
                )
            realm_id = state.get("realm_id", "learn")
            realm = REALMS.get(realm_id, LEARN_REALM)
            eff_debug = network.debug_dir or (
                Path(state["debug_dir"]) if state.get("debug_dir") else None
            )
            device = Device.load_or_create(paths.device)
            sso = SsoSession(
                device=device,
                verify_tls=network.verify_tls,
                trust_env=network.trust_env,
                debug_dir=eff_debug,
                captcha_path=paths.captcha,
                on_event=network.on_event,
            )
            load_cookies(sso.http.cookies, state.get("cookies"))
            sso.username = state["user"]
            sso.restore_step_idx(int(state.get("step_idx", 0)))
            sso.resume_2fa(realm, state["choice"], code,
                           interaction=interaction, policy=policy)
            self._prewarm_known_services(
                selected, sso, interaction=interaction, policy=policy,
            )
            paths.stage.unlink(missing_ok=True)
            return LoginResult(selected, paths.session)

        if interaction.passwd_fn is None:
            raise AuthError("interaction.passwd_fn is required for login")

        device = Device.load_or_create(paths.device)
        sso = SsoSession(
            device=device,
            verify_tls=network.verify_tls,
            trust_env=network.trust_env,
            debug_dir=network.debug_dir,
            captcha_path=paths.captcha,
            on_event=network.on_event,
        )
        sso.username = selected

        loaded = SsoSession.load(
            paths.session,
            device=device,
            verify_tls=network.verify_tls,
            trust_env=network.trust_env,
            debug_dir=network.debug_dir,
            captcha_path=paths.captcha,
            on_event=network.on_event,
        )
        if loaded and loaded.username == selected and not policy.force_login:
            load_cookies(sso.http.cookies, [
                {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
                for c in loaded.http.cookies
            ])
            sso._bootstrapped.update(loaded._bootstrapped)
            sso._app_bootstrapped.update(loaded._app_bootstrapped)

        cached = False
        if not policy.force_login and stage != "send":
            if sso.verify_realm(LEARN_REALM):
                sso._bootstrapped.setdefault("learn", datetime.now())
                cached = True

        if not cached:
            # Prewarm may need the password more than once.
            if interaction.passwd_fn is not None and sso._cached_password is None:
                sso._cached_password = interaction.passwd_fn()
            try:
                sso.ensure_realm(LEARN_REALM, interaction=interaction, policy=policy,
                                 defer_2fa=(stage == "send"))
            except TwoFactorPending as pending:
                _write_json_object(paths.stage, {"user": selected, **pending.to_dict()})
                return LoginResult(selected, paths.session, stage_pending=True)

        self._prewarm_known_services(
            selected, sso, interaction=interaction, policy=policy,
        )

        return LoginResult(
            selected,
            paths.session,
            twofa_skipped=(stage == "send" and not cached),
        )

    def verify(
        self,
        user: str | None = None,
        *,
        network: AuthNetwork | None = None,
    ) -> bool:
        network = network or AuthNetwork()
        selected = self.resolve_user(user)
        paths = profiles.profile_paths(selected)
        if not paths.session.exists():
            return False
        device = Device.load_or_create(paths.device)
        sso = SsoSession.load(
            paths.session,
            device=device,
            verify_tls=network.verify_tls,
            trust_env=network.trust_env,
            captcha_path=paths.captcha,
        )
        return bool(sso and sso.verify_realm(LEARN_REALM))

    def _load_sso_for_status(self, selected: str, network: AuthNetwork) -> SsoSession | None:
        paths = profiles.profile_paths(selected)
        if not paths.session.exists():
            return None
        device = Device.load_or_create(paths.device)
        return SsoSession.load(
            paths.session,
            device=device,
            verify_tls=network.verify_tls,
            trust_env=network.trust_env,
            captcha_path=paths.captcha,
        )

    def _remote_statuses(
        self,
        selected: str,
        *,
        offline: bool,
        network: AuthNetwork,
        session_present: bool,
    ) -> tuple[RemoteServiceState, ...]:
        student_type = profiles.get_student_type(selected)
        transcript_app, timetable_app = _student_apps(student_type)
        names = _remote_service_names(student_type)
        if offline:
            return tuple(RemoteServiceState(n, FileState("skipped", "--offline")) for n in names)
        if not session_present:
            return tuple(RemoteServiceState(n, FileState("skipped", "no session")) for n in names)

        sso = self._load_sso_for_status(selected, network)
        if sso is None:
            return tuple(RemoteServiceState(n, FileState("skipped", "no session")) for n in names)

        checks = (
            ("learn", lambda: sso.verify_realm(LEARN_REALM)),
            ("webvpn", lambda: sso.verify_realm(WEBVPN_REALM)),
            ("info", lambda: sso.verify_app(INFO_PORTAL)),
            (transcript_app.id, lambda: sso.verify_app(transcript_app)),
            (timetable_app.id, lambda: sso.verify_app(timetable_app)),
        )
        states: list[RemoteServiceState] = []
        for name, check in checks:
            try:
                ok = check()
            except Exception:
                ok = False
            states.append(RemoteServiceState(name, FileState("valid" if ok else "expired")))
        return tuple(states)

    def status(
        self,
        user: str | None = None,
        *,
        offline: bool = False,
        network: AuthNetwork | None = None,
    ) -> AuthStatus:
        network = network or AuthNetwork()
        selected = self.resolve_user(user)
        current = profiles.get_current_user()
        local = self.local_auth_state(selected)
        session_present = local.session.present
        stage_present = local.stage.present
        remote_services = self._remote_statuses(
            selected,
            offline=offline,
            network=network,
            session_present=session_present,
        )

        if offline:
            remote = FileState("skipped", "--offline")
            exit_code = 0 if session_present else 1
        elif not session_present:
            remote = FileState("skipped", "no session")
            exit_code = 1
        else:
            all_valid = bool(remote_services) and all(
                s.state.state == "valid" for s in remote_services
            )
            remote = FileState("valid" if all_valid else "expired")
            exit_code = 0 if all_valid else 2

        hint: AuthHint | None = None
        if stage_present:
            hint = AuthHint("stage_verify")
        elif remote.state == "expired":
            session_user = (local.session_data or {}).get("username") or selected
            hint = AuthHint("login_force", session_user)
        elif not session_present:
            hint = AuthHint("login", selected)

        return AuthStatus(
            current_user=current,
            selected_user=selected,
            student_type=profiles.get_student_type(selected),
            device=local.device,
            session=local.session,
            stage=local.stage,
            remote=remote,
            remote_services=remote_services,
            hint=hint,
            exit_code=exit_code,
        )

    def logout(self, user: str | None = None, *, include_device: bool = False) -> LogoutResult:
        selected = self.resolve_user(user)
        paths = profiles.profile_paths(selected)
        removed: list[str] = []
        if paths.session.exists():
            paths.session.unlink()
            removed.append("session")
        if paths.stage.exists():
            paths.stage.unlink()
            removed.append("stage")
        if include_device and paths.device.exists():
            paths.device.unlink()
            removed.append("device")
        return LogoutResult(
            user=selected,
            removed=tuple(removed),
            device_kept=(not include_device and paths.device.exists()),
        )


__all__ = [
    "AuthHint",
    "AuthService",
    "AuthStatus",
    "FileState",
    "LocalAuthState",
    "LoginResult",
    "LogoutResult",
    "ProfileRow",
    "RemoteServiceState",
]
