"""Tests for cross-platform VLC detection and launch logic."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import vlc_launcher


def test_find_vlc_returns_valid_custom_path(tmp_path):
    fake = tmp_path / "vlc"
    fake.write_text("")
    assert vlc_launcher.find_vlc(str(fake)) == str(fake)


def test_find_vlc_ignores_nonexistent_custom_path():
    with (
        patch.object(vlc_launcher, "_WIN_CANDIDATES", []),
        patch.object(vlc_launcher, "_MAC_CANDIDATES", []),
        patch("vlc_launcher.shutil.which", return_value=None),
        patch.object(vlc_launcher, "_lookup_registry", return_value=None),
    ):
        assert vlc_launcher.find_vlc("/does/not/exist") is None


def test_find_vlc_via_which(tmp_path):
    fake = tmp_path / "vlc"
    fake.write_text("")
    with (
        patch.object(vlc_launcher, "_WIN_CANDIDATES", []),
        patch.object(vlc_launcher, "_MAC_CANDIDATES", []),
        patch("vlc_launcher.shutil.which", return_value=str(fake)),
        patch.object(vlc_launcher, "_lookup_registry", return_value=None),
    ):
        assert vlc_launcher.find_vlc() == str(fake)


def test_find_vlc_returns_none_when_nothing_found():
    with (
        patch.object(vlc_launcher, "_WIN_CANDIDATES", []),
        patch.object(vlc_launcher, "_MAC_CANDIDATES", []),
        patch("vlc_launcher.shutil.which", return_value=None),
        patch.object(vlc_launcher, "_lookup_registry", return_value=None),
    ):
        assert vlc_launcher.find_vlc() is None


def test_lookup_registry_returns_none_on_non_windows():
    with patch("sys.platform", "darwin"):
        assert vlc_launcher._lookup_registry() is None

    with patch("sys.platform", "linux"):
        assert vlc_launcher._lookup_registry() is None


def test_win_candidates_are_exe_paths():
    assert len(vlc_launcher._WIN_CANDIDATES) >= 2
    assert all(c.lower().endswith("vlc.exe") for c in vlc_launcher._WIN_CANDIDATES)


def test_mac_candidates_reference_vlc_app():
    assert len(vlc_launcher._MAC_CANDIDATES) >= 1
    assert all("VLC.app" in c for c in vlc_launcher._MAC_CANDIDATES)


def test_play_uses_popen_when_vlc_found(tmp_path):
    fake = tmp_path / "vlc"
    fake.write_text("")
    url = "http://example.com/stream.m3u8"
    with patch("vlc_launcher.subprocess.Popen") as mock_popen:
        result = vlc_launcher.play(url, str(fake))
    assert result is True
    mock_popen.assert_called_once_with([str(fake), url], close_fds=True)


def test_play_returns_false_when_no_vlc_and_fallback_fails():
    with (
        patch.object(vlc_launcher, "find_vlc", return_value=None),
        patch("sys.platform", "linux"),
        patch("vlc_launcher.subprocess.Popen", side_effect=OSError("not found")),
    ):
        assert vlc_launcher.play("http://example.com/stream") is False


@pytest.mark.parametrize("platform,expected_cmd", [
    ("darwin", "open"),
    ("linux", "xdg-open"),
])
def test_play_fallback_uses_platform_command(platform, expected_cmd):
    with (
        patch.object(vlc_launcher, "find_vlc", return_value=None),
        patch("sys.platform", platform),
        patch("vlc_launcher.subprocess.Popen") as mock_popen,
    ):
        result = vlc_launcher.play("http://example.com/stream")
    assert result is True
    args = mock_popen.call_args[0][0]
    assert args[0] == expected_cmd
