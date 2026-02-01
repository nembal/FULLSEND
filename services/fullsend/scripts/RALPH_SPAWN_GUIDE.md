# RALPH Spawn Guide for FULLSEND

FULLSEND can spawn RALPH loops for complex multi-step tasks that are too involved
for a single Claude Code session. This guide documents when and how to use them.

## When to Spawn a RALPH Loop

Spawn a RALPH loop when a task requires:

1. **Multiple distinct steps** that build on each other
2. **Significant context** that needs to persist across steps
3. **Complex building** (e.g., creating a new tool with multiple components)
4. **Research followed by implementation** (multi-phase work)

### Examples of RALPH-worthy tasks:

- Building a complete scraper tool with rate limiting, caching, and error handling
- Creating a multi-step data pipeline
- Implementing a feature that requires research, design, and implementation phases
- Complex experiment setup requiring multiple API integrations

### DON'T spawn RALPH for:

- Simple experiment design (just write the YAML)
- Single API calls or simple scripts
- Tool requests (just write the tool request YAML)
- Any task that can be done in one Claude Code session

## How to Spawn a RALPH Loop

### Option 1: Automatic (Recommended)

Use the `spawn` command with a goal description:

```bash
# From services/fullsend/ directory
./ralph.sh spawn "Build a GitHub stargazer scraper tool with rate limiting and email extraction"
```

This will:
1. Create a unique work directory in `/tmp/fullsend_YYYYMMDD_HHMMSS_xxxx/`
2. Generate a `TASKS.md` with appropriate tasks
3. Create a `STATUS.md` with context
4. Run the RALPH loop until all tasks complete

### Option 2: Manual Setup

For more control over the task breakdown:

```bash
# 1. Create work directory
WORK_DIR="/tmp/fullsend_build_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$WORK_DIR"

# 2. Write TASKS.md with your specific tasks
cat > "$WORK_DIR/TASKS.md" << 'EOF'
# Tasks

Context:
- Goal: Build a GitHub stargazer scraper tool
- Work dir: /tmp/fullsend_build_20240115_143000

- [ ] TASK-001: Research GitHub API rate limits, authentication, and pagination
- [ ] TASK-002: Create the base scraper module with rate limiting
- [ ] TASK-003: Add email extraction from user profiles and commits
- [ ] TASK-004: Implement caching to avoid re-fetching
- [ ] TASK-005: Add error handling and partial result return
- [ ] TASK-006: Write unit tests
- [ ] TASK-007: Move final tool to /app/tools/ and test integration
EOF

# 3. Write STATUS.md with context
cat > "$WORK_DIR/STATUS.md" << 'EOF'
# RALPH Status - GitHub Stargazer Scraper

Stage: fullsend-spawn
State: IN_PROGRESS
Started: 2024-01-15T14:30:00-08:00

## Goal
Build a GitHub stargazer scraper tool that:
- Scrapes users who starred a given repo
- Extracts emails from profiles and commits
- Handles rate limiting gracefully
- Returns partial results on failure

## Requirements
- Must handle GitHub API rate limiting (5000 req/hr with token)
- Must paginate correctly for repos with many stars
- Must cache results to avoid re-scraping
- Return partial results on failure

## Progress Notes
- Loop initialized

## Files Changed
(To be updated as tasks complete)
EOF

# 4. Run the RALPH loop
./ralph.sh "$WORK_DIR"
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RALPH_MAX_ITERS` | 50 | Maximum iterations before giving up |

## Work Directory Structure

After spawning, the work directory contains:

```
/tmp/fullsend_20240115_143000_a1b2/
├── TASKS.md      # Task list (RALPH updates this)
├── STATUS.md     # Status/memory file (RALPH updates this)
└── ...           # Any files created during the tasks
```

## Monitoring a RALPH Loop

The loop outputs progress to stdout:

```
════════════════════════════════════════════
  RALPH ITERATION 1 / 50
  Task: TASK-001 (0/5 done)
  Work dir: /tmp/fullsend_20240115_143000_a1b2
════════════════════════════════════════════

[RALPH] ✅ TASK-001 complete
...
```

## Completion

When all tasks complete:

```
════════════════════════════════════════════
  ✅ ALL TASKS COMPLETE! (5/5)
════════════════════════════════════════════

[RALPH] Done.
```

The `STATUS.md` will be updated to `State: COMPLETE`.

## Retrieving Results

After completion, check:

1. `STATUS.md` - Summary of what was done
2. Any output files in the work directory
3. Files moved to their final locations (e.g., `/app/tools/`)

## Examples

### Example 1: Build a Tool

```bash
./ralph.sh spawn "Build a LinkedIn profile enricher tool using Browserbase"
```

RALPH will:
1. Research LinkedIn scraping approaches and Browserbase API
2. Create the base enricher module
3. Implement session management and rate limiting
4. Add data extraction and normalization
5. Test and integrate

### Example 2: Complex Pipeline

```bash
./ralph.sh spawn "Build a lead gen pipeline: scrape GitHub stars → enrich with LinkedIn → filter CTOs → prepare for email"
```

RALPH will break this into discrete tasks for each stage.

### Example 3: Research + Build

```bash
./ralph.sh spawn "Research Product Hunt API and build a maker scraper tool"
```

RALPH will:
1. Research Product Hunt API/scraping options
2. Document findings
3. Implement the scraper
4. Test and validate

## Integration with FULLSEND

In your FULLSEND Claude Code session, when you encounter a complex task:

```bash
# Example: In FULLSEND, when you need to build a tool

# Check if the tool exists first
redis-cli -u $REDIS_URL GET tools:github_stargazer_scraper

# If it doesn't exist and you need it, spawn a RALPH loop to build it
./ralph.sh spawn "Build a GitHub stargazer scraper tool with rate limiting, pagination, and email extraction from profiles/commits"

# After completion, the tool will be available
# You can then reference it in your experiment spec
```

## Troubleshooting

### Loop times out (hits max iterations)

Increase `RALPH_MAX_ITERS` or break the goal into smaller sub-goals.

### Task keeps failing

Check the `STATUS.md` for error notes. The task may be:
- Too vague (make it more specific)
- Dependent on unavailable resources
- Too large (break it down further)

### No TASK_DONE signal

The Claude Code session may have:
- Timed out
- Encountered an unrecoverable error
- Forgotten to output TASK_DONE

Check the loop output for details.
