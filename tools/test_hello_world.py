"""
test_hello_world

Simple test tool that returns hello world.
Built by Builder from PRD: test_hello_world
"""


def test_hello_world() -> dict:
    """
    Generate a hello world message.

    Args:
        None

    Returns:
        dict with:
            - result: Dict containing the message string
            - success: Boolean indicating success
            - error: Error message if any
    """
    result = None

    try:
        result = {"message": "Hello, World!"}
        return {
            "result": result,
            "success": True,
            "error": None
        }

    except Exception as e:
        return {
            "result": result,
            "success": False,
            "error": str(e)
        }


# For Executor compatibility
run = test_hello_world
