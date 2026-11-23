"""EPUB 电子书文本提取。

EPUB 是一个 ZIP：``META-INF/container.xml`` 指向 OPF 包文档，OPF 里的
``manifest`` 给出 id→文件名，``spine`` 给出阅读顺序。按 spine 逐章取出
XHTML，用与 HTML 相同的抽取流程转成文本，并把书名、章节名写进标题路径。

不解析 DRM、不解析 CSS 排版；章节内没有显式标题时，用 <title> 或正文首个
Markdown 标题作为章节名。页数留空——EPUB 没有固定页码，不能伪造「第 N 页」。
"""

import posixpath
import re
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

from app.services.parsers.base import ParseError, TextBlock, normalize_text
from app.services.parsers.html_text import (
    blocks_from_html,
    decode_html,
    extract_markdown,
)
from app.services.parsers.markdown import blocks_from_markdown_text

_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_ANY_TAG = re.compile(r"<[^>]+>")
_FIRST_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_MAX_CHAPTERS = 5000
# 解压预算：上传上限 100 MB，而一个零字节压缩的 zip 能膨胀到上百 GB。
_MAX_ENTRY_BYTES = 32 * 1024 * 1024
_MAX_TOTAL_BYTES = 256 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 200
_RATIO_MIN_BYTES = 4 * 1024 * 1024


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _parse_xml(raw: bytes) -> ElementTree.Element | None:
    try:
        return ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return None


def _opf(root: ElementTree.Element) -> tuple[str, dict[str, str], list[str]]:
    title = ""
    manifest: dict[str, str] = {}
    spine_ids: list[str] = []
    for element in root.iter():
        name = _local(element.tag)
        if name == "title" and not title:
            title = normalize_text("".join(element.itertext()))
        elif name == "item":
            item_id = element.get("id", "")
            href = element.get("href", "")
            if item_id and href:
                manifest[item_id] = href
        elif name == "itemref":
            idref = element.get("idref", "")
            if idref:
                spine_ids.append(idref)
    return title, manifest, [manifest[idref] for idref in spine_ids if idref in manifest]


def _chapter_title(html: str, markdown: str) -> str:
    match = _TITLE_TAG.search(html)
    if match:
        title = normalize_text(_ANY_TAG.sub("", match.group(1)))
        if title:
            return title
    heading = _FIRST_HEADING.search(markdown)
    return normalize_text(heading.group(1)) if heading else ""


class _UnzipBudget:
    """限制 EPUB 的解压总量与压缩比，避免小体积上传膨胀成 GB 级内存。"""

    def __init__(self) -> None:
        self.used = 0

    def read(self, archive: zipfile.ZipFile, name: str) -> bytes:
        info = archive.getinfo(name)
        size = info.file_size
        if size > _MAX_ENTRY_BYTES:
            raise ParseError(
                f"EPUB 章节解压后过大（{size} 字节），超过单章上限 {_MAX_ENTRY_BYTES} 字节"
            )
        if self.used + size > _MAX_TOTAL_BYTES:
            raise ParseError("EPUB 解压后的总大小超过上限，可能是压缩炸弹")
        if size > _RATIO_MIN_BYTES and size / max(info.compress_size, 1) > _MAX_COMPRESSION_RATIO:
            raise ParseError("EPUB 的压缩比异常，拒绝解压")
        data = archive.read(name)
        self.used += len(data)
        return data


def parse_epub(data: bytes | Path) -> list[TextBlock]:
    source = BytesIO(data) if isinstance(data, bytes) else data
    blocks: list[TextBlock] = []
    try:
        with zipfile.ZipFile(source) as archive:
            names = set(archive.namelist())
            if "META-INF/container.xml" not in names:
                raise ParseError("EPUB 缺少 META-INF/container.xml，不是有效的电子书")

            container = _parse_xml(archive.read("META-INF/container.xml"))
            opf_path = ""
            if container is not None:
                for element in container.iter():
                    if _local(element.tag) == "rootfile":
                        opf_path = element.get("full-path", "")
                        break
            if not opf_path or opf_path not in names:
                raise ParseError("EPUB 缺少 OPF 包文档")

            opf = _parse_xml(archive.read(opf_path))
            if opf is None:
                raise ParseError("EPUB 的 OPF 包文档无法解析")
            book_title, _manifest, spine = _opf(opf)
            base = posixpath.dirname(opf_path)
            budget = _UnzipBudget()
            for href in spine[:_MAX_CHAPTERS]:
                # spine 里的 href 是百分号编码的，可能还带 #fragment。
                target = unquote(href.split("#", 1)[0])
                path = posixpath.normpath(posixpath.join(base, target)) if base else target
                if path not in names:
                    continue
                html = decode_html(budget.read(archive, path))
                markdown = extract_markdown(html)
                prefix = " > ".join(
                    part for part in (book_title, _chapter_title(html, markdown)) if part
                )
                chapter_blocks = (
                    blocks_from_markdown_text(markdown, heading_prefix=prefix)
                    if markdown.strip()
                    else []
                )
                if not chapter_blocks:
                    chapter_blocks = blocks_from_html(html, heading_prefix=prefix)
                blocks.extend(chapter_blocks)
    except zipfile.BadZipFile as exc:
        raise ParseError("EPUB 文件损坏或格式不正确") from exc
    except RuntimeError as exc:
        # 加密条目在 zipfile 里抛 RuntimeError，而不是 BadZipFile。
        raise ParseError("EPUB 内含加密章节，无法解压") from exc

    if not blocks:
        raise ParseError("未从 EPUB 中提取到文本内容")
    return blocks
