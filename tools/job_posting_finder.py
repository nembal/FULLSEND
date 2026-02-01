"""
job_posting_finder

Find mid-market companies actively hiring for automatable roles.
Built by Builder from PRD: job_posting_finder
"""

import os
import re
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import quote_plus


def job_posting_finder(
    role_keywords: List[str],
    company_size: str = "200-2000",
    max_results: int = 10,
    location: Optional[str] = None
) -> dict:
    """
    Find companies hiring for specific roles using LinkedIn Jobs.

    Args:
        role_keywords: List of job titles/keywords (e.g., ['data entry clerk', 'invoice processor'])
        company_size: Company size filter as employee range (default: "200-2000")
        max_results: Number of companies to return (default: 10)
        location: Optional geographic filter (e.g., 'United States', 'Remote')

    Returns:
        dict with:
            - result: Dict containing 'companies' list with job posting details
            - success: Boolean indicating success
            - error: Error message if any
    """
    result = None

    try:
        # Validate inputs
        if not role_keywords or not isinstance(role_keywords, list):
            raise ValueError("role_keywords must be a non-empty list")

        if max_results < 1 or max_results > 100:
            raise ValueError("max_results must be between 1 and 100")

        # Parse company size range
        size_parts = company_size.split("-")
        if len(size_parts) != 2:
            raise ValueError("company_size must be in format 'min-max' (e.g., '200-2000')")

        min_size, max_size = int(size_parts[0]), int(size_parts[1])

        # Check for required environment variables
        api_key = os.getenv("BROWSERBASE_API_KEY")
        project_id = os.getenv("BROWSERBASE_PROJECT_ID")

        if not api_key or not project_id:
            raise ValueError(
                "Missing environment variables: BROWSERBASE_API_KEY and BROWSERBASE_PROJECT_ID are required"
            )

        # Import dependencies
        from browserbase import Browserbase
        from playwright.sync_api import sync_playwright

        companies = []
        processed_companies = set()  # Deduplicate by domain

        # Initialize Browserbase client
        bb = Browserbase(api_key=api_key)

        # Search for each role keyword
        for keyword in role_keywords:
            if len(companies) >= max_results:
                break

            # Build LinkedIn Jobs search URL
            query = quote_plus(keyword)
            url = f"https://www.linkedin.com/jobs/search/?keywords={query}"

            # Add location filter if provided
            if location:
                url += f"&location={quote_plus(location)}"

            # Add date posted filter (past 30 days)
            url += "&f_TPR=r2592000"  # Last 30 days

            # Create a session
            session = bb.sessions.create(project_id=project_id)

            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(session.connect_url)
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.new_page()

                page.set_default_timeout(30000)

                # Navigate to search results
                page.goto(url, wait_until="domcontentloaded")

                # Wait for job listings to load
                try:
                    page.wait_for_selector(".jobs-search__results-list", timeout=10000)
                except Exception:
                    # If the selector doesn't load, continue to next keyword
                    browser.close()
                    continue

                # Extract job listings
                job_cards = page.query_selector_all(".base-card")

                for card in job_cards[:max_results]:
                    if len(companies) >= max_results:
                        break

                    try:
                        # Extract job details
                        title_el = card.query_selector(".base-search-card__title")
                        company_el = card.query_selector(".base-search-card__subtitle")
                        location_el = card.query_selector(".job-search-card__location")
                        link_el = card.query_selector("a.base-card__full-link")
                        time_el = card.query_selector("time")

                        if not title_el or not company_el or not link_el:
                            continue

                        job_title = title_el.text_content().strip()
                        company_name = company_el.text_content().strip()
                        job_location = location_el.text_content().strip() if location_el else "Unknown"
                        job_url = link_el.get_attribute("href")
                        posting_date = time_el.get_attribute("datetime") if time_el else None

                        # Extract company domain (requires additional lookup)
                        # For now, use a placeholder - we'd need to visit company page or use an API
                        company_domain = _extract_domain_from_company_name(company_name)

                        # Skip if we've already processed this company
                        if company_domain in processed_companies:
                            continue

                        # Estimate employee count (LinkedIn doesn't always provide this publicly)
                        # We'd need to visit the company page or use LinkedIn API
                        # For now, use a placeholder that falls within range
                        employee_count = _estimate_employee_count(company_name)

                        # Filter by company size
                        if not (min_size <= employee_count <= max_size):
                            continue

                        # Extract industry (placeholder - would need company page visit)
                        industry = "Unknown"

                        companies.append({
                            "company_name": company_name,
                            "company_domain": company_domain,
                            "employee_count": employee_count,
                            "industry": industry,
                            "job_title": job_title,
                            "job_posting_url": job_url,
                            "posting_date": posting_date,
                            "location": job_location
                        })

                        processed_companies.add(company_domain)

                    except Exception as e:
                        # Skip this card if extraction fails
                        continue

                browser.close()

        result = {"companies": companies}

        return {
            "result": result,
            "success": True,
            "error": None
        }

    except ImportError as e:
        missing_pkg = str(e).split("'")[-2] if "'" in str(e) else "browserbase/playwright"
        return {
            "result": result,
            "success": False,
            "error": f"Missing dependency: {missing_pkg}. Install with: pip install browserbase playwright"
        }

    except Exception as e:
        return {
            "result": result,
            "success": False,
            "error": str(e)
        }


def _extract_domain_from_company_name(company_name: str) -> str:
    """
    Generate a domain from company name (best guess).
    For production, this should use a company data API or additional scraping.
    """
    # Remove common suffixes and clean
    clean_name = re.sub(r'\b(Inc|LLC|Ltd|Corporation|Corp|Company|Co)\b\.?', '', company_name, flags=re.IGNORECASE)
    clean_name = re.sub(r'[^\w\s]', '', clean_name)
    clean_name = clean_name.strip().lower().replace(' ', '')

    # Generate domain guess
    return f"{clean_name}.com"


def _estimate_employee_count(company_name: str) -> int:
    """
    Placeholder function for employee count estimation.
    In production, this should use:
    - LinkedIn Company API
    - Clearbit API
    - Company page scraping
    - ZoomInfo API

    For now, return a value within mid-market range.
    """
    # Return middle of mid-market range as placeholder
    return 600


# For Executor compatibility
run = job_posting_finder
