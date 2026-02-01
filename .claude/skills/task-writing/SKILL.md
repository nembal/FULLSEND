---
name: task-writing
description: "Use this skill when writing TASKS.md for Builder RALPH loops. Ensures tasks are properly scoped, ordered, and actionable for autonomous execution."
---

# Writing Excellent TASKS.md for Builder RALPH Loops

## Overview

When FULLSEND decides to build a tool, it spawns a RALPH loop for Builder. The quality of the TASKS.md directly determines whether the RALPH loop succeeds or fails. This skill teaches you how to write tasks that Builder's Claude Code instances can execute autonomously.

## The RALPH Loop Mental Model

Each task in TASKS.md will be executed by a **fresh Claude Code instance** that:
- Has NO memory of previous tasks (except via STATUS.md)
- Can only see: the task description, STATUS.md context, and the codebase
- Must complete autonomously without human intervention
- Must know exactly when it's "done"

This means each task must be **self-contained** and **verifiable**.

## Task Anatomy

```markdown
- [ ] TASK-001: [Action Verb] [Specific Target] [Measurable Outcome]
```

### Good Examples

```markdown
- [ ] TASK-001: Research GitHub API pagination and rate limits, document findings in STATUS.md
- [ ] TASK-002: Write core github_scraper function with pagination support in tools/github_scraper.py
- [ ] TASK-003: Add rate limiting (max 30 requests/minute) to github_scraper
- [ ] TASK-004: Run smoke test with octocat/Hello-World repo and verify dict return format
- [ ] TASK-005: Git commit and register tool in Redis
```

### Bad Examples

```markdown
- [ ] TASK-001: Set up the project  # Too vague - what does "set up" mean?
- [ ] TASK-002: Make it work  # No specificity
- [ ] TASK-003: Handle edge cases  # Which edge cases?
- [ ] TASK-004: Test thoroughly  # No concrete success criteria
```

## The 7 Rules of RALPH Tasks

### Rule 1: Start with Action Verbs

Every task starts with a concrete action:
- **Research** - Investigate APIs, docs, patterns
- **Write** - Create new code/files
- **Add** - Extend existing code with new functionality
- **Fix** - Resolve a specific issue
- **Run** - Execute tests/commands
- **Update** - Modify existing content
- **Commit** - Git operations

### Rule 2: One Logical Unit Per Task

Each task should do ONE thing. If you find yourself using "and" or "then", split the task.

**Too big:**
```markdown
- [ ] TASK-001: Write the scraper, add error handling, and test it
```

**Just right:**
```markdown
- [ ] TASK-001: Write core scraper function with basic API calls
- [ ] TASK-002: Add try/except error handling with partial result returns
- [ ] TASK-003: Run smoke test with test repo
```

### Rule 3: Include Success Criteria

The Claude Code instance needs to know when it's done. Include verification in the task or make it implicit.

**Implicit verification (code tasks):**
```markdown
- [ ] TASK-002: Write github_scraper in tools/github_scraper.py following Builder tool contract
```
(Success = file exists with correct structure)

**Explicit verification:**
```markdown
- [ ] TASK-004: Run smoke test, verify output is {result, success, error} dict format
```

### Rule 4: Reference Concrete Paths

Claude Code navigates by file paths. Be explicit.

**Vague:**
```markdown
- [ ] TASK-002: Write the tool
```

**Concrete:**
```markdown
- [ ] TASK-002: Write github_scraper function in tools/github_scraper.py
```

### Rule 5: Put Research First

If the task requires understanding external APIs, docs, or patterns, make research TASK-001.

```markdown
- [ ] TASK-001: Research LinkedIn API rate limits and auth flow, document in STATUS.md
- [ ] TASK-002: Write linkedin_enricher using researched approach
```

This puts knowledge into STATUS.md where future tasks can read it.

### Rule 6: End with Commit + Register

Builder's contract requires git commit and Redis registration. Make this the final task.

```markdown
- [ ] TASK-00N: Git add tools/{tool_name}.py, commit with message "Add {tool_name} tool - {description}", register in Redis with HSET tools:{tool_name}
```

### Rule 7: 4-8 Tasks is the Sweet Spot

- **< 4 tasks**: Probably too coarse, each task doing too much
- **4-8 tasks**: Good granularity for autonomous execution
- **> 8 tasks**: Consider if you're over-engineering or building multiple tools

## Task Templates by Tool Type

### Simple API Tool (4-5 tasks)

```markdown
# Tasks

Context:
- Tool: {tool_name}
- PRD: {brief description}
- Output: tools/{tool_name}.py

- [ ] TASK-001: Research {API} endpoints, auth, rate limits - document in STATUS.md
- [ ] TASK-002: Write core {tool_name} function with API calls in tools/{tool_name}.py
- [ ] TASK-003: Add error handling with partial result returns
- [ ] TASK-004: Run smoke test with realistic inputs, verify dict return format
- [ ] TASK-005: Git commit and Redis registration
```

### Complex Scraper Tool (6-8 tasks)

```markdown
# Tasks

Context:
- Tool: {tool_name}
- PRD: {brief description}
- Output: tools/{tool_name}.py

- [ ] TASK-001: Research {target} API/page structure, identify data extraction points
- [ ] TASK-002: Write core {tool_name} function with basic scraping logic
- [ ] TASK-003: Add pagination support (handle next_page tokens or page numbers)
- [ ] TASK-004: Add rate limiting (max N requests per minute)
- [ ] TASK-005: Add retry logic for transient failures (3 retries, exponential backoff)
- [ ] TASK-006: Add error handling returning partial results on failure
- [ ] TASK-007: Run smoke test with {test_target}, verify output format
- [ ] TASK-008: Git commit and Redis registration
```

### Multi-File Tool (7+ tasks)

```markdown
# Tasks

Context:
- Tool: {tool_name}
- PRD: {brief description}
- Output: tools/{tool_name}.py + tools/{tool_name}_utils.py

- [ ] TASK-001: Research {domain} patterns, plan module structure
- [ ] TASK-002: Write utility functions in tools/{tool_name}_utils.py
- [ ] TASK-003: Write main {tool_name} function importing utilities
- [ ] TASK-004: Add configuration handling (env vars or defaults)
- [ ] TASK-005: Add error handling and logging
- [ ] TASK-006: Run unit tests on utility functions
- [ ] TASK-007: Run integration smoke test on main function
- [ ] TASK-008: Git commit all files and Redis registration
```

## STATUS.md: The Memory Bridge

Each RALPH iteration reads STATUS.md for context. Structure it to help future tasks:

```markdown
# Status

## PRD Summary
Name: github_scraper
Description: Scrape GitHub stargazers with pagination
Inputs: repo (str), limit (int, optional)
Outputs: list of {username, profile_url, email}

## Research Findings
(TASK-001 will populate this)
- GitHub API: api.github.com/repos/{owner}/{repo}/stargazers
- Rate limit: 60/hr unauthenticated, 5000/hr with token
- Pagination: Link header with next page URL

## Implementation Notes
(Tasks will add notes here as they complete)

## Files Changed
(Track what was created/modified)
```

## Common Pitfalls

### Pitfall 1: Assuming Context
**Wrong:** "TASK-003: Continue building the scraper"
**Right:** "TASK-003: Add pagination to github_scraper in tools/github_scraper.py"

Each task must stand alone - the Claude Code instance doesn't remember what "continue" means.

### Pitfall 2: Vague Verification
**Wrong:** "TASK-004: Test the tool"
**Right:** "TASK-004: Run smoke test with repo='octocat/Hello-World', limit=5, verify returns dict with result, success, error keys"

### Pitfall 3: Missing Dependencies
If TASK-003 needs info from TASK-001, make sure TASK-001 writes that info to STATUS.md.

**Wrong:**
```markdown
- [ ] TASK-001: Research the API
- [ ] TASK-003: Implement using the API patterns  # What patterns? Where are they?
```

**Right:**
```markdown
- [ ] TASK-001: Research the API, document endpoints and auth in STATUS.md
- [ ] TASK-003: Implement using API patterns from STATUS.md research section
```

### Pitfall 4: Scope Creep
Each task should take ~1 Claude Code session. If you're describing multiple features or "and then also", split the task.

## Quick Reference Checklist

Before finalizing TASKS.md, verify:

- [ ] Every task starts with an action verb
- [ ] Every task references specific file paths
- [ ] Every task has clear done criteria
- [ ] Research tasks come before implementation
- [ ] Final task includes git commit + Redis registration
- [ ] Total task count is 4-8
- [ ] No task uses "continue" or assumes prior context
- [ ] STATUS.md context section matches task needs
