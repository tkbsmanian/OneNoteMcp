"""Data models and custom exceptions for the OneNote Organizer MCP Server."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


# --- Data Models ---


@dataclass(frozen=True)
class Notebook:
    """A top-level OneNote container."""

    id: str
    display_name: str


@dataclass(frozen=True)
class Section:
    """A container within a Notebook that holds pages."""

    id: str
    display_name: str
    notebook_id: str | None = None


@dataclass(frozen=True)
class PageMetadata:
    """Metadata for a OneNote page (without content)."""

    id: str
    title: str
    last_modified: datetime
    section_id: str | None = None


@dataclass(frozen=True)
class PageContent:
    """A OneNote page with its content."""

    id: str
    title: str
    content: str


@dataclass(frozen=True)
class SuggestedSection:
    """A section proposed by the reorganization planner."""

    display_name: str
    notebook_id: str


@dataclass(frozen=True)
class PageMove:
    """A proposed page move within a reorganization plan."""

    page_id: str
    source_section_id: str
    target_section_display_name: str


@dataclass(frozen=True)
class ReorganizationPlan:
    """A structured proposal for reorganizing notebook content."""

    suggested_sections: list[SuggestedSection]
    page_moves: list[PageMove]


@dataclass(frozen=True)
class ToolError:
    """Structured error information returned by tools."""

    category: str  # "graph_error" | "auth_error" | "validation_error" | "network_error"
    message: str
    status_code: int | None = None
    tool_name: str = ""
    invalid_fields: dict[str, str] | None = None  # field -> reason (for validation errors)


@dataclass(frozen=True)
class ToolResult:
    """Standard response structure for all MCP tool invocations."""

    success: bool
    summary: str
    dry_run: bool = False
    data: dict | None = None
    error: ToolError | None = None


@dataclass(frozen=True)
class OperationResult:
    """Result of a long-running Graph API operation (e.g., copy-as-move)."""

    status: str  # "completed" | "failed"
    resource_id: str | None = None
    error_message: str | None = None


# --- Custom Exceptions ---


class OneNoteOrganizerError(Exception):
    """Base exception for the OneNote Organizer package."""


class AuthError(OneNoteOrganizerError):
    """Raised when authentication fails (token acquisition, expired refresh, etc.)."""


class GraphError(OneNoteOrganizerError):
    """Raised when a Microsoft Graph API call returns an HTTP error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ValidationError(OneNoteOrganizerError):
    """Raised when tool input does not conform to the required schema."""

    def __init__(self, message: str, invalid_fields: dict[str, str] | None = None):
        super().__init__(message)
        self.invalid_fields = invalid_fields or {}


class NetworkError(OneNoteOrganizerError):
    """Raised when a Graph API call fails due to network timeout or connectivity."""
