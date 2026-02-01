# PRD: Browserbase Tool

## Overview

**Name:** `browserbase`
**Location:** `tools/browserbase.py`
**Purpose:** Web research and scraping tool using Browserbase cloud browser automation API. Enables FULLSEND and other components to research companies, scrape pages, and gather web data.

**Requested by:** System design (SYSTEM_COMPONENTS.md)
**Priority:** High (first skill, enables everything else)

---

## What It Does

The browserbase tool provides web research capabilities:

1. **Scrape webpage content** — Fetch and extract text/HTML from any URL
2. **Research companies** — Visit company websites and extract key information
3. **Navigate and interact** — Handle JavaScript-rendered pages via cloud browser
4. **Screenshot capture** — Take screenshots for visual analysis

---

## Inputs

```yaml
inputs:
  - name: url
    type: string
    description: "URL to scrape or navigate to"
    required: true

  - name: action
    type: string
    description: "Action to perform: 'scrape', 'screenshot', 'research'"
    default: "scrape"

  - name: selector
    type: string
    description: "CSS selector to extract specific content (optional)"
    required: false

  - name: wait_for
    type: string
    description: "CSS selector to wait for before scraping (for JS-rendered pages)"
    required: false

  - name: timeout
    type: integer
    description: "Timeout in seconds for page load"
    default: 30

  - name: extract_links
    type: boolean
    description: "Whether to extract all links from the page"
    default: false
```

---

## Outputs

```yaml
outputs:
  - name: content
    type: string
    description: "Text content extracted from the page"

  - name: title
    type: string
    description: "Page title"

  - name: html
    type: string
    description: "Raw HTML (if requested)"

  - name: links
    type: list
    description: "List of links found on page (if extract_links=true)"
    schema:
      text: string
      href: string

  - name: screenshot_url
    type: string
    description: "URL to screenshot image (if action='screenshot')"

  - name: metadata
    type: dict
    description: "Page metadata (description, keywords, etc.)"

  - name: success
    type: boolean
    description: "Whether the operation succeeded"

  - name: error
    type: string
    description: "Error message if operation failed"
```

---

## Requirements

### Functional Requirements
- Must use Browserbase API for cloud browser automation
- Must handle JavaScript-rendered pages (SPA, React, etc.)
- Must support CSS selectors for targeted extraction
- Must handle timeouts gracefully
- Must return partial results on failure
- Must sanitize/clean extracted text content

### Non-Functional Requirements
- Timeout: Max 60 seconds per request
- Rate limiting: Respect Browserbase API limits
- Error handling: Never crash, always return structured response
- Caching: Consider caching recent results (optional)

### Environment Variables Required
```
BROWSERBASE_API_KEY=...
BROWSERBASE_PROJECT_ID=...
```

---

## Tool Contract

Following the Builder tool contract from PRD_BUILDER.md:

```python
# tools/browserbase.py
"""
Browserbase Web Research Tool

Scrapes webpages and researches companies using Browserbase cloud browser API.
Built by Builder from PRD: PRD_BROWSERBASE_TOOL
"""

from typing import Optional
import os

def browserbase(
    url: str,
    action: str = "scrape",
    selector: Optional[str] = None,
    wait_for: Optional[str] = None,
    timeout: int = 30,
    extract_links: bool = False
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
    try:
        # Implementation using Browserbase API
        # ...

        return {
            "content": extracted_text,
            "title": page_title,
            "html": None,  # Only if requested
            "links": links if extract_links else [],
            "screenshot_url": None,  # Only if action='screenshot'
            "metadata": {
                "description": meta_description,
                "keywords": meta_keywords,
                "url": final_url
            },
            "success": True,
            "error": None
        }

    except Exception as e:
        return {
            "content": "",
            "title": "",
            "html": None,
            "links": [],
            "screenshot_url": None,
            "metadata": {},
            "success": False,
            "error": str(e)
        }

# For Executor compatibility
run = browserbase
```

---

## Example Usage

### Basic Page Scraping
```python
from tools.browserbase import browserbase

result = browserbase(url="https://example.com")
print(result["title"])
print(result["content"][:500])
```

### Research a Company
```python
from tools.browserbase import browserbase

# Scrape company homepage
result = browserbase(
    url="https://anthropic.com",
    action="research",
    extract_links=True
)

if result["success"]:
    print(f"Company: {result['title']}")
    print(f"Description: {result['metadata'].get('description')}")
    print(f"Found {len(result['links'])} links")
```

### Wait for JavaScript Content
```python
from tools.browserbase import browserbase

# Wait for dynamic content to load
result = browserbase(
    url="https://app.example.com/dashboard",
    wait_for=".dashboard-content",
    timeout=45
)
```

### Take Screenshot
```python
from tools.browserbase import browserbase

result = browserbase(
    url="https://example.com",
    action="screenshot"
)

if result["success"]:
    print(f"Screenshot: {result['screenshot_url']}")
```

---

## Implementation Notes

### Browserbase API Usage

Browserbase provides cloud-hosted browser automation. The implementation should:

1. **Create a session** — Start a browser session via API
2. **Navigate to URL** — Load the target page
3. **Wait for content** — Wait for selectors or page load
4. **Extract content** — Get text, HTML, or screenshot
5. **Close session** — Clean up resources

### Typical Browserbase Flow
```python
import httpx
from browserbase import Browserbase

bb = Browserbase(api_key=os.getenv("BROWSERBASE_API_KEY"))

# Create session
session = bb.sessions.create(project_id=os.getenv("BROWSERBASE_PROJECT_ID"))

# Connect with Playwright
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(session.connect_url)
    page = browser.new_page()
    page.goto(url)

    if wait_for:
        page.wait_for_selector(wait_for, timeout=timeout * 1000)

    content = page.content()
    title = page.title()

    browser.close()
```

### Error Scenarios to Handle
- Network timeouts
- Invalid URLs
- Pages that block scraping
- JavaScript errors
- Rate limiting from Browserbase
- Session creation failures

---

## Dependencies

```
browserbase>=0.3.0
playwright>=1.40.0
httpx>=0.25.0
beautifulsoup4>=4.12.0
```

---

## Redis Registration

After building, register the tool:

```bash
redis-cli HSET tools:browserbase \
    name "browserbase" \
    description "Web research and scraping via Browserbase cloud browser" \
    path "tools/browserbase.py" \
    status "active" \
    created_at "$(date -Iseconds)"
```

---

## Acceptance Criteria

- [ ] Tool file exists at `tools/browserbase.py`
- [ ] Follows tool contract (inputs, dict output with success/error)
- [ ] Uses Browserbase API correctly
- [ ] Handles JavaScript-rendered pages
- [ ] Gracefully handles errors (returns partial results)
- [ ] Works with environment variables (no hardcoded secrets)
- [ ] Includes docstrings and type hints
- [ ] Basic smoke test passes
- [ ] Registered in Redis

---

## Test Plan

### Smoke Test
```bash
python -c "
from tools.browserbase import browserbase

# Test basic scrape
result = browserbase(url='https://example.com')
assert result['success'], f'Failed: {result[\"error\"]}'
assert 'Example Domain' in result['title']
print('Basic scrape: PASS')

# Test with selector
result = browserbase(url='https://example.com', selector='h1')
assert result['success']
print('Selector scrape: PASS')

# Test error handling
result = browserbase(url='https://invalid-url-that-does-not-exist.xyz')
assert not result['success']
assert result['error'] is not None
print('Error handling: PASS')

print('ALL TESTS PASSED')
"
```

### Integration Test
```bash
# Test with a real JS-rendered page
python -c "
from tools.browserbase import browserbase

result = browserbase(
    url='https://github.com/anthropics',
    wait_for='[data-hovercard-type=\"organization\"]',
    timeout=30
)
assert result['success'], f'Failed: {result[\"error\"]}'
assert 'Anthropic' in result['content'] or 'anthropic' in result['content'].lower()
print('JS page scrape: PASS')
"
```

---

## Notes for Builder

- This is a critical first tool — enables web research for FULLSEND
- Browserbase handles the browser complexity (headless Chrome in cloud)
- Focus on clean API and good error handling
- The tool should be easy to use in experiment designs
- Test with both static (example.com) and dynamic (GitHub, etc.) pages
- Consider adding a simple `research_company(domain)` helper function
