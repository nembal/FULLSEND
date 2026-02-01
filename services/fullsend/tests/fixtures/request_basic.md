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
