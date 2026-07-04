# Feature: onenote-organizer, Property 8: Human-Readable Summary Format
"""Property 8: Human-Readable Summary Format.

Summary references entities by name (not ID), no UUIDs/timestamps, plain English,
≤ 256 chars.

Validates: Requirements 8.2, 9.2, 14.1, 14.3
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from onenote_organizer.models import OperationResult, PageMetadata, Section
from onenote_organizer.server import move_page_to_section, rename_page

# --- Regex patterns for technical identifiers that should NOT appear in summaries ---

# UUID pattern: 8-4-4-4-12 hex digits
UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)

# ISO 8601 timestamps (e.g., 2024-01-15T10:30:00Z, 2024-01-15T10:30:00+00:00)
ISO8601_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


# --- Strategies ---

# Generate non-empty printable titles (avoiding whitespace-only)
title_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip())

# Generate non-empty section display names
section_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=80,
).filter(lambda s: s.strip())

# Generate non-empty IDs (alphanumeric + dashes)
id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip())


def _run_async(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _assert_summary_format(summary: str, expected_names: list[str]) -> None:
    """Assert that a summary follows human-readable format rules.

    - No UUID patterns
    - No ISO 8601 timestamps
    - ≤ 256 characters
    - References entities by name (at least one expected name appears)
    """
    # No UUIDs
    assert not UUID_PATTERN.search(summary), (
        f"Summary contains UUID-like pattern: {summary!r}"
    )

    # No ISO 8601 timestamps
    assert not ISO8601_PATTERN.search(summary), (
        f"Summary contains ISO 8601 timestamp: {summary!r}"
    )

    # ≤ 256 characters
    assert len(summary) <= 256, (
        f"Summary exceeds 256 chars (len={len(summary)}): {summary!r}"
    )

    # Contains at least one entity name (page title or section name)
    found_name = any(name in summary for name in expected_names if name)
    assert found_name, (
        f"Summary does not reference any entity by name. "
        f"Expected one of {expected_names!r} in: {summary!r}"
    )


# **Validates: Requirements 8.2, 9.2, 14.1, 14.3**
class TestHumanReadableSummaryFormat:
    """Property 8: Summary format for write operations."""

    @given(
        page_id=id_strategy,
        target_section_id=id_strategy,
        page_title=title_strategy,
        source_section_name=section_name_strategy,
        target_section_name=section_name_strategy,
    )
    @settings(max_examples=100)
    def test_move_page_dry_run_summary_format(
        self,
        page_id: str,
        target_section_id: str,
        page_title: str,
        source_section_name: str,
        target_section_name: str,
    ) -> None:
        """move_page_to_section dry-run summary is human-readable."""
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

        assert result["success"] is True
        summary = result["summary"]
        _assert_summary_format(
            summary, [page_title, source_section_name, target_section_name]
        )

    @given(
        page_id=id_strategy,
        target_section_id=id_strategy,
        page_title=title_strategy,
        source_section_name=section_name_strategy,
        target_section_name=section_name_strategy,
    )
    @settings(max_examples=100)
    def test_move_page_live_summary_format(
        self,
        page_id: str,
        target_section_id: str,
        page_title: str,
        source_section_name: str,
        target_section_name: str,
    ) -> None:
        """move_page_to_section live mode summary is human-readable."""
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
        mock_graph.copy_page_to_section.return_value = "https://graph.microsoft.com/operation/123"
        mock_graph.poll_operation.return_value = OperationResult(
            status="completed", resource_id="new-page-id"
        )

        with patch("onenote_organizer.server._get_graph_client", return_value=mock_graph):
            result = _run_async(
                move_page_to_section(page_id, target_section_id, dry_run=False)
            )

        assert result["success"] is True
        summary = result["summary"]
        _assert_summary_format(
            summary, [page_title, source_section_name, target_section_name]
        )

    @given(
        page_id=id_strategy,
        current_title=title_strategy,
        new_title=title_strategy,
    )
    @settings(max_examples=100)
    def test_rename_page_dry_run_summary_format(
        self,
        page_id: str,
        current_title: str,
        new_title: str,
    ) -> None:
        """rename_page dry-run summary is human-readable."""
        # Ensure titles differ to avoid no-op path
        distinct_current = current_title + "_OLD" if current_title == new_title else current_title

        mock_graph = AsyncMock()
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

        assert result["success"] is True
        summary = result["summary"]
        _assert_summary_format(summary, [distinct_current, new_title])

    @given(
        page_id=id_strategy,
        current_title=title_strategy,
        new_title=title_strategy,
    )
    @settings(max_examples=100)
    def test_rename_page_live_summary_format(
        self,
        page_id: str,
        current_title: str,
        new_title: str,
    ) -> None:
        """rename_page live mode summary is human-readable."""
        # Ensure titles differ to avoid no-op path
        distinct_current = current_title + "_OLD" if current_title == new_title else current_title

        mock_graph = AsyncMock()
        mock_graph.get_page_metadata.return_value = PageMetadata(
            id=page_id,
            title=distinct_current,
            last_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
            section_id="some-section",
        )

        with patch("onenote_organizer.server._get_graph_client", return_value=mock_graph):
            result = _run_async(
                rename_page(page_id, new_title, dry_run=False)
            )

        assert result["success"] is True
        summary = result["summary"]
        _assert_summary_format(summary, [distinct_current, new_title])
