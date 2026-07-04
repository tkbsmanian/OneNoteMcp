# Feature: onenote-organizer, Property 12: Apply Summary Contains Operation Counts
"""
Property 12: Apply Summary Contains Operation Counts

For any execution of apply_reorganization_plan (live or dry-run), the summary
should contain the numeric count of sections created and pages moved, and these
counts should equal the actual number of successful section creations and page
moves performed (or projected).

Validates: Requirements 11.4, 14.4
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from onenote_organizer.models import OperationResult, PageMetadata, Section
from onenote_organizer.server import apply_reorganization_plan


@pytest.fixture(autouse=True)
def reset_graph_client():
    """Reset the module-level _graph_client before each test."""
    import onenote_organizer.server as server_mod

    server_mod._graph_client = None
    yield
    server_mod._graph_client = None


def _inject_mock_client() -> AsyncMock:
    """Inject a mock GraphClient into the server module and return it."""
    import onenote_organizer.server as server_mod

    client = AsyncMock()
    server_mod._graph_client = client
    return client


# --- Strategies ---

# Generate plan sizes: 1-5 sections, 1-10 page moves
num_sections_st = st.integers(min_value=1, max_value=5)
num_page_moves_st = st.integers(min_value=1, max_value=10)


def _build_plan(num_sections: int, num_moves: int) -> dict:
    """Build a valid plan with the given number of sections and page moves."""
    suggested_sections = [
        {"displayName": f"Section-{i}", "notebookId": "nb-1"}
        for i in range(num_sections)
    ]
    page_moves = [
        {
            "pageId": f"pg-{j}",
            "sourceSectionId": "sec-old",
            "targetSectionDisplayName": f"Section-{j % num_sections}",
        }
        for j in range(num_moves)
    ]
    return {"suggestedSections": suggested_sections, "pageMoves": page_moves}


# --- Property Tests ---


# **Validates: Requirements 11.4, 14.4**
@settings(max_examples=50)
@given(num_sections=num_sections_st, num_moves=num_page_moves_st)
@pytest.mark.asyncio
async def test_dry_run_summary_contains_correct_counts(
    num_sections: int, num_moves: int
) -> None:
    """In dry-run mode, summary says 'Would create N sections and move M pages'
    where N=len(suggestedSections) and M=len(pageMoves)."""
    mock_client = _inject_mock_client()

    # Validation: notebook and pages exist
    mock_client.list_sections.return_value = []
    mock_client.get_page_metadata.return_value = PageMetadata(
        id="pg-0", title="Test Page", last_modified=datetime.now(timezone.utc)
    )

    plan = _build_plan(num_sections, num_moves)
    result = await apply_reorganization_plan(plan=plan, dry_run=True)

    assert result["success"] is True
    assert result["dryRun"] is True

    summary = result["summary"]
    expected_summary = f"Would create {num_sections} sections and move {num_moves} pages"
    assert summary == expected_summary, (
        f"Expected '{expected_summary}', got '{summary}'"
    )

    # Verify no mutations were made
    mock_client.create_section.assert_not_called()
    mock_client.copy_page_to_section.assert_not_called()


# **Validates: Requirements 11.4, 14.4**
@settings(max_examples=50)
@given(num_sections=num_sections_st, num_moves=num_page_moves_st)
@pytest.mark.asyncio
async def test_live_mode_summary_contains_correct_counts(
    num_sections: int, num_moves: int
) -> None:
    """In live mode, summary says 'Created N sections and moved M pages'
    where N and M match the actual successful operations."""
    mock_client = _inject_mock_client()

    # Validation: notebook and pages exist
    mock_client.list_sections.return_value = []
    mock_client.get_page_metadata.return_value = PageMetadata(
        id="pg-0", title="Test Page", last_modified=datetime.now(timezone.utc)
    )

    # Section creation succeeds for all sections
    mock_client.create_section.side_effect = [
        Section(id=f"sec-new-{i}", display_name=f"Section-{i}", notebook_id="nb-1")
        for i in range(num_sections)
    ]

    # Page move succeeds for all pages
    mock_client.copy_page_to_section.return_value = "http://op-url"
    mock_client.poll_operation.return_value = OperationResult(
        status="completed", resource_id="new-page-id"
    )

    plan = _build_plan(num_sections, num_moves)
    result = await apply_reorganization_plan(plan=plan, dry_run=False)

    assert result["success"] is True

    summary = result["summary"]
    expected_summary = f"Created {num_sections} sections and moved {num_moves} pages"
    assert summary == expected_summary, (
        f"Expected '{expected_summary}', got '{summary}'"
    )

    # Verify actual operation counts match summary
    assert mock_client.create_section.call_count == num_sections
    assert mock_client.copy_page_to_section.call_count == num_moves

    # Extract counts from summary and verify they match
    match = re.search(r"Created (\d+) sections and moved (\d+) pages", summary)
    assert match is not None
    assert int(match.group(1)) == num_sections
    assert int(match.group(2)) == num_moves
