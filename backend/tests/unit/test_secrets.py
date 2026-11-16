import base64

from app.core.secrets import decrypt_secret, encrypt_secret, mask_secret, reencrypt_secret


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
