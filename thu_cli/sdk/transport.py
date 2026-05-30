"""Protocol helpers shared across SDK clients."""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests

from ..core.errors import SessionExpired

logger = logging.getLogger("thu_cli.sdk.transport")


@dataclass(frozen=True)
class RemoteFile:
    """Common description for a remote downloadable file."""
    id: str
    name: str
    download_url: str
    preview_url: str = ""
    size: str | None = None

    def filename(self) -> str:
        return safe_filename(self.name)


def csrf_params(http: requests.Session, *, domain: str) -> dict[str, str]:
    """Build ``_csrf`` params from an XSRF-TOKEN cookie for ``domain``."""
    token = http.cookies.get("XSRF-TOKEN", domain=domain) or http.cookies.get("XSRF-TOKEN")
    if not token:
        raise SessionExpired(f"{domain} has no XSRF-TOKEN; re-login required")
    return {"_csrf": token}


def json_or_expired(r: requests.Response) -> Any:
    """Parse JSON or raise ``SessionExpired`` for login-like responses."""
    ct = r.headers.get("Content-Type", "")
    if r.status_code in (302, 401, 403) or "html" in ct:
        raise SessionExpired(f"API returned non-JSON status={r.status_code} ct={ct!r}")
    try:
        return r.json()
    except ValueError as e:
        raise SessionExpired(f"API JSON parse failed: {e}") from e


def raise_if_unauthenticated(r: requests.Response, *, context: str = "request") -> None:
    """Detect auth loss for endpoints that may legitimately return HTML."""
    if r.status_code in (302, 401, 403):
        raise SessionExpired(f"{context} requires re-login: status={r.status_code}")


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().strip(".")
    return cleaned or "download"


def unique_path(path: Path) -> Path:
    """Append ``-1`` / ``-2`` / ... when the target path already exists."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for idx in range(1, 1000):
        candidate = parent / f"{stem}-{idx}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"cannot allocate download filename: {path}")


def content_disposition_filename(value: str | None) -> str | None:
    if not value:
        return None
    m = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", value, re.I)
    if m:
        return unquote(m.group(1).strip().strip('"'))
    m = re.search(r'filename="?([^";]+)"?', value, re.I)
    if m:
        return unquote(m.group(1).strip())
    return None


def display_time(value: Any) -> str:
    """Format millisecond timestamps, otherwise return unescaped text."""
    if value in (None, ""):
        return ""
    text = str(value)
    if text.isdigit() and len(text) >= 12:
        try:
            return datetime.fromtimestamp(int(text) / 1000).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, ValueError):
            return text
    return unescape(text)


def display_size(value: Any) -> str:
    """Format byte counts, otherwise return the original text."""
    if value in (None, ""):
        return ""
    text = str(value)
    if not text.isdigit():
        return text
    size = float(text)
    units = ["B", "KB", "MB", "GB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return text


def stream_download(
    http: requests.Session,
    remote_file: RemoteFile,
    dest_dir: str | Path,
    *,
    csrf_domain: str,
    dump: Callable[[str, requests.Response], None] | None = None,
    filename: str | None = None,
    chunk_size: int = 1024 * 256,
    timeout: int = 60,
) -> Path:
    """Stream a remote file to disk."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    r = http.get(
        remote_file.download_url,
        params=csrf_params(http, domain=csrf_domain),
        stream=True,
        timeout=timeout,
        allow_redirects=False,
    )
    if dump is not None:
        dump("stream_download", r)
    ct = r.headers.get("Content-Type", "")
    if r.status_code in (302, 401, 403) or "html" in ct:
        r.close()
        raise SessionExpired(f"download requires re-login: status={r.status_code} ct={ct!r}")
    if r.status_code != 200:
        r.close()
        raise RuntimeError(f"download failed: status={r.status_code}")
    name = filename or content_disposition_filename(r.headers.get("Content-Disposition"))
    path = unique_path(dest / safe_filename(name or remote_file.filename()))
    with path.open("wb") as fh:
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                fh.write(chunk)
    r.close()
    return path


__all__ = [
    "RemoteFile",
    "content_disposition_filename",
    "csrf_params",
    "display_size",
    "display_time",
    "json_or_expired",
    "raise_if_unauthenticated",
    "safe_filename",
    "stream_download",
    "unique_path",
]
