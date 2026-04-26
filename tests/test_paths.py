"""Tests for profile key and path utilities in paths.py."""
import paths


def test_profile_key_is_deterministic():
    k1 = paths.profile_key("http://example.com:8080", "alice")
    k2 = paths.profile_key("http://example.com:8080", "alice")
    assert k1 == k2


def test_profile_key_length_is_16():
    k = paths.profile_key("http://example.com", "user")
    assert len(k) == 16
    assert all(c in "0123456789abcdef" for c in k)


def test_profile_key_is_case_insensitive():
    k1 = paths.profile_key("HTTP://EXAMPLE.COM:8080", "Alice")
    k2 = paths.profile_key("http://example.com:8080", "alice")
    assert k1 == k2


def test_profile_key_strips_trailing_slash():
    k1 = paths.profile_key("http://example.com:8080/", "user")
    k2 = paths.profile_key("http://example.com:8080", "user")
    assert k1 == k2


def test_profile_keys_are_unique_across_servers():
    k1 = paths.profile_key("http://server1.com", "user")
    k2 = paths.profile_key("http://server2.com", "user")
    assert k1 != k2


def test_profile_keys_are_unique_across_users():
    k1 = paths.profile_key("http://server.com", "alice")
    k2 = paths.profile_key("http://server.com", "bob")
    assert k1 != k2


def test_profile_cache_dir_created(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CACHE_DIR", tmp_path / "cache")
    d = paths.profile_cache_dir("http://example.com", "user")
    assert d.is_dir()


def test_profile_data_dir_created(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    d = paths.profile_data_dir("http://example.com", "user")
    assert d.is_dir()
