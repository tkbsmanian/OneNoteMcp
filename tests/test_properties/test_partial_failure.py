# Feature: onenote-organizer, Property 13: Partial Failure Continues Processing
"""
Property 13: Partial Failure Continues Processing

For any reorganization plan where some operations fail, the apply_reorganization_plan
tool should attempt all remaining operations (skipping only page moves targeting a
failed section), and the error summary should list every individual failure encountered.

Validates: Requirements 11.5
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, call

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from onenote_organizer.models import (
    GraphError,
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


# --- Strategies ---

# Generate a list of 2+ distinct section display names
section_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=20,
)

# Generate page IDs
page_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=20,
)


@st.composite
def partial_failure_plan_strategy(draw):
    """Generate a plan with 2+ sections where the first section will fail.

    Returns (plan_dict, failing_section_name, succeeding_section_name, page_ids_for_success, page_ids_for_failure).
    """
    # Generate 2 distinct section names
    name1 = draw(section_name_strategy.filter(lambda s: s.strip()))
    name2 = draw(
        section_name_strategy.filter(lambda s: s.strip() and s != name1)
    )

    failing_section = name1
    succeeding_section = name2

    # Generate at least 1 page targeting the succeeding section
    num_success_pages = draw(st.integers(min_value=1, max_value=3))
    success_page_ids = [
        draw(page_id_strategy.filter(lambda s: s.strip()))
        for _ in range(num_success_pages)
    ]
    # Ensure unique page IDs
    success_page_ids = list(dict.fromkeys(success_page_ids))
    if not success_page_ids:
        success_page_ids = ["pg_succ_1"]

    # Generate at least 1 page targeting the failing section
    num_fail_pages = draw(st.integers(min_value=1, max_value=3))
    fail_page_ids = [
        draw(
            page_id_strategy.filter(
                lambda s: s.strip() and s not in success_page_ids
            )
        )
        for _ in range(num_fail_pages)
    ]
    # Ensure unique page IDs
    fail_page_ids = list(dict.fromkeys(fail_page_ids))
    if not fail_page_ids:
        fail_page_ids = ["pg_fail_1"]

    # Build the plan
    plan = {
        "suggestedSections": [
            {"displayName": failing_section, "notebookId": "nb-test"},
            {"displayName": succeeding_section, "notebookId": "nb-test"},
        ],
        "pageMoves": [],
    }

    # Add moves targeting the failing section
    for pid in fail_page_ids:
        plan["pageMoves"].append(
            {
                "pageId": pid,
                "sourceSectionId": "sec-src",
                "targetSectionDisplayName": failing_section,
            }
        )

    # Add moves targeting the succeeding section
    for pid in success_page_ids:
        plan["pageMoves"].append(
            {
                "pageId": pid,
                "sourceSectionId": "sec-src",
                "targetSectionDisplayName": succeeding_section,
            }
        )

    return (
        plan,
        failing_section,
        succeeding_section,
        success_page_ids,
        fail_page_ids,
    )


# **Validates: Requirements 11.5**
@settings(max_examples=50)
@given(data=partial_failure_plan_strategy())
@pytest.mark.asyncio
async def test_partial_failure_continues_processing(data):
    """When one section creation fails, all remaining operations are still attempted,
    page moves to the failed section are skipped, moves to the successful section
    are executed, and the error summary lists all failures."""
    import onenote_organizer.server as server_mod

    (
        plan,
        failing_section,
        succeeding_section,
        success_page_ids,
        fail_page_ids,
    ) = data

    # Set up mock graph client
    mock_client = AsyncMock()
    server_mod._graph_client = mock_client

    # --- Validation phase: all resources exist ---
    mock_client.list_sections.return_value = []
    all_page_ids = set(success_page_ids + fail_page_ids)
    mock_client.get_page_metadata.side_effect = lambda page_id: PageMetadata(
        id=page_id, title=f"Page {page_id}", last_modified=datetime.now(timezone.utc)
    )

    # --- Section creation: first FAILS (GraphError), second SUCCEEDS ---
    def create_section_side_effect(notebook_id, display_name):
        if display_name == failing_section:
            raise GraphError("Internal Server Error", status_code=500)
        return Section(
            id=f"sec-{display_name}", display_name=display_name, notebook_id=notebook_id
        )

    mock_client.create_section.side_effect = create_section_side_effect

    # --- Page moves: succeed for pages targeting the successful section ---
    mock_client.copy_page_to_section.return_value = "http://operation-url"
    mock_client.poll_operation.return_value = OperationResult(
        status="completed", resource_id="new-resource-id"
    )

    # Execute the plan
    result = await apply_reorganization_plan(plan=plan, dry_run=False)

    # --- Verification 1: create_section is attempted for ALL sections ---
    # (not stopped at first failure)
    create_section_calls = mock_client.create_section.call_args_list
    called_display_names = {c[0][1] for c in create_section_calls}
    assert failing_section in called_display_names, (
        f"create_section should be attempted for failing section '{failing_section}'"
    )
    assert succeeding_section in called_display_names, (
        f"create_section should be attempted for succeeding section '{succeeding_section}'"
    )

    # --- Verification 2: Page moves targeting the failed section are SKIPPED ---
    copy_calls = mock_client.copy_page_to_section.call_args_list
    moved_page_ids = {c[0][0] for c in copy_calls}
    for pid in fail_page_ids:
        assert pid not in moved_page_ids, (
            f"Page '{pid}' targeting failed section should NOT have been moved"
        )

    # --- Verification 3: Page moves targeting the successful section are EXECUTED ---
    for pid in success_page_ids:
        assert pid in moved_page_ids, (
            f"Page '{pid}' targeting successful section SHOULD have been moved"
        )

    # --- Verification 4: The errors list contains entries for the failed section
    # and skipped moves ---
    assert "errors" in result, "Result should contain 'errors' list"
    errors = result["errors"]
    assert len(errors) >= 1 + len(fail_page_ids), (
        f"Should have at least 1 section creation error + {len(fail_page_ids)} skipped move errors, "
        f"got {len(errors)} errors"
    )

    # Check there's an error for the failed section creation
    section_error_found = any(failing_section in e for e in errors)
    assert section_error_found, (
        f"Errors should mention the failed section '{failing_section}'"
    )

    # Check there are errors for each skipped page move
    for pid in fail_page_ids:
        page_error_found = any(pid in e for e in errors)
        assert page_error_found, (
            f"Errors should mention skipped page '{pid}'"
        )

    # --- Verification 5: Summary still shows counts of successful operations ---
    assert "summary" in result
    summary = result["summary"]
    # Should contain the count of successfully created sections (1)
    assert "1" in summary, (
        "Summary should contain count of successful section creations"
    )
    # Should contain the count of successfully moved pages
    expected_moves = len(success_page_ids)
    assert str(expected_moves) in summary, (
        f"Summary should contain count of pages moved ({expected_moves})"
    )
