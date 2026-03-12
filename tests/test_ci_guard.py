"""Unit tests for the CI guard script."""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ci_guard_no_local_wifi import scan_file, FORBIDDEN_PATTERNS


@pytest.fixture
def tmp_py_file(tmp_path: Path):
    """Helper to write a temporary .py file and return its path."""
    def _write(content: str, name: str = "test_module.py") -> Path:
        p = tmp_path / name
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return p
    return _write


def test_clean_file_has_no_violations(tmp_py_file):
    p = tmp_py_file("""\
        import httpx
        async def call_worker():
            r = await httpx.post("http://worker/wifi/connect")
            return r.json()
    """)
    assert scan_file(p) == []


def test_detects_wifi_connect_local(tmp_py_file):
    p = tmp_py_file("""\
        from worker.wifi import wifi_connect_local
        wifi_connect_local("TestSSID")
    """)
    violations = scan_file(p)
    assert len(violations) == 2
    assert all("wifi_connect_local" in v["pattern"] for v in violations)


def test_detects_netsh_wlan_connect(tmp_py_file):
    p = tmp_py_file("""\
        import subprocess
        subprocess.run("netsh wlan connect name=TestSSID", shell=True)
    """)
    violations = scan_file(p)
    assert len(violations) >= 1
    assert any("netsh" in v["pattern"] for v in violations)


def test_detects_netsh_wlan_disconnect(tmp_py_file):
    p = tmp_py_file("""\
        os.system("netsh wlan disconnect")
    """)
    violations = scan_file(p)
    assert len(violations) >= 1


def test_case_insensitive(tmp_py_file):
    p = tmp_py_file("""\
        WIFI_CONNECT_LOCAL("foo")
    """)
    violations = scan_file(p)
    assert len(violations) >= 1
