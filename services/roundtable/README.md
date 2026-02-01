# Roundtable

ARTIST, BUSINESS, and TECH agents communicate over a shared transcript to generate GTM ideas. Same LLM (W&B Inference), different prompts per persona.

## Run (only the roundtable)

From repo root, using the **weave_hacks** conda env:

```bash
# One-liner (no need to activate conda yourself):
./run_roundtable.sh "Topic: What GTM channels should we try next?"
```

Or manually:

```bash
conda activate weave_hacks
# Set WANDB_KEY or OPENAI_API_KEY (e.g. in .env), then:
python -m services.roundtable "Topic: What GTM channels should we try next?"
```

No Discord, Redis, or other services are started—only the roundtable runs.

Optional env:

- `ROUNDTABLE_MAX_ROUNDS` — default `2` (each persona speaks once per round)
- `OPENAI_API_BASE` — default `https://api.inference.wandb.ai/v1`
- `OPENAI_MODEL` — default `openai/gpt-oss-120b`

## Layout

- `llm.py` — `get_llm()` (W&B only)
- `personas.py` — System prompts for ARTIST, BUSINESS, TECH
- `runner.py` — Loop: build messages, call LLM per speaker, append to transcript
- `__main__.py` — CLI entrypoint

Redis seed (once before start) can be added later; no Redis during the loop.
