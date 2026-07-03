"""Unit tests for the OperationLogger.

Tests fallback to stderr when file path is unwritable, stdout output mode,
stderr output mode, default behavior, and ONENOTE_LOG_DESTINATION env var.

Requirements: 13.3, 13.5
"""

from __future__ import annotations

import sys
from io import StringIO
from unittest.mock import patch

import pytest

from onenote_organizer.logger import OperationLogger


class TestLoggerStderrFallback:
    """Test that logger falls back to stderr when file path is unwritable."""

    def test_unwritable_path_falls_back_to_stderr(self, capsys):
        """When initialized with an unwritable path, output goes to stderr."""
        logger = OperationLogger(destination="/nonexistent/dir/file.log")

        logger.log_move(
            page_id="pg-001",
            source_section_id="sec-001",
            target_section_id="sec-002",
            success=True,
            summary="Moved page",
        )

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "move_page_to_section" in captured.err
        assert "pg-001" in captured.err
        assert "success" in captured.err

    def test_unwritable_path_sets_fallback_flag(self):
        """Internal fallback flag is set when path is unwritable."""
        logger = OperationLogger(destination="/nonexistent/dir/file.log")
        assert logger._fallback_to_stderr is True

    def test_unwritable_path_does_not_raise(self):
        """Initialization with unwritable path does not raise an exception."""
        # Should not raise - logger falls back silently (Req 13.5)
        logger = OperationLogger(destination="/nonexistent/dir/file.log")
        assert logger is not None


class TestLoggerStdoutMode:
    """Test that stdout output mode works correctly."""

    def test_stdout_destination_writes_to_stdout(self, capsys):
        """When initialized with 'stdout', log entries go to stdout."""
        logger = OperationLogger(destination="stdout")

        logger.log_rename(
            page_id="pg-002",
            old_title="Old Title",
            new_title="New Title",
            success=True,
            summary="Renamed page",
        )

        captured = capsys.readouterr()
        assert "rename_page" in captured.out
        assert "pg-002" in captured.out
        assert captured.err == ""

    def test_stdout_does_not_set_fallback_flag(self):
        """Stdout mode does not trigger the fallback flag."""
        logger = OperationLogger(destination="stdout")
        assert logger._fallback_to_stderr is False


class TestLoggerStderrMode:
    """Test that stderr output mode works correctly."""

    def test_stderr_destination_writes_to_stderr(self, capsys):
        """When initialized with 'stderr', log entries go to stderr."""
        logger = OperationLogger(destination="stderr")

        logger.log_move(
            page_id="pg-003",
            source_section_id="sec-010",
            target_section_id="sec-020",
            success=False,
            summary="Move failed",
        )

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "move_page_to_section" in captured.err
        assert "failure" in captured.err

    def test_stderr_does_not_set_fallback_flag(self):
        """Stderr mode does not trigger the fallback flag."""
        logger = OperationLogger(destination="stderr")
        assert logger._fallback_to_stderr is False


class TestLoggerFileMode:
    """Test that file-based logging works correctly."""

    def test_writable_file_path(self, tmp_path):
        """When initialized with a writable file path, entries go to the file."""
        log_file = tmp_path / "test.log"
        logger = OperationLogger(destination=str(log_file))

        logger.log_move(
            page_id="pg-100",
            source_section_id="sec-a",
            target_section_id="sec-b",
            success=True,
            summary="Moved successfully",
        )

        content = log_file.read_text()
        assert "move_page_to_section" in content
        assert "pg-100" in content
        assert "success" in content

    def test_file_entries_are_appended(self, tmp_path):
        """Multiple log entries are appended to the same file."""
        log_file = tmp_path / "test.log"
        logger = OperationLogger(destination=str(log_file))

        logger.log_move("pg-1", "s1", "s2", True, "First move")
        logger.log_rename("pg-2", "Old", "New", True, "Renamed")

        content = log_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert "move_page_to_section" in lines[0]
        assert "rename_page" in lines[1]


class TestLoggerDefaultBehavior:
    """Test the default behavior when no destination is specified."""

    def test_default_no_env_var_writes_to_stderr(self, capsys, monkeypatch):
        """When no destination is given and no env var is set, defaults to stderr."""
        monkeypatch.delenv("ONENOTE_LOG_DESTINATION", raising=False)
        logger = OperationLogger()

        logger.log_move(
            page_id="pg-default",
            source_section_id="sec-x",
            target_section_id="sec-y",
            success=True,
            summary="Default test",
        )

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "move_page_to_section" in captured.err


class TestLoggerEnvVar:
    """Test that ONENOTE_LOG_DESTINATION environment variable is respected."""

    def test_env_var_stdout(self, capsys, monkeypatch):
        """When ONENOTE_LOG_DESTINATION is 'stdout', output goes to stdout."""
        monkeypatch.setenv("ONENOTE_LOG_DESTINATION", "stdout")
        logger = OperationLogger()

        logger.log_rename("pg-env", "A", "B", True, "Env var test")

        captured = capsys.readouterr()
        assert "rename_page" in captured.out
        assert captured.err == ""

    def test_env_var_stderr(self, capsys, monkeypatch):
        """When ONENOTE_LOG_DESTINATION is 'stderr', output goes to stderr."""
        monkeypatch.setenv("ONENOTE_LOG_DESTINATION", "stderr")
        logger = OperationLogger()

        logger.log_rename("pg-env2", "C", "D", True, "Env stderr test")

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "rename_page" in captured.err

    def test_env_var_file_path(self, tmp_path, monkeypatch):
        """When ONENOTE_LOG_DESTINATION is a file path, output goes to that file."""
        log_file = tmp_path / "env_log.log"
        monkeypatch.setenv("ONENOTE_LOG_DESTINATION", str(log_file))
        logger = OperationLogger()

        logger.log_apply_plan(
            notebook_id="nb-env",
            sections_created=2,
            pages_moved=5,
            errors=[],
            summary="Applied plan via env",
        )

        content = log_file.read_text()
        assert "apply_reorganization_plan" in content
        assert "nb-env" in content

    def test_env_var_unwritable_falls_back_to_stderr(self, capsys, monkeypatch):
        """When ONENOTE_LOG_DESTINATION points to unwritable path, falls back to stderr."""
        monkeypatch.setenv("ONENOTE_LOG_DESTINATION", "/nonexistent/path/log.txt")
        logger = OperationLogger()

        logger.log_move("pg-fail", "s1", "s2", True, "Fallback test")

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "move_page_to_section" in captured.err


class TestLoggerContinuesOnFailure:
    """Test that logging failures do not interrupt operations (Req 13.5)."""

    def test_write_failure_during_file_logging_falls_back(self, tmp_path, capsys):
        """If a file becomes unwritable after init, fallback to stderr on write."""
        log_file = tmp_path / "test.log"
        logger = OperationLogger(destination=str(log_file))

        # First write should succeed
        logger.log_move("pg-1", "s1", "s2", True, "First entry")
        assert log_file.exists()

        # Simulate file becoming unwritable by patching open to raise
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            logger.log_move("pg-2", "s3", "s4", True, "After failure")

        captured = capsys.readouterr()
        # The second write should have fallen back to stderr
        assert "pg-2" in captured.err
