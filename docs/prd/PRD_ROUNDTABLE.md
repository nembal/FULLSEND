# PRD: Roundtable

## Overview

**Role:** The creative council — multi-agent debate for generating novel ideas or solving hard problems. Called by Orchestrator when stuck or exploring.

**Runtime:** Python script that runs multiple LLM calls with different personas
**Model:** Mixed (Gemini, Claude, etc. for diversity)
**Container:** `fullsend-roundtable`

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Orchestrator                             │
│                                                              │
│  "I'm stuck on how to reach AI startup CTOs..."             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      Roundtable                              │
│                                                              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                      │
│  │ ARTIST  │  │BUSINESS │  │  TECH   │                      │
│  │         │  │         │  │         │                      │
│  │ Creative│  │ Revenue │  │ Builder │                      │
│  │ wild    │  │ focused │  │ focused │                      │
│  └─────────┘  └─────────┘  └─────────┘                      │
│       │            │            │                            │
│       └────────────┴────────────┘                            │
│                    │                                         │
│                    ▼                                         │
│              ┌───────────┐                                   │
│              │ SUMMARIZER│                                   │
│              │           │                                   │
│              │ 3-5 tasks │                                   │
│              └───────────┘                                   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
                    Actionable Ideas
```

---

## Personality (The Three Agents)

### ARTIST
Creative. Wild. Ignores constraints. Thinks in metaphors and unexpected angles.
"What if we treated CTOs like art collectors?"

### BUSINESS
Revenue-focused. Practical. Cares about conversion and ROI.
"How many can we reach? What's the cost per lead?"

### TECH
Builder-focused. Thinks about what's automatable and scalable.
"We could scrape this API and pipe it through..."

---

## What It Does

1. **Receives prompt** from Orchestrator (problem or exploration topic)
2. **Runs debate** between 3 agents (ARTIST, BUSINESS, TECH)
3. **Each agent responds** to the prompt and to each other
4. **Summarizer distills** into 3-5 actionable tasks
5. **Returns output** to Orchestrator

## What It Does NOT Do

- Make strategic decisions (that's Orchestrator)
- Execute ideas (that's FULLSEND/Executor)
- Run continuously (triggered on-demand)

---

## File Structure

```
services/roundtable/
├── __init__.py
├── main.py           # Entry point
├── config.py         # Pydantic settings
├── debate.py         # Multi-agent orchestration
├── personas/         # Agent persona prompts
│   ├── artist.txt
│   ├── business.txt
│   ├── tech.txt
│   └── summarizer.txt
└── run.sh            # CLI wrapper
```

---

## Dependencies

### Environment Variables
```
GOOGLE_API_KEY=...           # For Gemini agents
ANTHROPIC_API_KEY=...        # For Claude summarizer
OPENAI_API_KEY=...           # Optional, for diversity
ROUNDTABLE_MODEL=gemini-2.0-flash-exp
SUMMARIZER_MODEL=claude-3-haiku-20240307
```

### Input (from Orchestrator)
```yaml
prompt: "How can we reach AI startup CTOs who just raised funding?"
context: |
  - We've had success with GitHub-based targeting
  - LinkedIn outreach has low response rates
  - Event-based targeting worked well last quarter
learnings:
  - "Developer-focused messaging converts 2x better"
  - "Personalization on company news increases opens"
max_rounds: 3
```

### Output (to Orchestrator)
```yaml
transcript: |
  ARTIST: What if we treated funding announcements like gallery openings...
  BUSINESS: I like the timing angle. Freshly funded = budget available...
  TECH: We could scrape Crunchbase for recent raises...
  ...

summary:
  - "Monitor Crunchbase for Series A+ raises in AI/ML space"
  - "Scrape founder Twitter for recent posts (personalization hooks)"
  - "Time outreach within 2 weeks of announcement"
  - "Lead with congratulations + specific insight about their space"
  - "Build Crunchbase scraper tool (Builder task)"
```

---

## Core Logic

### Main (main.py)

```python
import asyncio
from debate import run_debate, summarize_debate

async def main(prompt: str, context: str = "", learnings: list = None):
    """Run a roundtable session."""

    # Run the debate
    transcript = await run_debate(
        prompt=prompt,
        context=context,
        learnings=learnings or [],
        rounds=3
    )

    # Summarize into actionable tasks
    summary = await summarize_debate(transcript)

    return {
        "transcript": transcript,
        "summary": summary
    }

if __name__ == "__main__":
    import sys
    import json

    # Read input from file or stdin
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            input_data = json.load(f)
    else:
        input_data = json.load(sys.stdin)

    result = asyncio.run(main(
        prompt=input_data["prompt"],
        context=input_data.get("context", ""),
        learnings=input_data.get("learnings", [])
    ))

    print(json.dumps(result, indent=2))
```

### Debate (debate.py)

```python
import google.generativeai as genai
from pathlib import Path

genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

PERSONAS_DIR = Path(__file__).parent / "personas"

def load_persona(name: str) -> str:
    return (PERSONAS_DIR / f"{name}.txt").read_text()

async def run_debate(
    prompt: str,
    context: str,
    learnings: list,
    rounds: int = 3
) -> str:
    """Run a multi-agent debate."""

    personas = {
        "ARTIST": load_persona("artist"),
        "BUSINESS": load_persona("business"),
        "TECH": load_persona("tech"),
    }

    # Build initial context
    debate_context = f"""## Topic
{prompt}

## Context
{context}

## Learnings from Past Experiments
{chr(10).join(f"- {l}" for l in learnings)}
"""

    transcript = []

    for round_num in range(rounds):
        transcript.append(f"\n--- Round {round_num + 1} ---\n")

        for agent_name, persona in personas.items():
            # Build prompt with debate history
            agent_prompt = f"""{persona}

{debate_context}

## Debate So Far
{chr(10).join(transcript)}

## Your Turn
Respond to the topic. Build on or challenge previous points.
Keep it concise (2-3 sentences). Be distinctive to your persona.
"""

            model = genai.GenerativeModel(ROUNDTABLE_MODEL)
            response = await asyncio.to_thread(
                model.generate_content,
                agent_prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.8,  # Higher temp for creativity
                    max_output_tokens=200,
                )
            )

            transcript.append(f"{agent_name}: {response.text.strip()}\n")

    return "".join(transcript)

async def summarize_debate(transcript: str) -> list[str]:
    """Summarize debate into 3-5 actionable tasks."""

    summarizer_prompt = load_persona("summarizer")

    prompt = f"""{summarizer_prompt}

## Debate Transcript
{transcript}

## Output
List 3-5 actionable tasks. Each should be specific and executable.
Format as a simple list:
- Task 1
- Task 2
- ...
"""

    model = genai.GenerativeModel(SUMMARIZER_MODEL)
    response = await asyncio.to_thread(
        model.generate_content,
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.3,  # Lower temp for summarization
            max_output_tokens=300,
        )
    )

    # Parse into list
    lines = response.text.strip().split("\n")
    tasks = [line.lstrip("- ").strip() for line in lines if line.strip().startswith("-")]

    return tasks[:5]  # Max 5 tasks
```

---

## Personas

### personas/artist.txt
```
You are ARTIST, a creative strategist in a GTM brainstorm.

Your role:
- Think outside the box
- Make unexpected connections
- Challenge assumptions
- Propose bold, unconventional ideas

Your style:
- Use metaphors and analogies
- Ask "what if" questions
- Ignore practical constraints (others will ground you)
- Think about emotional hooks and storytelling

Example: "What if we treated developers like artists looking for patrons? Fund their side projects in exchange for attention..."
```

### personas/business.txt
```
You are BUSINESS, a revenue-focused strategist in a GTM brainstorm.

Your role:
- Ground ideas in business reality
- Think about conversion and ROI
- Consider scale and unit economics
- Focus on what actually drives revenue

Your style:
- Ask about numbers and metrics
- Challenge ideas that don't convert
- Suggest ways to test cheaply
- Think about the sales funnel

Example: "I like the concept, but how many leads can we realistically get? What's our cost per qualified meeting?"
```

### personas/tech.txt
```
You are TECH, a builder-focused strategist in a GTM brainstorm.

Your role:
- Think about what's automatable
- Consider available tools and APIs
- Ground ideas in technical feasibility
- Suggest ways to build and scale

Your style:
- Reference specific tools and platforms
- Think about data sources and scraping
- Consider what we can build vs buy
- Focus on leverage and automation

Example: "We could scrape Crunchbase for this data and pipe it through our email system automatically..."
```

### personas/summarizer.txt
```
You are the SUMMARIZER. Your job is to distill a brainstorm debate into actionable tasks.

Rules:
- Output exactly 3-5 tasks
- Each task must be specific and executable
- Include WHO should do it (FULLSEND, Builder, Orchestrator)
- Prioritize ideas that appeared multiple times or had strong agreement
- Include at least one "quick win" that can be done today

Format:
- Task description (Owner: who)
```

---

## CLI Usage

```bash
# Run roundtable with a question
echo '{"prompt": "How can we reach AI startup CTOs?"}' | python -m services.roundtable.main

# Or with a file
python -m services.roundtable.main input.json > output.json

# Or via run.sh
./services/roundtable/run.sh "How can we reach AI startup CTOs?"
```

### run.sh
```bash
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "$1" ]; then
    # Prompt passed as argument
    echo "{\"prompt\": \"$1\"}" | python -m services.roundtable.main
else
    # Read from stdin
    python -m services.roundtable.main
fi
```

---

## Acceptance Criteria

- [ ] Runs 3-agent debate (ARTIST, BUSINESS, TECH)
- [ ] Each agent has distinct persona
- [ ] Debate runs for 3 rounds
- [ ] Agents respond to each other (not just the prompt)
- [ ] Summarizer produces 3-5 actionable tasks
- [ ] Works via CLI (stdin/stdout)
- [ ] Can include context and learnings
- [ ] Returns structured output (transcript + summary)
- [ ] Handles LLM errors gracefully

---

## Test Plan

### Basic Test
```bash
echo '{"prompt": "How can we reach developers who use competitor products?"}' | \
    python -m services.roundtable.main | \
    jq '.summary'

# Should output 3-5 actionable tasks
```

### Full Test
```bash
cat > /tmp/roundtable_input.json << 'EOF'
{
    "prompt": "How can we reach AI startup CTOs who just raised Series A?",
    "context": "We sell developer tools. Our best customers are technical founders.",
    "learnings": [
        "GitHub-based targeting has 15% response rate",
        "Personalization on recent news increases opens 2x"
    ]
}
EOF

python -m services.roundtable.main /tmp/roundtable_input.json

# Verify:
# - Transcript shows 3 agents debating
# - Summary has 3-5 specific tasks
# - Tasks reference the context and learnings
```

### Persona Test
Verify each agent stays in character:
- ARTIST: Should have creative/unconventional ideas
- BUSINESS: Should mention metrics, conversion, ROI
- TECH: Should mention specific tools, APIs, automation

---

## Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY services/roundtable/requirements.txt .
RUN pip install -r requirements.txt

COPY services/roundtable/ ./services/roundtable/

ENV GOOGLE_API_KEY=""
ENV ANTHROPIC_API_KEY=""

CMD ["python", "-m", "services.roundtable.main"]
```

---

## Integration with Orchestrator

Orchestrator calls Roundtable when:
- Stuck on a decision
- Need fresh ideas for a sector
- All current experiments are failing
- Periodic ideation (weekly)

```python
# In Orchestrator:
async def call_roundtable(prompt: str, context: str):
    result = subprocess.run(
        ["python", "-m", "services.roundtable.main"],
        input=json.dumps({
            "prompt": prompt,
            "context": context,
            "learnings": await get_recent_learnings()
        }),
        capture_output=True,
        text=True
    )

    return json.loads(result.stdout)
```

---

## Notes for Builder

- This is a simple Python script, not a Claude Code instance
- Focus on persona distinctiveness — agents should sound different
- Higher temperature for agents (creativity), lower for summarizer
- Debate should build on itself (agents respond to each other)
- Summary is the key output — must be actionable
- Keep it fast — 3 rounds is enough
- Consider using different models for diversity
- Test that personas are distinct (common failure mode: all sound the same)
