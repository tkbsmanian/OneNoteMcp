"""Structured operation logging for write operations."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path


class OperationLogger:
    """Structured logging for write operations.

    Logs each write operation as a single-line structured text record.

    Format:
        ISO8601_timestamp | tool_name | outcome | resource_ids | description(≤200 chars)

    Example:
        2024-01-15T10:30:00+00:00 | move_page_to_section | success | page=abc123 source=sec001 target=sec002 | Moved "Meeting Notes" from "Inbox" to "Work"
    """

    def __init__(self, destination: str | None = None) -> None:
        """Initialize the logger.

        Args:
            destination: File path or "stdout" or "stderr". If None, reads from
                ONENOTE_LOG_DESTINATION environment variable (default "stderr").
                Falls back to stderr if configured destination is not writable.

        Note:
            Defaults to stderr rather than stdout to avoid corrupting the
            JSON-RPC stream when running in stdio transport mode.
        """
        if destination is None:
            destination = os.environ.get("ONENOTE_LOG_DESTINATION", "stderr")
        self._destination = destination
        self._fallback_to_stderr = False
        self._file_handle = None

        if destination not in ("stdout", "stderr"):
            # Verify the file path is writable
            try:
                path = Path(destination)
                path.parent.mkdir(parents=True, exist_ok=True)
                # Test that we can open the file for appending
                with open(path, "a"):
                    pass
            except (OSError, PermissionError):
                self._fallback_to_stderr = True

    def _write_entry(self, entry: str) -> None:
        """Write a log entry to the configured destination.

        Falls back to stderr if the configured destination is not writable.
        """
        line = entry + "\n"

        if self._fallback_to_stderr:
            sys.stderr.write(line)
            sys.stderr.flush()
            return

        if self._destination == "stdout":
            sys.stdout.write(line)
            sys.stdout.flush()
            return

        if self._destination == "stderr":
            sys.stderr.write(line)
            sys.stderr.flush()
            return

        # Write to file
        try:
            with open(self._destination, "a", encoding="utf-8") as f:
                f.write(line)
        except (OSError, PermissionError):
            # Fall back to stderr on write failure
            sys.stderr.write(line)
            sys.stderr.flush()

    @staticmethod
    def _truncate_description(description: str, max_length: int = 200) -> str:
        """Truncate description to max_length characters."""
        if len(description) <= max_length:
            return description
        return description[: max_length - 3] + "..."

    @staticmethod
    def _format_timestamp() -> str:
        """Return current time as ISO 8601 with timezone offset."""
        return datetime.now(timezone.utc).isoformat()

    def _format_entry(
        self, tool_name: str, outcome: str, resource_ids: str, description: str
    ) -> str:
        """Format a structured log entry as a single line.

        Format:
            ISO8601_timestamp | tool_name | outcome | resource_ids | description(≤200 chars)
        """
        timestamp = self._format_timestamp()
        truncated_desc = self._truncate_description(description)
        return f"{timestamp} | {tool_name} | {outcome} | {resource_ids} | {truncated_desc}"

    def log_move(
        self,
        page_id: str,
        source_section_id: str,
        target_section_id: str,
        success: bool,
        summary: str,
    ) -> None:
        """Log a move_page_to_section operation.

        Args:
            page_id: The ID of the page that was moved.
            source_section_id: The ID of the source section.
            target_section_id: The ID of the target section.
            success: Whether the operation succeeded.
            summary: Human-readable description of the operation.
        """
        outcome = "success" if success else "failure"
        resource_ids = (
            f"page={page_id} source={source_section_id} target={target_section_id}"
        )
        entry = self._format_entry("move_page_to_section", outcome, resource_ids, summary)
        self._write_entry(entry)

    def log_rename(
        self,
        page_id: str,
        old_title: str,
        new_title: str,
        success: bool,
        summary: str,
    ) -> None:
        """Log a rename_page operation.

        Args:
            page_id: The ID of the page that was renamed.
            old_title: The original title of the page.
            new_title: The new title of the page.
            success: Whether the operation succeeded.
            summary: Human-readable description of the operation.
        """
        outcome = "success" if success else "failure"
        resource_ids = f"page={page_id} old_title={old_title} new_title={new_title}"
        entry = self._format_entry("rename_page", outcome, resource_ids, summary)
        self._write_entry(entry)

    def log_apply_plan(
        self,
        notebook_id: str,
        sections_created: int,
        pages_moved: int,
        errors: list[str],
        summary: str,
    ) -> None:
        """Log an apply_reorganization_plan operation.

        Args:
            notebook_id: The ID of the notebook being reorganized.
            sections_created: Number of sections created.
            pages_moved: Number of pages moved.
            errors: List of error messages encountered.
            summary: Human-readable description of the operation.
        """
        outcome = "success" if not errors else "partial_failure"
        resource_ids = (
            f"notebook={notebook_id} sections_created={sections_created} "
            f"pages_moved={pages_moved}"
        )
        entry = self._format_entry(
            "apply_reorganization_plan", outcome, resource_ids, summary
        )
        self._write_entry(entry)
