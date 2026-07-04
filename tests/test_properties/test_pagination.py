"""Property 2: Pagination Collects All Items.

For any paginated response with N total items, pagination logic collects
exactly N items with no duplicates.

Validates: Requirements 4.1, 5.1, 6.1
"""

# Feature: onenote-organizer, Property 2: Pagination Collects All Items

from __future__ import annotations

from typing import Any

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from unittest.mock import AsyncMock

from onenote_organizer.graph_client import GraphClient


def _make_page_response(items: list[dict], next_link: str | None = None) -> dict:
    """Create a Graph API page response with optional nextLink."""
    response: dict[str, Any] = {"value": items}
    if next_link is not None:
        response["@odata.nextLink"] = next_link
    return response


# Strategy: generate a list of pages (1-5 pages), each with 0-10 items
pages_strategy = st.lists(
    st.integers(min_value=0, max_value=10),
    min_size=1,
    max_size=5,
)


class TestPaginationCollectsAllItems:
    """Verify that _paginated_get collects exactly N items with no duplicates."""

    # **Validates: Requirements 4.1, 5.1, 6.1**

    @given(items_per_page=pages_strategy)
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_paginated_get_collects_all_items(
        self, items_per_page: list[int],
    ) -> None:
        """For any N items split across pages, _paginated_get returns exactly N items
        with no duplicates and no omissions."""

        # Build pages with unique items; each page has a variable number of items
        pages: list[list[dict]] = []
        item_counter = 0
        all_items: list[dict] = []

        for page_item_count in items_per_page:
            page_items = [
                {"id": f"item-{item_counter + i}", "displayName": f"Item {item_counter + i}"}
                for i in range(page_item_count)
            ]
            pages.append(page_items)
            all_items.extend(page_items)
            item_counter += page_item_count

        total_items = len(all_items)
        base_url = "https://graph.microsoft.com/v1.0/me/onenote/notebooks"

        # Build URL -> response body mapping simulating @odata.nextLink pagination
        url_map: dict[str, dict] = {}
        for page_idx, page_items in enumerate(pages):
            if page_idx == 0:
                url = base_url
            else:
                url = f"{base_url}?$skip={page_idx}"

            # Add nextLink for all pages except the last
            if page_idx < len(pages) - 1:
                next_link = f"{base_url}?$skip={page_idx + 1}"
            else:
                next_link = None

            url_map[url] = _make_page_response(page_items, next_link)

        # Mock auth provider to return a static token
        mock_auth = AsyncMock()
        mock_auth.get_access_token.return_value = "fake-token"

        client = GraphClient(mock_auth)

        # Mock _request to simulate httpx responses for paginated Graph API
        async def mock_request(method: str, url: str, **kwargs: Any) -> httpx.Response:
            body = url_map.get(url)
            if body is None:
                raise httpx.HTTPStatusError(
                    "Not found",
                    request=httpx.Request("GET", url),
                    response=httpx.Response(404),
                )
            return httpx.Response(
                status_code=200,
                json=body,
                request=httpx.Request("GET", url),
            )

        client._request = mock_request  # type: ignore[assignment]

        result = await client._paginated_get(base_url)

        # Verify exactly N items collected
        assert len(result) == total_items

        # Verify no duplicates (all IDs are unique)
        ids = [item["id"] for item in result]
        assert len(set(ids)) == len(ids)

        # Verify all original items are present (no omissions)
        expected_ids = {item["id"] for item in all_items}
        actual_ids = set(ids)
        assert actual_ids == expected_ids
