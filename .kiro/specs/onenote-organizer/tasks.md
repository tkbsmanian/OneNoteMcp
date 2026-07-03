# Implementation Plan: OneNote Organizer MCP Server

## Overview

This plan implements a Python MCP server using FastMCP, httpx, and MSAL that exposes OneNote notebook management tools to AI assistants. The implementation follows a bottom-up approach: data models and auth first, then the Graph client, then tools, and finally wiring the entry point and transport handling.

## Tasks

- [x] 1. Set up project structure, data models, and error types
  - [x] 1.1 Create package structure and data models
    - Create the package directory with `__init__.py`
    - Implement `models.py` with all frozen dataclasses: `Notebook`, `Section`, `PageMetadata`, `PageContent`, `SuggestedSection`, `PageMove`, `ReorganizationPlan`, `ToolResult`, `ToolError`, `OperationResult`
    - Define custom exception classes: `AuthError`, `GraphError`, `ValidationError`, `NetworkError`
    - _Requirements: 15.4, 10.6_

  - [x] 1.2 Write property test for response shape invariant
    - **Property 3: List/Get Response Shape Invariant**
    - Verify that model dataclasses enforce all required fields and reject None for non-optional fields
    - **Validates: Requirements 4.2, 5.2, 6.2, 7.4**

  - [x] 1.3 Write property test for reorganization plan schema validity
    - **Property 11: Reorganization Plan Schema Validity**
    - Verify that `ReorganizationPlan` always contains `suggestedSections` with displayName/notebookId and `pageMoves` with pageId/sourceSectionId/targetSectionDisplayName
    - **Validates: Requirements 10.6**

- [x] 2. Implement the Auth Module
  - [x] 2.1 Implement `auth.py` with Protocol interface and DeviceCodeAuthProvider
    - Define `AuthProvider` Protocol with `async get_access_token() -> str`
    - Implement `DeviceCodeAuthProvider` using `msal.PublicClientApplication`
    - Read `AZURE_CLIENT_ID` (required) and `AZURE_TENANT_ID` (optional, default "common") from environment
    - Implement encrypted token cache using `cryptography.Fernet` with machine-derived key
    - Handle silent token refresh, device code flow initiation, and timeout
    - Raise `AuthError` with descriptive messages including verification URL
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 3.1, 3.2, 3.3, 3.4_

  - [x] 2.2 Write property test for token encryption round-trip
    - **Property 1: Token Encryption Round-Trip**
    - For any valid token string, encrypt then decrypt should produce the original string
    - **Validates: Requirements 2.5**

  - [x] 2.3 Write unit tests for Auth Module
    - Test missing `AZURE_CLIENT_ID` raises error before MSAL call
    - Test corrupted token cache re-initiates device code flow
    - Test expired refresh token triggers device code flow
    - _Requirements: 2.6, 2.7, 2.10_

- [x] 3. Implement the Graph Client
  - [x] 3.1 Implement `graph_client.py` with paginated GET and error mapping
    - Create `GraphClient` class with `httpx.AsyncClient`
    - Implement `_request()` method with bearer token injection and error mapping (httpx.HTTPStatusError → GraphError, TimeoutException → NetworkError, ConnectError → NetworkError)
    - Implement `_paginated_get()` following `@odata.nextLink` until exhausted
    - Implement `list_notebooks()`, `list_sections()`, `list_pages()`
    - Implement `get_page_content()`, `get_page_metadata()`, `get_section_metadata()`
    - _Requirements: 4.1, 5.1, 6.1, 15.1, 15.5_

  - [x] 3.2 Implement copy-as-move and mutation methods in Graph Client
    - Implement `copy_page_to_section()` that POSTs and returns operation URL
    - Implement `poll_operation()` with exponential backoff (1s, 2s, 4s, 8s up to 60s)
    - Implement `update_page_title()` via PATCH
    - Implement `create_section()` via POST
    - _Requirements: 8.1, 9.1, 11.2, 11.3_

  - [ ] 3.3 Write property test for pagination completeness
    - **Property 2: Pagination Collects All Items**
    - For any paginated response with N total items, pagination logic collects exactly N items with no duplicates
    - **Validates: Requirements 4.1, 5.1, 6.1**

  - [ ] 3.4 Write property test for Graph error mapping consistency
    - **Property 4: Graph Error Mapping Consistency**
    - For any HTTP error from Graph, produce structured error with status code, message, tool name, and category "graph_error"
    - **Validates: Requirements 4.4, 7.7, 15.1, 15.4**

  - [ ] 3.5 Write unit tests for Graph Client
    - Test paginated response assembly
    - Test error mapping for 404, 401, 500 status codes
    - Test timeout handling
    - _Requirements: 4.4, 5.4, 15.1, 15.5_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement the Operation Logger
  - [x] 5.1 Implement `logger.py` with structured single-line log entries
    - Create `OperationLogger` class with configurable destination (file path or "stdout")
    - Read destination from `ONENOTE_LOG_DESTINATION` environment variable (default "stdout")
    - Implement `log_move()`, `log_rename()`, `log_apply_plan()` methods
    - Format entries as single-line: `ISO8601_timestamp | tool_name | outcome | resource_ids | description(≤200 chars)`
    - Fall back to stderr if configured destination is not writable
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

  - [x] 5.2 Write property test for log entry structure and format
    - **Property 15: Log Entry Structure and Format**
    - For any write operation, log entry is one line, contains ISO 8601 timestamp with timezone, tool name, outcome, resource IDs, and description ≤ 200 chars
    - **Validates: Requirements 13.1, 13.4**

  - [x] 5.3 Write unit tests for logger
    - Test fallback to stderr when file path is unwritable
    - Test stdout output mode
    - _Requirements: 13.3, 13.5_

- [x] 6. Implement read-only MCP tools
  - [x] 6.1 Implement `list_notebooks`, `list_sections`, `list_pages` tools in `server.py`
    - Register tools with `@mcp.tool()` decorators
    - Implement input validation (missing/empty parameters → validation error)
    - Wire to Graph Client methods
    - Return properly shaped responses (id + displayName for notebooks/sections; id + title + lastModifiedDateTime for pages)
    - Handle auth errors and graph errors with consistent error structure
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 6.2 Implement `get_page_content` tool in `server.py`
    - Accept `page_id` and optional `format` parameter (default "html")
    - Validate format is "html" or "text"
    - For "text" format, strip HTML tags while preserving visible text content
    - Return object with id, title, and content fields
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [ ] 6.3 Write property test for input validation
    - **Property 5: Input Validation Rejects Invalid Parameters**
    - For any tool invocation with missing/empty/invalid params, return validation error with category "validation_error" listing each field and reason
    - **Validates: Requirements 5.5, 6.5, 7.6, 9.4, 10.9, 15.3**

  - [ ] 6.4 Write property test for HTML-to-text stripping
    - **Property 6: HTML-to-Text Stripping Preserves Visible Content**
    - For any valid HTML, text output contains no tags and preserves all visible text
    - **Validates: Requirements 7.2**

- [x] 7. Implement write MCP tools (move, rename)
  - [x] 7.1 Implement `move_page_to_section` tool in `server.py`
    - Validate inputs (pageId, targetSectionId required)
    - Implement dry-run mode: return projected outcome without Graph API calls
    - For live mode: look up page/section metadata, call copy_page_to_section, poll operation
    - Handle same-source-target case (no-op with success message)
    - Generate human-readable summary referencing page title and section names
    - Log operation via OperationLogger
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 12.1, 12.2, 12.3, 12.4, 14.1, 14.2, 14.3_

  - [x] 7.2 Implement `rename_page` tool in `server.py`
    - Validate inputs: newTitle non-empty, not whitespace-only, ≤ 256 characters
    - Implement dry-run mode
    - For live mode: look up current title, call update_page_title
    - Handle same-title case (no-op with success message)
    - Generate human-readable summary with old and new title
    - Log operation via OperationLogger
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 12.1, 12.2, 12.3, 12.4, 14.1, 14.2, 14.3_

  - [ ] 7.3 Write property test for dry-run invariant
    - **Property 7: Dry-Run Invariant**
    - For any write tool with dryRun=true, zero Graph mutations, response includes dryRun=true, same top-level fields as live
    - **Validates: Requirements 8.4, 9.5, 11.6, 12.1, 12.2, 12.3**

  - [ ] 7.4 Write property test for human-readable summary format
    - **Property 8: Human-Readable Summary Format**
    - Summary references entities by name (not ID), no UUIDs/timestamps, plain English, ≤ 256 chars
    - **Validates: Requirements 8.2, 9.2, 14.1, 14.3**

  - [ ] 7.5 Write property test for dry-run summary prefix
    - **Property 9: Dry-Run Summary Prefix**
    - For any write tool in dry-run mode, summary starts with "Would"
    - **Validates: Requirements 14.2**

  - [ ] 7.6 Write unit tests for move and rename tools
    - Test same-source-target no-op for move
    - Test same-title no-op for rename
    - Test title validation edge cases (empty, whitespace, 257 chars)
    - _Requirements: 8.6, 9.4, 9.7_

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement reorganization tools (plan + apply)
  - [x] 9.1 Implement `bulk_plan_reorganization` tool in `server.py`
    - Validate notebookId and strategy ("by_topic", "by_date", "by_tag"; default "by_topic")
    - Fetch all sections and pages for the notebook
    - Implement "by_topic" strategy: group pages by title/content similarity
    - Implement "by_date" strategy: group pages by lastModifiedDateTime ranges (non-overlapping)
    - Implement "by_tag" strategy: group pages by keywords from titles/content
    - Return `ReorganizationPlan` with suggestedSections and pageMoves arrays
    - Ensure operation is read-only (no modifications)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9_

  - [x] 9.2 Implement `apply_reorganization_plan` tool in `server.py`
    - Validate plan structure and verify all referenced pages/notebooks exist before any mutations
    - Implement dry-run mode: validate and forecast without modifications
    - For live mode: create missing sections first, then move pages
    - Handle partial failures: continue processing, skip moves targeting failed sections
    - Return summary with sections created count and pages moved count
    - Log each write operation
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 12.1, 12.2, 12.3, 14.4_

  - [ ] 9.3 Write property test for date-range grouping coherence
    - **Property 10: Date-Range Grouping Coherence**
    - For any set of pages grouped by "by_date", pages in same section share a contiguous date range, no overlapping ranges between sections
    - **Validates: Requirements 10.3**

  - [ ] 9.4 Write property test for apply summary operation counts
    - **Property 12: Apply Summary Contains Operation Counts**
    - Summary contains numeric counts of sections created and pages moved matching actual operations
    - **Validates: Requirements 11.4, 14.4**

  - [ ] 9.5 Write property test for partial failure continues processing
    - **Property 13: Partial Failure Continues Processing**
    - For plans where some operations fail, all remaining operations are attempted, moves to failed sections are skipped, error summary lists all failures
    - **Validates: Requirements 11.5**

  - [ ] 9.6 Write property test for invalid plan references block writes
    - **Property 14: Invalid Plan References Block All Writes**
    - For plans with non-existent pages/notebooks, return error listing invalid refs and make zero Graph mutations
    - **Validates: Requirements 11.8**

  - [ ] 9.7 Write unit tests for reorganization tools
    - Test section creation failure skips dependent page moves
    - Test invalid strategy returns validation error
    - Test empty notebook returns empty plan
    - _Requirements: 10.8, 10.9, 11.5_

- [x] 10. Implement entry point and transport handling
  - [x] 10.1 Implement `__main__.py` with transport flag handling
    - Parse `--transport` flag (choices: "stdio", "http"; default "stdio")
    - Parse `--port` flag (default 8080) for HTTP transport
    - Wire FastMCP server with selected transport
    - Handle invalid transport flag with error message and non-zero exit
    - Ensure server indicates readiness within 10 seconds
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ] 10.2 Write unit tests for entry point
    - Test default transport is stdio
    - Test invalid transport flag returns error and exits non-zero
    - Test HTTP transport accepts custom port
    - _Requirements: 1.4, 1.5_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The "move" operation uses Microsoft Graph's copy-to-section pattern (no native move API)
- All Graph API calls are mocked in tests — no real network calls

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
