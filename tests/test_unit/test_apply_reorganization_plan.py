"""Unit tests for apply_reorganization_plan tool."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from onenote_organizer.models import (
    AuthError,
    GraphError,
    NetworkError,
    OperationResult,
    PageMetadata,
    Section,
)
from onenote_organizer.server import apply_reorganization_plan


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


def _valid_plan():
    """Return a minimal valid plan for testing."""
    return {
        "suggestedSections": [
            {"displayName": "Work", "notebookId": "nb-1"},
        ],
        "pageMoves": [
            {
                "pageId": "pg-1",
                "sourceSectionId": "sec-old",
                "targetSectionDisplayName": "Work",
            },
        ],
    }


# --- Plan structure validation tests ---


@pytest.mark.asyncio
async def test_invalid_plan_not_dict():
    """Returns validation error if plan is not a dictionary."""
    result = await apply_reorganization_plan(plan="not-a-dict")

    assert result["success"] is False
    assert result["error"]["category"] == "validation_error"
    assert result["error"]["toolName"] == "apply_reorganization_plan"


@pytest.mark.asyncio
async def test_missing_suggested_sections():
    """Returns validation error if suggestedSections is missing."""
    result = await apply_reorganization_plan(plan={"pageMoves": []})

    assert result["success"] is False
    assert result["error"]["category"] == "validation_error"
    assert "suggestedSections" in result["error"]["invalidFields"]


@pytest.mark.asyncio
async def test_missing_page_moves():
    """Returns validation error if pageMoves is missing."""
    result = await apply_reorganization_plan(
        plan={"suggestedSections": []}
    )

    assert result["success"] is False
    assert result["error"]["category"] == "validation_error"
    assert "pageMoves" in result["error"]["invalidFields"]


@pytest.mark.asyncio
async def test_invalid_suggested_section_missing_fields():
    """Returns validation error for suggestedSection missing required fields."""
    plan = {
        "suggestedSections": [{"displayName": "Work"}],  # missing notebookId
        "pageMoves": [],
    }
    result = await apply_reorganization_plan(plan=plan)

    assert result["success"] is False
    assert result["error"]["category"] == "validation_error"
    assert any("notebookId" in k for k in result["error"]["invalidFields"])


@pytest.mark.asyncio
async def test_invalid_page_move_missing_fields():
    """Returns validation error for pageMove missing required fields."""
    plan = {
        "suggestedSections": [],
        "pageMoves": [{"pageId": "pg-1"}],  # missing other fields
    }
    result = await apply_reorganization_plan(plan=plan)

    assert result["success"] is False
    assert result["error"]["category"] == "validation_error"
    assert any("sourceSectionId" in k for k in result["error"]["invalidFields"])


# --- Reference validation tests ---


@pytest.mark.asyncio
async def test_nonexistent_notebook_blocks_execution(mock_graph_client):
    """Returns validation error listing invalid notebook without any mutations."""
    plan = _valid_plan()
    mock_graph_client.list_sections.side_effect = GraphError("Not found", status_code=404)
    # Pages exist
    mock_graph_client.get_page_metadata.return_value = PageMetadata(
        id="pg-1", title="Test", last_modified=datetime.now(timezone.utc)
    )

    result = await apply_reorganization_plan(plan=plan)

    assert result["success"] is False
    assert result["error"]["category"] == "validation_error"
    assert "notebook:nb-1" in result["error"]["invalidFields"]
    # Ensure no mutations were attempted
    mock_graph_client.create_section.assert_not_called()
    mock_graph_client.copy_page_to_section.assert_not_called()


@pytest.mark.asyncio
async def test_nonexistent_page_blocks_execution(mock_graph_client):
    """Returns validation error listing invalid page without any mutations."""
    plan = _valid_plan()
    # Notebook exists
    mock_graph_client.list_sections.return_value = []
    # Page does not exist
    mock_graph_client.get_page_metadata.side_effect = GraphError("Not found", status_code=404)

    result = await apply_reorganization_plan(plan=plan)

    assert result["success"] is False
    assert result["error"]["category"] == "validation_error"
    assert "page:pg-1" in result["error"]["invalidFields"]
    mock_graph_client.create_section.assert_not_called()


# --- Dry-run mode tests ---


@pytest.mark.asyncio
async def test_dry_run_returns_forecast(mock_graph_client):
    """Dry-run validates plan, returns forecast without making mutations."""
    plan = _valid_plan()
    # Notebook and pages exist
    mock_graph_client.list_sections.return_value = []
    mock_graph_client.get_page_metadata.return_value = PageMetadata(
        id="pg-1", title="Test", last_modified=datetime.now(timezone.utc)
    )

    result = await apply_reorganization_plan(plan=plan, dry_run=True)

    assert result["success"] is True
    assert result["dryRun"] is True
    assert "Would create 1 sections and move 1 pages" in result["summary"]
    # No mutations
    mock_graph_client.create_section.assert_not_called()
    mock_graph_client.copy_page_to_section.assert_not_called()


# --- Live mode tests ---


@pytest.mark.asyncio
async def test_live_mode_creates_sections_and_moves_pages(mock_graph_client):
    """Live mode creates sections and moves pages successfully."""
    plan = _valid_plan()
    # Validation: notebook and pages exist
    mock_graph_client.list_sections.return_value = []
    mock_graph_client.get_page_metadata.return_value = PageMetadata(
        id="pg-1", title="Test", last_modified=datetime.now(timezone.utc)
    )
    # Section creation succeeds
    mock_graph_client.create_section.return_value = Section(
        id="sec-new", display_name="Work", notebook_id="nb-1"
    )
    # Page move succeeds
    mock_graph_client.copy_page_to_section.return_value = "http://op-url"
    mock_graph_client.poll_operation.return_value = OperationResult(
        status="completed", resource_id="new-page-id"
    )

    result = await apply_reorganization_plan(plan=plan, dry_run=False)

    assert result["success"] is True
    assert "Created 1 sections and moved 1 pages" in result["summary"]
    assert "errors" not in result
    mock_graph_client.create_section.assert_called_once_with("nb-1", "Work")
    mock_graph_client.copy_page_to_section.assert_called_once_with("pg-1", "sec-new")


# --- Partial failure tests ---


@pytest.mark.asyncio
async def test_section_creation_failure_skips_dependent_moves(mock_graph_client):
    """When a section creation fails, page moves targeting it are skipped."""
    plan = {
        "suggestedSections": [
            {"displayName": "Work", "notebookId": "nb-1"},
            {"displayName": "Personal", "notebookId": "nb-1"},
        ],
        "pageMoves": [
            {
                "pageId": "pg-1",
                "sourceSectionId": "sec-old",
                "targetSectionDisplayName": "Work",
            },
            {
                "pageId": "pg-2",
                "sourceSectionId": "sec-old",
                "targetSectionDisplayName": "Personal",
            },
        ],
    }
    # Validation passes
    mock_graph_client.list_sections.return_value = []
    mock_graph_client.get_page_metadata.return_value = PageMetadata(
        id="pg-1", title="Test", last_modified=datetime.now(timezone.utc)
    )
    # First section creation fails, second succeeds
    mock_graph_client.create_section.side_effect = [
        GraphError("Failed", status_code=500),
        Section(id="sec-personal", display_name="Personal", notebook_id="nb-1"),
    ]
    # Page move for "Personal" succeeds
    mock_graph_client.copy_page_to_section.return_value = "http://op-url"
    mock_graph_client.poll_operation.return_value = OperationResult(
        status="completed", resource_id="new-id"
    )

    result = await apply_reorganization_plan(plan=plan, dry_run=False)

    assert result["success"] is False
    assert "Created 1 sections and moved 1 pages" in result["summary"]
    assert "errors" in result
    assert len(result["errors"]) >= 2  # section creation + skipped move
    # Only one copy call (for pg-2 to "Personal", pg-1 was skipped)
    mock_graph_client.copy_page_to_section.assert_called_once_with(
        "pg-2", "sec-personal"
    )


@pytest.mark.asyncio
async def test_auth_error_during_validation(mock_graph_client):
    """Returns auth_error if auth fails during reference validation."""
    plan = _valid_plan()
    mock_graph_client.list_sections.side_effect = AuthError("Token expired")

    result = await apply_reorganization_plan(plan=plan)

    assert result["success"] is False
    assert result["error"]["category"] == "auth_error"
    assert result["error"]["toolName"] == "apply_reorganization_plan"
