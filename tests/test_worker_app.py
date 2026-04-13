"""Unit tests for worker FastAPI app endpoints.

Tests security mapping, health checks, Wi-Fi connection logic,
and ping functionality using mocking to avoid Windows/netsh dependencies.
"""
from __future__ import annotations

from unittest import mock

import pytest
from fastapi.testclient import TestClient

from worker.app import (
    SECURITY_MAP,
    ConnectRequest,
    PingRequest,
    WifiResponse,
    app,
)


client = TestClient(app)


# ---------------------------------------------------------------------------
# SECURITY_MAP tests
# ---------------------------------------------------------------------------

class TestSecurityMap:
    """Test SECURITY_MAP covers known security types with correct tuples."""

    def test_security_map_wpa2(self):
        """SECURITY_MAP 'wpa2' maps to WPA2PSK/AES auth/cipher tuple."""
        assert SECURITY_MAP["wpa2"] == ("WPA2PSK", "AES")

    def test_security_map_wpa2_personal(self):
        """SECURITY_MAP 'wpa2-personal' maps to WPA2PSK/AES."""
        assert SECURITY_MAP["wpa2-personal"] == ("WPA2PSK", "AES")

    def test_security_map_wpa3(self):
        """SECURITY_MAP 'wpa3' maps to WPA3SAE/AES auth/cipher tuple."""
        assert SECURITY_MAP["wpa3"] == ("WPA3SAE", "AES")

    def test_security_map_wpa3_personal(self):
        """SECURITY_MAP 'wpa3-personal' maps to WPA3SAE/AES."""
        assert SECURITY_MAP["wpa3-personal"] == ("WPA3SAE", "AES")

    def test_security_map_auto(self):
        """SECURITY_MAP 'auto' defaults to WPA2PSK/AES."""
        assert SECURITY_MAP["auto"] == ("WPA2PSK", "AES")

    def test_security_map_open(self):
        """SECURITY_MAP 'open' maps to open/none (unencrypted)."""
        assert SECURITY_MAP["open"] == ("open", "none")


# ---------------------------------------------------------------------------
# Health endpoint tests
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Test /health endpoint returns correct status."""

    def test_health_endpoint_returns_ok(self):
        """GET /health returns status ok and service identifier."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "worker"


# ---------------------------------------------------------------------------
# Wi-Fi connect endpoint tests
# ---------------------------------------------------------------------------

class TestWifiConnectAdapterNotFound:
    """Test wifi_connect when adapter_hint resolves to None."""

    def test_wifi_connect_adapter_hint_not_found(self):
        """When netsh.resolve_interface_by_hint returns None, error response."""
        with mock.patch("worker.wifi.netsh.resolve_interface_by_hint", return_value=None):
            req = ConnectRequest(
                ssid="TestSSID",
                password="testpass",
                adapter_hint="NoSuchAdapter",
            )
            response = client.post("/wifi/connect", json=req.model_dump())

        assert response.status_code == 200
        data = WifiResponse(**response.json())
        assert data.success is False
        assert data.step == "resolve_adapter"
        assert "No WLAN interface found" in data.error
        assert data.error_code == -1


class TestWifiConnectProfileAddFails:
    """Test wifi_connect when netsh.add_profile fails."""

    def test_wifi_connect_add_profile_failure(self):
        """When netsh.add_profile returns failure, stop and report error."""
        mock_interface = "Wireless"
        mock_result = {
            "success": False,
            "stdout": "Profile add output",
            "stderr": "Profile add failed",
            "return_code": 1,
        }

        with mock.patch("worker.wifi.netsh.resolve_interface_by_hint", return_value=mock_interface), \
             mock.patch("worker.app.retry_sync") as mock_retry:

            # First call to retry_sync is add_profile, return failure
            mock_retry.return_value = mock_result

            req = ConnectRequest(
                ssid="TestSSID",
                password="testpass",
                adapter_hint="Intel",
            )
            response = client.post("/wifi/connect", json=req.model_dump())

        assert response.status_code == 200
        data = WifiResponse(**response.json())
        assert data.success is False
        assert data.step == "add_profile"
        assert data.error_code == 1
        assert "Failed to add Wi-Fi profile" in data.error


class TestWifiConnectSecurityResolution:
    """Test security shorthand resolution in wifi_connect."""

    def test_wifi_connect_security_wpa3_resolution(self):
        """Passing security='wpa3' uses WPA3SAE/AES auth/cipher."""
        mock_interface = "Wireless"
        mock_add_result = {
            "success": True,
            "stdout": "",
            "stderr": "",
            "return_code": 0,
        }
        mock_connect_result = {
            "success": True,
            "stdout": "Connected",
            "stderr": "",
            "return_code": 0,
        }

        with mock.patch("worker.wifi.netsh.resolve_interface_by_hint", return_value=mock_interface), \
             mock.patch("worker.app.retry_sync") as mock_retry, \
             mock.patch("worker.wifi.verify.verify_connection") as mock_verify, \
             mock.patch("worker.wifi.netsh.get_interface_detail", return_value=None):

            # First call is add_profile, second is connect
            mock_retry.side_effect = [mock_add_result, mock_connect_result]
            mock_verify.return_value = {"success": True}

            req = ConnectRequest(
                ssid="TestSSID",
                password="testpass",
                adapter_hint="Intel",
                security="wpa3",
            )
            response = client.post("/wifi/connect", json=req.model_dump())

        # Verify that retry_sync was called with add_profile first
        calls = mock_retry.call_args_list
        assert len(calls) >= 1, f"Expected retry_sync calls, got {len(calls)}"
        # The first positional arg to retry_sync is the function (netsh.add_profile),
        # second is ssid. Check kwargs for auth/cipher.
        add_call = calls[0]
        assert add_call.kwargs.get("auth") == "WPA3SAE" or \
            (len(add_call.args) > 1 and "WPA3SAE" in str(add_call)), \
            f"Expected WPA3SAE auth in call: {add_call}"


# ---------------------------------------------------------------------------
# Ping endpoint tests
# ---------------------------------------------------------------------------

class TestPingEndpoint:
    """Test /net/ping endpoint response structure."""

    def test_ping_endpoint_response_structure(self):
        """Mock run_ping and verify ping response structure is correct."""
        mock_ping_result = {
            "success": True,
            "host": "192.168.1.100",
            "packets_sent": 4,
            "packets_received": 4,
            "loss_percent": 0.0,
            "avg_latency_ms": 12.5,
            "raw_output": "ping output",
            "artifact_path": None,
            "error": None,
        }

        with mock.patch("worker.app.run_ping", return_value=mock_ping_result):
            req = PingRequest(
                host="192.168.1.100",
                count=4,
                timeout_sec=5,
            )
            response = client.post("/net/ping", json=req.model_dump())

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["host"] == "192.168.1.100"
        assert data["packets_sent"] == 4
        assert data["packets_received"] == 4
        assert data["loss_percent"] == 0.0
        assert data["avg_latency_ms"] == 12.5
        assert data["raw_output"] == "ping output"
