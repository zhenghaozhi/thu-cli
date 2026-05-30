"""webvpn.tsinghua.edu.cn URL 改写工具。

webvpn 用 URL 路径段把内网 host 编码成混淆 hash，路径形如：

    https://webvpn.tsinghua.edu.cn/<scheme>[-port]/<host_hash>/<inner_path>

例如 ``https://info.tsinghua.edu.cn/f/foo`` →
``https://webvpn.tsinghua.edu.cn/https/<info_hash>/f/foo``

``WEBVPN_HOST_HASH`` 维护 host → hash 的映射，需要新 host 时直接往里加。
"""
from __future__ import annotations

import re

WEBVPN_BASE = "https://webvpn.tsinghua.edu.cn"

# host → webvpn-encoded host hash. 抄自 thu-info-lib HOST_MAP；只加我们用到的。
WEBVPN_HOST_HASH: dict[str, str] = {
    "info2021.tsinghua.edu.cn":  "77726476706e69737468656265737421f9f9479375603a01301c9aa596522b208e9cd9c9e383ff3f",
    "info.tsinghua.edu.cn":      "77726476706e69737468656265737421f9f9479369247b59700f81b9991b2631506205de",
    "id.tsinghua.edu.cn":        "77726476706e69737468656265737421f9f30f8834396657761d88e29d51367bcfe7",
    "zhjw.cic.tsinghua.edu.cn":  "77726476706e69737468656265737421eaff4b8b69336153301c9aa596522b20bc86e6e559a9b290",
    "jxgl.cic.tsinghua.edu.cn":  "77726476706e69737468656265737421faef469069336153301c9aa596522b20e33c1eb39606919f",
    "ecard.tsinghua.edu.cn":     "77726476706e69737468656265737421f5f4408e237e7c4377068ea48d546d303341e9882a",
    "learn.tsinghua.edu.cn":     "77726476706e69737468656265737421fcf2408e297e7c4377068ea48d546d30ca8cc97bcc",
    "mails.tsinghua.edu.cn":     "77726476706e69737468656265737421fdf64890347e7c4377068ea48d546d3011ff591d40",
    "50.tsinghua.edu.cn":        "77726476706e69737468656265737421a5a70f8834396657761d88e29d51367b6a00",
    "fa-online.tsinghua.edu.cn": "77726476706e69737468656265737421f6f60c93293c615e7b469dbf915b243daf0f96e17deaf447b4",
    "dzpj.tsinghua.edu.cn":      "77726476706e69737468656265737421f4ed519669247b59700f81b9991b2631aee63c51",
    "jjhyhdf.tsinghua.edu.cn":   "77726476706e69737468656265737421fafd49852f346e1e6a1b80a29f5d36342bb9c40cf69277",
    "yhdf.tsinghua.edu.cn":      "77726476706e69737468656265737421e9ff459a69247b59700f81b9991b26317dbd36ae",
    "usereg.tsinghua.edu.cn":    "77726476706e69737468656265737421e5e4448e223726446d0187ab9040227b54b6c80fcd73",
    "thos.tsinghua.edu.cn":      "77726476706e69737468656265737421e4ff4e8f69247b59700f81b9991b2631ca359dd4",
}


def webvpn_url(host: str, path: str, *, scheme: str = "https") -> str:
    """拼一个 webvpn 代理 URL。

    例：
        webvpn_url("zhjw.cic.tsinghua.edu.cn", "/cj.cjCjbAll.do", scheme="http")
        → https://webvpn.tsinghua.edu.cn/http/<zhjw_hash>/cj.cjCjbAll.do
    """
    if host not in WEBVPN_HOST_HASH:
        raise KeyError(f"no webvpn hash for host {host!r}; add it to WEBVPN_HOST_HASH")
    h = WEBVPN_HOST_HASH[host]
    if not path.startswith("/"):
        path = "/" + path
    return f"{WEBVPN_BASE}/{scheme}/{h}{path}"


def webvpn_translate(url: str) -> str:
    """把一个原始的清华内网 URL 翻译成 webvpn 代理形式。

    主要用于 info portal 的 ``onlineAppRedirect`` 返回的内网 URL — 必须改写后才能 fetch。

    支持：
        ``http://1.2.3.4:port/path`` → ``https://webvpn.../http-port/<hash>/path``
        ``scheme://host.tsinghua.edu.cn[:port]/path``
            → ``https://webvpn.../scheme[-port]/<hash>/path``
    """
    ip_match = re.match(r"http://(\d+\.\d+\.\d+\.\d+):(\d+)/(.+)", url)
    if ip_match:
        ip, port, path = ip_match.groups()
        if ip not in WEBVPN_HOST_HASH:
            raise KeyError(f"no webvpn hash for IP {ip}")
        return f"{WEBVPN_BASE}/http-{port}/{WEBVPN_HOST_HASH[ip]}/{path}"

    host_match = re.match(r"(\w+)://(.+?\.tsinghua\.edu\.cn)(?::(\d+))?/(.+)", url)
    if host_match:
        scheme, host, port, path = host_match.groups()
        if host not in WEBVPN_HOST_HASH:
            raise KeyError(f"no webvpn hash for host {host}")
        protocol = scheme if port is None else f"{scheme}-{port}"
        return f"{WEBVPN_BASE}/{protocol}/{WEBVPN_HOST_HASH[host]}/{path}"

    raise ValueError(f"cannot translate URL to webvpn form: {url!r}")


__all__ = [
    "WEBVPN_BASE",
    "WEBVPN_HOST_HASH",
    "webvpn_translate",
    "webvpn_url",
]
