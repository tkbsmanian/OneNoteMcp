"""Property 4: Graph Error Mapping Consistency.

For any HTTP error response from Microsoft Graph (with any status code and error message),
the MCP server should produce a structured error containing the HTTP status code, the error
message, the tool name that produced the error, and the category code "graph_error".

Validates: Requirements 4.4, 7.7, 15.1, 15.4
"""

# Feature: onenote-organizer, Property 4: Graph Error Mapping Consistency

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from onenote_organizer.graph_client import GraphClient
from onenote_organizer.models import GraphError, NetworkError


# --- Strategies ---

http_error_status_codes = st.integers(min_value=400, max_value=599)
error_messages = st.text(min_size=1, max_size=300).filter(lambda s: s.strip())


# --- Helpers ---


def _make_mock_auth() -> AsyncMock:
    """Create a mock auth provider that returns a static token."""
    auth = AsyncMock()
    auth.get_access_token = AsyncMock(return_value="fake-token")
    return auth


def _make_http_error_response(status_code: int, message: str) -> httpx.Response:
    """Create an httpx.Response that simulates a Graph API error response."""
    error_body = json.dumps({"error": {"message": message}})
    response = httpx.Response(
        status_code=status_code,
        content=error_body.encode("utf-8"),
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", "https://graph.microsoft.com/v1.0/test"),
    )
    return response


# **Validates: Requirements 4.4, 7.7, 15.1, 15.4**
class TestGraphErrorMappingConsistency:
    """Property 4: For any HTTP error from Graph, produce structured error with
    status code, message, and category 'graph_error'."""

    @given(
        status_code=http_error_status_codes,
        message=error_messages,
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_http_error_maps_to_graph_error_with_status_and_message(
        self, status_code: int, message: str
    ) -> None:
        """Any HTTP error from Graph produces a GraphError with correct status_code and message."""
        auth = _make_mock_auth()
        client = GraphClient(auth_provider=auth)

        # Create a mock response that raises HTTPStatusError
        error_response = _make_http_error_response(status_code, message)

        # Patch the internal httpx client to return the error response
        async def mock_request(*args, **kwargs):
            return error_response

        client._client.request = mock_request  # type: ignore[assignment]

        with pytest.raises(GraphError) as exc_info:
            await client._request("GET", "https://graph.microsoft.com/v1.0/test")

        # Verify the GraphError has the correct status code and message
        assert exc_info.value.status_code == status_code
        assert exc_info.value.args[0] == message

        await client.close()

    @given(
        status_code=http_error_status_codes,
        message=error_messages,
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_graph_error_can_populate_tool_error_with_category(
        self, status_code: int, message: str
    ) -> None:
        """GraphError can be used to construct a ToolError with category 'graph_error'."""
        from onenote_organizer.models import ToolError

        auth = _make_mock_auth()
        client = GraphClient(auth_provider=auth)

        error_response = _make_http_error_response(status_code, message)

        async def mock_request(*args, **kwargs):
            return error_response

        client._client.request = mock_request  # type: ignore[assignment]

        with pytest.raises(GraphError) as exc_info:
            await client._request("GET", "https://graph.microsoft.com/v1.0/test")

        # Verify we can construct the standard ToolError from the GraphError
        graph_err = exc_info.value
        tool_error = ToolError(
            category="graph_error",
            message=graph_err.args[0],
            status_code=graph_err.status_code,
            tool_name="test_tool",
        )

        assert tool_error.category == "graph_error"
        assert tool_error.status_code == status_code
        assert tool_error.message == message
        assert tool_error.tool_name == "test_tool"

        await client.close()

    @pytest.mark.asyncio
    async def test_timeout_exception_maps_to_network_error(self) -> None:
        """Timeout exceptions from httpx map to NetworkError."""
        auth = _make_mock_auth()
        client = GraphClient(auth_provider=auth)

        async def mock_request(*args, **kwargs):
            raise httpx.TimeoutException("Connection timed out")

        client._client.request = mock_request  # type: ignore[assignment]

        with pytest.raises(NetworkError) as exc_info:
            await client._request("GET", "https://graph.microsoft.com/v1.0/test")

        assert "timed out" in str(exc_info.value).lower()

        await client.close()

    @pytest.mark.asyncio
    async def test_connect_error_maps_to_network_error(self) -> None:
        """Connection errors from httpx map to NetworkError."""
        auth = _make_mock_auth()
        client = GraphClient(auth_provider=auth)

        async def mock_request(*args, **kwargs):
            raise httpx.ConnectError("Connection refused")

        client._client.request = mock_request  # type: ignore[assignment]

        with pytest.raises(NetworkError) as exc_info:
            await client._request("GET", "https://graph.microsoft.com/v1.0/test")

        assert "connection failed" in str(exc_info.value).lower()

        await client.close()
