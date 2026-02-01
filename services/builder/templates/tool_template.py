"""
{tool_name}

{description}
Built by Builder from PRD: {prd_id}
"""

from typing import Optional


def {function_name}(
    # Required inputs from PRD (no default value)
    # required_input: str,
    # Optional inputs from PRD (with default value)
    # optional_input: int = 100,
    # optional_flag: Optional[str] = None,
) -> dict:
    """
    {description}

    Args:
        # Document each input from PRD:
        # required_input: Description of the input
        # optional_input: Description (default: 100)

    Returns:
        dict with:
            - result: {describe primary output from PRD}
            - success: Boolean indicating success
            - error: Error message if any
    """
    # Initialize result for partial results on error
    result = None

    try:
        # ===========================================
        # IMPLEMENTATION GOES HERE
        # ===========================================
        #
        # 1. Validate inputs if needed
        # 2. Perform the main operation
        # 3. Build the result
        #
        # For multiple outputs, use a dict:
        # result = {
        #     "primary_data": ...,
        #     "count": ...,
        #     "metadata": {...}
        # }

        result = None  # Replace with actual result

        # SUCCESS: Return result with success=True
        return {
            "result": result,
            "success": True,
            "error": None
        }

    except Exception as e:
        # FAILURE: Return partial results with error message
        return {
            "result": result,  # Return whatever we computed so far
            "success": False,
            "error": str(e)
        }


# For Executor compatibility - REQUIRED
run = {function_name}
