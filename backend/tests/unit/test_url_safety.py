import ipaddress

import pytest

from app.core.errors import AppError
from app.services.sources import build_markdown_filename, validate_url
from app.services.sources.url import _is_public_ip


def test_validate_url_rejects_non_http_schemes() -> None:
    for url in ("file:///etc/passwd", "ftp://example.com/a", "javascript:alert(1)"):
        with pytest.raises(AppError) as exc:
            validate_url(url)
        assert exc.value.code == "INVALID_URL"


def test_validate_url_rejects_local_and_private_hosts() -> None:
    for url in (
        "http://localhost/a",
        "http://127.0.0.1/a",
        "http://10.0.0.5/a",
        "http://192.168.1.10:8080/a",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/a",
    ):
        with pytest.raises(AppError) as exc:
            validate_url(url)
        assert exc.value.code in {"URL_FORBIDDEN", "INVALID_URL"}


def test_validate_url_rejects_userinfo() -> None:
    with pytest.raises(AppError) as exc:
        validate_url("http://user:secret@example.com/a")
    assert exc.value.code == "INVALID_URL"


def test_build_markdown_filename_strips_path_characters() -> None:
    assert build_markdown_filename("报告/2026:预算") == "报告 2026 预算.md"
    assert build_markdown_filename("") == "网页.md"


def test_cgnat_and_reserved_addresses_are_not_public() -> None:
    for value in ("100.64.0.1", "198.18.0.1", "169.254.169.254", "::ffff:127.0.0.1"):
        assert not _is_public_ip(ipaddress.ip_address(value))


def test_public_address_is_allowed() -> None:
    assert _is_public_ip(ipaddress.ip_address("8.8.8.8"))
