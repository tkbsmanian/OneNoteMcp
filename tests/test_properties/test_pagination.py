"""Property 2: Pagination Collects All Items.

For any paginated response with N total items, pagination logic collects
exactly N items with no duplicates.

Validates: Requirements 4.1, 5.1, 6.1
"""

# Feature: onenote-organizer, Property 2: Pagination Collects All Items

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from unittest.mock import AsyncMock, patch

from onenote_organizer.graph_client import GraphClient


def _make_page_response(items: list[dict], next_link: str | None = None) -> dict:
    """Create a Graph API page response with optional nextLink."""
    response: dict = {"value": items}
    if next_link is not None:
        response["@odata.nextLink"] = next_link
    return response


def _split_items_into_pages(
    items: list[dict], num_pages: int
) -> list[list[dict]]:
    """Split items into num_pages chunks (some may be empty if num_pages > len(items))."""
    if num_pages <= 0:
        return [items] if items else [[]]
    pages: list[list[dict]] = [[] for _ in range(num_pages)]
    for i, item in enumerate(items):
        pages[i % num_pages].append(item)
    return pages


def _create_mock_response(body: dict, request: httpx.Request) -> httpx.Response:
    """Create a proper httpx.Response with request set (needed for raise_for_status)."""
    response = httpx.Response(
        status_code=200,
        json=body,
        request=request,
    )
    return response


# Strategy: generate N items (0-50) and split across 1-5 pages
items_strategy = st.integers(min_value=0, max_value=50).flatmap(
    lambda n: st.tuples(
        st.just(n),
        st.integers(min_value=1, max_value=5),
    )
)


class TestPaginationCollectsAllItems:
    """Verify that _paginated_get collects exactly N items with no duplicates."""

    # **Validates: Requirements 4.1, 5.1, 6.1**

    @given(data=items_strategy)
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_paginated_get_collects_all_items(
        self, data: tuple[int, int]
    ) -> None:
        """For any N items split across pages, _paginated_get returns exactly N items."""
        n_items, num_pages = data

        # Generate N unique items with distinct IDs
        all_items = [{"id": f"item-{i}", "name": f"Item {i}"} for i in range(n_items)]

        # Split items across pages
        pages = _split_items_into_pages(all_items, num_pages)

        base_url = "https://graph.microsoft.com/v1.0/me/onenote/notebooks"

        # Build URL -> response body mapping
        url_map: dict[str, dict] = {}
        for page_idx, page_items in enumerate(pages):
            if page_idx == 0:
                url = base_url
            else:
                url = f"{base_url}?$skip={page_idx}"

            if page_idx < len(pages) - 1:
                next_link = f"{base_url}?$skip={page_idx + 1}"
            else:
                next_link = None

            url_map[url] = _make_page_response(page_items, next_link)

        # Mock the _request method directly on the GraphClient instance
        mock_auth = AsyncMock()
        mock_auth.get_access_token.return_value = "fake-token"

        client = GraphClient(mock_auth)

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
        assert len(result) == n_items

        # Verify no duplicates (all IDs are unique)
        ids = [item["id"] for item in result]
        assert len(set(ids)) == len(ids)

        # Verify all original items are present
        expected_ids = {f"item-{i}" for i in range(n_items)}
        actual_ids = set(ids)
        assert actual_ids == expected_ids

    @given(data=items_strategy)
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_paginated_get_no_omissions(
        self, data: tuple[int, int]
    ) -> None:
        """For any N items, no item from any page is omitted in the final result."""
        n_items, num_pages = data

        all_items = [
            {"id": f"entry-{i}", "value": i * 10} for i in range(n_items)
        ]
        pages = _split_items_into_pages(all_items, num_pages)

        base_url = "https://graph.microsoft.com/v1.0/me/onenote/sections/sec-1/pages"

        # Build URL -> response body mapping
        url_map: dict[str, dict] = {}
        for page_idx, page_items in enumerate(pages):
            if page_idx == 0:
                url = base_url
            else:
                url = f"{base_url}?$skip={page_idx}"

            if page_idx < len(pages) - 1:
                next_link = f"{base_url}?$skip={page_idx + 1}"
            else:
                next_link = None

            url_map[url] = _make_page_response(page_items, next_link)

        mock_auth = AsyncMock()
        mock_auth.get_access_token.return_value = "fake-token"

        client = GraphClient(mock_auth)

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

        # Every original item must appear in the result
        for item in all_items:
            assert item in result, f"Item {item['id']} was omitted from results"
