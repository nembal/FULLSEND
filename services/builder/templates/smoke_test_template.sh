#!/bin/bash
# Smoke test template for Builder-generated tools
#
# Usage: Replace {tool_name} with the actual tool name
#        Replace {test_args} with test arguments if needed

TOOL_NAME="{tool_name}"

echo "=== Smoke Testing: $TOOL_NAME ==="

python -c "
from tools.${TOOL_NAME} import ${TOOL_NAME}

# Test 1: Import works
print('1. Import: OK')

# Test 2: Run with test args (adjust as needed)
# For tools with required args, add them here:
# result = ${TOOL_NAME}(required_arg='test_value')
result = ${TOOL_NAME}()
print('2. Run: OK')

# Test 3: Verify return format
assert isinstance(result, dict), 'Result must be a dict'
assert 'result' in result, 'Missing result key'
assert 'success' in result, 'Missing success key'
assert 'error' in result, 'Missing error key'
print('3. Format: OK')

# Test 4: Report status
print(f'4. Success: {result[\"success\"]}')
if result['error']:
    print(f'   Error: {result[\"error\"]}')
else:
    print(f'   Result preview: {str(result[\"result\"])[:100]}...')

print('')
print('=== SMOKE TEST PASSED ===')
"

TEST_EXIT=$?

if [ $TEST_EXIT -eq 0 ]; then
    echo ""
    echo "Tool $TOOL_NAME is ready for commit."
    exit 0
else
    echo ""
    echo "=== SMOKE TEST FAILED ==="
    echo "Fix the tool and re-run the test."
    exit 1
fi
