"""Tsinghua SSO implementation built around ``SsoSession``.

Design notes:
    - The protocol layer never prints or reads input directly; interaction is
      injected through ``AuthInteraction`` callbacks.
    - ``id.tsinghua`` is the master credential source. Realms share one device
      fingerprint, and a trusted device usually avoids repeated 2FA.
    - Campus apps inside the webvpn realm are bootstrapped lazily. Default
      policy apps depend on ``INFO_PORTAL``.
    - The SDK has no ``config`` dependency. Paths and callbacks are injected by
      services or by SDK users directly.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from gmssl import sm2
from urllib3.exceptions import InsecureRequestWarning

from ..core.apps import CampusApp
from ..core.endpoints import (
    DA_LOGIN,
    DA_SAVE_FINGER,
    ID_BASE,
    INFO_CSRF_COOKIE_URL,
    INFO_ROAMING_URL,
    SSO_CAPTCHA_IMG,
    SSO_CHECK,
    sso_form_url,
)
from ..core.errors import (
    AuthError,
    BadCredentials,
    CaptchaRequired,
    SessionExpired,
    TwoFactorFailed,
    TwoFactorPending,
)
from ..core.realms import Realm
from ..core.webvpn import webvpn_translate
from ._literals import (
    SERVER_NO,
    SERVER_YES,
    SSO_BAD_CREDENTIALS_MARKER,
    SSO_DOUBLE_AUTH_MARKER,
    SSO_LOGIN_SUCCESS_MARKER,
    SSO_NO_PERMISSION_MARKER,
    SSO_NOT_LOGGED_IN_MARKER,
    SSO_TRUST_DEVICE_LIMIT_MARKER,
)

logger = logging.getLogger("thu_cli.sdk.auth")

# Silence urllib3 warnings only after the user explicitly disables TLS checks.
_warnings_silenced = False


def _silence_insecure_warnings_once() -> None:
    global _warnings_silenced
    if not _warnings_silenced:
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        _warnings_silenced = True

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

_MSG_SELECTORS = ("#msg_note", ".alert-danger", ".error", ".red")

# id.tsinghua SM2 public key. Prefer a pubkey from the form when present.
SM2_PUBKEY_FALLBACK = (
    "04d0c9e1ae89279fe05b435d63e3eba437bf510e09da5f71558974a19dc596724227f08dc2fc6e74bbb9d8b468d4dd5205e9b6793a3bbc48df3fdf219b3ea140e3"
)


@dataclass(frozen=True)
class AuthInteraction:
    """Callbacks for data and decisions supplied by the caller."""
    passwd_fn: Callable[[], str] | None = None
    on_2fa_choice: Callable[[dict], str] | None = None
    on_code: Callable[[str], str] | None = None
    on_captcha: Callable[[bytes], str] | None = None
    trust_device: bool | str | Callable[[], bool] = False
    code_prompt: Callable[[str], str] | None = None


@dataclass(frozen=True)
class AuthNetwork:
    """Protocol-independent network and debugging options."""
    verify_tls: bool = True
    trust_env: bool = True
    debug_dir: Path | None = None
    on_event: Callable[[str, str], None] | None = None


@dataclass(frozen=True)
class AuthPolicy:
    """Login strategy: 2FA preference, single-login, and forced bootstrap."""
    prefer_2fa: str | None = None
    single_login: bool = True
    single_login_key: str | None = None
    force_login: bool = False


def _write_private_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def dump_cookies(jar: requests.cookies.RequestsCookieJar) -> list[dict]:
    return [
        {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path, "expires": c.expires}
        for c in jar
    ]


def load_cookies(jar: requests.cookies.RequestsCookieJar, data: list[dict] | None) -> None:
    for c in data or []:
        jar.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path", "/"))


def sm2_encrypt(plain: str, pubkey_hex: str) -> str:
    """Match sm2Util.js: gmssl mode=1 (C1C2C3) plus the ``04`` prefix."""
    key = pubkey_hex[2:] if pubkey_hex.startswith("04") else pubkey_hex
    ct = sm2.CryptSM2(public_key=key, private_key="", mode=1).encrypt(plain.encode("utf-8")).hex()
    return "04" + ct


@dataclass
class Device:
    """Locally persisted device fingerprint."""
    fingerprint: str
    fingerGenPrint: str
    fingerGenPrint3: str
    singleLoginKey: str
    deviceName: str = "thu-cli"

    @classmethod
    def load_or_create(cls, path: Path) -> Device:
        if path.exists():
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        dev = cls(
            fingerprint=uuid.uuid4().hex,
            fingerGenPrint=uuid.uuid4().hex,
            fingerGenPrint3=uuid.uuid4().hex,
            singleLoginKey=uuid.uuid4().hex,
        )
        _write_private_json(path, dev.__dict__)
        return dev


def _normalize_trust_device(arg: bool | str | Callable[[], bool]) -> Callable[[], bool]:
    if callable(arg):
        return arg
    if isinstance(arg, bool):
        return (lambda: True) if arg else (lambda: False)
    if isinstance(arg, str):
        v = arg.strip().lower()
        if v in ("yes", "y", "true", SERVER_YES):
            return lambda: True
        if v in ("no", "n", "false", SERVER_NO):
            return lambda: False
        if v == "ask":
            return lambda: False
    raise ValueError(f"invalid trust_device: {arg!r} (expected bool / 'ask' / 'yes'|'no' / callable)")


def _extract_message(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for sel in _MSG_SELECTORS:
        node = soup.select_one(sel)
        if node:
            txt = " ".join(node.get_text(" ", strip=True).split())
            if txt:
                return txt
    title = soup.find("title")
    return " ".join(title.get_text(" ", strip=True).split()) if title else ""


def _captcha_visible(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one("#c_code")
    if not node:
        return False
    classes = set(node.get("class") or [])
    style = (node.get("style") or "").replace(" ", "").lower()
    return "hidden" not in classes and "display:none" not in style


def _extract_sm2_pubkey(html: str) -> str | None:
    m = re.search(r'id=["\']sm2publicKey["\'][^>]*>([^<]+)<', html)
    return m.group(1).strip() if m else None


def _extract_anchor_href(html: str, base_url: str) -> str | None:
    """Find a redirect target in anchors, forms, or simple JS redirects."""
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.find_all(["a", "form"]):
        href = node.get("href") or node.get("action") or ""
        if href:
            return urljoin(base_url, href)
    m = re.search(
        r"""window\.location"""
        r"""(?:\.replace\s*\(|\.assign\s*\(|\.href\s*=|\s*=)"""
        r"""\s*["']([^"']+)["']""", html)
    if m:
        return urljoin(base_url, m.group(1))
    return None


def _safe_label(label: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", label).strip("_")


class SsoSession:
    """Tsinghua SSO session with lazy realm and campus-app bootstrap."""

    def __init__(
        self,
        *,
        device: Device | None = None,
        verify_tls: bool = True,
        trust_env: bool = True,
        debug_dir: Path | None = None,
        captcha_path: Path | None = None,
        on_event: Callable[[str, str], None] | None = None,
    ) -> None:
        self.http: requests.Session = requests.Session()
        self.http.headers.update({
            "User-Agent": UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        self.http.verify = bool(verify_tls)
        if not verify_tls:
            _silence_insecure_warnings_once()
        self.http.trust_env = bool(trust_env)
        self.device: Device | None = device
        self.username: str | None = None
        self.debug_dir: Path | None = Path(debug_dir) if debug_dir else None
        self.captcha_path: Path | None = Path(captcha_path) if captcha_path else None
        self.on_event = on_event
        self._step_idx: int = 0
        self._bootstrapped: dict[str, datetime] = {}
        self._app_bootstrapped: dict[str, datetime] = {}
        self._cached_password: str | None = None
        self._cached_sm2_pubkey: str | None = None
        if self.debug_dir:
            self.debug_dir.mkdir(parents=True, exist_ok=True)

    def _event(self, level: str, message: str) -> None:
        if self.on_event is not None:
            self.on_event(level, message)

    def _require_device(self) -> Device:
        if self.device is None:
            raise AuthError("SsoSession requires a device; pass device=Device.load_or_create(path)")
        return self.device

    def _resolve_password(self, interaction: AuthInteraction | None) -> str:
        if self._cached_password:
            return self._cached_password
        if interaction and interaction.passwd_fn:
            pw = interaction.passwd_fn()
            self._cached_password = pw
            return pw
        raise AuthError("password required; provide interaction.passwd_fn or pre-cache _cached_password")

    def dump_response(self, label: str, response: requests.Response) -> None:
        logger.debug("[%s] %s %d ct=%s len=%d",
                     label, response.url, response.status_code,
                     response.headers.get("Content-Type", ""),
                     len(response.content))
        if not self.debug_dir:
            return
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        self._step_idx += 1
        stem = f"{self._step_idx:02d}_{_safe_label(label)}"
        meta = {
            "url": response.url,
            "status_code": response.status_code,
            "headers": dict(response.headers),  # may include Set-Cookie; keep files private
            "history": [
                {"status_code": h.status_code, "url": h.url, "location": h.headers.get("Location")}
                for h in response.history
            ],
            "cookies_set": [
                {"domain": c.domain, "name": c.name, "path": c.path}
                for c in response.cookies
            ],
        }
        headers_path = self.debug_dir / f"{stem}.headers.json"
        headers_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        ct = response.headers.get("Content-Type", "")
        suffix = ".json" if "json" in ct else (".html" if "html" in ct else ".bin")
        body_path = self.debug_dir / f"{stem}{suffix}"
        body_path.write_bytes(response.content)
        for path in (headers_path, body_path):
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass

    def restore_step_idx(self, step_idx: int) -> None:
        self._step_idx = int(step_idx)

    def save(self, path: Path) -> Path:
        """Write session cookies and bootstrap timestamps; never write passwords."""
        _write_private_json(path, {
            "username": self.username,
            "cookies": dump_cookies(self.http.cookies),
            "bootstrapped_realms": {k: v.isoformat() for k, v in self._bootstrapped.items()},
            "bootstrapped_apps": {k: v.isoformat() for k, v in self._app_bootstrapped.items()},
        })
        return path

    @classmethod
    def load(cls, path: Path, **session_kwargs: Any) -> SsoSession | None:
        """Load a saved session, returning ``None`` when the file is absent."""
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        s = cls(**session_kwargs)
        s.username = data.get("username")
        load_cookies(s.http.cookies, data.get("cookies"))
        for k, v in (data.get("bootstrapped_realms") or {}).items():
            try:
                s._bootstrapped[k] = datetime.fromisoformat(v)
            except (TypeError, ValueError):
                pass
        for k, v in (data.get("bootstrapped_apps") or {}).items():
            try:
                s._app_bootstrapped[k] = datetime.fromisoformat(v)
            except (TypeError, ValueError):
                pass
        return s

    def verify_realm(self, realm: Realm) -> bool:
        """Ping ``realm.verify_url`` and return whether the session looks alive."""
        params = None
        if realm.id == "learn":
            token = self.http.cookies.get("XSRF-TOKEN", domain=realm.cookie_domain)
            if not token:
                return False
            params = {"_csrf": token}
        try:
            r = self.http.get(realm.verify_url, params=params, timeout=15, allow_redirects=False)
            self.dump_response(f"verify_{realm.id}", r)
        except Exception:
            return False
        if r.status_code != 200:
            return False
        if realm.id == "learn":
            try:
                return bool(r.json().get("result", {}).get("id"))
            except Exception:
                return False
        return True

    def verify_app(self, app: CampusApp) -> bool:
        """Ping ``app.verify_url`` and return whether the app session looks alive."""
        if not app.verify_url:
            return app.id in self._app_bootstrapped
        try:
            r = self.http.get(app.verify_url, timeout=15, allow_redirects=False)
            self.dump_response(f"verify_app_{app.id}", r)
        except Exception:
            return False
        if r.status_code != 200:
            return False
        text = r.text[:500].lower() if "html" in r.headers.get("Content-Type", "") else ""
        if "login/form" in text or "loginform" in text:
            return False
        return True

    def ensure_realm(
        self,
        realm: Realm,
        *,
        interaction: AuthInteraction | None = None,
        policy: AuthPolicy | None = None,
        defer_2fa: bool = False,
    ) -> None:
        """Lazy-bootstrap a realm, no-oping while cookies are still valid."""
        policy = policy or AuthPolicy()
        if not defer_2fa and not policy.force_login and realm.id in self._bootstrapped:
            if self.verify_realm(realm):
                return
            self._event("info", f"realm {realm.id} cookies expired; re-bootstrap")
            self._bootstrapped.pop(realm.id, None)

        self._bootstrap_realm(
            realm,
            interaction=interaction or AuthInteraction(),
            policy=policy,
            defer_2fa=defer_2fa,
        )
        self._bootstrapped[realm.id] = datetime.now()

    def ensure_app(
        self,
        app: CampusApp,
        *,
        interaction: AuthInteraction | None = None,
        policy: AuthPolicy | None = None,
    ) -> None:
        """Lazy-bootstrap a campus app, including its parent realm/app."""
        policy = policy or AuthPolicy()
        self.ensure_realm(app.realm, interaction=interaction, policy=policy)
        if app.parent_app is not None:
            self.ensure_app(app.parent_app, interaction=interaction, policy=policy)
        if not policy.force_login and app.id in self._app_bootstrapped:
            if self.verify_app(app):
                return
            self._event("info", f"app {app.id} cookies expired; re-bootstrap")
            self._app_bootstrapped.pop(app.id, None)

        self._bootstrap_app(app, interaction=interaction or AuthInteraction(), policy=policy)
        self._app_bootstrapped[app.id] = datetime.now()

    def resume_2fa(
        self,
        realm: Realm,
        choice: str,
        code: str,
        *,
        interaction: AuthInteraction | None = None,
        policy: AuthPolicy | None = None,
    ) -> None:
        """Resume the verify step of a previously deferred 2FA flow."""
        if not self.username:
            raise AuthError("resume_2fa requires self.username (restored from stage.json)")
        interaction = interaction or AuthInteraction()
        policy = policy or AuthPolicy()
        r2fa = self._verify_2fa_and_follow(
            choice, code,
            trust_device=interaction.trust_device,
            single_login_key=policy.single_login_key,
        )
        self._follow_redirects_to_realm(realm, start=r2fa)
        self._bootstrapped[realm.id] = datetime.now()

    def _bootstrap_realm(
        self,
        realm: Realm,
        *,
        interaction: AuthInteraction,
        policy: AuthPolicy,
        defer_2fa: bool = False,
    ) -> None:
        if not self.username:
            raise AuthError("SsoSession.username must be set before bootstrap")
        logger.info("bootstrap realm=%s kind=%s defer=%s",
                    realm.id, realm.bootstrap_kind, defer_2fa)
        if realm.bootstrap_kind == "direct":
            form_response = self._fetch_form_direct(realm.entry_url)
        elif realm.bootstrap_kind == "oauth":
            form_response = self._fetch_form_oauth(realm.entry_url)
        else:
            raise AuthError(f"unknown bootstrap_kind: {realm.bootstrap_kind!r}")

        self._submit_password_and_finish(
            form_response,
            interaction=interaction,
            policy=policy,
            realm=realm,
            defer_2fa=defer_2fa,
        )

    def _fetch_form_direct(self, entry_url: str) -> requests.Response:
        """Fetch a direct realm whose entry URL is the id.tsinghua form."""
        r = self.http.get(entry_url, timeout=30)
        self.dump_response("realm_form_direct", r)
        r.raise_for_status()
        return r

    def _fetch_form_oauth(self, entry_url: str) -> requests.Response:
        """Follow an OAuth realm entry until the id.tsinghua form is reached."""
        r = self.http.get(entry_url, timeout=30, allow_redirects=False)
        self.dump_response("realm_oauth_entry", r)
        for hop in range(12):
            loc = r.headers.get("Location")
            if loc:
                nxt = urljoin(r.url, loc)
                r = self.http.get(nxt, timeout=30, allow_redirects=False)
                self.dump_response(f"realm_oauth_follow_{hop}", r)
                if (urlparse(r.url).netloc == "id.tsinghua.edu.cn"
                        and "/login/form/" in urlparse(r.url).path
                        and r.status_code == 200):
                    return r
                continue
            if r.status_code == 200:
                return r
            raise AuthError(f"oauth realm bootstrap stuck at {r.url} status={r.status_code}")
        raise AuthError(f"oauth realm bootstrap exceeded 12 hops, last url={r.url}")

    def _submit_password_and_finish(
        self,
        form_response: requests.Response,
        *,
        interaction: AuthInteraction,
        policy: AuthPolicy,
        realm: Realm,
        defer_2fa: bool = False,
    ) -> None:
        pubkey = _extract_sm2_pubkey(form_response.text) or self._cached_sm2_pubkey
        if not pubkey:
            pubkey = SM2_PUBKEY_FALLBACK
        self._cached_sm2_pubkey = pubkey
        captcha = self._handle_captcha(form_response.text, interaction.on_captcha)
        password = self._resolve_password(interaction)

        form_url = form_response.url
        if "/login/form/" not in urlparse(form_url).path:
            form_url = realm.entry_url
        r = self._password_post(
            form_url, pubkey=pubkey, password=password,
            captcha=captcha, single_login=policy.single_login,
        )
        body = r.text

        if r.status_code in (301, 302):
            if r.headers.get("Location"):
                self._follow_redirects_to_realm(realm, start=r)
            return
        if _extract_anchor_href(body, r.url):
            self._event("info", f"server skipped 2FA for trusted device; follow ticket for realm {realm.id}")
            self._follow_redirects_to_realm(realm, start=r)
            return

        msg = _extract_message(body)
        if SSO_BAD_CREDENTIALS_MARKER in msg:
            raise BadCredentials(msg)
        if SSO_DOUBLE_AUTH_MARKER not in body and "doubleAuth" not in body:
            raise AuthError(f"unexpected SSO response len={len(body)} msg={msg!r}")

        approaches = self._da_post(action="FIND_APPROACHES")
        if approaches.get("result") != "success":
            raise AuthError(f"FIND_APPROACHES failed: {approaches}")
        if policy.prefer_2fa:
            choice = policy.prefer_2fa
        else:
            if interaction.on_2fa_choice is None:
                raise AuthError("2FA required; provide policy.prefer_2fa or interaction.on_2fa_choice")
            choice = interaction.on_2fa_choice(approaches["object"])
        logger.info("2FA path: choice=%s", choice)

        sent = self._da_post(action="SEND_CODE", type=choice)
        if sent.get("result") != "success":
            raise AuthError(f"SEND_CODE failed: {sent}")

        if defer_2fa:
            raise TwoFactorPending(
                choice=choice,
                cookies=dump_cookies(self.http.cookies),
                debug_dir=str(self.debug_dir) if self.debug_dir else None,
                step_idx=self._step_idx,
                realm_id=realm.id,
            )

        if interaction.on_code is None:
            raise AuthError("2FA code required; provide interaction.on_code")
        prompt = (
            interaction.code_prompt(choice)
            if interaction.code_prompt is not None
            else {
                "wechat": "WeCom verification code",
                "mobile": "SMS verification code",
                "totp": "TOTP 6-digit code",
            }[choice]
        )
        r2fa = self._verify_2fa_and_follow(
            choice, interaction.on_code(prompt),
            trust_device=interaction.trust_device,
            single_login_key=policy.single_login_key,
        )
        self._follow_redirects_to_realm(realm, start=r2fa)

    def _bootstrap_app(self, app: CampusApp, *, interaction: AuthInteraction, policy: AuthPolicy) -> None:
        logger.info("bootstrap app=%s policy=%s", app.id, app.policy)
        if app.policy == "id":
            self._bootstrap_app_id(app, interaction=interaction, policy=policy)
        elif app.policy == "default":
            self._bootstrap_app_default(app, interaction=interaction, policy=policy)
        else:
            raise AuthError(f"unknown app.policy: {app.policy!r}")

    def _bootstrap_app_id(self, app: CampusApp, *, interaction: AuthInteraction, policy: AuthPolicy) -> None:
        """Bootstrap an id-policy app by posting credentials for its APP_ID."""
        form_url = sso_form_url(app.sso_app_id)
        r = self.http.get(form_url, timeout=30, allow_redirects=False)
        self.dump_response(f"app_{app.id}_form_get", r)

        pubkey = self._cached_sm2_pubkey or _extract_sm2_pubkey(r.text)
        if not pubkey:
            full_form = self.http.get(form_url + "/0", timeout=30)
            self.dump_response(f"app_{app.id}_form_full", full_form)
            pubkey = _extract_sm2_pubkey(full_form.text) or SM2_PUBKEY_FALLBACK
        self._cached_sm2_pubkey = pubkey

        password = self._resolve_password(interaction)
        r = self._password_post(form_url, pubkey=pubkey, password=password,
                                captcha="", single_login=policy.single_login)
        if SSO_LOGIN_SUCCESS_MARKER not in r.text:
            msg = _extract_message(r.text)
            if SSO_BAD_CREDENTIALS_MARKER in msg:
                raise BadCredentials(msg)
            raise AuthError(f"app {app.id} bootstrap: unexpected response {msg!r}")
        self._follow_redirects_generic(r, max_hops=20)

    def _bootstrap_app_default(self, app: CampusApp, *, interaction: AuthInteraction, policy: AuthPolicy) -> None:
        """Bootstrap a default-policy app through INFO_PORTAL onlineAppRedirect."""
        csrf = self._get_info_csrf()
        roaming_endpoint = f"{INFO_ROAMING_URL}?yyfwid={app.yyfwid}&_csrf={csrf}&machine=p"
        r = self.http.get(roaming_endpoint, timeout=30)
        self.dump_response(f"app_{app.id}_onlineAppRedirect", r)
        try:
            payload = r.json()
        except ValueError as e:
            raise SessionExpired(
                f"onlineAppRedirect for {app.id} returned non-JSON: {r.text[:200]!r}"
            ) from e
        if payload.get("result") == "error":
            msg = payload.get("msg") or "<no msg>"
            if SSO_NOT_LOGGED_IN_MARKER in msg or SSO_NO_PERMISSION_MARKER in msg:
                self._app_bootstrapped.pop("info_portal", None)
                raise SessionExpired(f"onlineAppRedirect for {app.id}: {msg}")
            raise AuthError(f"onlineAppRedirect for {app.id} failed: {msg}")
        roaming_raw = (payload.get("object") or {}).get("roamingurl", "").replace("&amp;", "&")
        if not roaming_raw:
            raise AuthError(f"onlineAppRedirect for {app.id}: no roamingurl in {payload!r}")
        try:
            roaming_url = webvpn_translate(roaming_raw)
        except (KeyError, ValueError) as e:
            raise AuthError(f"cannot translate roaming URL {roaming_raw!r}: {e}") from e
        fetched = self.http.get(roaming_url, timeout=30, allow_redirects=False)
        self.dump_response(f"app_{app.id}_roam_follow", fetched)
        self._follow_redirects_generic(fetched, max_hops=15)

    def _get_info_csrf(self) -> str:
        """Fetch the INFO_PORTAL XSRF token through the webvpn cookie bridge."""
        r = self.http.get(INFO_CSRF_COOKIE_URL, timeout=30)
        self.dump_response("info_csrf_fetch", r)
        m = re.search(r"XSRF-TOKEN=([^;]+);", r.text + ";")
        if not m:
            raise SessionExpired(f"info portal XSRF-TOKEN not found: {r.text[:200]!r}")
        return m.group(1)

    def _handle_captcha(self, form_html: str,
                        on_captcha: Callable[[bytes], str] | None) -> str:
        if not _captcha_visible(form_html):
            return ""
        r = self.http.get(SSO_CAPTCHA_IMG, timeout=30)
        self.dump_response("captcha_image", r)
        img = r.content
        if on_captcha is not None:
            return on_captcha(img).strip()
        raise CaptchaRequired("captcha required but no on_captcha callback was provided", image_bytes=img)

    def _password_post(
        self, form_url: str, *,
        pubkey: str, password: str, captcha: str, single_login: bool,
    ) -> requests.Response:
        device = self._require_device()
        payload = {
            "i_user": self.username,
            "i_pass": sm2_encrypt(password, pubkey),
            "fingerPrint": device.fingerprint,
            "fingerGenPrint": device.fingerGenPrint,
            "fingerGenPrint3": device.fingerGenPrint3,
            "deviceName": device.deviceName,
            "i_captcha": captcha,
        }
        if single_login:
            payload["singleLogin"] = "on"
        r = self.http.post(
            SSO_CHECK, data=payload, timeout=30, allow_redirects=False,
            headers={"Referer": form_url, "Origin": ID_BASE,
                     "Content-Type": "application/x-www-form-urlencoded"},
        )
        self.dump_response("login_check", r)
        return r

    def _da_post(self, **fields: Any) -> dict:
        r = self.http.post(
            DA_LOGIN, data=fields, timeout=30, allow_redirects=False,
            headers={"Referer": SSO_CHECK, "Origin": ID_BASE,
                     "X-Requested-With": "XMLHttpRequest",
                     "Accept": "application/json, text/plain, */*"},
        )
        self.dump_response(f"da_{fields.get('action', 'unknown').lower()}", r)
        if r.headers.get("Content-Type", "").startswith("application/json"):
            return r.json()
        return {"_raw_status": r.status_code, "_raw_body": r.text[:500]}

    def _save_finger(self, choice_yes: bool, single_login_key: str | None) -> dict:
        device = self._require_device()
        data = {
            "fingerprint": device.fingerprint,
            "deviceName": device.deviceName,
            "radioVal": SERVER_YES if choice_yes else SERVER_NO,
        }
        eff_key = single_login_key if single_login_key is not None else device.singleLoginKey
        if eff_key:
            data["singleLogin"] = eff_key
        r = self.http.post(
            DA_SAVE_FINGER, data=data, timeout=30, allow_redirects=False,
            headers={"Referer": SSO_CHECK, "Origin": ID_BASE,
                     "X-Requested-With": "XMLHttpRequest",
                     "Accept": "application/json, text/plain, */*"},
        )
        self.dump_response(f"savefinger_{'yes' if choice_yes else 'no'}", r)
        if not r.headers.get("Content-Type", "").startswith("application/json"):
            raise AuthError(f"saveFinger returned non-JSON status={r.status_code} body[:200]={r.text[:200]!r}")
        return r.json()

    def _verify_2fa_and_follow(
        self, choice: str, code: str, *,
        trust_device: bool | str | Callable[[], bool] = False,
        single_login_key: str | None = None,
    ) -> requests.Response:
        trust_fn = _normalize_trust_device(trust_device)
        verify_action = "VERITY_TOTP_CODE" if choice == "totp" else "VERITY_CODE"
        ver = self._da_post(action=verify_action, vericode=code)
        if not (isinstance(ver, dict) and ver.get("result") == "success"):
            raise TwoFactorFailed(f"VERITY failed: {(ver or {}).get('msg') or ver}")
        obj = ver.get("object") or {}
        redirect_url = obj.get("redirectUrl")
        if not redirect_url:
            raise AuthError(f"VERIFY succeeded but redirectUrl is missing: {ver}")
        if trust_fn():
            try:
                sf = self._save_finger(True, single_login_key)
                if sf.get("result") == "success":
                    self._event("success", "trusted device registered")
                else:
                    msg = sf.get("msg") or ""
                    if SSO_TRUST_DEVICE_LIMIT_MARKER in msg or "limit" in msg.lower():
                        self._event(
                            "warning",
                            f"trusted device limit reached; current login continues but next login may need 2FA: {msg}",
                        )
                    else:
                        self._event("warning", f"trusted device registration failed: {msg}")
            except Exception as e:
                self._event("warning", f"trusted device registration raised: {e}")
        else:
            self._event("info", "skipped trusted device registration")

        if redirect_url.startswith("/"):
            redirect_url = ID_BASE + redirect_url
        r = self.http.get(redirect_url, timeout=30, allow_redirects=False)
        self.dump_response("redirect_after_2fa", r)
        return r

    def _follow_redirects_to_realm(
        self, realm: Realm, *, start: requests.Response | None = None, max_hops: int = 15,
    ) -> requests.Response:
        """Follow redirects until reaching ``realm.cookie_domain`` outside login paths."""
        current = start
        for hop in range(max_hops):
            if current is not None:
                host = urlparse(current.url).netloc
                path = urlparse(current.url).path
                if (host == realm.cookie_domain
                        and "/login" not in path
                        and "/f/login" not in path
                        and current.status_code in (200, 302, 303)):
                    if current.status_code == 200:
                        return current
            nxt = self._step_one_redirect(current) if current is not None else None
            if nxt is None:
                return current  # type: ignore[return-value]
            current = nxt
            self.dump_response(f"follow_realm_{hop}", current)
        raise AuthError(f"follow_redirects_to_realm exceeded {max_hops} hops, last url={current.url if current else '<none>'}")

    def _follow_redirects_generic(
        self, start: requests.Response, *, max_hops: int = 15,
    ) -> requests.Response:
        """Follow redirects without a specific target until the chain ends."""
        current = start
        for hop in range(max_hops):
            nxt = self._step_one_redirect(current)
            if nxt is None:
                return current
            current = nxt
            self.dump_response(f"follow_{hop}", current)
        return current

    def _step_one_redirect(self, response: requests.Response | None) -> requests.Response | None:
        if response is None:
            return None
        loc = response.headers.get("Location")
        if loc:
            nxt = urljoin(response.url, loc)
            return self.http.get(nxt, headers={"Referer": response.url},
                                 timeout=30, allow_redirects=False)
        ct = response.headers.get("Content-Type", "")
        if "html" in ct:
            jump = _extract_anchor_href(response.text, response.url)
            if jump:
                return self.http.get(jump, headers={"Referer": response.url},
                                     timeout=30, allow_redirects=False)
        return None


__all__ = [
    "AuthInteraction",
    "AuthNetwork",
    "AuthPolicy",
    "Device",
    "SsoSession",
    "dump_cookies",
    "load_cookies",
    "sm2_encrypt",
]
