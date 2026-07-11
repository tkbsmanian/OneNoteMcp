"""Microsoft Graph client for OneNote operations.

Provides an async client that handles authenticated requests, pagination,
and error mapping for all OneNote Graph API endpoints.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from onenote_organizer.auth import AuthProvider
from onenote_organizer.models import (
    GraphError,
    NetworkError,
    Notebook,
    OperationResult,
    PageMetadata,
    Section,
    SectionGroup,
)


class GraphClient:
    """Async Microsoft Graph client for OneNote operations."""

    BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, auth_provider: AuthProvider) -> None:
        """Initialize the Graph client.

        Args:
            auth_provider: An object implementing the AuthProvider protocol
                that provides access tokens for Graph API requests.
        """
        self._auth = auth_provider
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Execute an authenticated request with error mapping.

        Injects the Bearer token into the Authorization header and maps
        httpx exceptions to domain-specific errors.

        Args:
            method: HTTP method (GET, POST, PATCH, etc.)
            url: Full URL for the request.
            **kwargs: Additional arguments passed to httpx.

        Returns:
            The httpx.Response on success.

        Raises:
            GraphError: If the Graph API returns an HTTP error status.
            NetworkError: If a timeout or connection error occurs.
        """
        token = await self._auth.get_access_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"

        try:
            response = await self._client.request(
                method, url, headers=headers, **kwargs
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            # Extract error message from Graph API response if available
            message = "Microsoft Graph API error"
            try:
                error_body = exc.response.json()
                if "error" in error_body:
                    message = error_body["error"].get("message", message)
            except (ValueError, KeyError):
                message = exc.response.text or message
            raise GraphError(
                message=message,
                status_code=exc.response.status_code,
            ) from exc
        except httpx.TimeoutException as exc:
            raise NetworkError(
                "Microsoft Graph service could not be reached: request timed out"
            ) from exc
        except httpx.ConnectError as exc:
            raise NetworkError(
                "Microsoft Graph service could not be reached: connection failed"
            ) from exc

    async def _paginated_get(self, url: str) -> list[dict]:
        """Follow @odata.nextLink until all results are retrieved.

        Args:
            url: The initial URL to request.

        Returns:
            A list of all items collected across all pages.
        """
        items: list[dict] = []
        next_url: str | None = url

        while next_url is not None:
            response = await self._request("GET", next_url)
            data = response.json()
            items.extend(data.get("value", []))
            next_url = data.get("@odata.nextLink")

        return items

    async def list_notebooks(self) -> list[Notebook]:
        """List all notebooks for the authenticated user.

        Returns:
            A list of Notebook objects with id and display_name.
        """
        url = f"{self.BASE_URL}/me/onenote/notebooks"
        items = await self._paginated_get(url)
        return [
            Notebook(id=item["id"], display_name=item["displayName"])
            for item in items
        ]

    async def list_sections(self, notebook_id: str) -> list[Section]:
        """List all sections in a specific notebook.

        Args:
            notebook_id: The ID of the notebook to query.

        Returns:
            A list of Section objects with id, display_name, and notebook_id.
        """
        url = f"{self.BASE_URL}/me/onenote/notebooks/{notebook_id}/sections"
        items = await self._paginated_get(url)
        return [
            Section(
                id=item["id"],
                display_name=item["displayName"],
                notebook_id=item.get("parentNotebook", {}).get("id", notebook_id),
            )
            for item in items
        ]

    async def list_pages(self, section_id: str) -> list[PageMetadata]:
        """List all pages in a specific section.

        Args:
            section_id: The ID of the section to query.

        Returns:
            A list of PageMetadata objects with id, title, last_modified, and section_id.
        """
        url = f"{self.BASE_URL}/me/onenote/sections/{section_id}/pages"
        items = await self._paginated_get(url)
        return [
            PageMetadata(
                id=item["id"],
                title=item.get("title", ""),
                last_modified=datetime.fromisoformat(
                    item["lastModifiedDateTime"]
                ),
                section_id=item.get("parentSection", {}).get("id", section_id),
            )
            for item in items
        ]

    async def get_page_content(self, page_id: str) -> str:
        """Get the HTML content of a specific page.

        Args:
            page_id: The ID of the page to retrieve content for.

        Returns:
            The page content as an HTML string.
        """
        url = f"{self.BASE_URL}/me/onenote/pages/{page_id}/content"
        response = await self._request("GET", url)
        return response.text

    async def get_page_metadata(self, page_id: str) -> PageMetadata:
        """Get metadata for a specific page.

        Args:
            page_id: The ID of the page.

        Returns:
            A PageMetadata object with the page's id, title, last_modified, and section_id.
        """
        url = f"{self.BASE_URL}/me/onenote/pages/{page_id}"
        response = await self._request("GET", url)
        item = response.json()
        return PageMetadata(
            id=item["id"],
            title=item.get("title", ""),
            last_modified=datetime.fromisoformat(item["lastModifiedDateTime"]),
            section_id=item.get("parentSection", {}).get("id"),
        )

    async def get_section_metadata(self, section_id: str) -> Section:
        """Get metadata for a specific section.

        Args:
            section_id: The ID of the section.

        Returns:
            A Section object with the section's id, display_name, and notebook_id.
        """
        url = f"{self.BASE_URL}/me/onenote/sections/{section_id}"
        response = await self._request("GET", url)
        item = response.json()
        return Section(
            id=item["id"],
            display_name=item["displayName"],
            notebook_id=item.get("parentNotebook", {}).get("id"),
        )

    async def copy_page_to_section(self, page_id: str, target_section_id: str) -> str:
        """Copy a page to a different section (used as move since Graph has no native move).

        POSTs to /me/onenote/pages/{id}/copyToSection with the target section ID.
        Returns the operation URL for polling the long-running operation status.

        Args:
            page_id: The ID of the page to copy.
            target_section_id: The ID of the destination section.

        Returns:
            The operation URL string for polling the copy status.

        Raises:
            GraphError: If the Graph API returns an HTTP error status.
            NetworkError: If a timeout or connection error occurs.
        """
        url = f"{self.BASE_URL}/me/onenote/pages/{page_id}/copyToSection"
        body = {"id": target_section_id}
        response = await self._request("POST", url, json=body)

        # The operation URL may be in the response body or the Operation-Location header
        operation_url = response.headers.get("Operation-Location", "")
        if not operation_url:
            # Try to extract from response body
            try:
                data = response.json()
                operation_url = data.get("uri", "") or data.get("id", "")
            except (ValueError, KeyError):
                pass

        return operation_url

    async def poll_operation(self, operation_url: str) -> OperationResult:
        """Poll a long-running operation until complete or failed.

        Uses exponential backoff starting at 1s, doubling each time
        (1s, 2s, 4s, 8s, ...) with a maximum total wait of 60s.

        Args:
            operation_url: The URL returned by a long-running operation (e.g., copyToSection).

        Returns:
            An OperationResult with status "completed" or "failed",
            and optionally a resource_id or error_message.
        """
        delay = 1.0
        total_waited = 0.0
        max_wait = 60.0

        while total_waited < max_wait:
            await asyncio.sleep(delay)
            total_waited += delay

            try:
                response = await self._request("GET", operation_url)
                data = response.json()
            except GraphError as exc:
                return OperationResult(
                    status="failed",
                    error_message=str(exc),
                )
            except NetworkError as exc:
                return OperationResult(
                    status="failed",
                    error_message=str(exc),
                )

            status = data.get("status", "").lower()

            if status == "completed":
                resource_id = data.get("resourceId") or data.get("resourceLocation", "")
                return OperationResult(
                    status="completed",
                    resource_id=resource_id if resource_id else None,
                )
            elif status == "failed":
                error_msg = data.get("error", {}).get("message", "Operation failed")
                return OperationResult(
                    status="failed",
                    error_message=error_msg,
                )

            # Double the delay for next iteration (exponential backoff)
            delay = min(delay * 2, max_wait - total_waited) if total_waited < max_wait else delay

        # Timed out waiting for completion
        return OperationResult(
            status="failed",
            error_message="Operation timed out after 60 seconds",
        )

    async def update_page_title(self, page_id: str, new_title: str) -> None:
        """Update the title of a page via PATCH.

        Uses the OneNote PATCH content API to replace the page title.

        Args:
            page_id: The ID of the page to update.
            new_title: The new title for the page.

        Raises:
            GraphError: If the Graph API returns an HTTP error status.
            NetworkError: If a timeout or connection error occurs.
        """
        url = f"{self.BASE_URL}/me/onenote/pages/{page_id}/content"
        # OneNote PATCH content format: array of patch actions
        patch_body = [
            {
                "target": "title",
                "action": "replace",
                "content": new_title,
            }
        ]
        await self._request(
            "PATCH",
            url,
            json=patch_body,
            headers={"Content-Type": "application/json"},
        )

    async def create_section(self, notebook_id: str, display_name: str) -> Section:
        """Create a new section in a notebook.

        POSTs to /me/onenote/notebooks/{id}/sections with the display name.

        Args:
            notebook_id: The ID of the notebook to create the section in.
            display_name: The display name for the new section.

        Returns:
            A Section object representing the newly created section.

        Raises:
            GraphError: If the Graph API returns an HTTP error status.
            NetworkError: If a timeout or connection error occurs.
        """
        url = f"{self.BASE_URL}/me/onenote/notebooks/{notebook_id}/sections"
        body = {"displayName": display_name}
        response = await self._request("POST", url, json=body)
        item = response.json()
        return Section(
            id=item["id"],
            display_name=item["displayName"],
            notebook_id=item.get("parentNotebook", {}).get("id", notebook_id),
        )

    async def clone_page_to_section(self, page_id: str, target_section_id: str) -> str:
        """Clone a page to a different section by reading HTML and re-posting it.

        This is the workaround for personal Microsoft accounts where copyToSection
        returns 501 "OData Feature not implemented". It reads the full page HTML,
        downloads embedded images, and creates a new page in the target section
        with the content and images as a multipart request.

        Safety: Verifies the new page was created successfully before returning.

        Args:
            page_id: The ID of the source page to clone.
            target_section_id: The ID of the destination section.

        Returns:
            The ID of the newly created page in the target section.

        Raises:
            GraphError: If the Graph API returns an HTTP error, or if the
                cloned page cannot be verified.
            NetworkError: If a timeout or connection error occurs.
        """
        import re
        import uuid as uuid_mod

        # Step 1: Read the source page's full HTML content
        html_content = await self.get_page_content(page_id)

        # Step 1b: Check if page has meaningful content (not blank)
        visible_text = re.sub(r"<[^>]+>", "", html_content).strip()
        if not visible_text:
            raise GraphError(
                message="Source page has no visible content (blank page) — skipping clone",
                status_code=None,
            )

        # Step 2: Extract image URLs from HTML and download them
        # OneNote images are referenced as src="https://graph.microsoft.com/..." 
        # or src="name:image_name" for multipart references
        img_pattern = re.compile(
            r'<img[^>]+src="(https://[^"]+)"[^>]*>', re.IGNORECASE
        )
        image_urls = img_pattern.findall(html_content)

        # Download images and build multipart parts
        image_parts: list[tuple[str, bytes, str]] = []  # (part_name, data, content_type)
        
        for i, img_url in enumerate(image_urls):
            try:
                token = await self._auth.get_access_token()
                img_response = await self._client.get(
                    img_url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30.0,
                )
                if img_response.status_code == 200:
                    content_type = img_response.headers.get("content-type", "image/png")
                    part_name = f"image{i+1}"
                    image_parts.append((part_name, img_response.content, content_type))
                    # Replace the URL in HTML with a multipart reference
                    html_content = html_content.replace(
                        img_url, f"name:{part_name}"
                    )
            except Exception:
                # If image download fails, leave the original URL (image won't show)
                pass

        # Step 3: Post to the destination section
        url = f"{self.BASE_URL}/me/onenote/sections/{target_section_id}/pages"

        if image_parts:
            # Use multipart/form-data when there are images
            boundary = f"OneNoteBoundary{uuid_mod.uuid4().hex[:12]}"
            
            # Build multipart body manually
            body_parts: list[bytes] = []
            
            # Part 1: HTML content (Presentation part)
            body_parts.append(f"--{boundary}\r\n".encode())
            body_parts.append(
                b'Content-Disposition: form-data; name="Presentation"\r\n'
            )
            body_parts.append(b"Content-Type: text/html\r\n\r\n")
            body_parts.append(html_content.encode("utf-8"))
            body_parts.append(b"\r\n")
            
            # Image parts
            for part_name, img_data, img_content_type in image_parts:
                body_parts.append(f"--{boundary}\r\n".encode())
                body_parts.append(
                    f'Content-Disposition: form-data; name="{part_name}"\r\n'.encode()
                )
                body_parts.append(
                    f"Content-Type: {img_content_type}\r\n\r\n".encode()
                )
                body_parts.append(img_data)
                body_parts.append(b"\r\n")
            
            # Closing boundary
            body_parts.append(f"--{boundary}--\r\n".encode())
            
            multipart_body = b"".join(body_parts)
            
            response = await self._request(
                "POST",
                url,
                content=multipart_body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}"
                },
            )
        else:
            # Simple HTML post when no images
            response = await self._request(
                "POST",
                url,
                content=html_content.encode("utf-8"),
                headers={"Content-Type": "text/html"},
            )

        # Step 4: Extract the new page ID from the response
        new_page_id = ""
        try:
            data = response.json()
            new_page_id = data.get("id", "")
        except (ValueError, KeyError):
            pass

        # Step 5: Verify the new page actually exists
        if not new_page_id:
            raise GraphError(
                message="Clone failed — no new page ID returned from Graph API",
                status_code=None,
            )

        # Step 6: Verify the new page is accessible
        try:
            new_page_meta = await self.get_page_metadata(new_page_id)
            if not new_page_meta.id:
                raise GraphError(
                    message="Clone verification failed — new page not found after creation",
                    status_code=None,
                )
        except GraphError:
            raise GraphError(
                message=f"Clone verification failed — cannot read new page {new_page_id}",
                status_code=None,
            )

        return new_page_id

    async def delete_page(self, page_id: str) -> None:
        """Delete a page from OneNote.

        WARNING: Pages deleted via the API cannot be recovered.

        Args:
            page_id: The ID of the page to delete.

        Raises:
            GraphError: If the Graph API returns an HTTP error status.
            NetworkError: If a timeout or connection error occurs.
        """
        url = f"{self.BASE_URL}/me/onenote/pages/{page_id}"
        await self._request("DELETE", url)

    async def list_section_groups(self, notebook_id: str) -> list[SectionGroup]:
        """List all section groups in a notebook.

        Args:
            notebook_id: The ID of the notebook to query.

        Returns:
            A list of SectionGroup objects.
        """
        url = f"{self.BASE_URL}/me/onenote/notebooks/{notebook_id}/sectionGroups"
        items = await self._paginated_get(url)
        return [
            SectionGroup(
                id=item["id"],
                display_name=item["displayName"],
                notebook_id=notebook_id,
            )
            for item in items
        ]

    async def create_section_group(self, notebook_id: str, display_name: str) -> SectionGroup:
        """Create a section group (folder) in a notebook.

        Args:
            notebook_id: The ID of the notebook.
            display_name: The name for the section group.

        Returns:
            A SectionGroup object for the newly created group.
        """
        url = f"{self.BASE_URL}/me/onenote/notebooks/{notebook_id}/sectionGroups"
        body = {"displayName": display_name}
        response = await self._request("POST", url, json=body)
        item = response.json()
        return SectionGroup(
            id=item["id"],
            display_name=item["displayName"],
            notebook_id=notebook_id,
        )

    async def create_section_in_group(self, section_group_id: str, display_name: str) -> Section:
        """Create a section inside a section group.

        Args:
            section_group_id: The ID of the section group.
            display_name: The name for the new section.

        Returns:
            A Section object for the newly created section.
        """
        url = f"{self.BASE_URL}/me/onenote/sectionGroups/{section_group_id}/sections"
        body = {"displayName": display_name}
        response = await self._request("POST", url, json=body)
        item = response.json()
        return Section(
            id=item["id"],
            display_name=item["displayName"],
            notebook_id=item.get("parentNotebook", {}).get("id"),
            section_group_id=section_group_id,
        )
