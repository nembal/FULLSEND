#!/bin/bash
# Test Builder with a simple tool (hello_world)
# Based on PRD Test Plan - Basic Test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BUILDER_DIR="$REPO_ROOT/services/builder"

echo "========================================="
echo "Builder Test: Simple Tool (hello_world)"
echo "========================================="
echo ""

# Step 1: Setup PRD
echo "[1/7] Setting up PRD..."
cat > "$BUILDER_DIR/requests/current_prd.yaml" << 'EOF'
prd:
  name: hello_world
  description: "A simple test tool"
  inputs:
    - name: name
      type: string
      default: "World"
  outputs:
    - name: greeting
      type: string
  requirements:
    - Return a greeting string
EOF
echo "PRD written to: $BUILDER_DIR/requests/current_prd.yaml"
echo ""

# Step 2: Run Builder
echo "[2/7] Running Builder..."
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

# Step 3: Verify tool file exists
echo "[3/7] Verifying tool file..."
TOOL_PATH="$REPO_ROOT/tools/hello_world.py"
if [ -f "$TOOL_PATH" ]; then
    echo "PASS: Tool file exists at $TOOL_PATH"
else
    echo "FAIL: Tool file not found at $TOOL_PATH"
    exit 1
fi
echo ""

# Step 4: Verify import
echo "[4/7] Verifying import..."
cd "$REPO_ROOT"
python -c "from tools.hello_world import hello_world; print('PASS: Import works')" || {
    echo "FAIL: Import failed"
    exit 1
}
echo ""

# Step 5: Verify tool runs
echo "[5/7] Verifying tool runs..."
python -c "
from tools.hello_world import hello_world
result = hello_world()
print(f'Result: {result}')
if result.get('success'):
    print('PASS: Tool runs successfully')
else:
    print(f'FAIL: Tool returned success=False, error={result.get(\"error\")}')
    exit(1)
"
echo ""

# Step 6: Verify contract compliance
echo "[6/7] Verifying contract compliance..."
python -c "
from tools.hello_world import hello_world, run

# Test main function
result = hello_world()
assert isinstance(result, dict), 'Result must be dict'
assert 'result' in result, 'Missing result key'
assert 'success' in result, 'Missing success key'
assert 'error' in result, 'Missing error key'

# Test run alias
alias_result = run(name='Test')
assert isinstance(alias_result, dict), 'run alias must return dict'

print('PASS: Contract compliance verified')
"
echo ""

# Step 7: Verify git commit (optional)
echo "[7/7] Checking git commit..."
if git log --oneline -1 -- tools/hello_world.py 2>/dev/null | head -1; then
    echo "PASS: Tool is committed to git"
else
    echo "WARN: Tool not yet committed (may be normal in test mode)"
fi
echo ""

# Summary
echo "========================================="
echo "TEST RESULT: PASSED"
echo "========================================="
echo ""
echo "Cleanup: rm -f tools/hello_world.py services/builder/requests/current_prd.yaml"
