import pytest
from app.passwords import hash_password, verify_password, normalize_username


def test_salted_hash_and_wrong_password():
    secret = "a-long-test-password"
    first, second = hash_password(secret), hash_password(secret)
    assert first != second
    assert secret not in first
    assert verify_password(secret, first)
    assert not verify_password("incorrect", first)
    assert not verify_password(secret, "invalid")


def test_username_and_password_boundaries():
    assert normalize_username(" Employee ") == "employee"
    with pytest.raises(ValueError):
        normalize_username("invalid account")
    with pytest.raises(ValueError):
        hash_password("short")
