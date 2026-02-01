#!/bin/bash
# FULLSEND Test Plan
# Based on PRD test plan: sample request → spec output
#
# Tests:
# 1. Basic test: Simple experiment request → outputs valid YAML spec
# 2. Tool request test: Request requiring new tool → outputs tool request
# 3. Quality check: Verify spec meets quality criteria
#
# Usage:
#   ./tests/test_plan.sh basic       # Run basic test
#   ./tests/test_plan.sh tool        # Run tool request test
#   ./tests/test_plan.sh quality     # Run quality check on existing spec
#   ./tests/test_plan.sh all         # Run all tests
#   ./tests/test_plan.sh             # Show usage

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FULLSEND_DIR="$(dirname "$SCRIPT_DIR")"
REQUESTS_DIR="$FULLSEND_DIR/requests"
EXPERIMENTS_DIR="$FULLSEND_DIR/experiments"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_header() {
    echo ""
    echo "=========================================="
    echo "$1"
    echo "=========================================="
}

# Backup current request if exists
backup_request() {
    if [[ -f "$REQUESTS_DIR/current.md" ]]; then
        cp "$REQUESTS_DIR/current.md" "$REQUESTS_DIR/current.md.backup"
        print_status "Backed up current request"
    fi
}

# Restore request from backup
restore_request() {
    if [[ -f "$REQUESTS_DIR/current.md.backup" ]]; then
        mv "$REQUESTS_DIR/current.md.backup" "$REQUESTS_DIR/current.md"
        print_status "Restored previous request"
    fi
}

# Test 1: Basic experiment request
test_basic() {
    print_header "TEST 1: Basic Experiment Request"

    backup_request

    # Write test request (from PRD)
    cat > "$REQUESTS_DIR/current.md" << 'EOF'
# Experiment Request

## Idea
Scrape GitHub stargazers of anthropic/claude and email CTOs

## Context from Orchestrator
- We have had success with developer-focused outreach
- GitHub-based targeting has worked well before
- We need the github_stargazer_scraper tool (request from Builder if missing)

## Available Tools
- resend_email: Send emails via Resend API
- browserbase: Web scraping

## Output
Write experiment spec to experiments/exp_test_github_stars.yaml
EOF

    print_status "Wrote test request to requests/current.md"

    echo ""
    echo "To run FULLSEND with this request:"
    echo "  cd $FULLSEND_DIR && ./run.sh"
    echo ""
    echo "After running, verify output at:"
    echo "  $EXPERIMENTS_DIR/exp_test_github_stars.yaml"
    echo ""

    restore_request
}

# Test 2: Tool request test
test_tool_request() {
    print_header "TEST 2: Tool Request Test"

    backup_request

    # Write request that requires a new tool
    cat > "$REQUESTS_DIR/current.md" << 'EOF'
# Experiment Request

## Idea
Scrape Hacker News "Who's Hiring" threads and reach out to companies hiring for AI/ML roles

## Context from Orchestrator
- Companies actively hiring are often growing and have budget
- HN job posts often include direct contact info
- No existing tool for HN scraping

## Available Tools
- resend_email: Send emails via Resend API
- browserbase: Web scraping (generic)

## Output
1. Write experiment spec to experiments/exp_test_hn_hiring.yaml
2. Since we don't have an HN scraper tool, also output a tool request
EOF

    print_status "Wrote tool request test to requests/current.md"

    echo ""
    echo "To run FULLSEND with this request:"
    echo "  cd $FULLSEND_DIR && ./run.sh"
    echo ""
    echo "Expected outputs:"
    echo "  - Experiment spec: $EXPERIMENTS_DIR/exp_test_hn_hiring.yaml"
    echo "  - Tool request: Should request an hn_job_scraper tool"
    echo ""

    restore_request
}

# Test 3: Quality check on existing spec
test_quality() {
    print_header "TEST 3: Quality Check"

    local spec_file="${1:-$EXPERIMENTS_DIR/examples/exp_20240115_github_stargazers.yaml}"

    if [[ ! -f "$spec_file" ]]; then
        print_error "Spec file not found: $spec_file"
        echo "Usage: ./test_plan.sh quality [path/to/spec.yaml]"
        return 1
    fi

    echo "Checking: $spec_file"
    echo ""

    local passed=0
    local failed=0

    # Check 1: ID format
    if grep -qE "id: exp_[0-9]{8}_[a-z_]+" "$spec_file"; then
        print_status "ID format: Valid (exp_YYYYMMDD_name)"
        ((passed++))
    else
        print_error "ID format: Invalid or missing"
        ((failed++))
    fi

    # Check 2: Hypothesis exists and is specific (at least 20 chars of content)
    local hypothesis_line=$(grep "hypothesis:" "$spec_file" | head -1)
    if [[ -n "$hypothesis_line" ]] && [[ ${#hypothesis_line} -gt 30 ]]; then
        print_status "Hypothesis: Present and substantive"
        ((passed++))
    else
        print_error "Hypothesis: Missing or too short"
        ((failed++))
    fi

    # Check 3: Target size is positive
    if grep -qE "size: [1-9][0-9]*" "$spec_file"; then
        print_status "Target size: Positive integer"
        ((passed++))
    else
        print_error "Target size: Missing or invalid"
        ((failed++))
    fi

    # Check 4: Real template (no obvious placeholders)
    if grep -q "template:" "$spec_file" && ! grep -qE "\[INSERT|\[PLACEHOLDER|\{\{PLACEHOLDER" "$spec_file"; then
        print_status "Template: Contains real content (no placeholders)"
        ((passed++))
    else
        print_error "Template: Missing or contains placeholders"
        ((failed++))
    fi

    # Check 5: Metrics defined
    if grep -q "metrics:" "$spec_file" && grep -q "name:" "$spec_file"; then
        print_status "Metrics: Defined"
        ((passed++))
    else
        print_error "Metrics: Not defined"
        ((failed++))
    fi

    # Check 6: Success criteria present
    if grep -qE "success_criteria:" "$spec_file"; then
        print_status "Success criteria: Present"
        ((passed++))
    else
        print_error "Success criteria: Missing"
        ((failed++))
    fi

    # Check 7: Failure criteria present (guardrails)
    if grep -qE "failure_criteria:" "$spec_file"; then
        print_status "Failure criteria: Present (guardrails defined)"
        ((passed++))
    else
        print_error "Failure criteria: Missing (no guardrails!)"
        ((failed++))
    fi

    # Check 8: Valid schedule
    if grep -qE 'schedule: "[0-9*/ ]+ [0-9*/ ]+ [0-9*/ ]+ [0-9*/ ]+ [0-9*A-Z,/]+"' "$spec_file"; then
        print_status "Schedule: Valid cron expression"
        ((passed++))
    else
        print_warning "Schedule: Could not validate cron format"
    fi

    echo ""
    echo "Results: $passed passed, $failed failed"

    if [[ $failed -eq 0 ]]; then
        print_status "All quality checks passed!"
        return 0
    else
        print_error "Some checks failed"
        return 1
    fi
}

# Validate YAML syntax
validate_yaml() {
    local spec_file="$1"

    print_header "YAML Validation"

    if [[ ! -f "$spec_file" ]]; then
        print_error "File not found: $spec_file"
        return 1
    fi

    # Check if python is available for YAML validation
    if command -v python3 &> /dev/null; then
        if python3 -c "import yaml; yaml.safe_load(open('$spec_file'))" 2>/dev/null; then
            print_status "YAML syntax: Valid"
            return 0
        else
            print_error "YAML syntax: Invalid"
            python3 -c "import yaml; yaml.safe_load(open('$spec_file'))" 2>&1 | head -5
            return 1
        fi
    else
        print_warning "Python3 not available for YAML validation"
        return 0
    fi
}

# Run all tests
test_all() {
    echo "Running all FULLSEND tests..."
    echo ""
    echo "Note: Tests 1 and 2 prepare test requests."
    echo "You must manually run './run.sh' to execute FULLSEND."
    echo ""

    test_basic
    echo ""

    test_tool_request
    echo ""

    # Quality check on example specs
    print_header "Quality Check: Example Specs"
    for spec in "$EXPERIMENTS_DIR"/examples/*.yaml; do
        if [[ -f "$spec" ]]; then
            echo "---"
            test_quality "$spec"
        fi
    done
}

# Show usage
show_usage() {
    echo "FULLSEND Test Plan"
    echo ""
    echo "Usage: $0 <command> [args]"
    echo ""
    echo "Commands:"
    echo "  basic              Set up basic test request (GitHub stargazers)"
    echo "  tool               Set up tool request test (HN scraper)"
    echo "  quality [file]     Run quality checks on spec (default: example spec)"
    echo "  validate <file>    Validate YAML syntax"
    echo "  all                Run all tests"
    echo ""
    echo "Examples:"
    echo "  $0 basic                    # Set up basic test request"
    echo "  $0 quality                  # Check example spec quality"
    echo "  $0 quality experiments/my_spec.yaml"
    echo "  $0 validate experiments/my_spec.yaml"
    echo ""
    echo "Test Flow:"
    echo "  1. Run '$0 basic' to set up test request"
    echo "  2. Run '../run.sh' to execute FULLSEND"
    echo "  3. Run '$0 quality experiments/exp_test_*.yaml' to verify output"
}

# Main
case "${1:-}" in
    basic)
        test_basic
        ;;
    tool)
        test_tool_request
        ;;
    quality)
        test_quality "${2:-}"
        ;;
    validate)
        validate_yaml "${2:-}"
        ;;
    all)
        test_all
        ;;
    *)
        show_usage
        ;;
esac
