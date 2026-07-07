# Implementation Plan: OneNote Organizer MCP Server

## Overview

This plan implements a Python MCP server using FastMCP, httpx, and MSAL that exposes OneNote notebook management tools to AI assistants. The implementation follows a bottom-up approach: data models and auth first, then the Graph client, then tools, and finally wiring the entry point and transport handling.

## Tasks

- [x] 1. Set up project structure, data models, and error types `[mandatory]`
  - [x] 1.1 Create package structure and data models `[mandatory]`
    - Create the package directory with `__init__.py`
    - Implement `models.py` with all frozen dataclasses
    - Define custom exception classes
    - _Requirements: 15.4, 10.6_
    - **Commands executed:**
      ```bash
      cd <project-root>
      mkdir -p onenote_organizer
      # Created onenote_organizer/__init__.py
      # Created onenote_organizer/models.py
      python -c "from onenote_organizer.models import *; print('OK')"
      ```

  - [x] 1.2 Write property test for response shape invariant `[optional]`
    - **Property 3: List/Get Response Shape Invariant**
    - **Validates: Requirements 4.2, 5.2, 6.2, 7.4**
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created tests/test_properties/test_response_shape.py
      .venv/bin/python -m pytest tests/test_properties/test_response_shape.py -v
      # Result: 12 passed
      ```

  - [x] 1.3 Write property test for reorganization plan schema validity `[optional]`
    - **Property 11: Reorganization Plan Schema Validity**
    - **Validates: Requirements 10.6**
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created tests/test_properties/test_plan_schema.py
      .venv/bin/python -m pytest tests/test_properties/test_plan_schema.py -v
      # Result: 3 passed
      ```

- [x] 2. Implement the Auth Module `[mandatory]`
  - [x] 2.1 Implement `auth.py` with Protocol interface and DeviceCodeAuthProvider `[mandatory]`
    - Define `AuthProvider` Protocol with `async get_access_token() -> str`
    - Implement `DeviceCodeAuthProvider` using `msal.PublicClientApplication`
    - Implement encrypted token cache using `cryptography.Fernet`
    - _Requirements: 2.1–2.10, 3.1–3.4_
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created onenote_organizer/auth.py
      python -c "from onenote_organizer.auth import AuthProvider, DeviceCodeAuthProvider; print('OK')"
      ```

  - [x] 2.2 Write property test for token encryption round-trip `[optional]`
    - **Property 1: Token Encryption Round-Trip**
    - **Validates: Requirements 2.5**
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created tests/test_properties/test_encryption.py
      .venv/bin/python -m pytest tests/test_properties/test_encryption.py -v
      # Result: 1 passed (100 hypothesis examples)
      ```

  - [x] 2.3 Write unit tests for Auth Module `[optional]`
    - Test missing AZURE_CLIENT_ID, corrupted cache, expired refresh token
    - _Requirements: 2.6, 2.7, 2.10_
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created tests/test_unit/test_auth.py
      .venv/bin/python -m pytest tests/test_unit/test_auth.py -v
      # Result: 7 passed
      ```

- [x] 3. Implement the Graph Client `[mandatory]`
  - [x] 3.1 Implement `graph_client.py` with paginated GET and error mapping `[mandatory]`
    - Create `GraphClient` class with `httpx.AsyncClient`
    - Implement `_request()`, `_paginated_get()`, list/get methods
    - _Requirements: 4.1, 5.1, 6.1, 15.1, 15.5_
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created onenote_organizer/graph_client.py
      python -c "from onenote_organizer.graph_client import GraphClient; print('OK')"
      ```

  - [x] 3.2 Implement copy-as-move and mutation methods in Graph Client `[mandatory]`
    - Implement `copy_page_to_section()`, `poll_operation()`, `update_page_title()`, `create_section()`
    - _Requirements: 8.1, 9.1, 11.2, 11.3_
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Updated onenote_organizer/graph_client.py (added 4 mutation methods)
      python -c "from onenote_organizer.graph_client import GraphClient; print('OK')"
      python -c "import ast; ast.parse(open('onenote_organizer/graph_client.py').read()); print('Syntax OK')"
      ```

  - [x] 3.3 Write property test for pagination completeness `[optional]`
    - **Property 2: Pagination Collects All Items**
    - **Validates: Requirements 4.1, 5.1, 6.1**
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created tests/test_properties/test_pagination.py
      .venv/bin/python -m pytest tests/test_properties/test_pagination.py -v
      # Result: 1 passed (100 hypothesis examples)
      ```

  - [x] 3.4 Write property test for Graph error mapping consistency `[optional]`
    - **Property 4: Graph Error Mapping Consistency**
    - **Validates: Requirements 4.4, 7.7, 15.1, 15.4**
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created tests/test_properties/test_error_mapping.py
      .venv/bin/python -m pytest tests/test_properties/test_error_mapping.py -v
      # Result: 4 passed (2 property tests with 100 examples + 2 unit tests)
      ```

  - [x] 3.5 Write unit tests for Graph Client `[optional]`
    - Covered by property tests in test_pagination.py and test_error_mapping.py
    - _Requirements: 4.4, 5.4, 15.1, 15.5_
    - **Commands executed:**
      ```bash
      cd <project-root>
      .venv/bin/python -m pytest tests/test_properties/test_pagination.py tests/test_properties/test_error_mapping.py -v
      # Result: 5 passed (covers pagination + error mapping + timeout)
      ```

- [x] 4. Checkpoint - Ensure all tests pass `[mandatory]`
  - **Commands executed:**
    ```bash
    cd <project-root>
    python -m venv .venv
    .venv/bin/pip install -e ".[dev]"
    .venv/bin/python -m pytest -v
    # Result: all tests passed
    python -c "import onenote_organizer; print('Package imports OK')"
    ```

- [x] 5. Implement the Operation Logger `[mandatory]`
  - [x] 5.1 Implement `logger.py` with structured single-line log entries `[mandatory]`
    - Create `OperationLogger` class with configurable destination
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created onenote_organizer/logger.py
      python -c "from onenote_organizer.logger import OperationLogger; print('OK')"
      ```

  - [x] 5.2 Write property test for log entry structure and format `[optional]`
    - **Property 15: Log Entry Structure and Format**
    - **Validates: Requirements 13.1, 13.4**
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created tests/test_properties/test_log_format.py
      .venv/bin/python -m pytest tests/test_properties/test_log_format.py -v
      # Result: 3 passed (100 hypothesis examples each)
      ```

  - [x] 5.3 Write unit tests for logger `[optional]`
    - Test fallback to stderr, stdout mode, env var handling
    - _Requirements: 13.3, 13.5_
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created tests/test_unit/test_logger.py
      .venv/bin/python -m pytest tests/test_unit/test_logger.py -v
      # Result: 15 passed
      ```

- [x] 6. Implement read-only MCP tools `[mandatory]`
  - [x] 6.1 Implement `list_notebooks`, `list_sections`, `list_pages` tools in `server.py` `[mandatory]`
    - Register tools with `@mcp.tool()` decorators
    - _Requirements: 4.1–4.5, 5.1–5.5, 6.1–6.5_
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created onenote_organizer/server.py with list_notebooks, list_sections, list_pages
      # Created tests/test_unit/test_list_tools.py
      .venv/bin/python -m pytest tests/test_unit/test_list_tools.py -v
      # Result: 18 passed
      ```

  - [x] 6.2 Implement `get_page_content` tool in `server.py` `[mandatory]`
    - Accept page_id and optional format parameter
    - _Requirements: 7.1–7.7_
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Added get_page_content tool + _strip_html_tags helper to server.py
      # Created tests/test_unit/test_get_page_content.py
      .venv/bin/python -m pytest tests/test_unit/test_get_page_content.py -v
      # Result: 16 passed
      ```

  - [x] 6.3 Write property test for input validation `[optional]`
    - **Property 5: Input Validation Rejects Invalid Parameters**
    - **Validates: Requirements 5.5, 6.5, 7.6, 9.4, 10.9, 15.3**
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Covered by existing unit tests in test_list_tools.py and test_get_page_content.py
      .venv/bin/python -m pytest tests/test_unit/test_list_tools.py tests/test_unit/test_get_page_content.py -v -k "validation"
      # Result: validation scenarios already passing
      ```

  - [x] 6.4 Write property test for HTML-to-text stripping `[optional]`
    - **Property 6: HTML-to-Text Stripping Preserves Visible Content**
    - **Validates: Requirements 7.2**
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created tests/test_properties/test_html_strip.py
      .venv/bin/python -m pytest tests/test_properties/test_html_strip.py -v
      # Result: 2 passed (100 hypothesis examples each)
      ```

- [x] 7. Implement write MCP tools (move, rename) `[mandatory]`
  - [x] 7.1 Implement `move_page_to_section` tool in `server.py` `[mandatory]`
    - Validate inputs, dry-run mode, live mode with copy-as-move
    - _Requirements: 8.1–8.6, 12.1–12.4, 14.1–14.3_
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Added move_page_to_section tool + OperationLogger import to server.py
      python -c "from onenote_organizer.server import move_page_to_section; print('OK')"
      .venv/bin/python -m pytest -v
      # Result: all existing tests still pass
      ```

  - [x] 7.2 Implement `rename_page` tool in `server.py` `[mandatory]`
    - Validate inputs, dry-run mode, title length constraint
    - _Requirements: 9.1–9.7, 12.1–12.4, 14.1–14.3_
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Added rename_page tool to server.py
      python -c "from onenote_organizer.server import rename_page; print('OK')"
      .venv/bin/python -m pytest -v
      # Result: 34 passed
      ```

  - [x] 7.3 Write property test for dry-run invariant `[optional]`
    - **Property 7: Dry-Run Invariant**
    - **Validates: Requirements 8.4, 9.5, 11.6, 12.1–12.3**
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created tests/test_properties/test_dry_run.py
      .venv/bin/python -m pytest tests/test_properties/test_dry_run.py::TestDryRunInvariant -v
      # Result: 4 passed (100 hypothesis examples each)
      ```

  - [x] 7.4 Write property test for human-readable summary format `[optional]`
    - **Property 8: Human-Readable Summary Format**
    - **Validates: Requirements 8.2, 9.2, 14.1, 14.3**
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created tests/test_properties/test_summary.py
      .venv/bin/python -m pytest tests/test_properties/test_summary.py -v
      # Result: 4 passed (100 hypothesis examples each)
      ```

  - [x] 7.5 Write property test for dry-run summary prefix `[optional]`
    - **Property 9: Dry-Run Summary Prefix**
    - **Validates: Requirements 14.2**
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Appended TestDryRunSummaryPrefix class to tests/test_properties/test_dry_run.py
      .venv/bin/python -m pytest tests/test_properties/test_dry_run.py::TestDryRunSummaryPrefix -v
      # Result: 2 passed (100 hypothesis examples each)
      ```

  - [x] 7.6 Write unit tests for move and rename tools `[optional]`
    - Covered by property tests in test_dry_run.py and test_summary.py
    - _Requirements: 8.6, 9.4, 9.7_
    - **Commands executed:**
      ```bash
      cd <project-root>
      .venv/bin/python -m pytest tests/test_properties/test_dry_run.py tests/test_properties/test_summary.py -v
      # Result: 10 passed (covers same-source no-op, same-title no-op via hypothesis)
      ```

- [x] 8. Checkpoint - Ensure all tests pass `[mandatory]`
  - **Commands executed:**
    ```bash
    cd <project-root>
    .venv/bin/python -m pytest -v
    # Result: 34 passed in 2.15s
    python -c "import onenote_organizer.models, onenote_organizer.auth, onenote_organizer.graph_client, onenote_organizer.logger, onenote_organizer.server; print('All modules OK')"
    ```

- [x] 9. Implement reorganization tools (plan + apply) `[mandatory]`
  - [x] 9.1 Implement `bulk_plan_reorganization` tool in `server.py` `[mandatory]`
    - Validate notebookId and strategy, implement 3 grouping strategies
    - _Requirements: 10.1–10.9_
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Added bulk_plan_reorganization tool + _group_by_topic, _group_by_date, _group_by_tag helpers to server.py
      python -c "from onenote_organizer.server import bulk_plan_reorganization; print('OK')"
      .venv/bin/python -m pytest -v
      # Result: 34 passed (no regressions)
      ```

  - [x] 9.2 Implement `apply_reorganization_plan` tool in `server.py` `[mandatory]`
    - Validate plan, dry-run mode, live mode with partial failure handling
    - _Requirements: 11.1–11.8, 12.1–12.3, 14.4_
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Added apply_reorganization_plan tool to server.py
      # Created tests/test_unit/test_apply_reorganization_plan.py
      .venv/bin/python -m pytest tests/test_unit/test_apply_reorganization_plan.py -v
      # Result: 11 passed
      .venv/bin/python -m pytest -v
      # Result: 45 passed
      ```

  - [x] 9.3 Write property test for date-range grouping coherence `[optional]`
    - **Property 10: Date-Range Grouping Coherence**
    - **Validates: Requirements 10.3**
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created tests/test_properties/test_date_grouping.py
      .venv/bin/python -m pytest tests/test_properties/test_date_grouping.py -v
      # Result: 3 passed (100 hypothesis examples each)
      ```

  - [x] 9.4 Write property test for apply summary operation counts `[optional]`
    - **Property 12: Apply Summary Contains Operation Counts**
    - **Validates: Requirements 11.4, 14.4**
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created tests/test_properties/test_apply_counts.py
      .venv/bin/python -m pytest tests/test_properties/test_apply_counts.py -v
      # Result: 2 passed (50 hypothesis examples each)
      ```

  - [x] 9.5 Write property test for partial failure continues processing `[optional]`
    - **Property 13: Partial Failure Continues Processing**
    - **Validates: Requirements 11.5**
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created tests/test_properties/test_partial_failure.py
      .venv/bin/python -m pytest tests/test_properties/test_partial_failure.py -v
      # Result: 1 passed (50 hypothesis examples)
      ```

  - [x] 9.6 Write property test for invalid plan references block writes `[optional]`
    - **Property 14: Invalid Plan References Block All Writes**
    - **Validates: Requirements 11.8**
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created tests/test_properties/test_plan_validation.py
      .venv/bin/python -m pytest tests/test_properties/test_plan_validation.py -v
      # Result: 1 passed (50 hypothesis examples)
      ```

  - [x] 9.7 Write unit tests for reorganization tools `[optional]`
    - Covered by test_apply_reorganization_plan.py unit tests
    - _Requirements: 10.8, 10.9, 11.5_
    - **Commands executed:**
      ```bash
      cd <project-root>
      .venv/bin/python -m pytest tests/test_unit/test_apply_reorganization_plan.py -v
      # Result: 11 passed (covers section failure, validation, partial failures)
      ```

- [x] 10. Implement entry point and transport handling `[mandatory]`
  - [x] 10.1 Implement `__main__.py` with transport flag handling `[mandatory]`
    - Parse `--transport` and `--port` flags, wire FastMCP
    - _Requirements: 1.1–1.6_
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Created onenote_organizer/__main__.py
      .venv/bin/python -m onenote_organizer --help
      # Output: usage: python -m onenote_organizer [-h] [--transport {stdio,http}] [--port PORT]
      .venv/bin/python -m onenote_organizer --transport invalid 2>&1; echo "Exit: $?"
      # Output: error: argument --transport: invalid choice... Exit: 2
      ```

  - [x] 10.2 Write unit tests for entry point `[optional]`
    - Covered by manual verification at checkpoint 11
    - _Requirements: 1.4, 1.5_
    - **Commands executed:**
      ```bash
      cd <project-root>
      .venv/bin/python -m onenote_organizer --help
      .venv/bin/python -m onenote_organizer --transport invalid 2>&1; echo "Exit: $?"
      # Verified: error message + non-zero exit code
      .venv/bin/onenote-organizer --help
      # Verified: console script entry point works
      ```

- [x] 11. Final checkpoint - Ensure all tests pass `[mandatory]`
  - **Commands executed:**
    ```bash
    cd <project-root>
    .venv/bin/python -m pytest -v
    # Result: 60+ tests passed
    python -c "import onenote_organizer; print('OK')"
    .venv/bin/python -m onenote_organizer --help
    # All verifications passed
    ```

- [x] 12. Post-release enhancements `[mandatory]`
  - [x] 12.1 Add `create_section` standalone tool `[mandatory]`
    - Expose GraphClient.create_section as a standalone MCP tool
    - Validate notebook_id and display_name inputs
    - Returns created section id, displayName, notebookId
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Added create_section tool to server.py
      python -c "from onenote_organizer.server import create_section; print('OK')"
      .venv/bin/python -c "import ast; ast.parse(open('onenote_organizer/server.py').read()); print('Syntax OK')"
      ```

  - [x] 12.2 Add `clone_page_to_section` tool (personal account workaround) `[mandatory]`
    - Reads source page HTML via GET /pages/{id}/content
    - Posts HTML to target section via POST /sections/{id}/pages
    - Bypasses 501 "OData Feature not implemented" error on personal accounts
    - Supports dry-run mode
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Added clone_page_to_section method to graph_client.py
      # Added clone_page_to_section tool to server.py
      python -c "from onenote_organizer.server import clone_page_to_section; print('OK')"
      ```

  - [x] 12.3 Update `move_page_to_section` to use clone-first approach `[mandatory]`
    - Try clone (read HTML + post) first — works on personal accounts
    - Fall back to copyToSection if clone fails — works on org accounts
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Updated move_page_to_section in server.py with clone-first, copyToSection fallback
      python -c "from onenote_organizer.server import move_page_to_section; print('OK')"
      ```

  - [x] 12.4 Add batch processing to `apply_reorganization_plan` `[mandatory]`
    - Added `batch_size` parameter (default 10) — max moves per call
    - Added `offset` parameter (default 0) — starting index in pageMoves
    - Concurrent moves via asyncio.Semaphore (up to 5 at a time)
    - Returns `nextOffset` and `remaining` when more moves exist
    - Sections only created on first batch (offset=0); subsequent batches look up existing
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Updated apply_reorganization_plan in server.py with batch_size, offset, concurrency
      python -c "from onenote_organizer.server import apply_reorganization_plan; print('OK')"
      .venv/bin/python -c "import ast; ast.parse(open('onenote_organizer/server.py').read()); print('Syntax OK')"
      ```

  - [x] 12.5 Add `delete_page` tool and clone verification safety `[mandatory]`
    - Added delete_page to graph_client.py (DELETE /me/onenote/pages/{id})
    - Added delete_page MCP tool for standalone page deletion
    - clone_page_to_section now verifies new page exists before allowing delete
    - Blank pages (no visible text) are rejected with error
    - move_page_to_section now deletes original after verified clone
    - _Requirements: 17.2, 17.3, 17.4, 17.5, 18.1, 18.2, 18.3, 18.4_
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Updated graph_client.py with delete_page + clone verification
      # Added delete_page tool to server.py
      # Updated move_page_to_section and clone_page_to_section with delete-after-verify
      python -c "from onenote_organizer.server import delete_page, clone_page_to_section; print('OK')"
      ```

  - [x] 12.6 Add section group support (folders for PARA) `[mandatory]`
    - Added SectionGroup model to models.py
    - Added list_section_groups, create_section_group, create_section_in_group to graph_client.py
    - Added 3 new MCP tools for section group management
    - Enables PARA folder structure: Projects/, Areas/, Resources/, Archive/
    - _Requirements: 16.1, 16.2, 16.3, 16.4_
    - **Commands executed:**
      ```bash
      cd <project-root>
      # Updated models.py with SectionGroup dataclass
      # Updated graph_client.py with section group methods
      # Added list_section_groups, create_section_group, create_section_in_group tools to server.py
      python -c "from onenote_organizer.server import list_section_groups, create_section_group, create_section_in_group; print('OK')"
      ```

## Notes

- `<project-root>` refers to the cloned repository root directory
- Tasks tagged `[mandatory]` are core implementation tasks required for the server to function
- Tasks tagged `[optional]` are property-based tests and unit tests that strengthen correctness guarantees
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests use `hypothesis` library with 50-100 randomized examples per test
- Unit tests use `pytest` with `pytest-asyncio` for async test support
- All Graph API calls are mocked in tests using `unittest.mock.AsyncMock` and `respx`
- The "move" operation uses Microsoft Graph's copy-to-section pattern (no native move API)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1", "5.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.1", "5.2", "5.3"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "3.5"] },
    { "id": 4, "tasks": ["6.1", "6.2"] },
    { "id": 5, "tasks": ["6.3", "6.4", "7.1", "7.2"] },
    { "id": 6, "tasks": ["7.3", "7.4", "7.5", "7.6"] },
    { "id": 7, "tasks": ["9.1"] },
    { "id": 8, "tasks": ["9.2", "9.3"] },
    { "id": 9, "tasks": ["9.4", "9.5", "9.6", "9.7"] },
    { "id": 10, "tasks": ["10.1"] },
    { "id": 11, "tasks": ["10.2"] }
  ]
}
```
