# Feature: onenote-organizer, Property 14: Invalid Plan References Block All Writes
"""
Property 14: Invalid Plan References Block All Writes

For any reorganization plan containing references to non-existent pages or notebooks,
the apply_reorganization_plan tool should return an error listing all invalid references
and should make zero create/update/delete requests to Microsoft Graph.

Validates: Requirements 11.8
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from onenote_organizer.models import GraphError
from onenote_organizer.server import apply_reorganization_plan


@pytest.fixture(autouse=True)
def reset_graph_client():
    """Reset the module-level _graph_client before each test."""
    import onenote_organizer.server as server_mod

    server_mod._graph_client = None
    yield
    server_mod._graph_client = None


# --- Strategies ---

# Generate IDs that look like resource identifiers
resource_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=3,
    max_size=20,
).filter(lambda s: s.strip())


@st.composite
def invalid_refs_plan_strategy(draw):
    """Generate a plan with non-existent page refs (1-5) and non-existent notebook refs (0-2).

    Returns (plan_dict, invalid_page_ids, invalid_notebook_ids).
    """
    # Generate invalid page IDs (1-5)
    num_invalid_pages = draw(st.integers(min_value=1, max_value=5))
    invalid_page_ids = []
    for _ in range(num_invalid_pages):
        pid = draw(resource_id_strategy)
        if pid not in invalid_page_ids:
            invalid_page_ids.append(pid)
    # Ensure at least 1 invalid page
    if not invalid_page_ids:
        invalid_page_ids = ["nonexistent_page_1"]

    # Generate invalid notebook IDs (0-2)
    num_invalid_notebooks = draw(st.integers(min_value=0, max_value=2))
    invalid_notebook_ids = []
    for _ in range(num_invalid_notebooks):
        nb_id = draw(resource_id_strategy.filter(lambda s: s not in invalid_page_ids))
        if nb_id not in invalid_notebook_ids:
            invalid_notebook_ids.append(nb_id)

    # Use a valid notebook ID if there are no invalid notebooks
    # (so that we always have at least a suggestedSection)
    notebook_id = invalid_notebook_ids[0] if invalid_notebook_ids else "valid_nb_1"

    # Build suggestedSections - one per invalid notebook + one valid section
    suggested_sections = []
    for nb_id in invalid_notebook_ids:
        suggested_sections.append(
            {"displayName": f"Section for {nb_id}", "notebookId": nb_id}
        )
    # Always have at least one suggested section (even with a valid notebook)
    if not suggested_sections:
        suggested_sections.append(
            {"displayName": "Target Section", "notebookId": "valid_nb_1"}
        )

    # Build pageMoves referencing invalid pages
    page_moves = []
    target_section_name = suggested_sections[0]["displayName"]
    for pid in invalid_page_ids:
        page_moves.append(
            {
                "pageId": pid,
                "sourceSectionId": "sec_src_1",
                "targetSectionDisplayName": target_section_name,
            }
        )

    plan = {
        "suggestedSections": suggested_sections,
        "pageMoves": page_moves,
    }

    return plan, invalid_page_ids, invalid_notebook_ids


# **Validates: Requirements 11.8**
@settings(max_examples=50)
@given(data=invalid_refs_plan_strategy())
@pytest.mark.asyncio
async def test_invalid_plan_references_block_all_writes(data):
    """Plans referencing non-existent pages/notebooks return an error listing
    invalid refs and make zero Graph mutations (no create_section, no copy_page_to_section)."""
    import onenote_organizer.server as server_mod

    plan, invalid_page_ids, invalid_notebook_ids = data

    # Set up mock graph client
    mock_client = AsyncMock()
    server_mod._graph_client = mock_client

    # Mock list_sections: raise GraphError(404) for non-existent notebooks,
    # return empty list for valid ones
    def list_sections_side_effect(notebook_id):
        if notebook_id in invalid_notebook_ids:
            raise GraphError("Notebook not found", status_code=404)
        return []

    mock_client.list_sections.side_effect = list_sections_side_effect

    # Mock get_page_metadata: raise GraphError(404) for non-existent pages
    def get_page_metadata_side_effect(page_id):
        if page_id in invalid_page_ids:
            raise GraphError("Page not found", status_code=404)
        # Should not be called for valid pages in this test since all are invalid
        raise GraphError("Page not found", status_code=404)

    mock_client.get_page_metadata.side_effect = get_page_metadata_side_effect

    # Execute the plan (live mode, not dry-run)
    result = await apply_reorganization_plan(plan=plan, dry_run=False)

    # --- Verification 1: Response has success=False with category "validation_error" ---
    assert result["success"] is False, "Result should be unsuccessful for invalid refs"
    assert "error" in result, "Result should contain an error object"
    error = result["error"]
    assert error["category"] == "validation_error", (
        f"Error category should be 'validation_error', got '{error['category']}'"
    )

    # --- Verification 2: invalidFields dict lists each non-existent resource ---
    assert "invalidFields" in error, "Error should contain invalidFields"
    invalid_fields = error["invalidFields"]

    # Check that all invalid page refs are listed
    for pid in invalid_page_ids:
        ref_key = f"page:{pid}"
        assert ref_key in invalid_fields, (
            f"invalidFields should list non-existent page ref '{ref_key}', "
            f"got keys: {list(invalid_fields.keys())}"
        )

    # Check that all invalid notebook refs are listed
    for nb_id in invalid_notebook_ids:
        ref_key = f"notebook:{nb_id}"
        assert ref_key in invalid_fields, (
            f"invalidFields should list non-existent notebook ref '{ref_key}', "
            f"got keys: {list(invalid_fields.keys())}"
        )

    # --- Verification 3: create_section is NEVER called (zero mutations) ---
    mock_client.create_section.assert_not_called()

    # --- Verification 4: copy_page_to_section is NEVER called (zero mutations) ---
    mock_client.copy_page_to_section.assert_not_called()
