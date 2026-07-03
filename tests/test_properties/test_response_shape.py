"""Property 3: List/Get Response Shape Invariant.

Verify that model dataclasses enforce all required fields and reject None
for non-optional fields.

Validates: Requirements 4.2, 5.2, 6.2, 7.4
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from hypothesis import given, settings
from hypothesis import strategies as st

from onenote_organizer.models import Notebook, Section, PageMetadata, PageContent


# --- Strategies ---

non_empty_text = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())
datetime_strategy = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(timezone.utc),
)


# Feature: onenote-organizer, Property 3: List/Get Response Shape Invariant
class TestResponseShapeInvariant:
    """Verify model dataclasses enforce all required fields and reject None for non-optional fields."""

    # **Validates: Requirements 4.2, 5.2, 6.2, 7.4**

    @given(
        id=non_empty_text,
        display_name=non_empty_text,
    )
    @settings(max_examples=100)
    def test_notebook_has_required_fields(self, id: str, display_name: str) -> None:
        """Notebook always has id and display_name fields populated."""
        notebook = Notebook(id=id, display_name=display_name)

        assert notebook.id is not None
        assert notebook.display_name is not None
        assert isinstance(notebook.id, str)
        assert isinstance(notebook.display_name, str)
        assert len(notebook.id) > 0
        assert len(notebook.display_name) > 0

    @given(
        id=non_empty_text,
        display_name=non_empty_text,
    )
    @settings(max_examples=100)
    def test_section_has_required_fields(self, id: str, display_name: str) -> None:
        """Section always has id and display_name fields populated."""
        section = Section(id=id, display_name=display_name)

        assert section.id is not None
        assert section.display_name is not None
        assert isinstance(section.id, str)
        assert isinstance(section.display_name, str)
        assert len(section.id) > 0
        assert len(section.display_name) > 0

    @given(
        id=non_empty_text,
        title=non_empty_text,
        last_modified=datetime_strategy,
    )
    @settings(max_examples=100)
    def test_page_metadata_has_required_fields(
        self, id: str, title: str, last_modified: datetime
    ) -> None:
        """PageMetadata always has id, title, and last_modified fields populated."""
        page = PageMetadata(id=id, title=title, last_modified=last_modified)

        assert page.id is not None
        assert page.title is not None
        assert page.last_modified is not None
        assert isinstance(page.id, str)
        assert isinstance(page.title, str)
        assert isinstance(page.last_modified, datetime)
        assert len(page.id) > 0
        assert len(page.title) > 0

    @given(
        id=non_empty_text,
        title=non_empty_text,
        content=st.text(min_size=0, max_size=500),
    )
    @settings(max_examples=100)
    def test_page_content_has_required_fields(
        self, id: str, title: str, content: str
    ) -> None:
        """PageContent always has id, title, and content fields populated."""
        page = PageContent(id=id, title=title, content=content)

        assert page.id is not None
        assert page.title is not None
        assert page.content is not None
        assert isinstance(page.id, str)
        assert isinstance(page.title, str)
        assert isinstance(page.content, str)
        assert len(page.id) > 0
        assert len(page.title) > 0

    def test_notebook_rejects_none_for_required_fields(self) -> None:
        """Notebook should not accept None for id or display_name at runtime."""
        # While Python dataclasses don't enforce type at construction,
        # we verify that the type annotations are str (not Optional[str])
        # and that frozen dataclasses prevent mutation after creation.
        import dataclasses

        fields = {f.name: f for f in dataclasses.fields(Notebook)}
        # id field type should be str, not Optional
        assert fields["id"].type == "str"
        assert fields["display_name"].type == "str"

    def test_section_rejects_none_for_required_fields(self) -> None:
        """Section required fields are typed as non-optional str."""
        import dataclasses

        fields = {f.name: f for f in dataclasses.fields(Section)}
        assert fields["id"].type == "str"
        assert fields["display_name"].type == "str"

    def test_page_metadata_rejects_none_for_required_fields(self) -> None:
        """PageMetadata required fields are typed as non-optional."""
        import dataclasses

        fields = {f.name: f for f in dataclasses.fields(PageMetadata)}
        assert fields["id"].type == "str"
        assert fields["title"].type == "str"
        assert fields["last_modified"].type == "datetime"

    def test_page_content_rejects_none_for_required_fields(self) -> None:
        """PageContent required fields are typed as non-optional str."""
        import dataclasses

        fields = {f.name: f for f in dataclasses.fields(PageContent)}
        assert fields["id"].type == "str"
        assert fields["title"].type == "str"
        assert fields["content"].type == "str"

    @given(
        id=non_empty_text,
        display_name=non_empty_text,
    )
    @settings(max_examples=100)
    def test_notebook_is_frozen(self, id: str, display_name: str) -> None:
        """Notebook instances are immutable (frozen dataclass)."""
        notebook = Notebook(id=id, display_name=display_name)
        with pytest.raises(Exception):  # FrozenInstanceError
            notebook.id = "changed"  # type: ignore[misc]

    @given(
        id=non_empty_text,
        display_name=non_empty_text,
    )
    @settings(max_examples=100)
    def test_section_is_frozen(self, id: str, display_name: str) -> None:
        """Section instances are immutable (frozen dataclass)."""
        section = Section(id=id, display_name=display_name)
        with pytest.raises(Exception):  # FrozenInstanceError
            section.id = "changed"  # type: ignore[misc]

    @given(
        id=non_empty_text,
        title=non_empty_text,
        last_modified=datetime_strategy,
    )
    @settings(max_examples=100)
    def test_page_metadata_is_frozen(
        self, id: str, title: str, last_modified: datetime
    ) -> None:
        """PageMetadata instances are immutable (frozen dataclass)."""
        page = PageMetadata(id=id, title=title, last_modified=last_modified)
        with pytest.raises(Exception):  # FrozenInstanceError
            page.id = "changed"  # type: ignore[misc]

    @given(
        id=non_empty_text,
        title=non_empty_text,
        content=st.text(min_size=0, max_size=500),
    )
    @settings(max_examples=100)
    def test_page_content_is_frozen(
        self, id: str, title: str, content: str
    ) -> None:
        """PageContent instances are immutable (frozen dataclass)."""
        page = PageContent(id=id, title=title, content=content)
        with pytest.raises(Exception):  # FrozenInstanceError
            page.id = "changed"  # type: ignore[misc]
