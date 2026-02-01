#!/bin/bash
# Run all Builder tests
# Usage: ./services/builder/tests/run_all_tests.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================"
echo "       Builder Test Suite"
echo "============================================"
echo ""
echo "This will run both test scenarios:"
echo "  1. Simple Tool (hello_world)"
echo "  2. Complex Tool (website_scraper)"
echo ""
echo "Press Enter to continue or Ctrl+C to cancel..."
read

# Test 1: Simple Tool
echo ""
echo "============================================"
echo "Running Test 1: Simple Tool"
echo "============================================"
echo ""

"$SCRIPT_DIR/test_simple_tool.sh"
TEST1_RESULT=$?

echo ""
echo "Test 1 Result: $([ $TEST1_RESULT -eq 0 ] && echo 'PASSED' || echo 'FAILED')"
echo ""

# Pause between tests
echo "Press Enter to continue to Test 2..."
read

# Test 2: Complex Tool
echo ""
echo "============================================"
echo "Running Test 2: Complex Tool"
echo "============================================"
echo ""

"$SCRIPT_DIR/test_complex_tool.sh"
TEST2_RESULT=$?

echo ""
echo "Test 2 Result: $([ $TEST2_RESULT -eq 0 ] && echo 'PASSED' || echo 'FAILED')"
echo ""

# Summary
echo ""
echo "============================================"
echo "       Test Suite Summary"
echo "============================================"
echo ""
echo "Test 1 (Simple Tool):  $([ $TEST1_RESULT -eq 0 ] && echo 'PASSED' || echo 'FAILED')"
echo "Test 2 (Complex Tool): $([ $TEST2_RESULT -eq 0 ] && echo 'PASSED' || echo 'FAILED')"
echo ""

if [ $TEST1_RESULT -eq 0 ] && [ $TEST2_RESULT -eq 0 ]; then
    echo "ALL TESTS PASSED"
    exit 0
else
    echo "SOME TESTS FAILED"
    exit 1
fi
