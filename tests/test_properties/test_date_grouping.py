# Feature: onenote-organizer, Property 10: Date-Range Grouping Coherence
"""
Property 10: Date-Range Grouping Coherence

For any set of pages with lastModifiedDateTime values, when grouped using the
"by_date" strategy, all pages within the same suggested section should have dates
that fall within a single contiguous date range, and no two suggested sections
should have overlapping date ranges.

Validates: Requirements 10.3
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from onenote_organizer.server import _group_by_date


# Strategy: generate ISO datetime strings as YYYY-MM-DDTHH:MM:SS
_iso_datetime_strategy = st.builds(
    lambda y, m, d, h, mi, s: f"{y:04d}-{m:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:02d}",
    y=st.integers(min_value=2000, max_value=2030),
    m=st.integers(min_value=1, max_value=12),
    d=st.integers(min_value=1, max_value=28),  # safe for all months
    h=st.integers(min_value=0, max_value=23),
    mi=st.integers(min_value=0, max_value=59),
    s=st.integers(min_value=0, max_value=59),
)

non_empty_id = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=20,
)

notebook_id_strategy = non_empty_id


@st.composite
def unique_pages_strategy(draw: st.DrawFn) -> list[tuple[str, str, str, str]]:
    """Generate a list of page tuples with unique page_ids."""
    n = draw(st.integers(min_value=1, max_value=30))
    pages = []
    used_ids: set[str] = set()
    for i in range(n):
        # Use index-based IDs to guarantee uniqueness
        page_id = f"page-{i}"
        title = draw(non_empty_id)
        section_id = draw(non_empty_id)
        last_modified = draw(_iso_datetime_strategy)
        pages.append((page_id, title, section_id, last_modified))
        used_ids.add(page_id)
    return pages


# Validates: Requirements 10.3
@settings(max_examples=100)
@given(
    pages=unique_pages_strategy(),
    notebook_id=notebook_id_strategy,
)
def test_pages_in_same_section_share_same_month(
    pages: list[tuple[str, str, str, str]],
    notebook_id: str,
) -> None:
    """All pages within the same suggestedSection have dates in the same YYYY-MM bucket."""
    result = _group_by_date(pages, notebook_id)

    # Build a mapping: targetSectionDisplayName -> list of page_ids
    section_to_pages: dict[str, list[str]] = {}
    for move in result["pageMoves"]:
        section_name = move["targetSectionDisplayName"]
        section_to_pages.setdefault(section_name, []).append(move["pageId"])

    # Build a mapping: page_id -> last_modified_iso (from input)
    page_dates: dict[str, str] = {}
    for page_id, _title, _section_id, last_modified_iso in pages:
        page_dates[page_id] = last_modified_iso

    # Verify: all pages in a section share the same YYYY-MM
    from datetime import datetime

    for section_name, page_ids in section_to_pages.items():
        months_in_section: set[str] = set()
        for page_id in page_ids:
            iso_str = page_dates[page_id]
            try:
                dt = datetime.fromisoformat(iso_str)
                months_in_section.add(dt.strftime("%Y-%m"))
            except (ValueError, TypeError):
                months_in_section.add("Unknown")

        # All pages in this section must share one YYYY-MM bucket
        assert len(months_in_section) == 1, (
            f"Section '{section_name}' has pages from multiple months: {months_in_section}"
        )


# Validates: Requirements 10.3
@settings(max_examples=100)
@given(
    pages=unique_pages_strategy(),
    notebook_id=notebook_id_strategy,
)
def test_no_overlapping_date_ranges_between_sections(
    pages: list[tuple[str, str, str, str]],
    notebook_id: str,
) -> None:
    """No two suggested sections have the same YYYY-MM bucket (no overlap)."""
    result = _group_by_date(pages, notebook_id)

    # Each suggested section displayName should be unique
    display_names = [s["displayName"] for s in result["suggestedSections"]]
    assert len(display_names) == len(set(display_names)), (
        f"Duplicate section display names found: {display_names}"
    )


# Validates: Requirements 10.3
@settings(max_examples=100)
@given(
    pages=unique_pages_strategy(),
    notebook_id=notebook_id_strategy,
)
def test_every_page_appears_in_exactly_one_page_move(
    pages: list[tuple[str, str, str, str]],
    notebook_id: str,
) -> None:
    """Every page in the input appears in exactly one pageMove in the output."""
    result = _group_by_date(pages, notebook_id)

    input_page_ids = [page_id for page_id, _, _, _ in pages]
    output_page_ids = [move["pageId"] for move in result["pageMoves"]]

    # Every input page must appear in the output
    assert set(input_page_ids) == set(output_page_ids), (
        f"Input pages: {set(input_page_ids)}, Output pages: {set(output_page_ids)}"
    )

    # Each page appears exactly once (same count)
    assert len(output_page_ids) == len(input_page_ids), (
        f"Expected {len(input_page_ids)} page moves, got {len(output_page_ids)}"
    )
