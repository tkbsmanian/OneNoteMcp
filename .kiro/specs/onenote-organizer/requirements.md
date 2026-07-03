# Requirements Document

## Introduction

The onenote-organizer is a Model Context Protocol (MCP) server that enables an AI assistant to discover, read, and reorganize a user's personal Microsoft OneNote notebooks. The server authenticates via Microsoft Graph using device code flow, exposes a set of MCP tools for notebook inspection and manipulation, and runs as either a CLI process (stdin/stdout) or an HTTP/SSE endpoint. The system prioritizes safety through dry-run support, operation logging, and human-readable change summaries.

## Glossary

- **MCP_Server**: The Model Context Protocol server process that exposes tools to an AI assistant via JSON-RPC over stdin/stdout or HTTP/SSE.
- **Microsoft_Graph**: Microsoft's unified REST API for accessing OneNote data and performing operations on notebooks, sections, and pages.
- **Auth_Module**: A modular authentication component that handles OAuth 2.0 device code flow, token acquisition, token refresh, and token persistence.
- **Notebook**: A top-level OneNote container identified by a unique ID and a display name.
- **Section**: A container within a Notebook that holds pages, identified by a unique ID and a display name.
- **Page**: A content unit within a Section, identified by a unique ID, title, and last-modified timestamp.
- **Reorganization_Plan**: A structured proposal containing suggested sections to create and page moves to execute.
- **Dry_Run_Mode**: An operational mode where the MCP_Server forecasts changes without modifying any OneNote data.
- **Token_Store**: An encrypted local file that persists OAuth refresh tokens between sessions.
- **Tool**: A callable function exposed by the MCP_Server that accepts typed inputs and returns typed outputs.

## Requirements

### Requirement 1: MCP Server Transport

**User Story:** As a developer, I want the MCP server to support both stdin/stdout and HTTP/SSE transports, so that it can integrate with different AI assistant environments.

#### Acceptance Criteria

1. WHEN the MCP_Server is started with a CLI transport flag, THE MCP_Server SHALL communicate via JSON-RPC over stdin/stdout.
2. WHEN the MCP_Server is started with an HTTP transport flag, THE MCP_Server SHALL expose an HTTP/SSE endpoint on a configurable port (defaulting to port 8080 if not specified) for MCP communication.
3. THE MCP_Server SHALL provide a server manifest describing all available tools and their input/output schemas via the MCP protocol's standard discovery mechanism.
4. IF an unsupported transport flag is provided, THEN THE MCP_Server SHALL return an error message indicating the supported transport options and exit with a non-zero exit code.
5. IF no transport flag is provided, THEN THE MCP_Server SHALL default to CLI transport mode (stdin/stdout).
6. WHEN the MCP_Server has completed initialization on the selected transport, THE MCP_Server SHALL indicate readiness to accept connections within 10 seconds of startup.

### Requirement 2: Authentication via Device Code Flow

**User Story:** As a user, I want to authenticate using device code flow, so that I can log in interactively without storing passwords.

#### Acceptance Criteria

1. WHEN the MCP_Server requires authentication, THE Auth_Module SHALL initiate a device code flow via Microsoft_Graph and present the user code and verification URL to stderr (for CLI transport) or as a tool response message (for HTTP transport).
2. WHEN the device code flow completes successfully, THE Auth_Module SHALL store the resulting refresh token in the Token_Store.
3. WHEN a valid refresh token exists in the Token_Store, THE Auth_Module SHALL use the refresh token to acquire a new access token without user interaction.
4. IF the refresh token is expired or invalid, THEN THE Auth_Module SHALL re-initiate the device code flow.
5. THE Token_Store SHALL encrypt refresh tokens at rest using a local encryption key.
6. THE Auth_Module SHALL accept configuration via AZURE_CLIENT_ID environment variable for the app registration client ID.
7. IF the AZURE_CLIENT_ID environment variable is not set, THEN THE Auth_Module SHALL return an error indicating the required configuration is missing and refuse to initiate authentication.
8. WHERE AZURE_TENANT_ID is provided, THE Auth_Module SHALL use the specified tenant; WHERE AZURE_TENANT_ID is not provided, THE Auth_Module SHALL default to the "common" endpoint for personal accounts.
9. IF the device code flow does not complete within the expiration period specified by Microsoft_Graph, THEN THE Auth_Module SHALL return a timeout error indicating the user did not complete authentication in time.
10. IF the Token_Store file cannot be read or decrypted, THEN THE Auth_Module SHALL re-initiate the device code flow rather than failing permanently.

### Requirement 3: Auth Module Modularity

**User Story:** As a developer, I want the authentication layer to be a separate module with a defined interface, so that it can be swapped for a different auth mechanism later.

#### Acceptance Criteria

1. THE Auth_Module SHALL expose a defined interface containing at minimum a get_access_token() method that returns a valid access token string or raises an authentication error.
2. THE Auth_Module SHALL be implemented as a separate module that does not import or directly reference any MCP_Server tool implementation internals.
3. WHEN a different authentication mechanism is needed, THE Auth_Module SHALL be replaceable by any module implementing the same interface without modifying the MCP_Server tool implementations, verifiable by substituting a mock implementation that returns a static token.
4. IF the Auth_Module's get_access_token() method cannot provide a token, THEN it SHALL raise a typed error that the MCP_Server can translate into the standard error response structure.

### Requirement 4: List Notebooks Tool

**User Story:** As an AI assistant, I want to list all notebooks for the authenticated user, so that I can discover available content.

#### Acceptance Criteria

1. WHEN the list_notebooks tool is invoked, THE MCP_Server SHALL query Microsoft_Graph for all notebooks belonging to the authenticated user, following pagination links until all results are retrieved.
2. WHEN the list_notebooks tool succeeds and one or more notebooks exist, THE MCP_Server SHALL return an array of objects each containing an id field and a displayName field.
3. WHEN the list_notebooks tool succeeds and no notebooks exist, THE MCP_Server SHALL return an empty array.
4. IF the Microsoft_Graph request fails, THEN THE MCP_Server SHALL return a structured error containing the HTTP status code, the error message from Microsoft_Graph, and the tool name "list_notebooks".
5. IF the Auth_Module cannot provide a valid access token when the list_notebooks tool is invoked, THEN THE MCP_Server SHALL return an authentication error indicating the user must re-authenticate.

### Requirement 5: List Sections Tool

**User Story:** As an AI assistant, I want to list all sections in a notebook, so that I can understand the notebook structure.

#### Acceptance Criteria

1. WHEN the list_sections tool is invoked with a valid notebookId, THE MCP_Server SHALL query Microsoft_Graph for all sections in the specified notebook, following pagination links until all results are retrieved.
2. WHEN the list_sections tool succeeds and one or more sections exist, THE MCP_Server SHALL return an array of objects each containing an id field and a displayName field.
3. WHEN the list_sections tool succeeds and no sections exist in the notebook, THE MCP_Server SHALL return an empty array.
4. IF the provided notebookId does not correspond to an existing notebook, THEN THE MCP_Server SHALL return a structured error with the HTTP status code and an error message indicating the notebook was not found.
5. IF the notebookId parameter is missing or empty, THEN THE MCP_Server SHALL return a validation error specifying that notebookId is required.

### Requirement 6: List Pages Tool

**User Story:** As an AI assistant, I want to list all pages in a section, so that I can enumerate content for reorganization planning.

#### Acceptance Criteria

1. WHEN the list_pages tool is invoked with a valid sectionId, THE MCP_Server SHALL query Microsoft_Graph for all pages in the specified section, following pagination links until all results are retrieved.
2. WHEN the list_pages tool succeeds and one or more pages exist, THE MCP_Server SHALL return an array of objects each containing id, title, and lastModifiedDateTime fields.
3. WHEN the list_pages tool succeeds and no pages exist in the section, THE MCP_Server SHALL return an empty array.
4. IF the provided sectionId does not correspond to an existing section, THEN THE MCP_Server SHALL return a structured error with the HTTP status code and an error message indicating the section was not found.
5. IF the sectionId parameter is missing or empty, THEN THE MCP_Server SHALL return a validation error specifying that sectionId is required.

### Requirement 7: Get Page Content Tool

**User Story:** As an AI assistant, I want to read the content of a specific page, so that I can analyze it for reorganization.

#### Acceptance Criteria

1. WHEN the get_page_content tool is invoked with a valid pageId and format "html", THE MCP_Server SHALL return the page content as HTML retrieved from Microsoft_Graph.
2. WHEN the get_page_content tool is invoked with a valid pageId and format "text", THE MCP_Server SHALL return the page content as plain text with all HTML markup removed and visible text content preserved.
3. WHEN the get_page_content tool is invoked with a valid pageId and no format specified, THE MCP_Server SHALL default to "html" format.
4. WHEN the get_page_content tool succeeds, THE MCP_Server SHALL return an object containing id (string), title (string), and content (string) fields.
5. IF the provided pageId does not correspond to an existing page, THEN THE MCP_Server SHALL return a descriptive error indicating the page was not found.
6. IF the provided format value is not one of "html" or "text", THEN THE MCP_Server SHALL return a validation error indicating the accepted format values.
7. IF the Microsoft_Graph API call fails during content retrieval, THEN THE MCP_Server SHALL return a structured error containing the HTTP status code and the error message from Microsoft_Graph.

### Requirement 8: Move Page Tool

**User Story:** As an AI assistant, I want to move a page to a different section, so that I can reorganize notebook content.

#### Acceptance Criteria

1. WHEN the move_page_to_section tool is invoked with a valid pageId and targetSectionId, THE MCP_Server SHALL move the page to the target section via Microsoft_Graph.
2. WHEN the move operation succeeds, THE MCP_Server SHALL return an object with success set to true and a human-readable summary of the move including the page title, source section name, and target section name.
3. IF the pageId or targetSectionId does not correspond to an existing resource, THEN THE MCP_Server SHALL return an object with success set to false and a structured error message including the HTTP status code from Microsoft_Graph.
4. WHEN the move_page_to_section tool is invoked with dryRun set to true, THE MCP_Server SHALL return a response with the same structure as live execution (success, summary fields) with a dryRun boolean set to true, without dispatching any requests to Microsoft_Graph.
5. WHEN a move operation is executed (not dry run), THE MCP_Server SHALL log the operation with a timestamp, pageId, source sectionId, and target sectionId.
6. IF the targetSectionId is the same as the page's current sectionId, THEN THE MCP_Server SHALL return an object with success set to true and a summary indicating no move was necessary.

### Requirement 9: Rename Page Tool

**User Story:** As an AI assistant, I want to rename a page, so that I can improve content organization with descriptive titles.

#### Acceptance Criteria

1. WHEN the rename_page tool is invoked with a valid pageId and a non-empty newTitle of 256 characters or fewer, THE MCP_Server SHALL update the page title via Microsoft_Graph.
2. WHEN the rename operation succeeds, THE MCP_Server SHALL return an object with success set to true and a human-readable summary including the old and new title.
3. IF the pageId does not correspond to an existing page, THEN THE MCP_Server SHALL return an object with success set to false and a descriptive error message.
4. IF newTitle is empty, contains only whitespace, or exceeds 256 characters, THEN THE MCP_Server SHALL return an object with success set to false and an error indicating the title is invalid with the specific constraint violated.
5. WHEN the rename_page tool is invoked with dryRun set to true, THE MCP_Server SHALL return a response with the same structure as live execution (success, summary fields) with a dryRun boolean set to true, without dispatching any requests to Microsoft_Graph.
6. WHEN a rename operation is executed (not dry run), THE MCP_Server SHALL log the operation with a timestamp, pageId, old title, and new title.
7. IF newTitle is identical to the current page title, THEN THE MCP_Server SHALL return an object with success set to true and a summary indicating no rename was necessary.

### Requirement 10: Bulk Plan Reorganization Tool

**User Story:** As an AI assistant, I want to generate a reorganization plan for a notebook, so that I can propose structural improvements to the user.

#### Acceptance Criteria

1. WHEN the bulk_plan_reorganization tool is invoked with a valid notebookId, THE MCP_Server SHALL analyze existing sections and page metadata to generate a Reorganization_Plan.
2. WHEN a strategy of "by_topic" is specified, THE MCP_Server SHALL group pages into suggested sections based on page titles and content similarity.
3. WHEN a strategy of "by_date" is specified, THE MCP_Server SHALL group pages into suggested sections based on lastModifiedDateTime ranges.
4. WHEN a strategy of "by_tag" is specified, THE MCP_Server SHALL group pages into suggested sections based on keywords extracted from page titles and content.
5. WHEN no strategy is specified, THE MCP_Server SHALL default to the "by_topic" strategy.
6. WHEN the bulk_plan_reorganization tool succeeds, THE MCP_Server SHALL return a Reorganization_Plan containing suggestedSections (array of objects with displayName and notebookId fields) and pageMoves (array of objects with pageId, sourceSectionId, and targetSectionDisplayName fields).
7. THE MCP_Server SHALL generate the Reorganization_Plan as a read-only operation without modifying any notebook data.
8. IF the provided notebookId does not correspond to an existing notebook, THEN THE MCP_Server SHALL return a structured error indicating the notebook was not found.
9. IF the provided strategy is not one of "by_topic", "by_date", or "by_tag", THEN THE MCP_Server SHALL return a validation error indicating the accepted strategy values.

### Requirement 11: Apply Reorganization Plan Tool

**User Story:** As an AI assistant, I want to execute an approved reorganization plan, so that the user's notebook is restructured according to the proposal.

#### Acceptance Criteria

1. WHEN the apply_reorganization_plan tool is invoked with a Reorganization_Plan conforming to the required structure (suggestedSections and pageMoves arrays), THE MCP_Server SHALL validate that all referenced pages and notebooks exist before executing any modifications.
2. WHEN the plan contains suggestedSections that do not exist, THE MCP_Server SHALL create the missing sections in the target notebook via Microsoft_Graph before processing any page moves.
3. WHEN the plan contains pageMoves, THE MCP_Server SHALL move each page to its target section via Microsoft_Graph.
4. WHEN the apply operation completes, THE MCP_Server SHALL return a summary containing the number of sections created, pages moved, and any errors encountered.
5. IF any individual section creation or page move fails, THEN THE MCP_Server SHALL continue processing remaining operations, skip page moves targeting a failed section, and include all failures in the error summary.
6. WHEN the apply_reorganization_plan tool is invoked with dryRun set to true, THE MCP_Server SHALL validate the plan and return a forecast of all changes without modifying any data.
7. WHEN the apply operation is executed (not dry run), THE MCP_Server SHALL log each write operation with a timestamp and resource identifiers.
8. IF plan validation fails because referenced pages or notebooks do not exist, THEN THE MCP_Server SHALL return a structured error listing the invalid references without modifying any data.

### Requirement 12: Dry Run Mode

**User Story:** As a user, I want to preview changes before they happen, so that I can approve or reject proposed modifications.

#### Acceptance Criteria

1. WHEN any write tool (move_page_to_section, rename_page, apply_reorganization_plan) is invoked with dryRun set to true, THE MCP_Server SHALL return the projected outcome without dispatching any create, update, or delete requests to Microsoft_Graph.
2. WHEN Dry_Run_Mode is active, THE MCP_Server SHALL include a boolean field "dryRun" set to true in the response object to identify the response as a dry-run forecast.
3. WHEN Dry_Run_Mode is active, THE MCP_Server SHALL return a response containing the same top-level fields and data types as the corresponding live execution response for that tool.
4. IF the dryRun parameter is not provided in a write tool invocation, THEN THE MCP_Server SHALL default to live execution mode (dryRun false).

### Requirement 13: Operation Logging

**User Story:** As a user, I want all write operations logged, so that I can audit what changes were made and when.

#### Acceptance Criteria

1. WHEN any write operation is executed (not dry run), THE MCP_Server SHALL log a structured entry containing: an ISO 8601 timestamp with timezone offset, the tool name, the operation outcome (success or failure), and the resource identifiers specific to the tool (pageId and targetSectionId for move_page_to_section; pageId, old title, and new title for rename_page; notebookId, sections created, and pages moved for apply_reorganization_plan).
2. THE MCP_Server SHALL persist operation logs to a log destination configured via an environment variable, supporting file path or "stdout" as values.
3. IF no log destination is configured, THEN THE MCP_Server SHALL default to writing logs to stdout.
4. THE MCP_Server SHALL format each log entry as a single-line structured text record containing all fields from criterion 1, followed by a human-readable description of the operation in plain English (maximum 200 characters).
5. IF writing to the configured log destination fails, THEN THE MCP_Server SHALL fall back to stderr and continue processing the original operation without interruption.

### Requirement 14: Human-Readable Summaries

**User Story:** As an AI assistant, I want human-readable summaries in tool responses, so that I can explain changes clearly to the user.

#### Acceptance Criteria

1. WHEN any write tool completes successfully, THE MCP_Server SHALL include a summary field containing a plain English sentence describing the action performed and the entity names involved (page titles, section names), not exceeding 256 characters.
2. WHEN any write tool operates in Dry_Run_Mode, THE MCP_Server SHALL include a summary field prefixed with "Would" describing the projected changes using the same entity-referencing format as live execution summaries.
3. THE MCP_Server SHALL format summaries using only plain English without technical identifiers (IDs, timestamps), referencing entities by their display names or titles.
4. WHEN the apply_reorganization_plan tool completes, THE MCP_Server SHALL include a summary field that states the total count of sections created and pages moved (e.g., "Created 3 sections and moved 12 pages").

### Requirement 15: Error Handling

**User Story:** As an AI assistant, I want consistent and descriptive error responses, so that I can communicate issues clearly to the user.

#### Acceptance Criteria

1. IF a Microsoft_Graph API call returns an HTTP error, THEN THE MCP_Server SHALL return a structured error containing the HTTP status code, the error message from Microsoft_Graph, and a category code of "graph_error".
2. IF the Auth_Module cannot acquire a valid access token, THEN THE MCP_Server SHALL return an authentication error with a category code of "auth_error" and a message that includes the verification URL and instructions to re-initiate device code flow.
3. IF a tool receives input that does not conform to the defined schema, THEN THE MCP_Server SHALL return a validation error with a category code of "validation_error" listing each invalid field name paired with a reason string describing the constraint that was violated.
4. THE MCP_Server SHALL use a consistent error response structure across all tools containing: a category code (string identifying the error type), an HTTP status code (integer, where applicable), a human-readable message (string), and the tool name (string) that produced the error.
5. IF a Microsoft_Graph API call fails due to a network timeout or connectivity error, THEN THE MCP_Server SHALL return a structured error with a category code of "network_error" and a message indicating that the Microsoft_Graph service could not be reached.
