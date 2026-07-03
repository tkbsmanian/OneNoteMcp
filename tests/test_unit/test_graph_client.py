"""Unit tests for the Graph Client.

Tests paginated response assembly, error mapping for HTTP status codes,
timeout handling, and connection error handling.

Requirements: 4.4, 5.4, 15.1, 15.5
"""

from __future__ import annotations

import httpx
import pytest
import respx

from onenote_organizer.auth import AuthProvider
from onenote_organizer.graph_client import GraphClient
from onenote_organizer.models import GraphError, NetworkError


# --- Mock Auth Provider ---


class MockAuthProvider:
    """A mock AuthProvider that returns a static token for tests."""

    def __init__(self, token: str = "mock-access-token"):
        self._token = token

    async def get_access_token(self) -> str:
        return self._token


# --- Pagination Tests ---


class TestPaginatedGet:
    """Test _paginated_get follows @odata.nextLink and assembles all items."""

    @pytest.fixture
    def client(self):
        auth = MockAuthProvider()
        return GraphClient(auth)

    @respx.mock
    async def test_single_page_response(self, client: GraphClient):
        """Single page with no nextLink returns all items."""
        url = f"{client.BASE_URL}/me/onenote/notebooks"
        respx.get(url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "value": [
                        {"id": "nb-1", "displayName": "Notebook 1"},
                        {"id": "nb-2", "displayName": "Notebook 2"},
                    ]
                },
            )
        )

        items = await client._paginated_get(url)

        assert len(items) == 2
        assert items[0]["id"] == "nb-1"
        assert items[1]["id"] == "nb-2"

    @respx.mock
    async def test_two_page_response_with_next_link(self, client: GraphClient):
        """Two pages connected via @odata.nextLink collects all items."""
        base_url = f"{client.BASE_URL}/me/onenote/notebooks"
        next_url = f"{base_url}?$skiptoken=page2"

        # First page with nextLink
        respx.get(base_url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "value": [
                        {"id": "nb-1", "displayName": "Notebook 1"},
                        {"id": "nb-2", "displayName": "Notebook 2"},
                    ],
                    "@odata.nextLink": next_url,
                },
            )
        )

        # Second page without nextLink (last page)
        respx.get(next_url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "value": [
                        {"id": "nb-3", "displayName": "Notebook 3"},
                    ]
                },
            )
        )

        items = await client._paginated_get(base_url)

        assert len(items) == 3
        assert items[0]["id"] == "nb-1"
        assert items[1]["id"] == "nb-2"
        assert items[2]["id"] == "nb-3"

    @respx.mock
    async def test_empty_response(self, client: GraphClient):
        """Empty value array returns empty list."""
        url = f"{client.BASE_URL}/me/onenote/notebooks"
        respx.get(url).mock(
            return_value=httpx.Response(200, json={"value": []})
        )

        items = await client._paginated_get(url)

        assert items == []

    @respx.mock
    async def test_three_page_response(self, client: GraphClient):
        """Three pages linked via nextLink collects all items in order."""
        base_url = f"{client.BASE_URL}/me/onenote/sections/sec-1/pages"
        page2_url = f"{base_url}?$skiptoken=p2"
        page3_url = f"{base_url}?$skiptoken=p3"

        respx.get(base_url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "value": [{"id": "pg-1"}],
                    "@odata.nextLink": page2_url,
                },
            )
        )
        respx.get(page2_url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "value": [{"id": "pg-2"}],
                    "@odata.nextLink": page3_url,
                },
            )
        )
        respx.get(page3_url).mock(
            return_value=httpx.Response(
                200,
                json={"value": [{"id": "pg-3"}]},
            )
        )

        items = await client._paginated_get(base_url)

        assert len(items) == 3
        assert [item["id"] for item in items] == ["pg-1", "pg-2", "pg-3"]


# --- Error Mapping Tests ---


class TestErrorMapping:
    """Test that HTTP errors are mapped to GraphError with correct status codes."""

    @pytest.fixture
    def client(self):
        auth = MockAuthProvider()
        return GraphClient(auth)

    @respx.mock
    async def test_404_maps_to_graph_error(self, client: GraphClient):
        """404 response maps to GraphError with status_code=404."""
        url = f"{client.BASE_URL}/me/onenote/pages/nonexistent"
        respx.get(url).mock(
            return_value=httpx.Response(
                404,
                json={
                    "error": {
                        "code": "ErrorItemNotFound",
                        "message": "The requested resource was not found.",
                    }
                },
            )
        )

        with pytest.raises(GraphError) as exc_info:
            await client._request("GET", url)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value).lower()

    @respx.mock
    async def test_401_maps_to_graph_error(self, client: GraphClient):
        """401 response maps to GraphError with status_code=401."""
        url = f"{client.BASE_URL}/me/onenote/notebooks"
        respx.get(url).mock(
            return_value=httpx.Response(
                401,
                json={
                    "error": {
                        "code": "InvalidAuthenticationToken",
                        "message": "Access token has expired or is invalid.",
                    }
                },
            )
        )

        with pytest.raises(GraphError) as exc_info:
            await client._request("GET", url)

        assert exc_info.value.status_code == 401
        assert "token" in str(exc_info.value).lower()

    @respx.mock
    async def test_500_maps_to_graph_error(self, client: GraphClient):
        """500 response maps to GraphError with status_code=500."""
        url = f"{client.BASE_URL}/me/onenote/notebooks"
        respx.get(url).mock(
            return_value=httpx.Response(
                500,
                json={
                    "error": {
                        "code": "InternalServerError",
                        "message": "An internal server error occurred.",
                    }
                },
            )
        )

        with pytest.raises(GraphError) as exc_info:
            await client._request("GET", url)

        assert exc_info.value.status_code == 500
        assert "internal server error" in str(exc_info.value).lower()

    @respx.mock
    async def test_error_without_json_body(self, client: GraphClient):
        """HTTP error without JSON body still maps to GraphError."""
        url = f"{client.BASE_URL}/me/onenote/notebooks"
        respx.get(url).mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )

        with pytest.raises(GraphError) as exc_info:
            await client._request("GET", url)

        assert exc_info.value.status_code == 503

    @respx.mock
    async def test_error_message_extracted_from_graph_body(self, client: GraphClient):
        """Error message is extracted from Graph API error body."""
        url = f"{client.BASE_URL}/me/onenote/pages/pg-123"
        respx.get(url).mock(
            return_value=httpx.Response(
                403,
                json={
                    "error": {
                        "code": "AccessDenied",
                        "message": "You do not have permission to access this resource.",
                    }
                },
            )
        )

        with pytest.raises(GraphError) as exc_info:
            await client._request("GET", url)

        assert exc_info.value.status_code == 403
        assert "permission" in str(exc_info.value).lower()


# --- Timeout Handling Tests ---


class TestTimeoutHandling:
    """Test that timeout exceptions are mapped to NetworkError."""

    @pytest.fixture
    def client(self):
        auth = MockAuthProvider()
        return GraphClient(auth)

    @respx.mock
    async def test_timeout_maps_to_network_error(self, client: GraphClient):
        """httpx.TimeoutException maps to NetworkError."""
        url = f"{client.BASE_URL}/me/onenote/notebooks"
        respx.get(url).mock(side_effect=httpx.ReadTimeout("Read timed out"))

        with pytest.raises(NetworkError) as exc_info:
            await client._request("GET", url)

        assert "timed out" in str(exc_info.value).lower()

    @respx.mock
    async def test_connect_timeout_maps_to_network_error(self, client: GraphClient):
        """httpx.ConnectTimeout maps to NetworkError."""
        url = f"{client.BASE_URL}/me/onenote/notebooks"
        respx.get(url).mock(side_effect=httpx.ConnectTimeout("Connection timed out"))

        with pytest.raises(NetworkError) as exc_info:
            await client._request("GET", url)

        assert "timed out" in str(exc_info.value).lower()


# --- Connection Error Tests ---


class TestConnectionError:
    """Test that connection errors are mapped to NetworkError."""

    @pytest.fixture
    def client(self):
        auth = MockAuthProvider()
        return GraphClient(auth)

    @respx.mock
    async def test_connection_refused_maps_to_network_error(self, client: GraphClient):
        """httpx.ConnectError maps to NetworkError."""
        url = f"{client.BASE_URL}/me/onenote/notebooks"
        respx.get(url).mock(side_effect=httpx.ConnectError("Connection refused"))

        with pytest.raises(NetworkError) as exc_info:
            await client._request("GET", url)

        assert "connection failed" in str(exc_info.value).lower()


# --- Auth Header Injection Tests ---


class TestAuthHeaderInjection:
    """Test that the Bearer token is injected into requests."""

    @respx.mock
    async def test_bearer_token_sent_in_header(self):
        """Requests include Authorization: Bearer <token> header."""
        auth = MockAuthProvider(token="my-secret-token")
        client = GraphClient(auth)
        url = f"{client.BASE_URL}/me/onenote/notebooks"

        route = respx.get(url).mock(
            return_value=httpx.Response(200, json={"value": []})
        )

        await client._paginated_get(url)

        assert route.called
        request = route.calls[0].request
        assert request.headers["Authorization"] == "Bearer my-secret-token"
