"""MCP Server for OneNote Organizer.

Exposes OneNote notebook management tools to AI assistants via the
Model Context Protocol using FastMCP.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from mcp.server.fastmcp import FastMCP

from onenote_organizer.auth import DeviceCodeAuthProvider
from onenote_organizer.graph_client import GraphClient
from onenote_organizer.logger import OperationLogger
from onenote_organizer.models import (
    AuthError,
    GraphError,
    NetworkError,
    ValidationError,
)

# Initialize the MCP server
mcp = FastMCP("onenote-organizer")

# Module-level graph client (lazily initialized)
_graph_client: GraphClient | None = None

# Module-level operation logger
_logger = OperationLogger()


def _get_graph_client() -> GraphClient:
    """Get or create the shared Graph client instance."""
    global _graph_client
    if _graph_client is None:
        auth_provider = DeviceCodeAuthProvider()
        _graph_client = GraphClient(auth_provider)
    return _graph_client


def _make_error_response(
    category: str,
    message: str,
    tool_name: str,
    status_code: int | None = None,
    invalid_fields: dict[str, str] | None = None,
) -> dict:
    """Create a consistent error response structure."""
    error: dict = {
        "category": category,
        "message": message,
        "toolName": tool_name,
    }
    if status_code is not None:
        error["statusCode"] = status_code
    if invalid_fields is not None:
        error["invalidFields"] = invalid_fields
    return {"success": False, "error": error}


# --- HTML-to-Text Stripping ---


class _HTMLTextExtractor(HTMLParser):
    """Extract visible text content from HTML, stripping all tags."""

    def __init__(self) -> None:
        super().__init__()
        self._text_parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._text_parts.append(data)

    def get_text(self) -> str:
        """Return extracted text with excessive whitespace cleaned up."""
        raw = " ".join(self._text_parts)
        # Collapse multiple whitespace characters into a single space
        cleaned = re.sub(r"\s+", " ", raw).strip()
        return cleaned


def _strip_html_tags(html_content: str) -> str:
    """Strip HTML tags from content, preserving visible text.

    Args:
        html_content: The HTML string to strip.

    Returns:
        Plain text with HTML tags removed and whitespace cleaned up.
    """
    extractor = _HTMLTextExtractor()
    extractor.feed(html_content)
    return extractor.get_text()


# --- MCP Tools ---


@mcp.tool()
async def list_notebooks() -> list[dict] | dict:
    """List all OneNote notebooks for the authenticated user.

    Returns an array of objects each containing 'id' and 'displayName' fields,
    or an error object if the operation fails.
    """
    tool_name = "list_notebooks"

    try:
        graph_client = _get_graph_client()
        notebooks = await graph_client.list_notebooks()
        return [
            {"id": nb.id, "displayName": nb.display_name}
            for nb in notebooks
        ]
    except AuthError as exc:
        return _make_error_response(
            category="auth_error",
            message=str(exc),
            tool_name=tool_name,
        )
    except GraphError as exc:
        return _make_error_response(
            category="graph_error",
            message=str(exc),
            tool_name=tool_name,
            status_code=exc.status_code,
        )
    except NetworkError as exc:
        return _make_error_response(
            category="network_error",
            message=str(exc),
            tool_name=tool_name,
        )


@mcp.tool()
async def list_sections(notebook_id: str) -> list[dict] | dict:
    """List all sections in a specific notebook.

    Args:
        notebook_id: The ID of the notebook whose sections to list.

    Returns an array of objects each containing 'id' and 'displayName' fields,
    or an error object if the operation fails.
    """
    tool_name = "list_sections"

    # Input validation
    if not notebook_id or not notebook_id.strip():
        return _make_error_response(
            category="validation_error",
            message="notebook_id is required and must not be empty.",
            tool_name=tool_name,
            invalid_fields={"notebook_id": "Required parameter is missing or empty"},
        )

    try:
        graph_client = _get_graph_client()
        sections = await graph_client.list_sections(notebook_id)
        return [
            {"id": sec.id, "displayName": sec.display_name}
            for sec in sections
        ]
    except AuthError as exc:
        return _make_error_response(
            category="auth_error",
            message=str(exc),
            tool_name=tool_name,
        )
    except GraphError as exc:
        return _make_error_response(
            category="graph_error",
            message=str(exc),
            tool_name=tool_name,
            status_code=exc.status_code,
        )
    except NetworkError as exc:
        return _make_error_response(
            category="network_error",
            message=str(exc),
            tool_name=tool_name,
        )


@mcp.tool()
async def list_pages(section_id: str) -> list[dict] | dict:
    """List all pages in a specific section.

    Args:
        section_id: The ID of the section whose pages to list.

    Returns an array of objects each containing 'id', 'title', and
    'lastModifiedDateTime' fields, or an error object if the operation fails.
    """
    tool_name = "list_pages"

    # Input validation
    if not section_id or not section_id.strip():
        return _make_error_response(
            category="validation_error",
            message="section_id is required and must not be empty.",
            tool_name=tool_name,
            invalid_fields={"section_id": "Required parameter is missing or empty"},
        )

    try:
        graph_client = _get_graph_client()
        pages = await graph_client.list_pages(section_id)
        return [
            {
                "id": page.id,
                "title": page.title,
                "lastModifiedDateTime": page.last_modified.isoformat(),
            }
            for page in pages
        ]
    except AuthError as exc:
        return _make_error_response(
            category="auth_error",
            message=str(exc),
            tool_name=tool_name,
        )
    except GraphError as exc:
        return _make_error_response(
            category="graph_error",
            message=str(exc),
            tool_name=tool_name,
            status_code=exc.status_code,
        )
    except NetworkError as exc:
        return _make_error_response(
            category="network_error",
            message=str(exc),
            tool_name=tool_name,
        )


@mcp.tool()
async def get_page_content(page_id: str, format: str = "html") -> dict:
    """Get the content of a specific page.

    Args:
        page_id: The ID of the page to retrieve.
        format: Output format - "html" for raw HTML or "text" for plain text.
                Defaults to "html".

    Returns:
        A dictionary with id, title, and content fields, or an error response.
    """
    tool_name = "get_page_content"

    # Validate page_id is non-empty
    if not page_id or not page_id.strip():
        return _make_error_response(
            category="validation_error",
            message="pageId is required and cannot be empty",
            tool_name=tool_name,
            invalid_fields={"page_id": "pageId is required and cannot be empty"},
        )

    # Validate format is "html" or "text"
    if format not in ("html", "text"):
        return _make_error_response(
            category="validation_error",
            message=f"format must be 'html' or 'text', got '{format}'",
            tool_name=tool_name,
            invalid_fields={
                "format": "format must be one of: 'html', 'text'"
            },
        )

    try:
        graph_client = _get_graph_client()

        # Get page content (HTML) and metadata
        html_content = await graph_client.get_page_content(page_id)
        metadata = await graph_client.get_page_metadata(page_id)

        # Convert to text if requested
        content = html_content
        if format == "text":
            content = _strip_html_tags(html_content)

        return {
            "id": metadata.id,
            "title": metadata.title,
            "content": content,
        }

    except AuthError as exc:
        return _make_error_response(
            category="auth_error",
            message=str(exc),
            tool_name=tool_name,
        )
    except GraphError as exc:
        return _make_error_response(
            category="graph_error",
            message=str(exc),
            tool_name=tool_name,
            status_code=exc.status_code,
        )
    except NetworkError as exc:
        return _make_error_response(
            category="network_error",
            message=str(exc),
            tool_name=tool_name,
        )


@mcp.tool()
async def create_section(notebook_id: str, display_name: str) -> dict:
    """Create a new section in a notebook.

    Args:
        notebook_id: The ID of the notebook to create the section in.
        display_name: The display name for the new section.

    Returns:
        A dictionary with the created section's id and displayName, or an error.
    """
    tool_name = "create_section"

    # Input validation
    invalid_fields: dict[str, str] = {}
    if not notebook_id or not notebook_id.strip():
        invalid_fields["notebook_id"] = "notebookId is required and cannot be empty"
    if not display_name or not display_name.strip():
        invalid_fields["display_name"] = "displayName is required and cannot be empty"

    if invalid_fields:
        return _make_error_response(
            category="validation_error",
            message="Invalid input parameters.",
            tool_name=tool_name,
            invalid_fields=invalid_fields,
        )

    try:
        graph_client = _get_graph_client()
        section = await graph_client.create_section(notebook_id, display_name)
        return {
            "id": section.id,
            "displayName": section.display_name,
            "notebookId": section.notebook_id,
            "summary": f"Created section '{section.display_name}'",
        }
    except AuthError as exc:
        return _make_error_response(
            category="auth_error",
            message=str(exc),
            tool_name=tool_name,
        )
    except GraphError as exc:
        return _make_error_response(
            category="graph_error",
            message=str(exc),
            tool_name=tool_name,
            status_code=exc.status_code,
        )
    except NetworkError as exc:
        return _make_error_response(
            category="network_error",
            message=str(exc),
            tool_name=tool_name,
        )


@mcp.tool()
async def clone_page_to_section(
    page_id: str, target_section_id: str, dry_run: bool = False
) -> dict:
    """Clone a page to a different section (works with personal Microsoft accounts).

    This is the recommended tool for moving pages when using a personal account
    (outlook.com, hotmail.com, live.com). It reads the page's HTML content and
    recreates it in the target section, bypassing the copyToSection 501 limitation.

    Note: The original page remains in place. Images/attachments may not transfer.

    Args:
        page_id: The ID of the page to clone.
        target_section_id: The ID of the destination section.
        dry_run: If True, return projected outcome without making changes.

    Returns:
        A dictionary with success status, the new page ID, and a summary.
    """
    tool_name = "clone_page_to_section"

    # Input validation
    invalid_fields: dict[str, str] = {}
    if not page_id or not page_id.strip():
        invalid_fields["page_id"] = "pageId is required and cannot be empty"
    if not target_section_id or not target_section_id.strip():
        invalid_fields["target_section_id"] = (
            "targetSectionId is required and cannot be empty"
        )

    if invalid_fields:
        return _make_error_response(
            category="validation_error",
            message="Invalid input parameters.",
            tool_name=tool_name,
            invalid_fields=invalid_fields,
        )

    try:
        graph_client = _get_graph_client()

        # Look up page and section metadata for the summary
        page_metadata = await graph_client.get_page_metadata(page_id)
        page_title = page_metadata.title or "Untitled"
        source_section_id = page_metadata.section_id

        # Same section check
        if source_section_id == target_section_id:
            summary = f"No clone necessary for '{page_title}' — already in the target section."
            result: dict = {"success": True, "summary": summary}
            if dry_run:
                result["dryRun"] = True
            return result

        target_section = await graph_client.get_section_metadata(target_section_id)
        target_name = target_section.display_name

        # Dry-run mode
        if dry_run:
            summary = f"Would clone '{page_title}' to '{target_name}'"
            return {"success": True, "dryRun": True, "summary": summary}

        # Live mode: clone the page
        new_page_id = await graph_client.clone_page_to_section(
            page_id, target_section_id
        )

        summary = f"Cloned '{page_title}' to '{target_name}'"
        if len(summary) > 256:
            summary = summary[:253] + "..."

        # Log the operation
        _logger.log_move(
            page_id=page_id,
            source_section_id=source_section_id or "unknown",
            target_section_id=target_section_id,
            success=True,
            summary=summary,
        )

        return {
            "success": True,
            "summary": summary,
            "newPageId": new_page_id,
        }

    except AuthError as exc:
        return _make_error_response(
            category="auth_error",
            message=str(exc),
            tool_name=tool_name,
        )
    except GraphError as exc:
        return _make_error_response(
            category="graph_error",
            message=str(exc),
            tool_name=tool_name,
            status_code=exc.status_code,
        )
    except NetworkError as exc:
        return _make_error_response(
            category="network_error",
            message=str(exc),
            tool_name=tool_name,
        )


@mcp.tool()
async def move_page_to_section(
    page_id: str, target_section_id: str, dry_run: bool = False
) -> dict:
    """Move a page to a different section.

    Uses clone approach (read HTML + post to target) for personal accounts,
    with fallback to copyToSection for organizational accounts.
    Supports dry-run mode to preview the operation without making changes.

    Args:
        page_id: The ID of the page to move.
        target_section_id: The ID of the destination section.
        dry_run: If True, return projected outcome without making changes.

    Returns:
        A dictionary with success status, summary, and optional dryRun flag.
    """
    tool_name = "move_page_to_section"

    # --- Input validation ---
    invalid_fields: dict[str, str] = {}
    if not page_id or not page_id.strip():
        invalid_fields["page_id"] = "pageId is required and cannot be empty"
    if not target_section_id or not target_section_id.strip():
        invalid_fields["target_section_id"] = (
            "targetSectionId is required and cannot be empty"
        )

    if invalid_fields:
        return _make_error_response(
            category="validation_error",
            message="Invalid input parameters.",
            tool_name=tool_name,
            invalid_fields=invalid_fields,
        )

    try:
        graph_client = _get_graph_client()

        # --- Look up page metadata to get current section and title ---
        page_metadata = await graph_client.get_page_metadata(page_id)
        page_title = page_metadata.title or "Untitled"
        source_section_id = page_metadata.section_id

        # --- Same-source-target: no-op ---
        if source_section_id == target_section_id:
            summary = f"No move necessary for '{page_title}' — already in the target section."
            if len(summary) > 256:
                summary = summary[:253] + "..."
            result: dict = {"success": True, "summary": summary}
            if dry_run:
                result["dryRun"] = True
            return result

        # --- Look up section metadata for display names ---
        source_section = await graph_client.get_section_metadata(source_section_id)
        target_section = await graph_client.get_section_metadata(target_section_id)
        source_name = source_section.display_name
        target_name = target_section.display_name

        # --- Dry-run mode ---
        if dry_run:
            summary = (
                f"Would move '{page_title}' from '{source_name}' to '{target_name}'"
            )
            if len(summary) > 256:
                summary = summary[:253] + "..."
            return {"success": True, "dryRun": True, "summary": summary}

        # --- Live mode: try clone approach first (works on personal accounts),
        #     fall back to copyToSection if clone fails ---
        try:
            new_page_id = await graph_client.clone_page_to_section(
                page_id, target_section_id
            )
            summary = (
                f"Moved '{page_title}' from '{source_name}' to '{target_name}'"
            )
            if len(summary) > 256:
                summary = summary[:253] + "..."

            _logger.log_move(
                page_id=page_id,
                source_section_id=source_section_id,
                target_section_id=target_section_id,
                success=True,
                summary=summary,
            )

            return {"success": True, "summary": summary, "newPageId": new_page_id}

        except (GraphError, NetworkError):
            # Clone failed — fall back to copyToSection (for org accounts)
            pass

        # Fallback: copyToSection (works on organizational accounts)
        operation_url = await graph_client.copy_page_to_section(
            page_id, target_section_id
        )
        operation_result = await graph_client.poll_operation(operation_url)

        if operation_result.status == "completed":
            summary = (
                f"Moved '{page_title}' from '{source_name}' to '{target_name}'"
            )
            if len(summary) > 256:
                summary = summary[:253] + "..."

            # Log the successful operation
            _logger.log_move(
                page_id=page_id,
                source_section_id=source_section_id,
                target_section_id=target_section_id,
                success=True,
                summary=summary,
            )

            return {"success": True, "summary": summary}
        else:
            # Operation failed
            error_msg = operation_result.error_message or "Move operation failed"
            summary = (
                f"Failed to move '{page_title}' from '{source_name}' to "
                f"'{target_name}': {error_msg}"
            )
            if len(summary) > 256:
                summary = summary[:253] + "..."

            # Log the failed operation
            _logger.log_move(
                page_id=page_id,
                source_section_id=source_section_id,
                target_section_id=target_section_id,
                success=False,
                summary=summary,
            )

            return {"success": False, "summary": summary}

    except AuthError as exc:
        return _make_error_response(
            category="auth_error",
            message=str(exc),
            tool_name=tool_name,
        )
    except GraphError as exc:
        return _make_error_response(
            category="graph_error",
            message=str(exc),
            tool_name=tool_name,
            status_code=exc.status_code,
        )
    except NetworkError as exc:
        return _make_error_response(
            category="network_error",
            message=str(exc),
            tool_name=tool_name,
        )

@mcp.tool()
async def rename_page(page_id: str, new_title: str, dry_run: bool = False) -> dict:
    """Rename a page with a new title.

    Args:
        page_id: The ID of the page to rename.
        new_title: The new title for the page (non-empty, max 256 characters).
        dry_run: If True, return projected outcome without making changes.

    Returns:
        A dictionary with success, summary, and optionally dryRun fields,
        or an error response.
    """
    tool_name = "rename_page"

    # --- Input Validation ---
    # Validate page_id
    if not page_id or not page_id.strip():
        return _make_error_response(
            category="validation_error",
            message="page_id is required and must not be empty.",
            tool_name=tool_name,
            invalid_fields={"page_id": "Required parameter is missing or empty"},
        )

    # Validate new_title: not empty
    if not new_title:
        return _make_error_response(
            category="validation_error",
            message="newTitle is required and must not be empty.",
            tool_name=tool_name,
            invalid_fields={"new_title": "Title must not be empty"},
        )

    # Validate new_title: not whitespace-only
    if not new_title.strip():
        return _make_error_response(
            category="validation_error",
            message="newTitle must not be whitespace-only.",
            tool_name=tool_name,
            invalid_fields={"new_title": "Title must not contain only whitespace"},
        )

    # Validate new_title: max 256 characters
    if len(new_title) > 256:
        return _make_error_response(
            category="validation_error",
            message="newTitle must not exceed 256 characters.",
            tool_name=tool_name,
            invalid_fields={"new_title": "Title must not exceed 256 characters"},
        )

    try:
        graph_client = _get_graph_client()

        # Get current page metadata to learn the current title
        page_metadata = await graph_client.get_page_metadata(page_id)
        current_title = page_metadata.title

        # Handle same-title case (no-op)
        if new_title == current_title:
            return {
                "success": True,
                "summary": f"No rename necessary, '{current_title}' already has this title",
            }

        # Dry-run mode: return projected outcome without mutations
        if dry_run:
            return {
                "success": True,
                "dryRun": True,
                "summary": f"Would rename '{current_title}' to '{new_title}'",
            }

        # Live mode: perform the rename
        await graph_client.update_page_title(page_id, new_title)

        summary = f"Renamed '{current_title}' to '{new_title}'"

        # Log the operation
        _logger.log_rename(
            page_id=page_id,
            old_title=current_title,
            new_title=new_title,
            success=True,
            summary=summary,
        )

        return {
            "success": True,
            "summary": summary,
        }

    except AuthError as exc:
        return _make_error_response(
            category="auth_error",
            message=str(exc),
            tool_name=tool_name,
        )
    except GraphError as exc:
        return _make_error_response(
            category="graph_error",
            message=str(exc),
            tool_name=tool_name,
            status_code=exc.status_code,
        )
    except NetworkError as exc:
        return _make_error_response(
            category="network_error",
            message=str(exc),
            tool_name=tool_name,
        )


# --- Common stop words for keyword extraction ---
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "this", "that", "was", "are",
    "be", "has", "had", "have", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "not", "no", "so", "if",
    "then", "than", "when", "what", "which", "who", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "once",
    "up", "down", "here", "there", "where", "why", "about", "its", "my",
    "your", "his", "her", "our", "their", "me", "him", "us", "them",
    "i", "you", "he", "she", "we", "they", "new", "old", "page",
    "untitled", "",
})


def _extract_keywords(title: str) -> set[str]:
    """Extract meaningful keywords from a page title.

    Splits on whitespace and non-alphanumeric characters, lowercases,
    removes common stop words, and returns the remaining tokens.
    """
    # Split on non-alphanumeric characters
    tokens = re.split(r"[^a-zA-Z0-9]+", title.lower())
    return {t for t in tokens if t and t not in _STOP_WORDS and len(t) > 1}


def _group_by_topic(
    all_pages: list[tuple[str, str, str]],
    notebook_id: str,
) -> dict:
    """Group pages by title keyword similarity.

    Args:
        all_pages: List of (page_id, title, section_id) tuples.
        notebook_id: The notebook ID for suggested sections.

    Returns:
        A dict with suggestedSections and pageMoves.
    """
    from collections import defaultdict

    # Build keyword -> pages mapping
    keyword_pages: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for page_id, title, section_id in all_pages:
        keywords = _extract_keywords(title)
        for kw in keywords:
            keyword_pages[kw].append((page_id, section_id))

    # Find keywords that group multiple pages (at least 2)
    # Sort by group size descending to prioritize larger clusters
    significant_keywords = sorted(
        [(kw, pages) for kw, pages in keyword_pages.items() if len(pages) >= 2],
        key=lambda x: len(x[1]),
        reverse=True,
    )

    # Assign pages to sections based on their dominant keyword
    # Each page goes to at most one suggested section
    assigned_pages: set[str] = set()
    suggested_sections: list[dict] = []
    page_moves: list[dict] = []

    for keyword, pages in significant_keywords:
        # Create a section name from the keyword (capitalize)
        section_display_name = keyword.capitalize()

        # Check if any unassigned pages belong to this group
        unassigned_in_group = [
            (pid, sid) for pid, sid in pages if pid not in assigned_pages
        ]

        if len(unassigned_in_group) < 2:
            continue

        # Add the suggested section
        suggested_sections.append({
            "displayName": section_display_name,
            "notebookId": notebook_id,
        })

        # Add page moves for pages in this group
        for page_id, source_section_id in unassigned_in_group:
            assigned_pages.add(page_id)
            page_moves.append({
                "pageId": page_id,
                "sourceSectionId": source_section_id,
                "targetSectionDisplayName": section_display_name,
            })

    return {
        "suggestedSections": suggested_sections,
        "pageMoves": page_moves,
    }


def _group_by_date(
    all_pages_with_dates: list[tuple[str, str, str, str]],
    notebook_id: str,
) -> dict:
    """Group pages by lastModifiedDateTime into monthly buckets.

    Args:
        all_pages_with_dates: List of (page_id, title, section_id, last_modified_iso) tuples.
        notebook_id: The notebook ID for suggested sections.

    Returns:
        A dict with suggestedSections and pageMoves.
    """
    from collections import defaultdict
    from datetime import datetime

    # Group pages by year-month
    month_buckets: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for page_id, title, section_id, last_modified_iso in all_pages_with_dates:
        try:
            dt = datetime.fromisoformat(last_modified_iso)
            bucket_key = dt.strftime("%Y-%m")
        except (ValueError, TypeError):
            # If date parsing fails, put in an "Unknown" bucket
            bucket_key = "Unknown"
        month_buckets[bucket_key].append((page_id, section_id))

    # Sort buckets chronologically
    sorted_buckets = sorted(month_buckets.items())

    suggested_sections: list[dict] = []
    page_moves: list[dict] = []

    for bucket_key, pages in sorted_buckets:
        section_display_name = bucket_key  # e.g., "2024-01"

        suggested_sections.append({
            "displayName": section_display_name,
            "notebookId": notebook_id,
        })

        for page_id, source_section_id in pages:
            page_moves.append({
                "pageId": page_id,
                "sourceSectionId": source_section_id,
                "targetSectionDisplayName": section_display_name,
            })

    return {
        "suggestedSections": suggested_sections,
        "pageMoves": page_moves,
    }


def _group_by_tag(
    all_pages: list[tuple[str, str, str]],
    notebook_id: str,
) -> dict:
    """Group pages by common keywords (tags) from titles.

    Args:
        all_pages: List of (page_id, title, section_id) tuples.
        notebook_id: The notebook ID for suggested sections.

    Returns:
        A dict with suggestedSections and pageMoves.
    """
    from collections import Counter, defaultdict

    # Count keyword frequency across all pages
    keyword_counter: Counter = Counter()
    page_keywords: dict[str, set[str]] = {}

    for page_id, title, section_id in all_pages:
        keywords = _extract_keywords(title)
        page_keywords[page_id] = keywords
        keyword_counter.update(keywords)

    # Select the most common keywords as tag-based sections
    # Only use keywords that appear in at least 2 pages
    common_keywords = [
        kw for kw, count in keyword_counter.most_common()
        if count >= 2
    ]

    # Limit to a reasonable number of sections (top 10)
    common_keywords = common_keywords[:10]

    # Assign pages to their best-matching keyword section
    assigned_pages: set[str] = set()
    suggested_sections: list[dict] = []
    page_moves: list[dict] = []

    for keyword in common_keywords:
        section_display_name = keyword.capitalize()

        # Find pages that have this keyword and are not yet assigned
        matching_pages = [
            (pid, title, sid)
            for pid, title, sid in all_pages
            if pid not in assigned_pages and keyword in page_keywords.get(pid, set())
        ]

        if len(matching_pages) < 2:
            continue

        suggested_sections.append({
            "displayName": section_display_name,
            "notebookId": notebook_id,
        })

        for page_id, title, source_section_id in matching_pages:
            assigned_pages.add(page_id)
            page_moves.append({
                "pageId": page_id,
                "sourceSectionId": source_section_id,
                "targetSectionDisplayName": section_display_name,
            })

    return {
        "suggestedSections": suggested_sections,
        "pageMoves": page_moves,
    }


@mcp.tool()
async def apply_reorganization_plan(
    plan: dict, dry_run: bool = False, batch_size: int = 10, offset: int = 0
) -> dict:
    """Execute an approved reorganization plan.

    Validates the plan structure and all referenced resources before making
    any mutations. Supports dry-run mode to preview changes without modifying data.

    For large plans (many page moves), use batch_size and offset to process
    moves in batches across multiple calls, avoiding timeouts.

    Args:
        plan: A reorganization plan with "suggestedSections" and "pageMoves" arrays.
        dry_run: If True, validate and return forecast without making changes.
        batch_size: Max number of page moves to execute in this call (default 10).
        offset: Starting index in pageMoves to process from (default 0).
            Set to 0 on first call. Use the returned "nextOffset" for subsequent calls.

    Returns:
        A dictionary with success status, summary, any errors encountered,
        and "nextOffset" if more moves remain.
    """
    tool_name = "apply_reorganization_plan"

    # --- 1. Validate plan structure ---
    if not isinstance(plan, dict):
        return _make_error_response(
            category="validation_error",
            message="Plan must be a dictionary.",
            tool_name=tool_name,
            invalid_fields={"plan": "Plan must be a dictionary"},
        )

    suggested_sections = plan.get("suggestedSections")
    page_moves = plan.get("pageMoves")

    invalid_fields: dict[str, str] = {}

    if suggested_sections is None or not isinstance(suggested_sections, list):
        invalid_fields["suggestedSections"] = (
            "suggestedSections is required and must be a list"
        )

    if page_moves is None or not isinstance(page_moves, list):
        invalid_fields["pageMoves"] = "pageMoves is required and must be a list"

    if invalid_fields:
        return _make_error_response(
            category="validation_error",
            message="Invalid plan structure.",
            tool_name=tool_name,
            invalid_fields=invalid_fields,
        )

    # Validate each suggestedSection has required fields
    for i, section in enumerate(suggested_sections):
        if not isinstance(section, dict):
            invalid_fields[f"suggestedSections[{i}]"] = "Must be a dictionary"
            continue
        if not section.get("displayName") or not isinstance(
            section.get("displayName"), str
        ):
            invalid_fields[f"suggestedSections[{i}].displayName"] = (
                "displayName is required and must be a non-empty string"
            )
        if not section.get("notebookId") or not isinstance(
            section.get("notebookId"), str
        ):
            invalid_fields[f"suggestedSections[{i}].notebookId"] = (
                "notebookId is required and must be a non-empty string"
            )

    # Validate each pageMove has required fields
    for i, move in enumerate(page_moves):
        if not isinstance(move, dict):
            invalid_fields[f"pageMoves[{i}]"] = "Must be a dictionary"
            continue
        if not move.get("pageId") or not isinstance(move.get("pageId"), str):
            invalid_fields[f"pageMoves[{i}].pageId"] = (
                "pageId is required and must be a non-empty string"
            )
        if not move.get("sourceSectionId") or not isinstance(
            move.get("sourceSectionId"), str
        ):
            invalid_fields[f"pageMoves[{i}].sourceSectionId"] = (
                "sourceSectionId is required and must be a non-empty string"
            )
        if not move.get("targetSectionDisplayName") or not isinstance(
            move.get("targetSectionDisplayName"), str
        ):
            invalid_fields[f"pageMoves[{i}].targetSectionDisplayName"] = (
                "targetSectionDisplayName is required and must be a non-empty string"
            )

    if invalid_fields:
        return _make_error_response(
            category="validation_error",
            message="Invalid plan structure.",
            tool_name=tool_name,
            invalid_fields=invalid_fields,
        )

    # --- 2. Validate references exist (before any mutations) ---
    try:
        graph_client = _get_graph_client()

        invalid_refs: list[str] = []

        # Verify notebooks exist (collect unique notebookIds from suggestedSections)
        notebook_ids = {s["notebookId"] for s in suggested_sections}
        for nb_id in notebook_ids:
            try:
                await graph_client.list_sections(nb_id)
            except GraphError:
                invalid_refs.append(f"notebook:{nb_id}")

        # Verify all referenced pages exist
        page_ids = {m["pageId"] for m in page_moves}
        for page_id in page_ids:
            try:
                await graph_client.get_page_metadata(page_id)
            except GraphError:
                invalid_refs.append(f"page:{page_id}")

        if invalid_refs:
            return _make_error_response(
                category="validation_error",
                message=f"Plan references non-existent resources: {', '.join(invalid_refs)}",
                tool_name=tool_name,
                invalid_fields={
                    ref: "Resource does not exist" for ref in invalid_refs
                },
            )

    except AuthError as exc:
        return _make_error_response(
            category="auth_error",
            message=str(exc),
            tool_name=tool_name,
        )
    except NetworkError as exc:
        return _make_error_response(
            category="network_error",
            message=str(exc),
            tool_name=tool_name,
        )

    # --- 3. Dry-run mode ---
    num_sections = len(suggested_sections)
    num_moves = len(page_moves)

    if dry_run:
        summary = f"Would create {num_sections} sections and move {num_moves} pages"
        if len(summary) > 256:
            summary = summary[:253] + "..."
        return {
            "success": True,
            "dryRun": True,
            "summary": summary,
        }

    # --- 4. Live mode: create sections, then move pages in batches ---
    import asyncio

    errors: list[str] = []
    sections_created = 0
    pages_moved = 0

    # Map displayName -> created section ID (for page move targeting)
    created_section_map: dict[str, str] = {}
    failed_sections: set[str] = set()

    # Create missing sections first (only on first batch / offset == 0)
    if offset == 0:
        for section_spec in suggested_sections:
            display_name = section_spec["displayName"]
            notebook_id = section_spec["notebookId"]
            try:
                new_section = await graph_client.create_section(notebook_id, display_name)
                created_section_map[display_name] = new_section.id
                sections_created += 1
            except (GraphError, NetworkError) as exc:
                failed_sections.add(display_name)
                errors.append(
                    f"Failed to create section '{display_name}': {exc}"
                )
    else:
        # For subsequent batches, look up existing sections by display name
        # (they were created in the first batch)
        notebook_ids = {s["notebookId"] for s in suggested_sections}
        for nb_id in notebook_ids:
            try:
                existing_sections = await graph_client.list_sections(nb_id)
                for sec in existing_sections:
                    created_section_map[sec.display_name] = sec.id
            except (GraphError, NetworkError):
                pass

    # Slice the page moves for this batch
    batch_end = min(offset + batch_size, len(page_moves))
    batch_moves = page_moves[offset:batch_end]

    # Process page moves concurrently (up to 5 at a time)
    semaphore = asyncio.Semaphore(5)

    async def move_one_page(move_spec: dict) -> tuple[bool, str | None]:
        """Move a single page. Returns (success, error_message_or_None)."""
        page_id = move_spec["pageId"]
        target_display_name = move_spec["targetSectionDisplayName"]

        if target_display_name in failed_sections:
            return False, (
                f"Skipped moving page '{page_id}' — "
                f"target section '{target_display_name}' failed to create"
            )

        target_section_id = created_section_map.get(target_display_name)
        if target_section_id is None:
            return False, (
                f"Skipped moving page '{page_id}' — "
                f"target section '{target_display_name}' not found in created sections"
            )

        async with semaphore:
            try:
                operation_url = await graph_client.copy_page_to_section(
                    page_id, target_section_id
                )
                operation_result = await graph_client.poll_operation(operation_url)

                if operation_result.status == "completed":
                    return True, None
                else:
                    error_msg = operation_result.error_message or "Move operation failed"
                    return False, (
                        f"Failed to move page '{page_id}' to '{target_display_name}': {error_msg}"
                    )
            except (GraphError, NetworkError) as exc:
                return False, (
                    f"Failed to move page '{page_id}' to '{target_display_name}': {exc}"
                )

    # Execute batch concurrently
    results = await asyncio.gather(
        *(move_one_page(move_spec) for move_spec in batch_moves),
        return_exceptions=False,
    )

    for success, error_msg in results:
        if success:
            pages_moved += 1
        elif error_msg:
            errors.append(error_msg)

    # --- 5. Generate summary and log ---
    has_more = batch_end < len(page_moves)
    total_processed = batch_end
    total_remaining = len(page_moves) - batch_end

    summary = f"Created {sections_created} sections and moved {pages_moved} pages"
    if has_more:
        summary += f" (batch {offset}-{batch_end} of {len(page_moves)} total, {total_remaining} remaining)"
    if len(summary) > 256:
        summary = summary[:253] + "..."

    # Determine overall success
    success = len(errors) == 0

    # Log the operation
    log_notebook_id = (
        suggested_sections[0]["notebookId"] if suggested_sections else "unknown"
    )
    _logger.log_apply_plan(
        notebook_id=log_notebook_id,
        sections_created=sections_created,
        pages_moved=pages_moved,
        errors=errors,
        summary=summary,
    )

    result: dict = {
        "success": success,
        "summary": summary,
        "pagesMoved": pages_moved,
        "sectionsCreated": sections_created,
        "totalPageMoves": len(page_moves),
        "processedUpTo": batch_end,
    }
    if has_more:
        result["nextOffset"] = batch_end
        result["remaining"] = total_remaining
    if errors:
        result["errors"] = errors

    return result


@mcp.tool()
async def bulk_plan_reorganization(
    notebook_id: str, strategy: str = "by_topic"
) -> dict:
    """Generate a reorganization plan for a notebook.

    Analyzes existing sections and pages to propose a structural reorganization
    based on the chosen strategy. This is a read-only operation — no notebook
    data is modified.

    Args:
        notebook_id: The ID of the notebook to analyze.
        strategy: Grouping strategy — one of "by_topic", "by_date", or "by_tag".
                  Defaults to "by_topic".

    Returns:
        A dict with suggestedSections and pageMoves arrays, or an error response.
    """
    tool_name = "bulk_plan_reorganization"
    valid_strategies = ("by_topic", "by_date", "by_tag")

    # --- Input validation ---
    invalid_fields: dict[str, str] = {}

    if not notebook_id or not notebook_id.strip():
        invalid_fields["notebook_id"] = "notebookId is required and cannot be empty"

    if strategy not in valid_strategies:
        invalid_fields["strategy"] = (
            f"strategy must be one of: {', '.join(valid_strategies)}"
        )

    if invalid_fields:
        return _make_error_response(
            category="validation_error",
            message="Invalid input parameters.",
            tool_name=tool_name,
            invalid_fields=invalid_fields,
        )

    try:
        graph_client = _get_graph_client()

        # --- Fetch all sections for the notebook ---
        sections = await graph_client.list_sections(notebook_id)

        # --- Fetch all pages for each section ---
        # Collect page data depending on strategy needs
        all_pages: list[tuple[str, str, str]] = []  # (page_id, title, section_id)
        all_pages_with_dates: list[tuple[str, str, str, str]] = []  # + last_modified

        for section in sections:
            pages = await graph_client.list_pages(section.id)
            for page in pages:
                all_pages.append((page.id, page.title, section.id))
                all_pages_with_dates.append((
                    page.id,
                    page.title,
                    section.id,
                    page.last_modified.isoformat(),
                ))

        # --- Apply the chosen strategy ---
        if strategy == "by_topic":
            plan = _group_by_topic(all_pages, notebook_id)
        elif strategy == "by_date":
            plan = _group_by_date(all_pages_with_dates, notebook_id)
        elif strategy == "by_tag":
            plan = _group_by_tag(all_pages, notebook_id)
        else:
            # Should not reach here due to earlier validation
            plan = {"suggestedSections": [], "pageMoves": []}

        return plan

    except AuthError as exc:
        return _make_error_response(
            category="auth_error",
            message=str(exc),
            tool_name=tool_name,
        )
    except GraphError as exc:
        return _make_error_response(
            category="graph_error",
            message=str(exc),
            tool_name=tool_name,
            status_code=exc.status_code,
        )
    except NetworkError as exc:
        return _make_error_response(
            category="network_error",
            message=str(exc),
            tool_name=tool_name,
        )
