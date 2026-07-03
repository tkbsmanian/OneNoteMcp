"""Authentication module for the OneNote Organizer MCP Server.

Provides a Protocol-based interface for authentication and a concrete
implementation using Microsoft's device code OAuth 2.0 flow via MSAL.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import platform
import sys
import uuid
from pathlib import Path
from typing import Protocol

import msal
from cryptography.fernet import Fernet, InvalidToken

from onenote_organizer.models import AuthError

# Scopes required for OneNote access
SCOPES = ["Notes.Read", "Notes.ReadWrite"]


class AuthProvider(Protocol):
    """Interface for authentication providers."""

    async def get_access_token(self) -> str:
        """Return a valid access token or raise AuthError."""
        ...


class DeviceCodeAuthProvider:
    """MSAL-based device code flow authentication.

    Handles token acquisition, silent refresh, and encrypted token cache
    persistence. Reads configuration from environment variables.
    """

    def __init__(
        self,
        client_id: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        """Initialize the auth provider.

        Args:
            client_id: Azure app registration client ID. If not provided,
                reads from AZURE_CLIENT_ID environment variable.
            tenant_id: Azure AD tenant ID. If not provided, reads from
                AZURE_TENANT_ID environment variable, defaulting to "common".

        Raises:
            AuthError: If AZURE_CLIENT_ID is not set and client_id is not provided.
        """
        self._client_id = client_id or os.environ.get("AZURE_CLIENT_ID", "")
        if not self._client_id:
            raise AuthError(
                "AZURE_CLIENT_ID environment variable is required but not set. "
                "Please set it to your Azure app registration client ID."
            )

        self._tenant_id = tenant_id or os.environ.get("AZURE_TENANT_ID", "common")
        self._authority = f"https://login.microsoftonline.com/{self._tenant_id}"

        # Initialize token cache and MSAL app
        self._cache = msal.SerializableTokenCache()
        self._load_cache()
        self._app = msal.PublicClientApplication(
            client_id=self._client_id,
            authority=self._authority,
            token_cache=self._cache,
        )

    async def get_access_token(self) -> str:
        """Acquire a valid access token.

        Attempts silent token refresh first. If that fails, initiates
        the device code flow for interactive authentication.

        Returns:
            A valid access token string.

        Raises:
            AuthError: If token acquisition fails or times out.
        """
        # Try silent acquisition first
        accounts = self._app.get_accounts()
        if accounts:
            result = await asyncio.to_thread(
                self._app.acquire_token_silent,
                SCOPES,
                account=accounts[0],
            )
            if result and "access_token" in result:
                self._save_cache()
                return result["access_token"]

        # Silent acquisition failed; initiate device code flow
        return await self._device_code_flow()

    async def _device_code_flow(self) -> str:
        """Execute the device code flow for interactive authentication.

        Returns:
            A valid access token string.

        Raises:
            AuthError: If the flow fails or times out.
        """
        flow = await asyncio.to_thread(
            self._app.initiate_device_flow, SCOPES
        )

        if "user_code" not in flow:
            error_desc = flow.get("error_description", "Unknown error initiating device code flow")
            raise AuthError(
                f"Failed to initiate device code flow: {error_desc}"
            )

        # Present the device code to the user via stderr
        verification_uri = flow.get("verification_uri", "https://microsoft.com/devicelogin")
        user_code = flow["user_code"]
        message = (
            f"To authenticate, visit {verification_uri} "
            f"and enter the code: {user_code}"
        )
        print(message, file=sys.stderr)

        # Wait for user to complete authentication
        result = await asyncio.to_thread(
            self._app.acquire_token_by_device_flow, flow
        )

        if "access_token" not in result:
            error = result.get("error", "unknown_error")
            error_description = result.get("error_description", "Authentication failed")

            if "expired" in error_description.lower() or error == "authorization_pending":
                raise AuthError(
                    f"Device code flow timed out. The authentication code has expired. "
                    f"Please try again and visit {verification_uri} to enter the new code."
                )

            raise AuthError(
                f"Authentication failed: {error_description}. "
                f"Please try again and visit {verification_uri} to authenticate."
            )

        self._save_cache()
        return result["access_token"]

    def _get_token_cache_path(self) -> Path:
        """Return platform-appropriate path for encrypted token cache."""
        if platform.system() == "Windows":
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        elif platform.system() == "Darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

        cache_dir = base / "onenote-organizer"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "token_cache.bin"

    def _derive_encryption_key(self) -> bytes:
        """Derive a Fernet encryption key from machine-specific data.

        Uses a combination of machine ID, platform info, and the client ID
        to produce a deterministic key unique to this machine and app.
        """
        # Gather machine-specific components
        components = [
            platform.node(),  # hostname
            str(uuid.getnode()),  # MAC address as integer
            platform.system(),
            platform.machine(),
            self._client_id,
        ]
        seed = "|".join(components).encode("utf-8")
        # Derive a 32-byte key using SHA-256, then base64-encode for Fernet
        raw_key = hashlib.sha256(seed).digest()
        return base64.urlsafe_b64encode(raw_key)

    def _load_cache(self) -> None:
        """Load and decrypt the token cache from disk.

        If the cache file doesn't exist or cannot be decrypted,
        starts with an empty cache (device code flow will be triggered).
        """
        cache_path = self._get_token_cache_path()
        if not cache_path.exists():
            return

        try:
            encrypted_data = cache_path.read_bytes()
            fernet = Fernet(self._derive_encryption_key())
            decrypted_data = fernet.decrypt(encrypted_data)
            self._cache.deserialize(decrypted_data.decode("utf-8"))
        except (InvalidToken, ValueError, OSError):
            # Cache is corrupted or unreadable; start fresh
            # Device code flow will be re-initiated
            pass

    def _save_cache(self) -> None:
        """Encrypt and save the token cache to disk.

        If writing fails, the error is silently ignored (the next session
        will simply re-authenticate via device code flow).
        """
        if not self._cache.has_state_changed:
            return

        try:
            cache_path = self._get_token_cache_path()
            fernet = Fernet(self._derive_encryption_key())
            serialized = self._cache.serialize()
            encrypted_data = fernet.encrypt(serialized.encode("utf-8"))
            cache_path.write_bytes(encrypted_data)
        except OSError:
            # Silent failure — next session will re-authenticate
            pass
