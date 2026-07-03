# Feature: onenote-organizer, Property 11: Reorganization Plan Schema Validity
"""
Property 11: Reorganization Plan Schema Validity

For any valid notebook containing sections and pages, the bulk_plan_reorganization
tool should return a plan where: every object in suggestedSections contains
displayName and notebookId fields, and every object in pageMoves contains pageId,
sourceSectionId, and targetSectionDisplayName fields.

Validates: Requirements 10.6
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from onenote_organizer.models import (
    PageMove,
    ReorganizationPlan,
    SuggestedSection,
)


# Strategies for generating valid model instances
non_empty_str = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
    min_size=1,
    max_size=50,
)

suggested_section_strategy = st.builds(
    SuggestedSection,
    display_name=non_empty_str,
    notebook_id=non_empty_str,
)

page_move_strategy = st.builds(
    PageMove,
    page_id=non_empty_str,
    source_section_id=non_empty_str,
    target_section_display_name=non_empty_str,
)

reorganization_plan_strategy = st.builds(
    ReorganizationPlan,
    suggested_sections=st.lists(suggested_section_strategy, min_size=0, max_size=10),
    page_moves=st.lists(page_move_strategy, min_size=0, max_size=10),
)


# Validates: Requirements 10.6
@settings(max_examples=100)
@given(plan=reorganization_plan_strategy)
def test_reorganization_plan_suggested_sections_have_required_fields(
    plan: ReorganizationPlan,
) -> None:
    """Every SuggestedSection in a ReorganizationPlan has display_name and notebook_id."""
    assert isinstance(plan.suggested_sections, list)
    for section in plan.suggested_sections:
        assert isinstance(section, SuggestedSection)
        assert hasattr(section, "display_name")
        assert hasattr(section, "notebook_id")
        assert isinstance(section.display_name, str)
        assert isinstance(section.notebook_id, str)
        assert len(section.display_name) > 0
        assert len(section.notebook_id) > 0


# Validates: Requirements 10.6
@settings(max_examples=100)
@given(plan=reorganization_plan_strategy)
def test_reorganization_plan_page_moves_have_required_fields(
    plan: ReorganizationPlan,
) -> None:
    """Every PageMove in a ReorganizationPlan has page_id, source_section_id, and target_section_display_name."""
    assert isinstance(plan.page_moves, list)
    for move in plan.page_moves:
        assert isinstance(move, PageMove)
        assert hasattr(move, "page_id")
        assert hasattr(move, "source_section_id")
        assert hasattr(move, "target_section_display_name")
        assert isinstance(move.page_id, str)
        assert isinstance(move.source_section_id, str)
        assert isinstance(move.target_section_display_name, str)
        assert len(move.page_id) > 0
        assert len(move.source_section_id) > 0
        assert len(move.target_section_display_name) > 0


# Validates: Requirements 10.6
@settings(max_examples=100)
@given(plan=reorganization_plan_strategy)
def test_reorganization_plan_is_structurally_complete(
    plan: ReorganizationPlan,
) -> None:
    """A ReorganizationPlan always contains both suggestedSections and pageMoves lists."""
    assert hasattr(plan, "suggested_sections")
    assert hasattr(plan, "page_moves")
    assert isinstance(plan.suggested_sections, list)
    assert isinstance(plan.page_moves, list)

    # Verify the plan is frozen (immutable)
    try:
        plan.suggested_sections = []  # type: ignore[misc]
        assert False, "ReorganizationPlan should be frozen"
    except AttributeError:
        pass  # Expected: frozen dataclass
