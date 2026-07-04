# Feature: onenote-organizer, Property 7: Dry-Run Invariant
"""Property 7: Dry-Run Invariant.

For any write tool with dryRun=true, zero Graph mutations, response includes
dryRun=true, same top-level fields as live execution.

Validates: Requirements 8.4, 9.5, 11.6, 12.1, 12.2, 12.3
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from onenote_organizer.models import PageMetadata, Section
from onenote_organizer.server import move_page_to_section, rename_page


# --- Strategies ---

# Generate non-empty alphanumeric IDs (avoids whitespace-only strings which trigger validation errors)
page_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip())

section_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip())

# Titles: non-empty, non-whitespace, ≤ 256 chars
title_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=256,
).filter(lambda s: s.strip())


def _run_async(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# **Validates: Requirements 8.4, 9.5, 11.6, 12.1, 12.2, 12.3**
class TestDryRunInvariant:
    """Verify that dry-run mode makes zero mutations and returns correct structure."""

    @given(
        page_id=page_id_strategy,
        target_section_id=section_id_strategy,
        page_title=title_strategy,
        source_section_name=title_strategy,
        target_section_name=title_strategy,
    )
    @settings(max_examples=100)
    def test_move_page_dry_run_no_mutations(
        self,
        page_id: str,
        target_section_id: str,
        page_title: str,
        source_section_name: str,
        target_section_name: str,
    ) -> None:
        """move_page_to_section with dry_run=True makes zero Graph mutations."""
        # Create mock graph client
        mock_graph = AsyncMock()
        # Ensure source != target to reach the dry-run path (not no-op)
        source_section_id = "source-section-fixed"
        mock_graph.get_page_metadata.return_value = PageMetadata(
            id=page_id,
            title=page_title,
            last_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
            section_id=source_section_id,
        )
        mock_graph.get_section_metadata.side_effect = [
            Section(id=source_section_id, display_name=source_section_name),
            Section(id=target_section_id, display_name=target_section_name),
        ]

        with patch("onenote_organizer.server._get_graph_client", return_value=mock_graph):
            result = _run_async(
                move_page_to_section(page_id, target_section_id, dry_run=True)
            )

        # Verify zero mutation calls
        mock_graph.copy_page_to_section.assert_not_called()
        mock_graph.poll_operation.assert_not_called()

        # Verify response includes dryRun=True
        assert result.get("dryRun") is True

        # Verify response has same top-level fields as live (success, summary)
        assert "success" in result
        assert "summary" in result
        assert result["success"] is True

    @given(
        page_id=page_id_strategy,
        current_title=title_strategy,
        new_title=title_strategy,
    )
    @settings(max_examples=100)
    def test_rename_page_dry_run_no_mutations(
        self,
        page_id: str,
        current_title: str,
        new_title: str,
    ) -> None:
        """rename_page with dry_run=True makes zero Graph mutations."""
        # Create mock graph client
        mock_graph = AsyncMock()
        # Ensure current_title != new_title to reach the dry-run path (not no-op)
        # Use a distinct current title by appending a suffix
        distinct_current = current_title + "_OLD" if current_title == new_title else current_title
        mock_graph.get_page_metadata.return_value = PageMetadata(
            id=page_id,
            title=distinct_current,
            last_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
            section_id="some-section",
        )

        with patch("onenote_organizer.server._get_graph_client", return_value=mock_graph):
            result = _run_async(
                rename_page(page_id, new_title, dry_run=True)
            )

        # Verify zero mutation calls
        mock_graph.update_page_title.assert_not_called()
        mock_graph.create_section.assert_not_called()

        # Verify response includes dryRun=True
        assert result.get("dryRun") is True

        # Verify response has same top-level fields as live (success, summary)
        assert "success" in result
        assert "summary" in result
        assert result["success"] is True

    @given(
        page_id=page_id_strategy,
        target_section_id=section_id_strategy,
        page_title=title_strategy,
        target_section_name=title_strategy,
    )
    @settings(max_examples=100)
    def test_move_dry_run_response_fields_match_live(
        self,
        page_id: str,
        target_section_id: str,
        page_title: str,
        target_section_name: str,
    ) -> None:
        """move_page_to_section dry-run response has the same top-level field set as live."""
        source_section_id = "source-section-fixed"
        mock_graph = AsyncMock()
        mock_graph.get_page_metadata.return_value = PageMetadata(
            id=page_id,
            title=page_title,
            last_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
            section_id=source_section_id,
        )
        mock_graph.get_section_metadata.side_effect = [
            Section(id=source_section_id, display_name="Source"),
            Section(id=target_section_id, display_name=target_section_name),
        ]

        with patch("onenote_organizer.server._get_graph_client", return_value=mock_graph):
            dry_run_result = _run_async(
                move_page_to_section(page_id, target_section_id, dry_run=True)
            )

        # The dry-run response must have "success" and "summary" (same as live)
        # plus the additional "dryRun" field
        expected_live_fields = {"success", "summary"}
        assert expected_live_fields.issubset(set(dry_run_result.keys()))
        assert dry_run_result["dryRun"] is True

    @given(
        page_id=page_id_strategy,
        new_title=title_strategy,
    )
    @settings(max_examples=100)
    def test_rename_dry_run_response_fields_match_live(
        self,
        page_id: str,
        new_title: str,
    ) -> None:
        """rename_page dry-run response has the same top-level field set as live."""
        mock_graph = AsyncMock()
        # Ensure titles differ to avoid no-op path
        mock_graph.get_page_metadata.return_value = PageMetadata(
            id=page_id,
            title="Original Title That Differs",
            last_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
            section_id="some-section",
        )

        with patch("onenote_organizer.server._get_graph_client", return_value=mock_graph):
            dry_run_result = _run_async(
                rename_page(page_id, new_title, dry_run=True)
            )

        # The dry-run response must have "success" and "summary" (same as live)
        # plus the additional "dryRun" field
        expected_live_fields = {"success", "summary"}
        assert expected_live_fields.issubset(set(dry_run_result.keys()))
        assert dry_run_result["dryRun"] is True


# Feature: onenote-organizer, Property 9: Dry-Run Summary Prefix
# **Validates: Requirements 14.2**


class TestDryRunSummaryPrefix:
    """Verify that dry-run summaries start with 'Would'."""

    @given(
        page_id=page_id_strategy,
        target_section_id=section_id_strategy,
        page_title=title_strategy,
        source_section_name=title_strategy,
        target_section_name=title_strategy,
    )
    @settings(max_examples=100)
    def test_move_page_dry_run_summary_starts_with_would(
        self,
        page_id: str,
        target_section_id: str,
        page_title: str,
        source_section_name: str,
        target_section_name: str,
    ) -> None:
        """move_page_to_section dry-run summary starts with 'Would'."""
        # Ensure source != target to reach the dry-run summary path (not no-op)
        source_section_id = "source-section-fixed"
        mock_graph = AsyncMock()
        mock_graph.get_page_metadata.return_value = PageMetadata(
            id=page_id,
            title=page_title,
            last_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
            section_id=source_section_id,
        )
        mock_graph.get_section_metadata.side_effect = [
            Section(id=source_section_id, display_name=source_section_name),
            Section(id=target_section_id, display_name=target_section_name),
        ]

        with patch("onenote_organizer.server._get_graph_client", return_value=mock_graph):
            result = _run_async(
                move_page_to_section(page_id, target_section_id, dry_run=True)
            )

        # Verify dry-run summary starts with "Would"
        assert result["success"] is True
        assert result.get("dryRun") is True
        assert result["summary"].startswith("Would"), (
            f"Expected summary to start with 'Would', got: {result['summary']!r}"
        )

    @given(
        page_id=page_id_strategy,
        new_title=title_strategy,
        current_title=title_strategy,
    )
    @settings(max_examples=100)
    def test_rename_page_dry_run_summary_starts_with_would(
        self,
        page_id: str,
        new_title: str,
        current_title: str,
    ) -> None:
        """rename_page dry-run summary starts with 'Would'."""
        # Ensure current_title != new_title to reach the dry-run path (not no-op)
        if current_title == new_title:
            current_title = current_title + "_DIFFERENT"

        mock_graph = AsyncMock()
        mock_graph.get_page_metadata.return_value = PageMetadata(
            id=page_id,
            title=current_title,
            last_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
            section_id="some-section",
        )

        with patch("onenote_organizer.server._get_graph_client", return_value=mock_graph):
            result = _run_async(
                rename_page(page_id, new_title, dry_run=True)
            )

        # Verify dry-run summary starts with "Would"
        assert result["success"] is True
        assert result.get("dryRun") is True
        assert result["summary"].startswith("Would"), (
            f"Expected summary to start with 'Would', got: {result['summary']!r}"
        )
