"""
email_sender

Send personalized outreach emails via Resend API with full engagement tracking.
Built by Builder from PRD: email_sender
"""

import os
from datetime import datetime
from typing import Optional


def email_sender(
    to_email: str,
    to_name: str,
    subject: str,
    body_html: str,
    from_name: str,
    from_email: str,
    body_text: Optional[str] = None,
    campaign_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """
    Send a personalized outreach email with engagement tracking.

    Args:
        to_email: Recipient email address (required)
        to_name: Recipient name for personalization (required)
        subject: Email subject line (required)
        body_html: HTML email body (required)
        from_name: Sender display name (required)
        from_email: Sender email address (required)
        body_text: Plain text fallback (optional)
        campaign_id: Campaign identifier for grouping/analysis (optional)
        metadata: Key-value pairs for custom tracking (optional)

    Returns:
        dict with:
            - result: dict containing message_id, status, timestamp, tracking_enabled
            - success: Boolean indicating success
            - error: Error message if any
    """
    result = None

    try:
        # Validate required inputs
        if not to_email or "@" not in to_email:
            raise ValueError("Valid to_email is required")
        if not to_name:
            raise ValueError("to_name is required")
        if not subject:
            raise ValueError("subject is required")
        if not body_html:
            raise ValueError("body_html is required")
        if not from_name:
            raise ValueError("from_name is required")
        if not from_email or "@" not in from_email:
            raise ValueError("Valid from_email is required")

        # Check for Resend API key
        api_key = os.getenv("RESEND_API_KEY")
        if not api_key:
            raise ValueError(
                "Missing environment variable: RESEND_API_KEY is required. "
                "Get your API key from https://resend.com/api-keys"
            )

        # Import Resend SDK
        try:
            import resend
        except ImportError:
            raise ImportError(
                "Missing dependency: resend. Install with: pip install resend"
            )

        # Set API key
        resend.api_key = api_key

        # Build email parameters
        params = {
            "from": f"{from_name} <{from_email}>",
            "to": [to_email],
            "subject": subject,
            "html": body_html,
        }

        # Add optional parameters
        if body_text:
            params["text"] = body_text

        # Add tags for tracking
        tags = []
        if campaign_id:
            tags.append({"name": "campaign_id", "value": campaign_id})

        # Add metadata as tags (Resend supports tags for tracking)
        if metadata:
            for key, value in metadata.items():
                tags.append({"name": key, "value": str(value)})

        if tags:
            params["tags"] = tags

        # Send email via Resend API
        email_response = resend.Emails.send(params)

        # Extract response data
        # Resend returns an object with 'id' field
        message_id = email_response.get("id") if isinstance(email_response, dict) else getattr(email_response, "id", None)

        if not message_id:
            raise ValueError(f"Unexpected response from Resend API: {email_response}")

        # Build result
        result = {
            "message_id": message_id,
            "status": "sent",  # Resend returns success immediately on send
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "tracking_enabled": True,  # Resend enables tracking by default
            "to_email": to_email,
            "to_name": to_name,
            "campaign_id": campaign_id,
        }

        return {
            "result": result,
            "success": True,
            "error": None,
        }

    except ImportError as e:
        return {
            "result": result,
            "success": False,
            "error": str(e),
        }

    except ValueError as e:
        return {
            "result": result,
            "success": False,
            "error": str(e),
        }

    except Exception as e:
        # Catch all Resend API errors
        error_msg = str(e)

        # Provide more helpful error messages for common issues
        if "401" in error_msg or "Unauthorized" in error_msg:
            error_msg = "Invalid RESEND_API_KEY. Check your API key at https://resend.com/api-keys"
        elif "403" in error_msg or "Forbidden" in error_msg:
            error_msg = f"Permission denied. Verify from_email domain is verified in Resend: {from_email}"
        elif "429" in error_msg or "rate limit" in error_msg.lower():
            error_msg = "Rate limit exceeded. Wait before sending more emails."
        elif "400" in error_msg:
            error_msg = f"Invalid request: {error_msg}"

        return {
            "result": result,
            "success": False,
            "error": error_msg,
        }


# For Executor compatibility
run = email_sender
