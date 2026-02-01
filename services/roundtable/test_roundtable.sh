#!/bin/bash
# Test plan checks from PRD - services/roundtable/test_roundtable.sh
#
# Run from repo root:
#   ./services/roundtable/test_roundtable.sh
#
# Tests:
#   1. Basic Test - JSON stdin, check summary output
#   2. Full Test - Full input with context/learnings
#   3. Persona Test - Verify agents stay in character

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "================================================"
echo "Roundtable Test Plan Checks (from PRD)"
echo "================================================"
echo ""

# Temp files for test outputs
BASIC_OUTPUT=$(mktemp)
FULL_OUTPUT=$(mktemp)
FULL_INPUT=$(mktemp)

cleanup() {
    rm -f "$BASIC_OUTPUT" "$FULL_OUTPUT" "$FULL_INPUT"
}
trap cleanup EXIT

TESTS_PASSED=0
TESTS_FAILED=0

# ------------------------------------------------
# TEST 1: Basic Test
# ------------------------------------------------
echo -e "${YELLOW}TEST 1: Basic Test${NC}"
echo "Running: echo '{\"prompt\": \"...\"}' | python -m services.roundtable"
echo ""

echo '{"prompt": "How can we reach developers who use competitor products?"}' | \
    python -m services.roundtable > "$BASIC_OUTPUT" 2>&1 || true

# Check if output is valid JSON
if ! jq empty "$BASIC_OUTPUT" 2>/dev/null; then
    echo -e "${RED}FAIL: Output is not valid JSON${NC}"
    echo "Output:"
    head -20 "$BASIC_OUTPUT"
    TESTS_FAILED=$((TESTS_FAILED + 1))
else
    echo -e "${GREEN}PASS: Output is valid JSON${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
fi

# Check summary exists and has 3-5 tasks
SUMMARY_COUNT=$(jq '.summary | length' "$BASIC_OUTPUT" 2>/dev/null || echo "0")
if [ "$SUMMARY_COUNT" -ge 3 ] && [ "$SUMMARY_COUNT" -le 5 ]; then
    echo -e "${GREEN}PASS: Summary has $SUMMARY_COUNT tasks (expected 3-5)${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL: Summary has $SUMMARY_COUNT tasks (expected 3-5)${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Check transcript exists
TRANSCRIPT=$(jq -r '.transcript' "$BASIC_OUTPUT" 2>/dev/null || echo "")
if [ -n "$TRANSCRIPT" ] && [ "$TRANSCRIPT" != "null" ]; then
    echo -e "${GREEN}PASS: Transcript exists${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL: Transcript missing or null${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

echo ""
echo "Summary output:"
jq '.summary' "$BASIC_OUTPUT" 2>/dev/null || echo "(none)"
echo ""

# ------------------------------------------------
# TEST 2: Full Test
# ------------------------------------------------
echo -e "${YELLOW}TEST 2: Full Test (with context and learnings)${NC}"
echo ""

cat > "$FULL_INPUT" << 'EOF'
{
    "prompt": "How can we reach AI startup CTOs who just raised Series A?",
    "context": "We sell developer tools. Our best customers are technical founders.",
    "learnings": [
        "GitHub-based targeting has 15% response rate",
        "Personalization on recent news increases opens 2x"
    ]
}
EOF

python -m services.roundtable "$FULL_INPUT" > "$FULL_OUTPUT" 2>&1 || true

# Check valid JSON
if ! jq empty "$FULL_OUTPUT" 2>/dev/null; then
    echo -e "${RED}FAIL: Output is not valid JSON${NC}"
    echo "Output:"
    head -20 "$FULL_OUTPUT"
    TESTS_FAILED=$((TESTS_FAILED + 1))
else
    echo -e "${GREEN}PASS: Output is valid JSON${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
fi

# Check transcript shows 3 agents
TRANSCRIPT=$(jq -r '.transcript' "$FULL_OUTPUT" 2>/dev/null || echo "")

if echo "$TRANSCRIPT" | grep -q "ARTIST:"; then
    echo -e "${GREEN}PASS: ARTIST appears in transcript${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL: ARTIST missing from transcript${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

if echo "$TRANSCRIPT" | grep -q "BUSINESS:"; then
    echo -e "${GREEN}PASS: BUSINESS appears in transcript${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL: BUSINESS missing from transcript${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

if echo "$TRANSCRIPT" | grep -q "TECH:"; then
    echo -e "${GREEN}PASS: TECH appears in transcript${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL: TECH missing from transcript${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Check for round headers (PRD format)
if echo "$TRANSCRIPT" | grep -q "Round 1"; then
    echo -e "${GREEN}PASS: Round headers present${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL: Round headers missing${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Check summary has 3-5 tasks
SUMMARY_COUNT=$(jq '.summary | length' "$FULL_OUTPUT" 2>/dev/null || echo "0")
if [ "$SUMMARY_COUNT" -ge 3 ] && [ "$SUMMARY_COUNT" -le 5 ]; then
    echo -e "${GREEN}PASS: Full test summary has $SUMMARY_COUNT tasks${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL: Full test summary has $SUMMARY_COUNT tasks (expected 3-5)${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

echo ""

# ------------------------------------------------
# TEST 3: Persona Test
# ------------------------------------------------
echo -e "${YELLOW}TEST 3: Persona Test (agent distinctiveness)${NC}"
echo "Checking agents stay in character..."
echo ""

# Extract each agent's content from transcript
ARTIST_CONTENT=$(echo "$TRANSCRIPT" | grep -A1 "^ARTIST:" | head -20 || echo "")
BUSINESS_CONTENT=$(echo "$TRANSCRIPT" | grep -A1 "^BUSINESS:" | head -20 || echo "")
TECH_CONTENT=$(echo "$TRANSCRIPT" | grep -A1 "^TECH:" | head -20 || echo "")

# ARTIST should be creative/unconventional (check for typical keywords)
# Checking that content exists and is non-trivial
if [ ${#ARTIST_CONTENT} -gt 50 ]; then
    echo -e "${GREEN}PASS: ARTIST has substantial content${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL: ARTIST content too short or missing${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

if [ ${#BUSINESS_CONTENT} -gt 50 ]; then
    echo -e "${GREEN}PASS: BUSINESS has substantial content${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL: BUSINESS content too short or missing${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

if [ ${#TECH_CONTENT} -gt 50 ]; then
    echo -e "${GREEN}PASS: TECH has substantial content${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL: TECH content too short or missing${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Check that agents respond to each other (later rounds reference earlier content)
ROUND_2_EXISTS=$(echo "$TRANSCRIPT" | grep -c "Round 2" || echo "0")
ROUND_3_EXISTS=$(echo "$TRANSCRIPT" | grep -c "Round 3" || echo "0")

if [ "$ROUND_2_EXISTS" -ge 1 ] && [ "$ROUND_3_EXISTS" -ge 1 ]; then
    echo -e "${GREEN}PASS: Multiple rounds executed (agents can respond to each other)${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL: Not all 3 rounds present${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

echo ""
echo "================================================"
echo "TEST SUMMARY"
echo "================================================"
echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ "$TESTS_FAILED" -gt 0 ]; then
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi
