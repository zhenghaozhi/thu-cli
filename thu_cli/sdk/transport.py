"""跨子系统共享的协议工具箱。

只放与具体业务（learn / info / ...）无关的 HTTP / 协议原语：

    RemoteFile                       通用 "远端可下载文件" 对象
    csrf_params(http, *, domain)     从指定域名取 XSRF-TOKEN 拼 _csrf
    json_or_expired(r)               JSON 解析；HTML/302/401/403 抛 SessionExpired
    raise_if_unauthenticated(r)      非 JSON endpoint 的 session 失效检测
    safe_filename(name)              文件名清洗
    unique_path(path)                避免覆盖：file.ext → file-1.ext
    content_disposition_filename     从 header 解出 filename
    display_time / display_size      展示用格式化
    stream_download                  流式下载

下游 client 失败时抛 ``RuntimeError``，由具体业务层翻译成自己的领域异常。
"""
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


# ---------------- 数据对象 ----------------
@dataclass(frozen=True)
class RemoteFile:
    """远端可下载文件的通用描述。各业务客户端可直接复用或派生。"""
    id: str
    name: str
    download_url: str
    preview_url: str = ""
    size: str | None = None

    def filename(self) -> str:
        return safe_filename(self.name)


# ---------------- 协议原语 ----------------
def csrf_params(http: requests.Session, *, domain: str) -> dict[str, str]:
    """从指定域名的 XSRF-TOKEN cookie 拼 ``_csrf`` 参数。缺失抛 SessionExpired。

    ``domain`` 必传：thu 各子站 cookie 范围不同，learn / cloud / git 各有各的域。
    """
    token = http.cookies.get("XSRF-TOKEN", domain=domain) or http.cookies.get("XSRF-TOKEN")
    if not token:
        raise SessionExpired(f"{domain} 域无 XSRF-TOKEN，需重新登录")
    return {"_csrf": token}


def json_or_expired(r: requests.Response) -> Any:
    """期望 JSON；拿到 HTML / 302 / 401 / 403 视为 session 失效。"""
    ct = r.headers.get("Content-Type", "")
    if r.status_code in (302, 401, 403) or "html" in ct:
        raise SessionExpired(f"API 返回非 JSON（status={r.status_code} ct={ct!r}）")
    try:
        return r.json()
    except ValueError as e:
        raise SessionExpired(f"API JSON 解析失败：{e}") from e


def raise_if_unauthenticated(r: requests.Response, *, context: str = "request") -> None:
    """非 JSON 期望的 endpoint（HTML 详情页、下载等）的 session 失效检测。

    仅按 302 / 401 / 403 判定；HTML 内容本身可能是合法响应。
    """
    if r.status_code in (302, 401, 403):
        raise SessionExpired(f"{context} 需要重新登录：status={r.status_code}")


# ---------------- 文件名 / 路径 ----------------
def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().strip(".")
    return cleaned or "download"


def unique_path(path: Path) -> Path:
    """同名已存在时附加 ``-1`` / ``-2`` / ... 后缀；上限 999 后抛 RuntimeError。"""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for idx in range(1, 1000):
        candidate = parent / f"{stem}-{idx}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法生成下载文件名：{path}")


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


# ---------------- 格式化 ----------------
def display_time(value: Any) -> str:
    """毫秒时间戳 → "YYYY-MM-DD HH:MM:SS"，否则原样返回（HTML 转义解码）。"""
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
    """字节数 → "1.2 MB"，非数字原样返回。"""
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


# ---------------- 下载 ----------------
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
    """通用流式下载。

    cookie 失效抛 ``SessionExpired``；其它 HTTP 非 200 抛 ``RuntimeError``。
    具体业务 client 应捕获 ``RuntimeError`` 并翻译为自己的领域异常。
    """
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
        raise SessionExpired(f"download 需要重新登录：status={r.status_code} ct={ct!r}")
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
