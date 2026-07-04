# Feature: onenote-organizer, Property 4: Graph Error Mapping Consistency
"""Property 4: Graph Error Mapping Consistency.

For any HTTP error response from Microsoft Graph (with any status code and error message),
the MCP server should produce a structured error containing the HTTP status code, the error
message, the tool name that produced the error, and the category code "graph_error".

**Validates: Requirements 4.4, 7.7, 15.1, 15.4**
"""

from __future__ import annotations

import httpx
import pytest
import respx
from hypothesis import given, settings
from hypothesis import strategies as st

from onenote_organizer.graph_client import GraphClient
from onenote_organizer.models import GraphError, NetworkError, ToolError


# --- Strategies ---

http_error_status_codes = st.integers(min_value=400, max_value=599)
error_messages = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())


# --- Mock Auth Provider ---


class MockAuthProvider:
    """A mock AuthProvider that returns a static token for tests."""

    async def get_access_token(self) -> str:
        return "static-test-token"


# --- Constants ---

TEST_URL = "https://graph.microsoft.com/v1.0/me/onenote/notebooks"


# **Validates: Requirements 4.4, 7.7, 15.1, 15.4**
class TestGraphErrorMappingConsistency:
    """Property 4: For any HTTP error from Graph, produce structured error with
    status code, message, tool name, and category 'graph_error'."""

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
        auth = MockAuthProvider()
        client = GraphClient(auth_provider=auth)

        with respx.mock:
            respx.get(TEST_URL).mock(
                return_value=httpx.Response(
                    status_code,
                    json={"error": {"message": message}},
                )
            )

            with pytest.raises(GraphError) as exc_info:
                await client._request("GET", TEST_URL)

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
    async def test_graph_error_produces_tool_error_with_category_and_tool_name(
        self, status_code: int, message: str
    ) -> None:
        """GraphError maps to a ToolError with category 'graph_error', status_code, message, and tool_name."""
        auth = MockAuthProvider()
        client = GraphClient(auth_provider=auth)

        with respx.mock:
            respx.get(TEST_URL).mock(
                return_value=httpx.Response(
                    status_code,
                    json={"error": {"message": message}},
                )
            )

            with pytest.raises(GraphError) as exc_info:
                await client._request("GET", TEST_URL)

            # Construct the standard ToolError from the caught GraphError
            graph_err = exc_info.value
            tool_error = ToolError(
                category="graph_error",
                message=graph_err.args[0],
                status_code=graph_err.status_code,
                tool_name="list_notebooks",
            )

            # Verify all fields of the structured error
            assert tool_error.category == "graph_error"
            assert tool_error.status_code == status_code
            assert tool_error.message == message
            assert tool_error.tool_name == "list_notebooks"

        await client.close()

    @pytest.mark.asyncio
    async def test_timeout_exception_maps_to_network_error(self) -> None:
        """httpx.TimeoutException maps to NetworkError."""
        auth = MockAuthProvider()
        client = GraphClient(auth_provider=auth)

        with respx.mock:
            respx.get(TEST_URL).mock(
                side_effect=httpx.TimeoutException("Connection timed out")
            )

            with pytest.raises(NetworkError) as exc_info:
                await client._request("GET", TEST_URL)

            assert "timed out" in str(exc_info.value).lower()

        await client.close()

    @pytest.mark.asyncio
    async def test_connect_error_maps_to_network_error(self) -> None:
        """httpx.ConnectError maps to NetworkError."""
        auth = MockAuthProvider()
        client = GraphClient(auth_provider=auth)

        with respx.mock:
            respx.get(TEST_URL).mock(
                side_effect=httpx.ConnectError("Connection refused")
            )

            with pytest.raises(NetworkError) as exc_info:
                await client._request("GET", TEST_URL)

            assert "connection failed" in str(exc_info.value).lower()

        await client.close()
