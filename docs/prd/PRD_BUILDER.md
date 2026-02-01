# PRD: Builder

## Overview

**Role:** The tool factory — receives PRDs from FULLSEND or Orchestrator, builds working tools, tests them, commits to repo.

**Runtime:** Claude Code instance triggered by task queue (NOT a wrapper — Builder IS Claude Code)
**Model:** Claude Sonnet/Opus via Claude Code CLI
**Container:** `fullsend-builder`

---

## Architecture: Builder IS Claude Code

Like FULLSEND, Builder is a Claude Code instance — not a Python wrapper.

```
┌─────────────────────────────────────────────────────────────┐
│                   Builder = Claude Code                      │
│                                                              │
│  Triggered by: PRD file in requests/                         │
│                                                              │
│  Does:                                                       │
│  • Reads PRD specification                                   │
│  • Builds Python tool in tools/                              │
│  • Tests the tool works                                      │
│  • Commits to repo (YOLO mode)                               │
│  • Registers in Redis                                        │
│                                                              │
│  Uses RALPH loops for complex multi-file tools               │
└─────────────────────────────────────────────────────────────┘
```

### How to Run Builder

```bash
# Triggered when PRD appears in requests/
./services/builder/run.sh
```

Or Orchestrator writes PRD and runs the command.

---

## Personality

Methodical. Thorough. Quality-focused. Ships working code. Tests before committing. Handles errors gracefully.

---

## What It Does

1. **Reads PRD** from `requests/current_prd.yaml`
2. **Builds Python tool** in `tools/` directory
3. **Tests the tool** (basic smoke test)
4. **Commits to repo** (git add, commit, push)
5. **Registers in Redis** (`tools:{name}`)
6. **Reports completion** to Orchestrator

## What It Does NOT Do

- Design experiments (that's FULLSEND)
- Decide what tools to build (that's Orchestrator/FULLSEND)
- Run experiments (that's Executor)

---

## File Structure

```
services/builder/
├── run.sh                # Launches Claude Code
├── prompts/
│   └── system.txt        # System prompt for Builder
├── requests/             # Incoming PRDs
│   └── current_prd.yaml  # Current tool PRD
├── templates/            # Tool templates
│   └── tool_template.py  # Base template for tools
└── status/
    ├── TASKS.md          # For RALPH loops
    └── STATUS.md         # Memory
```

### run.sh (Entry Point)

```bash
#!/bin/bash
# Launch Builder (which IS Claude Code)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SYSTEM_PROMPT=$(cat "$SCRIPT_DIR/prompts/system.txt")

cd "$REPO_ROOT"

claude -p "$SYSTEM_PROMPT

## Current PRD
$(cat "$SCRIPT_DIR/requests/current_prd.yaml" 2>/dev/null || echo "No PRD pending")

## Existing Tools (for reference)
$(ls -la tools/*.py 2>/dev/null || echo "No tools yet")
" --allowedTools "Edit,Bash,Write,Read,Glob,Grep" \
  --dangerously-skip-permissions
```

---

## PRD Format (Input)

```yaml
prd:
  id: tool_github_scraper
  name: github_stargazer_scraper
  description: "Scrape users who starred a GitHub repo"
  requested_by: fullsend
  priority: high

  inputs:
    - name: repo
      type: string
      description: "owner/repo format"
      required: true
    - name: limit
      type: integer
      description: "Max users to return"
      default: 100

  outputs:
    - name: users
      type: list
      schema:
        username: string
        email: "string | null"
        company: "string | null"

  requirements:
    - Must handle GitHub API rate limiting
    - Must paginate correctly
    - Return partial results on failure

  example_usage: |
    from tools.github_stargazer_scraper import scrape_stargazers
    users = scrape_stargazers(repo="anthropics/claude", limit=100)
```

---

## Tool Output Format

Tools must follow this contract:

```python
# tools/github_stargazer_scraper.py
"""
GitHub Stargazer Scraper

Scrapes users who starred a GitHub repo.
Built by Builder from PRD: tool_github_scraper
"""

import requests
from typing import Optional

def github_stargazer_scraper(
    repo: str,
    limit: int = 100,
    github_token: Optional[str] = None
) -> dict:
    """
    Scrape users who starred a GitHub repo.

    Args:
        repo: Repository in owner/repo format
        limit: Maximum users to return (default 100)
        github_token: Optional GitHub token for higher rate limits

    Returns:
        dict with:
            - users: List of user dicts with username, email, company
            - count: Number of users returned
            - success: Boolean indicating success
            - error: Error message if any
    """
    users = []

    try:
        # Implementation here...

        return {
            "users": users,
            "count": len(users),
            "success": True,
            "error": None
        }

    except Exception as e:
        return {
            "users": users,  # Return partial results
            "count": len(users),
            "success": False,
            "error": str(e)
        }

# For Executor compatibility
run = github_stargazer_scraper
```

---

## Core Logic

### System Prompt (prompts/system.txt)

```
You are Builder, the tool factory for the Fullsend GTM system.

## Your Role
You receive PRDs (Product Requirement Documents) and build working Python tools.
You are methodical, thorough, and quality-focused.

## Your Process

1. **Read the PRD** — Understand inputs, outputs, requirements
2. **Plan the implementation** — What APIs? What error handling?
3. **Write the tool** — Clean Python in tools/{name}.py
4. **Test the tool** — Run a basic smoke test
5. **Commit to repo** — git add, commit with descriptive message
6. **Register in Redis** — Store metadata for Executor

## Tool Contract

All tools must:
- Have a main function matching the filename
- Also export a `run` alias for Executor
- Accept inputs as keyword arguments
- Return a dict with: result data, success boolean, error message
- Handle errors gracefully (return partial results)
- Include docstrings and type hints

## Output Location
Write tools to: /app/tools/{tool_name}.py

## Git Workflow
After writing and testing:
```bash
git add tools/{tool_name}.py
git commit -m "Add {tool_name} tool - {brief description}"
```

## Redis Registration
```bash
redis-cli HSET tools:{tool_name} \
    name "{tool_name}" \
    description "{description}" \
    path "tools/{tool_name}.py" \
    status "active" \
    created_at "$(date -Iseconds)"
```

## When Done
Output: **BUILD_COMPLETE**
Include: tool name, file path, test results
```

---

## RALPH Loops (for complex tools)

For multi-file or complex tools, Builder can spawn a RALPH loop:

```bash
# Inside Builder (Claude Code):

mkdir -p /tmp/builder_001

cat > /tmp/builder_001/TASKS.md << 'EOF'
# Tasks

- [ ] TASK-001: Research the API (GitHub, etc.)
- [ ] TASK-002: Write the core scraping logic
- [ ] TASK-003: Add pagination support
- [ ] TASK-004: Add rate limiting / retry logic
- [ ] TASK-005: Write error handling
- [ ] TASK-006: Add basic tests
- [ ] TASK-007: Commit and register
EOF

cat > /tmp/builder_001/STATUS.md << 'EOF'
# Status

## PRD
{paste PRD here}

## Progress
Starting build...
EOF

cd /tmp/builder_001 && /app/RALPH/ralph.sh
```

---

## Testing

Builder should run basic tests before committing:

```bash
# Test the tool works
python -c "
from tools.github_stargazer_scraper import github_stargazer_scraper
result = github_stargazer_scraper(repo='octocat/Hello-World', limit=5)
print(f'Success: {result[\"success\"]}')
print(f'Got {result[\"count\"]} users')
assert 'users' in result
assert 'success' in result
print('TESTS PASSED')
"
```

---

## Acceptance Criteria

- [ ] `run.sh` launches Claude Code with system prompt
- [ ] Reads PRD from `requests/current_prd.yaml`
- [ ] Creates working Python tool in `tools/`
- [ ] Tool follows the contract (inputs, outputs, error handling)
- [ ] Runs basic smoke test before committing
- [ ] Commits to git with descriptive message
- [ ] Registers tool in Redis (`tools:{name}`)
- [ ] Can use RALPH loops for complex builds
- [ ] Outputs BUILD_COMPLETE when done
- [ ] Handles build failures gracefully

---

## Test Plan

### Basic Test
```bash
# Write a simple PRD
cat > services/builder/requests/current_prd.yaml << 'EOF'
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

# Run Builder
./services/builder/run.sh

# Verify tool was created
cat tools/hello_world.py

# Verify it works
python -c "from tools.hello_world import hello_world; print(hello_world())"

# Verify Redis registration
redis-cli HGETALL tools:hello_world
```

### Complex Tool Test
```bash
# PRD requiring external API
cat > services/builder/requests/current_prd.yaml << 'EOF'
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

./services/builder/run.sh

# Check tool
python -c "from tools.website_scraper import website_scraper; print(website_scraper(url='https://example.com'))"
```

---

## Dockerfile

```dockerfile
FROM python:3.11-slim

# Install Claude Code CLI
RUN curl -fsSL https://claude.ai/install.sh | sh

# Install git
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Git config for commits
RUN git config --global user.email "builder@fullsend.ai" && \
    git config --global user.name "Fullsend Builder"

COPY services/builder/ ./services/builder/
COPY tools/ ./tools/
COPY RALPH/ ./RALPH/

# Mount points
VOLUME /app/tools
VOLUME /app/.git

CMD ["./services/builder/run.sh"]
```

---

## Notes for Builder

- **Builder IS Claude Code** — not a Python wrapper
- Main deliverable: working Python tools in `tools/`
- Always test before committing
- Error handling is critical — tools must not crash Executor
- Return partial results on failure
- Use descriptive commit messages
- Register in Redis so Executor can find tools
- For complex tools, use RALPH loops
- Check existing tools for patterns/style
