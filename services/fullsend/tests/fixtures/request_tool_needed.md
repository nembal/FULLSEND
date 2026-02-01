# Experiment Request

## Idea
Scrape Hacker News "Who's Hiring" threads and reach out to companies hiring for AI/ML roles

## Context from Orchestrator
- Companies actively hiring are often growing and have budget
- HN job posts often include direct contact info
- No existing tool for HN scraping - request one from Builder

## Available Tools
- resend_email: Send emails via Resend API
- browserbase: Web scraping (generic)

## Output
1. Write experiment spec to experiments/exp_test_hn_hiring.yaml
2. Since we don't have an HN scraper tool, also output a tool request YAML for an hn_job_scraper tool
