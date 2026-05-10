import pytest

from app.secrets_helper import (
    DecryptionError,
    decrypt,
    encrypt,
    is_encrypted_marker,
    unwrap_encrypted_values,
    wrap_secret,
)


def test_encrypt_decrypt_round_trip():
    plain = "sk-ant-api03-secret-token"
    cipher = encrypt(plain)
    assert cipher != plain
    assert decrypt(cipher) == plain


def test_decrypt_rejects_tampered_ciphertext():
    cipher = encrypt("hello")
    tampered = cipher[:-4] + "AAAA"
    with pytest.raises(DecryptionError):
        decrypt(tampered)


def test_wrap_secret_returns_marker():
    marker = wrap_secret("my-key")
    assert marker == {"_encrypted": True, "value": marker["value"]}
    assert decrypt(marker["value"]) == "my-key"


def test_is_encrypted_marker():
    assert is_encrypted_marker({"_encrypted": True, "value": "x"})
    assert not is_encrypted_marker({"_encrypted": False, "value": "x"})
    assert not is_encrypted_marker({"value": "x"})
    assert not is_encrypted_marker("plain string")
    assert not is_encrypted_marker(None)


def test_unwrap_encrypted_values_walks_nested_dict():
    cfg = {
        "llm_mode": "anthropic",
        "anthropic": {
            "api_key": wrap_secret("sk-test"),
            "model": "claude-sonnet-4-6",
        },
        "ollama": {
            "url": "http://x",
            "nested": {"deep_secret": wrap_secret("deep")},
        },
    }
    result = unwrap_encrypted_values(cfg)
    assert result["anthropic"]["api_key"] == "sk-test"
    assert result["anthropic"]["model"] == "claude-sonnet-4-6"
    assert result["ollama"]["nested"]["deep_secret"] == "deep"


def test_unwrap_passes_through_non_marker_values():
    assert unwrap_encrypted_values("plain") == "plain"
    assert unwrap_encrypted_values(42) == 42
    assert unwrap_encrypted_values([1, 2, 3]) == [1, 2, 3]
    assert unwrap_encrypted_values(None) is None
