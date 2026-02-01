# Skill and System Prompt Management

This document explains how Claude Code skills work, how FULLSEND can create its own skills, and how to update system prompts across all services.

## Part 1: How Claude Code Skills Work

### What Are Skills?

Skills are reusable instruction sets that Claude Code can invoke. They're defined as markdown files with YAML frontmatter and stored in `.claude/skills/`.

### Skill File Structure

```
.claude/skills/
├── brainstorming/
│   └── SKILL.md
├── task-writing/
│   └── SKILL.md
└── {skill-name}/
    └── SKILL.md
```

### SKILL.md Format

```markdown
---
name: skill-name
description: "Brief description shown when skill is available"
---

# Skill Title

## Overview
What this skill does and when to use it.

## The Process
Step-by-step instructions...

## Examples
Concrete examples...
```

### How Skills Are Invoked

1. **User invokes**: `/skill-name` in conversation
2. **Claude invokes**: Via the Skill tool when appropriate
3. **Auto-suggested**: Claude Code shows available skills in system reminders

### Creating a New Skill

```bash
# 1. Create skill directory
mkdir -p .claude/skills/my-new-skill

# 2. Write SKILL.md
cat > .claude/skills/my-new-skill/SKILL.md << 'EOF'
---
name: my-new-skill
description: "Use when X happens to do Y"
---

# My New Skill

## When to Use
...

## The Process
...
EOF
```

The skill is immediately available - no restart or registration needed.

---

## Part 2: FULLSEND Creating Its Own Skills

### Can FULLSEND Create Skills? YES!

FULLSEND runs as Claude Code with full file system access. It can:
1. Create new skill directories in `.claude/skills/`
2. Write SKILL.md files with new instructions
3. Reference its own skills in future sessions

### Self-Improvement Pattern

FULLSEND can evolve its own capabilities:

```
┌─────────────────────────────────────────────────────────────────┐
│  FULLSEND notices a recurring pattern or need                   │
│                           │                                     │
│                           ▼                                     │
│  FULLSEND creates a new skill:                                  │
│    mkdir -p .claude/skills/validate-experiment                  │
│    Write SKILL.md with validation checklist                     │
│                           │                                     │
│                           ▼                                     │
│  Future FULLSEND sessions can use /validate-experiment          │
└─────────────────────────────────────────────────────────────────┘
```

### Example: FULLSEND Creating a Skill

```bash
# FULLSEND executing this in a session:

mkdir -p .claude/skills/validate-experiment

cat > .claude/skills/validate-experiment/SKILL.md << 'EOF'
---
name: validate-experiment
description: "Use before publishing an experiment to verify it meets all requirements"
---

# Validate Experiment Spec

## Checklist
Before publishing, verify:
- [ ] Hypothesis is specific and testable
- [ ] Target size is realistic (< 1000 for first run)
- [ ] Metrics have clear success thresholds
- [ ] Template has no {{placeholders}} - all content is real
- [ ] Schedule is set (cron expression valid)
- [ ] Required tool exists (check Redis tools:*)

## Publishing
Only after all checks pass, run:
./scripts/redis_publish.sh publish_experiment_full experiments/{id}.yaml
EOF
```

### Skills FULLSEND Should Create

| Skill | Purpose |
|-------|---------|
| `/validate-experiment` | Pre-publish validation checklist |
| `/task-writing` | Writing TASKS.md for Builder (created) |
| `/tool-request` | Writing PRDs for Builder |
| `/analyze-results` | Interpreting experiment metrics |
| `/iterate-hypothesis` | Learning from failures |

---

## Part 3: System Prompt Locations

### All System Prompts in the Codebase

| Service | Location | Purpose |
|---------|----------|---------|
| **FULLSEND** | `services/fullsend/prompts/system.txt` | Experiment designer persona |
| **Builder** | `services/builder/prompts/system.txt` | Tool factory persona |
| **Orchestrator** | `services/orchestrator/prompts/system.txt` | Strategic manager |
| **Orchestrator** | `services/orchestrator/prompts/dispatch.txt` | Task dispatch logic |
| **Orchestrator** | `services/orchestrator/prompts/learn.txt` | Learning extraction |
| **Watcher** | `services/watcher/prompts/classify.txt` | Message classification |
| **Watcher** | `services/watcher/prompts/respond.txt` | Simple responses |
| **Redis Agent** | `services/redis_agent/prompts/analyze.txt` | Metrics analysis |
| **Redis Agent** | `services/redis_agent/prompts/summarize.txt` | Summary generation |
| **Roundtable** | `services/roundtable/personas/artist.txt` | Creative persona |
| **Roundtable** | `services/roundtable/personas/business.txt` | Business persona |
| **Roundtable** | `services/roundtable/personas/tech.txt` | Technical persona |
| **Roundtable** | `services/roundtable/personas/summarizer.txt` | Synthesis persona |

### Template Variables in Prompts

Prompts can include template variables filled at runtime:

| Variable | Filled By | Used In |
|----------|-----------|---------|
| `{{available_tools}}` | Redis lookup | FULLSEND |
| `{{recent_learnings}}` | Redis lookup | FULLSEND, Orchestrator |
| `{{product_context}}` | Config | Orchestrator |
| `{{worklist}}` | Redis | Orchestrator |
| `{{experiments_summary}}` | Redis | Orchestrator |
| `{{metrics_summary}}` | Redis | Redis Agent |

---

## Part 4: Updating System Prompts

### Method 1: Direct File Edit

The simplest approach - just edit the file:

```bash
# Edit FULLSEND's system prompt
vim services/fullsend/prompts/system.txt

# Changes take effect on next service run
./services/fullsend/run.sh
```

### Method 2: Via RALPH Loop

For complex prompt updates that need iteration:

```bash
./RALPH/ralph.sh spawn "Update FULLSEND system prompt to include new Redis channels documentation"
```

### Method 3: Programmatic Updates

For services that load prompts dynamically:

```python
# In services/orchestrator/agent.py
def load_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    return path.read_text()

# Template filling
prompt = load_prompt("system.txt")
prompt = prompt.replace("{{available_tools}}", get_tools_from_redis())
```

### Updating Multiple Services

When making cross-cutting changes (like adding a new Redis channel):

```bash
# 1. Update the source of truth
vim docs/architecture/REDIS_CHANNELS.md

# 2. Update each service's prompts that reference channels
vim services/fullsend/prompts/system.txt
vim services/builder/prompts/system.txt
vim services/orchestrator/prompts/system.txt

# 3. Grep to verify consistency
grep -r "fullsend:" services/*/prompts/
```

### Prompt Update Checklist

When updating a service's system prompt:

- [ ] Read the current prompt fully
- [ ] Make targeted changes (don't rewrite unless necessary)
- [ ] Verify template variables still present if used
- [ ] Test the service after update
- [ ] Update docs if behavior changed
- [ ] Commit with descriptive message

---

## Part 5: Architecture Notes

### Why Skills vs System Prompts?

| Aspect | Skills | System Prompts |
|--------|--------|----------------|
| **Scope** | Cross-cutting capabilities | Service-specific identity |
| **Invocation** | On-demand via `/skill` | Always loaded at start |
| **Creation** | Any Claude Code session | Usually human-authored |
| **Location** | `.claude/skills/` | `services/*/prompts/` |

### The Self-Improving FULLSEND Pattern

```
┌────────────────────────────────────────────────────────────────┐
│                      FULLSEND Evolution                         │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Session N: FULLSEND encounters a new pattern                   │
│      ↓                                                          │
│  Session N: Creates a skill to handle that pattern              │
│      ↓                                                          │
│  Session N+1: Uses the skill, refines it if needed              │
│      ↓                                                          │
│  Session N+2: Skill becomes stable, always available            │
│                                                                 │
│  Over time: FULLSEND accumulates domain expertise as skills     │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### Skill Discovery

Claude Code auto-discovers skills from `.claude/skills/`. The discovery happens at conversation start - skills created mid-conversation may need a new session to appear in suggestions.

### Cross-Service Skill Sharing

Skills in `.claude/skills/` are available to ALL Claude Code sessions in the repo:
- FULLSEND sessions
- Builder sessions
- Manual `claude` CLI sessions
- RALPH loop iterations

This means FULLSEND's skills help Builder, and vice versa.

---

## Quick Reference

### Create a New Skill

```bash
mkdir -p .claude/skills/{skill-name}
cat > .claude/skills/{skill-name}/SKILL.md << 'EOF'
---
name: {skill-name}
description: "{when to use}"
---

# {Title}

{content}
EOF
```

### Find All Prompts

```bash
find services -name "*.txt" -path "*/prompts/*"
find services -name "*.txt" -path "*/personas/*"
```

### Update a Prompt

```bash
vim services/{service}/prompts/{prompt}.txt
# Test by running the service
./services/{service}/run.sh
```

### List All Skills

```bash
ls -la .claude/skills/*/SKILL.md
```
