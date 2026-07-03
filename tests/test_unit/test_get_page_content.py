"""Unit tests for the get_page_content tool in server.py."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from onenote_organizer.models import AuthError, GraphError, NetworkError, PageMetadata
from onenote_organizer.server import _strip_html_tags, get_page_content


# --- HTML Stripping Tests ---


class TestStripHtmlTags:
    """Tests for the _strip_html_tags helper function."""

    def test_simple_html(self):
        html = "<p>Hello, world!</p>"
        assert _strip_html_tags(html) == "Hello, world!"

    def test_nested_tags(self):
        html = "<div><p>First <b>bold</b> paragraph.</p><p>Second.</p></div>"
        result = _strip_html_tags(html)
        assert "First" in result
        assert "bold" in result
        assert "Second" in result
        assert "<" not in result
        assert ">" not in result

    def test_empty_html(self):
        assert _strip_html_tags("") == ""

    def test_no_tags(self):
        assert _strip_html_tags("plain text") == "plain text"

    def test_whitespace_cleanup(self):
        html = "<p>  Hello   </p>  <p>  World  </p>"
        result = _strip_html_tags(html)
        # Should collapse excessive whitespace
        assert "  " not in result
        assert "Hello" in result
        assert "World" in result

    def test_complex_onenote_html(self):
        html = (
            '<!DOCTYPE html><html><head><title>My Page</title></head>'
            '<body><div id="content">'
            '<p style="font-size:12px">Notes from meeting</p>'
            "<ul><li>Item 1</li><li>Item 2</li></ul>"
            "</div></body></html>"
        )
        result = _strip_html_tags(html)
        assert "My Page" in result
        assert "Notes from meeting" in result
        assert "Item 1" in result
        assert "Item 2" in result
        assert "<" not in result

    def test_entities_preserved(self):
        # HTML entities are handled by the parser
        html = "<p>A &amp; B</p>"
        result = _strip_html_tags(html)
        assert "A & B" in result


# --- get_page_content Tool Tests ---


class TestGetPageContent:
    """Tests for the get_page_content MCP tool."""

    @pytest.fixture(autouse=True)
    def mock_graph_client(self):
        """Mock the graph client for all tests in this class."""
        mock_client = AsyncMock()
        with patch(
            "onenote_organizer.server._get_graph_client",
            return_value=mock_client,
        ):
            self.mock_client = mock_client
            yield mock_client

    async def test_get_page_content_html_format(self):
        """Test retrieving page content in HTML format."""
        self.mock_client.get_page_content.return_value = "<p>Hello</p>"
        self.mock_client.get_page_metadata.return_value = PageMetadata(
            id="page-123",
            title="Test Page",
            last_modified=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )

        result = await get_page_content("page-123", "html")

        assert result == {
            "id": "page-123",
            "title": "Test Page",
            "content": "<p>Hello</p>",
        }
        self.mock_client.get_page_content.assert_called_once_with("page-123")
        self.mock_client.get_page_metadata.assert_called_once_with("page-123")

    async def test_get_page_content_text_format(self):
        """Test retrieving page content in text format strips HTML."""
        self.mock_client.get_page_content.return_value = (
            "<div><p>Hello <b>World</b></p></div>"
        )
        self.mock_client.get_page_metadata.return_value = PageMetadata(
            id="page-456",
            title="Another Page",
            last_modified=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )

        result = await get_page_content("page-456", "text")

        assert result["id"] == "page-456"
        assert result["title"] == "Another Page"
        assert "<" not in result["content"]
        assert "Hello" in result["content"]
        assert "World" in result["content"]

    async def test_get_page_content_default_format_is_html(self):
        """Test that the default format is HTML."""
        self.mock_client.get_page_content.return_value = "<p>Content</p>"
        self.mock_client.get_page_metadata.return_value = PageMetadata(
            id="page-789",
            title="Default",
            last_modified=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )

        result = await get_page_content("page-789")

        assert result["content"] == "<p>Content</p>"

    async def test_invalid_format_returns_validation_error(self):
        """Test that invalid format returns a validation error."""
        result = await get_page_content("page-123", "xml")

        assert result["success"] is False
        assert result["error"]["category"] == "validation_error"
        assert result["error"]["toolName"] == "get_page_content"
        assert "format" in result["error"]["invalidFields"]

    async def test_empty_page_id_returns_validation_error(self):
        """Test that empty page_id returns a validation error."""
        result = await get_page_content("", "html")

        assert result["success"] is False
        assert result["error"]["category"] == "validation_error"
        assert result["error"]["toolName"] == "get_page_content"

    async def test_whitespace_page_id_returns_validation_error(self):
        """Test that whitespace-only page_id returns a validation error."""
        result = await get_page_content("   ", "html")

        assert result["success"] is False
        assert result["error"]["category"] == "validation_error"
        assert result["error"]["toolName"] == "get_page_content"

    async def test_graph_error_returns_structured_error(self):
        """Test that GraphError maps to graph_error category."""
        self.mock_client.get_page_content.side_effect = GraphError(
            message="Page not found", status_code=404
        )

        result = await get_page_content("nonexistent-page", "html")

        assert result["success"] is False
        assert result["error"]["category"] == "graph_error"
        assert result["error"]["statusCode"] == 404
        assert result["error"]["toolName"] == "get_page_content"
        assert "Page not found" in result["error"]["message"]

    async def test_auth_error_returns_structured_error(self):
        """Test that AuthError maps to auth_error category."""
        self.mock_client.get_page_content.side_effect = AuthError(
            "Token expired. Visit https://microsoft.com/devicelogin"
        )

        result = await get_page_content("page-123", "html")

        assert result["success"] is False
        assert result["error"]["category"] == "auth_error"
        assert result["error"]["toolName"] == "get_page_content"

    async def test_network_error_returns_structured_error(self):
        """Test that NetworkError maps to network_error category."""
        self.mock_client.get_page_content.side_effect = NetworkError(
            "Microsoft Graph service could not be reached: request timed out"
        )

        result = await get_page_content("page-123", "html")

        assert result["success"] is False
        assert result["error"]["category"] == "network_error"
        assert result["error"]["toolName"] == "get_page_content"
