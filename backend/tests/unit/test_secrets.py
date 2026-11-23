import base64

import pytest

from app.core.errors import AppError
from app.core.secrets import (
    decrypt_secret,
    encrypt_secret,
    mask_secret,
    read_secret,
    reencrypt_secret,
)


def test_encrypt_and_decrypt_roundtrip() -> None:
    ciphertext, key_version = encrypt_secret("sk-test-1234567890")
    assert ciphertext != "sk-test-1234567890"
    assert key_version == 1
    assert decrypt_secret(ciphertext, key_version) == "sk-test-1234567890"


def test_same_plaintext_uses_different_nonce() -> None:
    first, _ = encrypt_secret("sk-test-1234567890")
    second, _ = encrypt_secret("sk-test-1234567890")
    assert first != second


def test_mask_secret_keeps_only_edges() -> None:
    assert mask_secret("sk-test-1234567890") == "sk-****7890"
    assert mask_secret("short") == "****"


def test_reencrypt_secret_moves_to_new_key_and_version() -> None:
    old_key = base64.urlsafe_b64encode(b"a" * 32).decode()
    new_key = base64.urlsafe_b64encode(b"b" * 32).decode()
    ciphertext, version = encrypt_secret("sk-rotate", key=old_key, key_version=1)

    rotated, rotated_version = reencrypt_secret(
        ciphertext,
        old_key=old_key,
        old_version=version,
        new_key=new_key,
        new_version=2,
    )

    assert rotated_version == 2
    assert rotated != ciphertext
    assert decrypt_secret(rotated, 2, key=new_key) == "sk-rotate"


def test_read_secret_reports_unreadable_credential_as_409() -> None:
    old_key = base64.urlsafe_b64encode(b"z" * 32).decode()
    ciphertext, key_version = encrypt_secret("sk-lost", key=old_key, key_version=1)

    with pytest.raises(AppError) as excinfo:
        read_secret(ciphertext, key_version)

    assert excinfo.value.code == "CREDENTIAL_UNREADABLE"
    assert excinfo.value.status_code == 409
    assert "重新填写" in excinfo.value.message


def test_read_secret_reports_version_mismatch_as_409() -> None:
    ciphertext, _ = encrypt_secret("sk-current")

    with pytest.raises(AppError) as excinfo:
        read_secret(ciphertext, 99)

    assert excinfo.value.code == "CREDENTIAL_UNREADABLE"
