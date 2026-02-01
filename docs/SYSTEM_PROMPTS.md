# System Prompt Locations

Quick reference for all system prompts and personas in the Fullsend GTM agent system.

## Claude Code Services (RALPH Loop Runners)

These services run as Claude Code instances with system prompts:

| Service | Prompt File | Model | Purpose |
|---------|-------------|-------|---------|
| **FULLSEND** | `services/fullsend/prompts/system.txt` | Claude Opus 4 | Experiment designer, creative strategist |
| **Builder** | `services/builder/prompts/system.txt` | Claude Opus 4 | Tool factory, builds Python tools from PRDs |

## Python Services (LLM API Callers)

These services call LLM APIs with prompts:

| Service | Prompt Files | Model | Purpose |
|---------|--------------|-------|---------|
| **Orchestrator** | `services/orchestrator/prompts/system.txt` | Claude Opus 4 | Strategic decision maker |
| | `services/orchestrator/prompts/dispatch.txt` | | Task dispatch logic |
| | `services/orchestrator/prompts/learn.txt` | | Learning extraction |
| **Watcher** | `services/watcher/prompts/classify.txt` | Gemini Flash | Message classification |
| | `services/watcher/prompts/respond.txt` | | Simple response generation |
| **Redis Agent** | `services/redis_agent/prompts/analyze.txt` | Gemini Flash | Metrics analysis |
| | `services/redis_agent/prompts/summarize.txt` | | Summary generation |

## Roundtable Personas

Multi-agent debate system with specialized personas:

| Persona | File | Role |
|---------|------|------|
| Artist | `services/roundtable/personas/artist.txt` | Creative, unconventional ideas |
| Business | `services/roundtable/personas/business.txt` | ROI, market fit, scaling |
| Tech | `services/roundtable/personas/tech.txt` | Feasibility, implementation |
| Summarizer | `services/roundtable/personas/summarizer.txt` | Synthesize debate into actionable output |

## Skills (Claude Code Instruction Sets)

Skills are invokable instruction sets available to all Claude Code sessions:

| Skill | File | Purpose |
|-------|------|---------|
| brainstorming | `.claude/skills/brainstorming/SKILL.md` | Explore ideas before implementation |
| task-writing | `.claude/skills/task-writing/SKILL.md` | Write TASKS.md for Builder RALPH loops |

## Template Variables

Prompts may include template variables filled at runtime:

| Variable | Filled By | Used In |
|----------|-----------|---------|
| `{{available_tools}}` | Redis `tools:*` lookup | FULLSEND |
| `{{recent_learnings}}` | Redis `learnings:*` lookup | FULLSEND, Orchestrator |
| `{{product_context}}` | Config/env | Orchestrator |
| `{{worklist}}` | Redis worklist | Orchestrator |
| `{{experiments_summary}}` | Redis experiments | Orchestrator |
| `{{metrics_summary}}` | Redis metrics | Redis Agent |

## How to Update Prompts

### Direct Edit
```bash
vim services/{service}/prompts/{prompt}.txt
```

### Verify Changes
```bash
# Find all prompts
find services -name "*.txt" -path "*/prompts/*"
find services -name "*.txt" -path "*/personas/*"

# Check for a specific term across all prompts
grep -r "your_term" services/*/prompts/
```

### After Updating
- Restart the service to pick up changes
- For Claude Code services (FULLSEND, Builder): next `run.sh` invocation uses new prompt
- For Python services: restart the service process

## Adding New Prompts

1. Create the prompt file in the service's `prompts/` directory
2. Update the service code to load and use the prompt
3. Add the prompt to this reference file
4. Document any template variables used

## See Also

- `docs/architecture/SKILL_AND_PROMPT_MANAGEMENT.md` - Full documentation on skills and prompt management
- `SYSTEM_COMPONENTS.md` - Overall system architecture
