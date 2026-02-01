# FULLSEND Test Plan

This directory contains the test plan from PRD section "Test Plan" (lines 562-624).

## Quick Start

```bash
# Run all quality checks on example specs
./test_plan.sh all

# Set up basic test request
./test_plan.sh basic
../run.sh  # Run FULLSEND
./test_plan.sh quality ../experiments/exp_test_github_stars.yaml

# Set up tool request test
./test_plan.sh tool
../run.sh  # Run FULLSEND
# Check for both experiment spec and tool request in output
```

## Test Cases

### Test 1: Basic Experiment Request
**Purpose:** Verify FULLSEND can design a complete experiment from a simple request.

**Input:** `fixtures/request_basic.md`
- Simple idea: Scrape GitHub stargazers and email CTOs
- Available tools listed
- Clear output location

**Expected Output:**
- Valid YAML experiment spec at `experiments/exp_test_github_stars.yaml`
- Spec includes all required fields
- Real email template (not placeholders)

**Run:**
```bash
./test_plan.sh basic   # Sets up request
../run.sh              # Runs FULLSEND
./test_plan.sh quality ../experiments/exp_test_github_stars.yaml
```

### Test 2: Tool Request Test
**Purpose:** Verify FULLSEND requests new tools when needed.

**Input:** `fixtures/request_tool_needed.md`
- Idea requires scraping Hacker News
- No HN scraper tool available
- Should output both experiment spec AND tool request

**Expected Output:**
- Experiment spec at `experiments/exp_test_hn_hiring.yaml`
- Tool request for `hn_job_scraper` tool
- Tool request includes inputs, outputs, requirements

**Run:**
```bash
./test_plan.sh tool    # Sets up request
../run.sh              # Runs FULLSEND
# Verify both experiment spec and tool request in output
```

### Test 3: RALPH Loop Spawn Test
**Purpose:** Verify FULLSEND can spawn RALPH loops for complex tasks.

**Input:** `fixtures/request_ralph_spawn.md`
- Complex multi-step pipeline
- Requires building multiple components
- Should spawn RALPH loop

**Expected Output:**
- RALPH loop spawned at `/tmp/fullsend_*/`
- TASKS.md created with breakdown
- STATUS.md created with context

**Run:**
```bash
cp fixtures/request_ralph_spawn.md ../requests/current.md
../run.sh
ls /tmp/fullsend_*/   # Check RALPH loop was created
```

### Test 4: Quality Checks
**Purpose:** Verify experiment specs meet quality standards.

**Checks:**
1. ID format: `exp_YYYYMMDD_short_name`
2. Hypothesis: 20-500 chars, specific testable claim
3. Target size: Positive integer
4. Template: Real content (no placeholders)
5. Metrics: At least sent/rate metrics
6. Success criteria: At least one condition
7. Failure criteria: At least one guardrail
8. Schedule: Valid cron expression

**Run:**
```bash
./test_plan.sh quality                    # Check default example
./test_plan.sh quality path/to/spec.yaml  # Check specific spec
```

## Test Fixtures

| File | Description |
|------|-------------|
| `fixtures/request_basic.md` | Simple GitHub stargazers experiment |
| `fixtures/request_tool_needed.md` | Request requiring new tool |
| `fixtures/request_ralph_spawn.md` | Complex multi-step pipeline |

## Quality Checklist

From PRD section "Quality Check" (lines 617-624):

- [ ] Specific target audience (not generic)
- [ ] Real email template (actual copy, not placeholders)
- [ ] Measurable metrics with thresholds
- [ ] Clear success/failure criteria
- [ ] Valid cron schedule

## Validation Commands

```bash
# Validate YAML syntax
./test_plan.sh validate ../experiments/my_spec.yaml

# Run quality checks
./test_plan.sh quality ../experiments/my_spec.yaml

# Check all example specs
./test_plan.sh all
```

## Manual Testing

For full end-to-end testing:

1. **Start fresh:**
   ```bash
   # Clear any existing test outputs
   rm -f ../experiments/exp_test_*.yaml
   ```

2. **Run basic test:**
   ```bash
   ./test_plan.sh basic
   cd .. && ./run.sh
   # FULLSEND will design experiment interactively
   ```

3. **Verify output:**
   ```bash
   ./test_plan.sh quality ../experiments/exp_test_github_stars.yaml
   ```

4. **Check Redis (if configured):**
   ```bash
   redis-cli -u $REDIS_URL GET experiments:exp_test_github_stars
   ```

## Expected Behavior

### When No Request Pending
If `requests/current.md` contains only "No request pending" (or is empty):
- FULLSEND should report no work to do
- Should not output any experiment spec

### When Tool Missing
If the request requires a tool that's not available:
- FULLSEND should still design the experiment
- FULLSEND should also output a tool request YAML
- The experiment can be marked as "blocked" pending tool build

### When Task is Complex
If the request requires multiple steps or builds:
- FULLSEND should recognize the complexity
- FULLSEND should spawn a RALPH loop with TASKS.md
- RALPH loop should execute the build step by step
