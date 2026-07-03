# Feature: onenote-organizer, Property 15: Log Entry Structure and Format
"""
Property 15: Log Entry Structure and Format

For any write operation that is executed (not dry-run), the log entry should:
be exactly one line (no newline characters within the entry), contain an ISO 8601
timestamp with timezone offset, the tool name, the operation outcome, all resource
identifiers specific to the tool, and a human-readable description not exceeding
200 characters.

Validates: Requirements 13.1, 13.4
"""

import re
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from onenote_organizer.logger import OperationLogger


# --- Strategies ---

# Generate non-empty IDs (alphanumeric, no pipe/newline chars to avoid format confusion)
id_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        blacklist_characters="\n\r|",
    ),
    min_size=1,
    max_size=40,
)

# Generate titles/summaries that may contain various characters but no newlines
title_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        blacklist_characters="\n\r|",
    ),
    min_size=1,
    max_size=100,
)

# Generate summaries that can exceed 200 chars to test truncation
summary_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        blacklist_characters="\n\r",
    ),
    min_size=0,
    max_size=400,
)

# Generate booleans for success/failure
success_strategy = st.booleans()

# Generate non-negative integers for counts
count_strategy = st.integers(min_value=0, max_value=1000)

# Generate error lists (0 to 5 error strings)
errors_strategy = st.lists(
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "S", "Z"),
            blacklist_characters="\n\r",
        ),
        min_size=1,
        max_size=50,
    ),
    min_size=0,
    max_size=5,
)

# ISO 8601 with timezone regex pattern
ISO8601_TZ_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)"
)


def _read_log_output(log_path: Path) -> str:
    """Read the log file content."""
    return log_path.read_text(encoding="utf-8")


def _assert_log_entry_structure(entry: str, tool_name: str, outcome: str) -> None:
    """Common assertions for all log entries."""
    # Entry is exactly one line (no embedded newlines within the entry itself)
    # The logger appends a single \n, so strip trailing whitespace and check
    raw_line = entry.rstrip("\n")
    assert "\n" not in raw_line, (
        f"Log entry should be one line (no embedded newlines): {entry!r}"
    )

    line = raw_line

    # Contains ISO 8601 timestamp with timezone offset
    assert ISO8601_TZ_PATTERN.search(line), (
        f"Log entry should contain ISO 8601 timestamp with timezone: {line!r}"
    )

    # Contains the tool name
    assert tool_name in line, (
        f"Log entry should contain tool name '{tool_name}': {line!r}"
    )

    # Contains the outcome
    assert outcome in line, (
        f"Log entry should contain outcome '{outcome}': {line!r}"
    )

    # The format is: timestamp | tool | outcome | resources | description
    # There should be exactly 4 pipe characters separating 5 fields.
    pipe_count = line.count("|")
    assert pipe_count >= 4, (
        f"Log entry should have at least 4 pipe separators (5 fields): {line!r}"
    )

    # The description portion (last field after the last " | ") is ≤ 200 characters
    last_pipe_idx = line.rfind("| ")
    if last_pipe_idx != -1:
        description = line[last_pipe_idx + 2:]
    else:
        # Fallback: find last pipe and take everything after it
        last_pipe_idx = line.rfind("|")
        description = line[last_pipe_idx + 1:].strip()
    assert len(description) <= 200, (
        f"Description should be ≤ 200 chars, got {len(description)}: {description!r}"
    )


# Validates: Requirements 13.1, 13.4
@settings(max_examples=100)
@given(
    page_id=id_strategy,
    source_section_id=id_strategy,
    target_section_id=id_strategy,
    success=success_strategy,
    summary=summary_strategy,
)
def test_log_move_entry_structure(
    page_id: str,
    source_section_id: str,
    target_section_id: str,
    success: bool,
    summary: str,
) -> None:
    """log_move produces a single-line entry with ISO 8601 timestamp, tool name, outcome, and resource IDs."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        log_file = Path(f.name)

    logger = OperationLogger(destination=str(log_file))
    logger.log_move(page_id, source_section_id, target_section_id, success, summary)

    output = _read_log_output(log_file)
    log_file.unlink(missing_ok=True)

    expected_outcome = "success" if success else "failure"

    _assert_log_entry_structure(output, "move_page_to_section", expected_outcome)

    # Contains resource identifiers
    line = output.rstrip("\n")
    assert f"page={page_id}" in line, (
        f"Log entry should contain page_id: {line!r}"
    )
    assert f"source={source_section_id}" in line, (
        f"Log entry should contain source_section_id: {line!r}"
    )
    assert f"target={target_section_id}" in line, (
        f"Log entry should contain target_section_id: {line!r}"
    )


# Validates: Requirements 13.1, 13.4
@settings(max_examples=100)
@given(
    page_id=id_strategy,
    old_title=title_strategy,
    new_title=title_strategy,
    success=success_strategy,
    summary=summary_strategy,
)
def test_log_rename_entry_structure(
    page_id: str,
    old_title: str,
    new_title: str,
    success: bool,
    summary: str,
) -> None:
    """log_rename produces a single-line entry with ISO 8601 timestamp, tool name, outcome, and resource IDs."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        log_file = Path(f.name)

    logger = OperationLogger(destination=str(log_file))
    logger.log_rename(page_id, old_title, new_title, success, summary)

    output = _read_log_output(log_file)
    log_file.unlink(missing_ok=True)

    expected_outcome = "success" if success else "failure"

    _assert_log_entry_structure(output, "rename_page", expected_outcome)

    # Contains resource identifiers
    line = output.rstrip("\n")
    assert f"page={page_id}" in line, (
        f"Log entry should contain page_id: {line!r}"
    )
    assert f"old_title={old_title}" in line, (
        f"Log entry should contain old_title: {line!r}"
    )
    assert f"new_title={new_title}" in line, (
        f"Log entry should contain new_title: {line!r}"
    )


# Validates: Requirements 13.1, 13.4
@settings(max_examples=100)
@given(
    notebook_id=id_strategy,
    sections_created=count_strategy,
    pages_moved=count_strategy,
    errors=errors_strategy,
    summary=summary_strategy,
)
def test_log_apply_plan_entry_structure(
    notebook_id: str,
    sections_created: int,
    pages_moved: int,
    errors: list[str],
    summary: str,
) -> None:
    """log_apply_plan produces a single-line entry with ISO 8601 timestamp, tool name, outcome, and resource IDs."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        log_file = Path(f.name)

    logger = OperationLogger(destination=str(log_file))
    logger.log_apply_plan(notebook_id, sections_created, pages_moved, errors, summary)

    output = _read_log_output(log_file)
    log_file.unlink(missing_ok=True)

    expected_outcome = "success" if not errors else "partial_failure"

    _assert_log_entry_structure(output, "apply_reorganization_plan", expected_outcome)

    # Contains resource identifiers
    line = output.rstrip("\n")
    assert f"notebook={notebook_id}" in line, (
        f"Log entry should contain notebook_id: {line!r}"
    )
    assert f"sections_created={sections_created}" in line, (
        f"Log entry should contain sections_created count: {line!r}"
    )
    assert f"pages_moved={pages_moved}" in line, (
        f"Log entry should contain pages_moved count: {line!r}"
    )
