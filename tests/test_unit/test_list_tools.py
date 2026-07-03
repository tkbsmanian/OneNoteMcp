"""Unit tests for list_notebooks, list_sections, and list_pages tools."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from onenote_organizer.models import (
    AuthError,
    GraphError,
    NetworkError,
    Notebook,
    PageMetadata,
    Section,
)
from onenote_organizer.server import list_notebooks, list_pages, list_sections


@pytest.fixture(autouse=True)
def reset_graph_client():
    """Reset the module-level _graph_client before each test."""
    import onenote_organizer.server as server_mod

    server_mod._graph_client = None
    yield
    server_mod._graph_client = None


@pytest.fixture
def mock_graph_client():
    """Provide a mock GraphClient that gets injected into server._graph_client."""
    import onenote_organizer.server as server_mod

    client = AsyncMock()
    server_mod._graph_client = client
    return client


# --- list_notebooks tests ---


@pytest.mark.asyncio
async def test_list_notebooks_success(mock_graph_client):
    """list_notebooks returns correctly shaped objects on success."""
    mock_graph_client.list_notebooks.return_value = [
        Notebook(id="nb-1", display_name="Work"),
        Notebook(id="nb-2", display_name="Personal"),
    ]

    result = await list_notebooks()

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0] == {"id": "nb-1", "displayName": "Work"}
    assert result[1] == {"id": "nb-2", "displayName": "Personal"}


@pytest.mark.asyncio
async def test_list_notebooks_empty(mock_graph_client):
    """list_notebooks returns empty array when no notebooks exist."""
    mock_graph_client.list_notebooks.return_value = []

    result = await list_notebooks()

    assert result == []


@pytest.mark.asyncio
async def test_list_notebooks_auth_error(mock_graph_client):
    """list_notebooks returns auth_error when authentication fails."""
    mock_graph_client.list_notebooks.side_effect = AuthError("Token expired")

    result = await list_notebooks()

    assert result["success"] is False
    assert result["error"]["category"] == "auth_error"
    assert result["error"]["toolName"] == "list_notebooks"
    assert "Token expired" in result["error"]["message"]


@pytest.mark.asyncio
async def test_list_notebooks_graph_error(mock_graph_client):
    """list_notebooks returns graph_error with status code on Graph failure."""
    mock_graph_client.list_notebooks.side_effect = GraphError(
        "Service unavailable", status_code=503
    )

    result = await list_notebooks()

    assert result["success"] is False
    assert result["error"]["category"] == "graph_error"
    assert result["error"]["statusCode"] == 503
    assert result["error"]["toolName"] == "list_notebooks"


@pytest.mark.asyncio
async def test_list_notebooks_network_error(mock_graph_client):
    """list_notebooks returns network_error on connectivity failures."""
    mock_graph_client.list_notebooks.side_effect = NetworkError("Connection timed out")

    result = await list_notebooks()

    assert result["success"] is False
    assert result["error"]["category"] == "network_error"
    assert result["error"]["toolName"] == "list_notebooks"


@pytest.mark.asyncio
async def test_list_notebooks_missing_client_id():
    """list_notebooks returns auth_error when AZURE_CLIENT_ID is not set."""
    with patch.dict("os.environ", {}, clear=True):
        result = await list_notebooks()

    assert result["success"] is False
    assert result["error"]["category"] == "auth_error"
    assert "AZURE_CLIENT_ID" in result["error"]["message"]


# --- list_sections tests ---


@pytest.mark.asyncio
async def test_list_sections_success(mock_graph_client):
    """list_sections returns correctly shaped objects on success."""
    mock_graph_client.list_sections.return_value = [
        Section(id="sec-1", display_name="Meetings", notebook_id="nb-1"),
        Section(id="sec-2", display_name="Notes", notebook_id="nb-1"),
    ]

    result = await list_sections("nb-1")

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0] == {"id": "sec-1", "displayName": "Meetings"}
    assert result[1] == {"id": "sec-2", "displayName": "Notes"}


@pytest.mark.asyncio
async def test_list_sections_empty(mock_graph_client):
    """list_sections returns empty array when no sections exist."""
    mock_graph_client.list_sections.return_value = []

    result = await list_sections("nb-1")

    assert result == []


@pytest.mark.asyncio
async def test_list_sections_validation_empty_id(mock_graph_client):
    """list_sections returns validation_error when notebook_id is empty."""
    result = await list_sections("")

    assert result["success"] is False
    assert result["error"]["category"] == "validation_error"
    assert result["error"]["toolName"] == "list_sections"
    assert "notebook_id" in result["error"]["invalidFields"]


@pytest.mark.asyncio
async def test_list_sections_validation_whitespace_id(mock_graph_client):
    """list_sections returns validation_error when notebook_id is whitespace-only."""
    result = await list_sections("   ")

    assert result["success"] is False
    assert result["error"]["category"] == "validation_error"
    assert result["error"]["toolName"] == "list_sections"
    assert "notebook_id" in result["error"]["invalidFields"]


@pytest.mark.asyncio
async def test_list_sections_graph_error_not_found(mock_graph_client):
    """list_sections returns graph_error when notebook is not found."""
    mock_graph_client.list_sections.side_effect = GraphError(
        "The notebook was not found", status_code=404
    )

    result = await list_sections("nb-nonexistent")

    assert result["success"] is False
    assert result["error"]["category"] == "graph_error"
    assert result["error"]["statusCode"] == 404
    assert result["error"]["toolName"] == "list_sections"


@pytest.mark.asyncio
async def test_list_sections_auth_error(mock_graph_client):
    """list_sections returns auth_error when authentication fails."""
    mock_graph_client.list_sections.side_effect = AuthError("Not authenticated")

    result = await list_sections("nb-1")

    assert result["success"] is False
    assert result["error"]["category"] == "auth_error"
    assert result["error"]["toolName"] == "list_sections"


# --- list_pages tests ---


@pytest.mark.asyncio
async def test_list_pages_success(mock_graph_client):
    """list_pages returns correctly shaped objects with title and lastModifiedDateTime."""
    dt = datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    mock_graph_client.list_pages.return_value = [
        PageMetadata(id="pg-1", title="Meeting Notes", last_modified=dt, section_id="sec-1"),
        PageMetadata(id="pg-2", title="TODO List", last_modified=dt, section_id="sec-1"),
    ]

    result = await list_pages("sec-1")

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["id"] == "pg-1"
    assert result[0]["title"] == "Meeting Notes"
    assert result[0]["lastModifiedDateTime"] == dt.isoformat()
    assert result[1]["id"] == "pg-2"
    assert result[1]["title"] == "TODO List"


@pytest.mark.asyncio
async def test_list_pages_empty(mock_graph_client):
    """list_pages returns empty array when no pages exist."""
    mock_graph_client.list_pages.return_value = []

    result = await list_pages("sec-1")

    assert result == []


@pytest.mark.asyncio
async def test_list_pages_validation_empty_id(mock_graph_client):
    """list_pages returns validation_error when section_id is empty."""
    result = await list_pages("")

    assert result["success"] is False
    assert result["error"]["category"] == "validation_error"
    assert result["error"]["toolName"] == "list_pages"
    assert "section_id" in result["error"]["invalidFields"]


@pytest.mark.asyncio
async def test_list_pages_validation_whitespace_id(mock_graph_client):
    """list_pages returns validation_error when section_id is whitespace-only."""
    result = await list_pages("   \t  ")

    assert result["success"] is False
    assert result["error"]["category"] == "validation_error"
    assert result["error"]["toolName"] == "list_pages"
    assert "section_id" in result["error"]["invalidFields"]


@pytest.mark.asyncio
async def test_list_pages_graph_error_not_found(mock_graph_client):
    """list_pages returns graph_error when section is not found."""
    mock_graph_client.list_pages.side_effect = GraphError(
        "The section was not found", status_code=404
    )

    result = await list_pages("sec-nonexistent")

    assert result["success"] is False
    assert result["error"]["category"] == "graph_error"
    assert result["error"]["statusCode"] == 404
    assert result["error"]["toolName"] == "list_pages"


@pytest.mark.asyncio
async def test_list_pages_network_error(mock_graph_client):
    """list_pages returns network_error on connectivity failures."""
    mock_graph_client.list_pages.side_effect = NetworkError("Request timed out")

    result = await list_pages("sec-1")

    assert result["success"] is False
    assert result["error"]["category"] == "network_error"
    assert result["error"]["toolName"] == "list_pages"
