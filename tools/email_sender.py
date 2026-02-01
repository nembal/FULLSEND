"""
email_sender

Send personalized cold outreach emails with template support.
Built by Builder from PRD: email_sender
"""

import os
import re
import time
from typing import Optional, Any
from datetime import datetime


def email_sender(
    to_email: str,
    to_name: str,
    subject: str,
    body_template: str,
    personalization: dict[str, Any],
    from_name: str = "Fullsend",
    reply_to: Optional[str] = None
) -> dict:
    """
    Send a personalized email using Resend API.

    Args:
        to_email: Recipient email address
        to_name: Recipient name for personalization
        subject: Email subject line (supports {{variables}})
        body_template: Email body with {{variable}} placeholders
        personalization: Key/value pairs to substitute into template
        from_name: Sender display name (default: "Fullsend")
        reply_to: Reply-to address (optional, defaults to from_email)

    Returns:
        dict with:
            - result: dict with message_id and tracking info
            - success: Boolean indicating success
            - error: Error message if any
    """
    result = None

    try:
        # Check for Resend API key
        api_key = os.environ.get("RESEND_API_KEY")
        if not api_key:
            return {
                "result": None,
                "success": False,
                "error": "RESEND_API_KEY environment variable not set"
            }

        # Get from_email from environment
        from_email = os.environ.get("RESEND_FROM_EMAIL", "noreply@example.com")

        # Merge personalization with standard variables
        template_vars = {
            "to_name": to_name,
            "to_email": to_email,
            **personalization
        }

        # Apply template substitutions to subject
        rendered_subject = subject
        for key, value in template_vars.items():
            rendered_subject = rendered_subject.replace(f"{{{{{key}}}}}", str(value))

        # Apply template substitutions to body
        rendered_body = body_template
        for key, value in template_vars.items():
            rendered_body = rendered_body.replace(f"{{{{{key}}}}}", str(value))

        # Validate email format
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, to_email):
            return {
                "result": None,
                "success": False,
                "error": f"Invalid email format: {to_email}"
            }

        # Import requests here to avoid dependency issues if not installed
        try:
            import requests
        except ImportError:
            return {
                "result": None,
                "success": False,
                "error": "requests library not installed. Run: uv pip install requests"
            }

        # Prepare email payload
        payload = {
            "from": f"{from_name} <{from_email}>",
            "to": [to_email],
            "subject": rendered_subject,
            "html": rendered_body.replace("\n", "<br>"),  # Simple HTML conversion
            "text": rendered_body  # Plain text fallback
        }

        if reply_to:
            payload["reply_to"] = reply_to

        # Send via Resend API
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=10
        )

        # Handle response
        if response.status_code == 200:
            response_data = response.json()
            message_id = response_data.get("id", "unknown")

            result = {
                "message_id": message_id,
                "to_email": to_email,
                "to_name": to_name,
                "sent_at": datetime.utcnow().isoformat(),
                "subject": rendered_subject
            }

            # Rate limiting: sleep briefly to avoid spam flags
            time.sleep(0.5)

            return {
                "result": result,
                "success": True,
                "error": None
            }
        else:
            error_message = f"Resend API error (status {response.status_code})"
            try:
                error_data = response.json()
                error_message = f"{error_message}: {error_data.get('message', 'Unknown error')}"
            except:
                error_message = f"{error_message}: {response.text}"

            return {
                "result": None,
                "success": False,
                "error": error_message
            }

    except requests.exceptions.Timeout:
        return {
            "result": result,
            "success": False,
            "error": "Request timeout - Resend API took too long to respond"
        }

    except requests.exceptions.RequestException as e:
        return {
            "result": result,
            "success": False,
            "error": f"Network error: {str(e)}"
        }

    except Exception as e:
        return {
            "result": result,
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }


# For Executor compatibility
run = email_sender
