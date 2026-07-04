# Feature: onenote-organizer, Property 6: HTML-to-Text Stripping Preserves Visible Content
"""
Property 6: HTML-to-Text Stripping Preserves Visible Content

For any valid HTML, converting it to text format should produce output that
contains no HTML tags (no `<` followed by a tag name followed by `>`) and
preserves all visible text content from the original HTML.

Validates: Requirements 7.2
"""

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from onenote_organizer.server import _strip_html_tags

# Common HTML tag names to wrap text in
HTML_TAGS = [
    "p",
    "div",
    "span",
    "b",
    "i",
    "em",
    "strong",
    "h1",
    "h2",
    "h3",
    "a",
    "li",
    "ul",
    "ol",
    "td",
    "tr",
    "table",
    "section",
    "article",
    "header",
    "footer",
]

# Strategy: generate visible text content (no angle brackets to avoid ambiguity)
visible_text = st.text(
    alphabet=st.characters(
        codec="utf-8",
        min_codepoint=32,
        max_codepoint=126,
        exclude_characters="<>&",
    ),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() != "")

# Strategy: pick a random HTML tag name
tag_strategy = st.sampled_from(HTML_TAGS)


@st.composite
def html_with_known_text(draw: st.DrawFn) -> tuple[str, list[str]]:
    """Generate HTML by wrapping known text fragments in random tags.

    Returns a tuple of (html_string, list_of_visible_text_fragments).
    """
    num_fragments = draw(st.integers(min_value=1, max_value=5))
    fragments: list[str] = []
    html_parts: list[str] = []

    for _ in range(num_fragments):
        text = draw(visible_text)
        tag = draw(tag_strategy)
        fragments.append(text)
        html_parts.append(f"<{tag}>{text}</{tag}>")

    html = "".join(html_parts)
    return html, fragments


# Validates: Requirements 7.2
@settings(max_examples=100)
@given(data=html_with_known_text())
def test_html_strip_contains_no_tags(data: tuple[str, list[str]]) -> None:
    """Output of _strip_html_tags contains no HTML tags."""
    html, _ = data
    result = _strip_html_tags(html)

    # No HTML tags should remain: no < followed by tag name followed by >
    assert not re.search(r"<[a-zA-Z][^>]*>", result), (
        f"Output still contains HTML tags: {result!r}"
    )
    # Also check for closing tags
    assert not re.search(r"</[a-zA-Z][^>]*>", result), (
        f"Output still contains closing HTML tags: {result!r}"
    )


# Validates: Requirements 7.2
@settings(max_examples=100)
@given(data=html_with_known_text())
def test_html_strip_preserves_visible_text(data: tuple[str, list[str]]) -> None:
    """All visible text fragments from the HTML are present in the output."""
    html, fragments = data
    result = _strip_html_tags(html)

    for fragment in fragments:
        # Normalize whitespace in both the fragment and result for comparison,
        # since the function collapses whitespace
        normalized_fragment = re.sub(r"\s+", " ", fragment).strip()
        normalized_result = re.sub(r"\s+", " ", result)
        assert normalized_fragment in normalized_result, (
            f"Visible text {normalized_fragment!r} not found in output {normalized_result!r}"
        )
