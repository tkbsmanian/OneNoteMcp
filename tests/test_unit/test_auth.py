"""Unit tests for the Auth Module.

Tests cover:
- Missing AZURE_CLIENT_ID raises AuthError before MSAL is called (Req 2.7)
- Corrupted token cache silently re-initiates device code flow (Req 2.10)
- Expired refresh token (acquire_token_silent returns None) triggers device code flow (Req 2.6)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from onenote_organizer.auth import DeviceCodeAuthProvider
from onenote_organizer.models import AuthError


class TestMissingClientId:
    """Validates: Requirements 2.6, 2.7"""

    def test_empty_client_id_raises_auth_error(self, monkeypatch: pytest.MonkeyPatch):
        """When client_id is empty and AZURE_CLIENT_ID is unset, AuthError is raised."""
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)

        with pytest.raises(AuthError, match="AZURE_CLIENT_ID"):
            DeviceCodeAuthProvider(client_id="")

    def test_none_client_id_and_no_env_raises_auth_error(self, monkeypatch: pytest.MonkeyPatch):
        """When client_id is None and AZURE_CLIENT_ID is unset, AuthError is raised."""
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)

        with pytest.raises(AuthError, match="AZURE_CLIENT_ID"):
            DeviceCodeAuthProvider(client_id=None)

    @patch("onenote_organizer.auth.msal.PublicClientApplication")
    def test_error_raised_before_msal_call(
        self, mock_msal_app: MagicMock, monkeypatch: pytest.MonkeyPatch
    ):
        """MSAL PublicClientApplication should never be instantiated when client_id is missing."""
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)

        with pytest.raises(AuthError):
            DeviceCodeAuthProvider(client_id="")

        mock_msal_app.assert_not_called()


class TestCorruptedTokenCache:
    """Validates: Requirements 2.10"""

    @patch("onenote_organizer.auth.msal.PublicClientApplication")
    async def test_corrupted_cache_triggers_device_code_flow(
        self, mock_msal_cls: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """When token cache file contains invalid encrypted data, device code flow is triggered."""
        # Write corrupted data to the token cache location
        cache_file = tmp_path / "onenote-organizer" / "token_cache.bin"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(b"corrupted-invalid-data-not-fernet")

        # Patch _get_token_cache_path to return our tmp file
        monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")

        # Setup mock MSAL app
        mock_app = MagicMock()
        mock_msal_cls.return_value = mock_app

        # get_accounts returns empty (since cache is corrupted/empty)
        mock_app.get_accounts.return_value = []

        # Device code flow mocks
        mock_app.initiate_device_flow.return_value = {
            "user_code": "ABC123",
            "verification_uri": "https://microsoft.com/devicelogin",
        }
        mock_app.acquire_token_by_device_flow.return_value = {
            "access_token": "fresh-token-after-corrupt-cache",
        }

        # Create provider with patched cache path
        with patch.object(
            DeviceCodeAuthProvider, "_get_token_cache_path", return_value=cache_file
        ):
            provider = DeviceCodeAuthProvider(client_id="test-client-id")

        # Override the app with our mock (since __init__ creates a real one after cache load)
        provider._app = mock_app

        token = await provider.get_access_token()

        # Verify device code flow was initiated (not silent acquisition)
        mock_app.initiate_device_flow.assert_called_once()
        mock_app.acquire_token_by_device_flow.assert_called_once()
        assert token == "fresh-token-after-corrupt-cache"

    @patch("onenote_organizer.auth.msal.PublicClientApplication")
    async def test_corrupted_cache_does_not_raise_error(
        self, mock_msal_cls: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Corrupted cache is handled silently—no exception propagated from _load_cache."""
        cache_file = tmp_path / "onenote-organizer" / "token_cache.bin"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(b"\x00\x01\x02\x03garbage-bytes")

        monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")

        mock_app = MagicMock()
        mock_msal_cls.return_value = mock_app
        mock_app.get_accounts.return_value = []
        mock_app.initiate_device_flow.return_value = {
            "user_code": "XYZ789",
            "verification_uri": "https://microsoft.com/devicelogin",
        }
        mock_app.acquire_token_by_device_flow.return_value = {
            "access_token": "token-after-silent-recovery",
        }

        with patch.object(
            DeviceCodeAuthProvider, "_get_token_cache_path", return_value=cache_file
        ):
            # Should NOT raise—corrupted cache is silently discarded
            provider = DeviceCodeAuthProvider(client_id="test-client-id")

        provider._app = mock_app
        token = await provider.get_access_token()
        assert token == "token-after-silent-recovery"


class TestExpiredRefreshToken:
    """Validates: Requirements 2.6"""

    @patch("onenote_organizer.auth.msal.PublicClientApplication")
    async def test_expired_token_triggers_device_code_flow(
        self, mock_msal_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ):
        """When acquire_token_silent returns None, device code flow is triggered."""
        monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")

        mock_app = MagicMock()
        mock_msal_cls.return_value = mock_app

        # Simulate an account in cache but token refresh fails
        mock_app.get_accounts.return_value = [{"username": "user@example.com"}]
        mock_app.acquire_token_silent.return_value = None  # Expired/invalid

        # Device code flow succeeds
        mock_app.initiate_device_flow.return_value = {
            "user_code": "DEF456",
            "verification_uri": "https://microsoft.com/devicelogin",
        }
        mock_app.acquire_token_by_device_flow.return_value = {
            "access_token": "new-token-after-expiry",
        }

        provider = DeviceCodeAuthProvider(client_id="test-client-id")
        provider._app = mock_app

        token = await provider.get_access_token()

        # Silent acquisition was attempted first
        mock_app.acquire_token_silent.assert_called_once()
        # Then device code flow was initiated
        mock_app.initiate_device_flow.assert_called_once()
        mock_app.acquire_token_by_device_flow.assert_called_once()
        assert token == "new-token-after-expiry"

    @patch("onenote_organizer.auth.msal.PublicClientApplication")
    async def test_silent_returns_error_dict_triggers_device_code_flow(
        self, mock_msal_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ):
        """When acquire_token_silent returns a dict without 'access_token', device code flow is triggered."""
        monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")

        mock_app = MagicMock()
        mock_msal_cls.return_value = mock_app

        # Silent returns an error response (no access_token key)
        mock_app.get_accounts.return_value = [{"username": "user@example.com"}]
        mock_app.acquire_token_silent.return_value = {
            "error": "invalid_grant",
            "error_description": "Refresh token has expired",
        }

        mock_app.initiate_device_flow.return_value = {
            "user_code": "GHI012",
            "verification_uri": "https://microsoft.com/devicelogin",
        }
        mock_app.acquire_token_by_device_flow.return_value = {
            "access_token": "token-after-error-response",
        }

        provider = DeviceCodeAuthProvider(client_id="test-client-id")
        provider._app = mock_app

        token = await provider.get_access_token()

        mock_app.initiate_device_flow.assert_called_once()
        assert token == "token-after-error-response"
