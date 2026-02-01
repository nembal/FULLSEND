# Complex Request

## Idea
Build a complete lead gen pipeline:
1. Scrape GitHub stargazers
2. Enrich with LinkedIn data
3. Filter for CTOs
4. Send personalized emails

## Context from Orchestrator
- This is a complex multi-step task that requires building multiple tools
- Use RALPH loop to build step by step
- Each step should be validated before moving to the next

## Available Tools
- resend_email: Send emails via Resend API
- browserbase: Web scraping

## Output
This requires spawning a RALPH loop to build step by step.
Use the ralph.sh script to create a work directory and execute the build.
