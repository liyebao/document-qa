"""图片资料入库：只记录可核实的图像元信息，不伪造正文。

系统没有 OCR，因此图片里“写了什么”是未知的。这里诚实地返回一条元信息块
（格式、像素、色彩模式、文件大小），让资料在知识库里有正确的定位与描述，
而不是编造可检索文本，也不是直接失败——解析失败会被上层记为 FAILED，
反而让用户以为文件本身损坏。

图片内容要可检索属于 OCR 能力，不在本次范围内；接入 OCR 时只需替换本模块
的实现，注册表与调用方都不用改。
"""

from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.services.parsers.base import ParseError, TextBlock


def parse_image(data: bytes | Path) -> list[TextBlock]:
    raw = data if isinstance(data, bytes) else Path(data).read_bytes()
    try:
        with Image.open(BytesIO(raw)) as image:
            image_format = image.format or "未知"
            width, height = image.size
            mode = image.mode
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ParseError("图片文件损坏或格式不正确") from exc

    detail = "\n".join(
        (
            "图片资料（系统未启用 OCR，图片内的文字不会被提取）",
            f"图片格式：{image_format}",
            f"像素尺寸：{width} × {height}",
            f"色彩模式：{mode}",
            f"文件大小：{len(raw)} 字节",
        )
    )
    return [TextBlock(text=detail)]
