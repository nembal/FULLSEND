"""
Browserbase Web Research Tool

Scrapes webpages and researches companies using Browserbase cloud browser API.
Built by Builder from PRD: PRD_BROWSERBASE_TOOL
"""

import os
import re
from typing import Optional
from urllib.parse import urljoin, urlparse


def browserbase(
    url: str,
    action: str = "scrape",
    selector: Optional[str] = None,
    wait_for: Optional[str] = None,
    timeout: int = 30,
    extract_links: bool = False,
) -> dict:
    """
    Scrape a webpage or research a company using Browserbase.

    Args:
        url: URL to scrape or navigate to
        action: Action to perform ('scrape', 'screenshot', 'research')
        selector: CSS selector to extract specific content
        wait_for: CSS selector to wait for before scraping
        timeout: Timeout in seconds for page load
        extract_links: Whether to extract all links from the page

    Returns:
        dict with:
            - content: Extracted text content
            - title: Page title
            - html: Raw HTML (if requested)
            - links: List of links (if extract_links=true)
            - screenshot_url: Screenshot URL (if action='screenshot')
            - metadata: Page metadata dict
            - success: Boolean indicating success
            - error: Error message if any
    """
    # Validate inputs
    if not url:
        return _error_response("URL is required")

    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    # Validate URL format
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return _error_response(f"Invalid URL: {url}")
    except Exception as e:
        return _error_response(f"Invalid URL format: {e}")

    if action not in ("scrape", "screenshot", "research"):
        return _error_response(f"Invalid action: {action}. Must be 'scrape', 'screenshot', or 'research'")

    if timeout < 1 or timeout > 60:
        return _error_response("Timeout must be between 1 and 60 seconds")

    # Check for required environment variables
    api_key = os.getenv("BROWSERBASE_API_KEY")
    project_id = os.getenv("BROWSERBASE_PROJECT_ID")

    if not api_key or not project_id:
        return _error_response(
            "Missing environment variables: BROWSERBASE_API_KEY and BROWSERBASE_PROJECT_ID are required"
        )

    try:
        # Import dependencies inside function to allow tool file to load even if deps missing
        from browserbase import Browserbase
        from playwright.sync_api import sync_playwright

        # Initialize Browserbase client
        bb = Browserbase(api_key=api_key)

        # Create a session
        session = bb.sessions.create(project_id=project_id)

        with sync_playwright() as p:
            # Connect to the cloud browser
            browser = p.chromium.connect_over_cdp(session.connect_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()

            # Set timeout
            page.set_default_timeout(timeout * 1000)

            # Navigate to URL
            page.goto(url, wait_until="domcontentloaded")

            # Wait for specific selector if provided
            if wait_for:
                page.wait_for_selector(wait_for, timeout=timeout * 1000)

            # Get basic page info
            title = page.title()
            final_url = page.url

            # Handle screenshot action
            screenshot_url = None
            if action == "screenshot":
                # Take screenshot and get base64
                screenshot_bytes = page.screenshot(full_page=True)
                # For now, we'll store it as base64 data URL
                import base64
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
                screenshot_url = f"data:image/png;base64,{screenshot_b64}"

            # Extract content based on selector or full page
            if selector:
                elements = page.query_selector_all(selector)
                content = "\n".join([el.text_content() or "" for el in elements])
                html = "\n".join([el.inner_html() for el in elements])
            else:
                # Get main content, stripping scripts and styles
                content = page.evaluate("""
                    () => {
                        // Remove script and style elements
                        const clone = document.body.cloneNode(true);
                        clone.querySelectorAll('script, style, noscript').forEach(el => el.remove());
                        return clone.innerText || clone.textContent || '';
                    }
                """)
                html = page.content()

            # Clean up content
            content = _clean_text(content)

            # Extract links if requested
            links = []
            if extract_links:
                link_elements = page.query_selector_all("a[href]")
                for link in link_elements:
                    href = link.get_attribute("href")
                    text = (link.text_content() or "").strip()
                    if href:
                        # Convert relative URLs to absolute
                        absolute_href = urljoin(final_url, href)
                        links.append({"text": text, "href": absolute_href})

            # Extract metadata
            metadata = _extract_metadata(page, final_url)

            # Close browser
            browser.close()

            return {
                "content": content,
                "title": title,
                "html": html if action == "research" else None,
                "links": links,
                "screenshot_url": screenshot_url,
                "metadata": metadata,
                "success": True,
                "error": None,
            }

    except ImportError as e:
        missing_pkg = str(e).split("'")[-2] if "'" in str(e) else "browserbase/playwright"
        return _error_response(
            f"Missing dependency: {missing_pkg}. Install with: pip install browserbase playwright"
        )

    except Exception as e:
        error_msg = str(e)
        # Provide more helpful error messages for common issues
        if "net::ERR_NAME_NOT_RESOLVED" in error_msg:
            error_msg = f"Could not resolve domain: {urlparse(url).netloc}"
        elif "Timeout" in error_msg:
            error_msg = f"Page load timeout after {timeout} seconds"
        elif "net::ERR_CONNECTION_REFUSED" in error_msg:
            error_msg = f"Connection refused by {urlparse(url).netloc}"

        return _error_response(error_msg)


def _error_response(error: str) -> dict:
    """Return a standardized error response."""
    return {
        "content": "",
        "title": "",
        "html": None,
        "links": [],
        "screenshot_url": None,
        "metadata": {},
        "success": False,
        "error": error,
    }


def _clean_text(text: str) -> str:
    """Clean and normalize extracted text content."""
    if not text:
        return ""

    # Replace multiple whitespace with single space
    text = re.sub(r"\s+", " ", text)

    # Replace multiple newlines with double newline
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Strip leading/trailing whitespace
    text = text.strip()

    return text


def _extract_metadata(page, final_url: str) -> dict:
    """Extract metadata from page."""
    metadata = {"url": final_url}

    try:
        # Get meta description
        desc_el = page.query_selector('meta[name="description"]')
        if desc_el:
            metadata["description"] = desc_el.get_attribute("content")

        # Get meta keywords
        keywords_el = page.query_selector('meta[name="keywords"]')
        if keywords_el:
            metadata["keywords"] = keywords_el.get_attribute("content")

        # Get Open Graph data
        og_title = page.query_selector('meta[property="og:title"]')
        if og_title:
            metadata["og_title"] = og_title.get_attribute("content")

        og_desc = page.query_selector('meta[property="og:description"]')
        if og_desc:
            metadata["og_description"] = og_desc.get_attribute("content")

        og_image = page.query_selector('meta[property="og:image"]')
        if og_image:
            metadata["og_image"] = og_image.get_attribute("content")

        # Get canonical URL
        canonical = page.query_selector('link[rel="canonical"]')
        if canonical:
            metadata["canonical_url"] = canonical.get_attribute("href")

    except Exception:
        # Metadata extraction is best-effort
        pass

    return metadata


# For Executor compatibility
run = browserbase


# Convenience function for company research
def research_company(domain: str, timeout: int = 30) -> dict:
    """
    Research a company by its domain.

    Args:
        domain: Company domain (e.g., 'anthropic.com')
        timeout: Timeout in seconds

    Returns:
        dict with company information extracted from their website
    """
    url = f"https://{domain}" if not domain.startswith("http") else domain

    return browserbase(
        url=url,
        action="research",
        extract_links=True,
        timeout=timeout,
    )
