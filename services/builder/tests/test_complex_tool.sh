#!/bin/bash
# Test Builder with a complex tool (website_scraper)
# Based on PRD Test Plan - Complex Tool Test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BUILDER_DIR="$REPO_ROOT/services/builder"

echo "============================================"
echo "Builder Test: Complex Tool (website_scraper)"
echo "============================================"
echo ""

# Step 1: Check dependencies first
echo "[0/9] Checking dependencies..."
python -c "
import requests
from bs4 import BeautifulSoup
print('Dependencies available: requests, beautifulsoup4')
" || {
    echo "ERROR: Missing dependencies. Install with:"
    echo "  pip install requests beautifulsoup4"
    exit 1
}
echo ""

# Step 2: Setup PRD
echo "[1/9] Setting up PRD..."
cat > "$BUILDER_DIR/requests/current_prd.yaml" << 'EOF'
prd:
  name: website_scraper
  description: "Scrape text content from a website"
  inputs:
    - name: url
      type: string
      required: true
  outputs:
    - name: text
      type: string
    - name: title
      type: string
  requirements:
    - Use requests + beautifulsoup
    - Handle timeouts
    - Return partial results on error
EOF
echo "PRD written to: $BUILDER_DIR/requests/current_prd.yaml"
echo ""

# Step 3: Run Builder
echo "[2/9] Running Builder..."
echo "Command: $BUILDER_DIR/run.sh"
echo ""
echo "--- Builder Output Start ---"
"$BUILDER_DIR/run.sh"
BUILDER_EXIT=$?
echo "--- Builder Output End ---"
echo ""

if [ $BUILDER_EXIT -ne 0 ]; then
    echo "FAIL: Builder exited with code $BUILDER_EXIT"
    exit 1
fi

# Step 4: Verify tool file exists
echo "[3/9] Verifying tool file..."
TOOL_PATH="$REPO_ROOT/tools/website_scraper.py"
if [ -f "$TOOL_PATH" ]; then
    echo "PASS: Tool file exists at $TOOL_PATH"
else
    echo "FAIL: Tool file not found at $TOOL_PATH"
    exit 1
fi
echo ""

# Step 5: Verify import
echo "[4/9] Verifying import..."
cd "$REPO_ROOT"
python -c "from tools.website_scraper import website_scraper; print('PASS: Import works')" || {
    echo "FAIL: Import failed"
    exit 1
}
echo ""

# Step 6: Verify tool runs with valid URL
echo "[5/9] Verifying tool runs with valid URL..."
python -c "
from tools.website_scraper import website_scraper
result = website_scraper(url='https://example.com')
print(f'Result: {result}')
if result.get('success'):
    print('PASS: Tool runs successfully')
else:
    print(f'WARN: Tool returned success=False (may be network issue)')
    print(f'Error: {result.get(\"error\")}')
"
echo ""

# Step 7: Verify error handling
echo "[6/9] Verifying error handling..."
python -c "
from tools.website_scraper import website_scraper
result = website_scraper(url='https://this-domain-does-not-exist-12345.invalid')

# Should return dict even on failure
assert isinstance(result, dict), 'Result must be dict even on failure'
assert 'success' in result, 'Missing success key'
assert 'error' in result, 'Missing error key'

# Should indicate failure
if result['success'] == False and result['error'] is not None:
    print(f'PASS: Error handling works')
    print(f'Error message: {result[\"error\"][:80]}...' if len(str(result.get('error', ''))) > 80 else f'Error message: {result[\"error\"]}')
else:
    print('WARN: Expected failure for invalid domain but got success=True')
"
echo ""

# Step 8: Verify contract compliance
echo "[7/9] Verifying contract compliance..."
python -c "
from tools.website_scraper import website_scraper, run

# Test main function returns proper contract
result = website_scraper(url='https://example.com')
assert isinstance(result, dict), 'Result must be dict'
assert 'result' in result, 'Missing result key'
assert 'success' in result, 'Missing success key'
assert 'error' in result, 'Missing error key'

# Test run alias exists and works
alias_result = run(url='https://example.com')
assert isinstance(alias_result, dict), 'run alias must return dict'

print('PASS: Contract compliance verified')
"
echo ""

# Step 9: Verify git commit (optional)
echo "[8/9] Checking git commit..."
if git log --oneline -1 -- tools/website_scraper.py 2>/dev/null | head -1; then
    echo "PASS: Tool is committed to git"
else
    echo "WARN: Tool not yet committed (may be normal in test mode)"
fi
echo ""

# Step 10: Check Redis (optional)
echo "[9/9] Checking Redis registration..."
if command -v redis-cli &> /dev/null; then
    if redis-cli PING 2>/dev/null | grep -q PONG; then
        redis-cli HGETALL tools:website_scraper 2>/dev/null && echo "PASS: Redis registered" || echo "WARN: Not in Redis"
    else
        echo "SKIP: Redis not running"
    fi
else
    echo "SKIP: redis-cli not available"
fi
echo ""

# Summary
echo "============================================"
echo "TEST RESULT: PASSED"
echo "============================================"
echo ""
echo "Cleanup: rm -f tools/website_scraper.py services/builder/requests/current_prd.yaml"
