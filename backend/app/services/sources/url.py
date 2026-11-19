"""网页导入：抓取 HTML、提取正文，并对目标地址做 SSRF 防护。"""

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura

from app.core.errors import AppError

_MAX_BYTES = 5 * 1024 * 1024
_MAX_REDIRECTS = 3
_TIMEOUT = 10.0
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36 KnowledgeBaseBot/0.1"
)
_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\r\n\t]+')
_TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class FetchedPage:
    title: str
    content: str
    final_url: str


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # is_global 同时排除 CGNAT(100.64/10)、benchmark(198.18/15)、保留段和链路本地，
    # 比自行枚举黑名单更稳妥。
    return ip.is_global


def _assert_public_host(hostname: str, port: int) -> None:
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise AppError("URL_UNREACHABLE", "无法解析该网址的域名", 422) from exc
    if not infos:
        raise AppError("URL_UNREACHABLE", "无法解析该网址的域名", 422)
    for info in infos:
        address = str(info[4][0]).split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise AppError("URL_FORBIDDEN", "网址解析结果不合法", 422) from exc
        if not _is_public_ip(ip):
            raise AppError("URL_FORBIDDEN", "该网址指向内网或保留地址，已拒绝抓取", 422)


def validate_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as exc:
        raise AppError("INVALID_URL", "网址格式不正确", 422) from exc
    if parsed.scheme not in {"http", "https"}:
        raise AppError("INVALID_URL", "仅支持 http 或 https 链接", 422)
    if not parsed.hostname:
        raise AppError("INVALID_URL", "网址缺少域名", 422)
    if parsed.username or parsed.password:
        raise AppError("INVALID_URL", "网址不能包含用户名或密码", 422)
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "localhost.localdomain"}:
        raise AppError("URL_FORBIDDEN", "该网址指向本机地址，已拒绝抓取", 422)
    _assert_public_host(hostname, port or (443 if parsed.scheme == "https" else 80))
    return url


def _assert_connected_peer(response: httpx.Response) -> None:
    """连接建立后复核实际对端 IP，防止 DNS rebinding 绕过预解析校验。

    httpcore 在 ``network_stream`` 扩展里暴露真实 socket 地址；拿不到时
    保持原行为（至少预解析已校验），拿到就必须是公网地址。
    """
    stream = response.extensions.get("network_stream")
    if stream is None:
        return
    try:
        address = stream.get_extra_info("server_addr")
    except Exception:  # noqa: BLE001  不同 httpcore 版本实现有差异
        return
    if not address:
        return
    try:
        ip = ipaddress.ip_address(str(address[0]).split("%", 1)[0])
    except ValueError as exc:
        raise AppError("URL_FORBIDDEN", "网页实际连接地址不合法", 422) from exc
    if not ip.is_global:
        raise AppError("URL_FORBIDDEN", "该网址实际连接到内网或保留地址，已拒绝抓取", 422)


def _decode_html(data: bytes, declared: str | None) -> str:
    candidates = [declared, "utf-8", "gb18030"]
    for encoding in candidates:
        if not encoding:
            continue
        try:
            text = data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        if text.count("\ufffd") <= max(1, len(text) // 100):
            return text
    return data.decode("utf-8", errors="replace")


def _extract_title(html: str) -> str:
    try:
        metadata = trafilatura.extract_metadata(html)
    except Exception:  # noqa: BLE001  标题提取失败不影响正文
        metadata = None
    title = str(getattr(metadata, "title", "") or "").strip()
    if title:
        return title
    match = _TITLE_PATTERN.search(html)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    return ""


def _read_limited(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > _MAX_BYTES:
            raise AppError("URL_TOO_LARGE", "网页内容超过 5 MB，无法导入", 413)
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_page(url: str) -> FetchedPage:
    """抓取网页并提取正文；每次重定向都重新做地址校验。"""
    current = url.strip()
    if not current:
        raise AppError("INVALID_URL", "网址不能为空", 422)

    for _ in range(_MAX_REDIRECTS + 1):
        target = validate_url(current)
        try:
            with httpx.Client(
                timeout=_TIMEOUT,
                follow_redirects=False,
                trust_env=False,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
                },
            ) as client:
                with client.stream("GET", target) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise AppError("URL_FETCH_FAILED", "网页重定向缺少目标地址", 422)
                        current = urljoin(target, location)
                        continue
                    if response.status_code != 200:
                        raise AppError(
                            "URL_FETCH_FAILED",
                            f"网页返回状态码 {response.status_code}，无法导入",
                            422,
                        )
                    content_type = response.headers.get("content-type", "").lower()
                    if "html" not in content_type and "text/" not in content_type:
                        raise AppError("URL_UNSUPPORTED", "该链接不是可解析的网页内容", 422)
                    _assert_connected_peer(response)
                    declared = response.charset_encoding
                    html = _decode_html(_read_limited(response), declared)
        except httpx.HTTPError as exc:
            raise AppError(
                "URL_UNREACHABLE", "抓取网页失败，请检查链接或稍后重试", 422
            ) from exc

        title = _extract_title(html)
        try:
            content = trafilatura.extract(
                html,
                url=target,
                include_comments=False,
                include_tables=True,
                favor_recall=True,
                output_format="markdown",
            )
        except TypeError:
            content = trafilatura.extract(
                html,
                url=target,
                include_comments=False,
                include_tables=True,
            )
        if not content or not content.strip():
            raise AppError(
                "URL_NO_CONTENT",
                "未能从该网页提取正文，可能需要登录或是脚本渲染页面",
                422,
            )
        return FetchedPage(
            title=title or urlparse(target).hostname or "网页",
            content=content.strip(),
            final_url=target,
        )

    raise AppError("URL_TOO_MANY_REDIRECTS", "网页重定向次数过多，无法导入", 422)


def build_markdown_filename(title: str, fallback: str = "网页") -> str:
    cleaned = _UNSAFE_FILENAME.sub(" ", title or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)[:80].strip()
    return f"{cleaned or fallback}.md"
