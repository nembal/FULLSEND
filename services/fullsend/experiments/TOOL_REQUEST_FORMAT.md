# Tool Request YAML Format

This document defines the YAML format for FULLSEND tool requests sent to Builder.

## When to Use

FULLSEND creates tool requests when an experiment requires a tool that doesn't exist in the available tools registry. The request is published to `fullsend:builder_requests` for Builder to pick up.

## Full Template

```yaml
tool_request:
  # Required: Unique request identifier (format: req_YYYYMMDD_NNN)
  id: req_20240115_001

  # Required: Tool name (snake_case, descriptive)
  name: github_stargazer_scraper

  # Required: Clear description of what the tool does
  description: "Scrape users who starred a GitHub repo, extracting profile info"

  # Required: Priority level for Builder
  priority: high  # high | medium | low

  # Required: Who requested this tool
  requested_by: fullsend

  # Optional: Experiment that's blocked waiting for this tool
  experiment_blocked: exp_20240115_github_stars

  # --- INPUTS ---
  inputs:
    # Each input parameter the tool accepts
    - name: repo
      type: string
      description: "GitHub repo in owner/repo format"
      required: true

    - name: limit
      type: integer
      description: "Maximum number of users to return"
      default: 100

    - name: include_email
      type: boolean
      description: "Whether to extract emails from profiles/commits"
      default: true

  # --- OUTPUTS ---
  outputs:
    # What the tool returns
    - name: users
      type: list
      schema:
        username: string
        email: "string | null"
        name: "string | null"
        company: "string | null"
        bio: "string | null"
        location: "string | null"
        twitter: "string | null"
        followers: integer

    - name: total_found
      type: integer

    - name: rate_limited
      type: boolean

  # --- REQUIREMENTS ---
  # Specific technical requirements for Builder
  requirements:
    - Must handle GitHub API rate limiting (5000 req/hr with token)
    - Must paginate correctly for repos with many stars
    - Must extract email from profile or commits if public
    - Return partial results on failure (don't lose progress)
    - Cache results to avoid re-scraping same users

  # --- EXAMPLE USAGE ---
  # Show Builder exactly how this tool will be called
  example_usage: |
    from tools.github_stargazer_scraper import scrape_stargazers

    users = scrape_stargazers(
        repo="anthropics/claude",
        limit=100
    )

    for user in users:
        if user.email and "CTO" in (user.bio or ""):
            add_to_outreach(user)
```

## Field Reference

### tool_request (root)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | string | yes | Unique ID format: `req_YYYYMMDD_NNN` |
| name | string | yes | Tool name in snake_case |
| description | string | yes | What the tool does |
| priority | enum | yes | high, medium, low |
| requested_by | string | yes | Always "fullsend" |
| experiment_blocked | string | no | Experiment ID waiting for this tool |

### inputs

List of parameters the tool accepts:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | yes | Parameter name |
| type | enum | yes | string, integer, boolean, list, object |
| description | string | yes | What this parameter does |
| required | boolean | no | Whether parameter is required (default: false) |
| default | any | no | Default value if not provided |

### outputs

List of values the tool returns:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | yes | Output field name |
| type | enum | yes | string, integer, boolean, list, object |
| schema | object | list/object | Nested field definitions |

### requirements

List of strings describing:
- Technical constraints (rate limits, pagination)
- Error handling expectations
- Performance requirements
- Integration needs

### example_usage

Python code showing exactly how FULLSEND will call this tool. This helps Builder understand the interface expectations.

## Priority Levels

- **high**: Experiment is actively blocked, needs this ASAP
- **medium**: Experiment is planned, tool needed soon
- **low**: Nice to have, no experiment waiting

## Type Definitions

### Input Types
- **string**: Text value
- **integer**: Whole number
- **boolean**: true/false
- **list**: Array of values
- **object**: Key-value mapping

### Output Types
Same as input types, plus:
- **"type | null"**: Value may be null (e.g., `"string | null"`)

## Naming Conventions

### Request ID
Format: `req_YYYYMMDD_NNN`
- Date when request was created
- Sequential number for that day

Examples:
- `req_20240115_001`
- `req_20240115_002`
- `req_20240120_001`

### Tool Name
Format: `snake_case` describing action and target

Examples:
- `github_stargazer_scraper` - Scrapes GitHub stargazers
- `linkedin_profile_enricher` - Enriches profiles with LinkedIn data
- `twitter_follower_scraper` - Scrapes Twitter followers
- `email_validator` - Validates email addresses
- `company_data_enricher` - Enriches company information

## Redis Integration

Tool requests are published to Builder via Redis:

```bash
# FULLSEND publishes tool request
redis-cli PUBLISH fullsend:builder_requests "$(cat tool_request.yaml)"

# Also stored as pending request
redis-cli HSET tool_requests:req_20240115_001 status pending yaml "$(cat tool_request.yaml)"
```

## Lifecycle

```
FULLSEND creates request → Builder picks up → Builder builds tool → Builder notifies FULLSEND
        ↓                         ↓                    ↓                      ↓
  req_YYYYMMDD_NNN         status: building      tools/tool_name/       experiment unblocked
```

1. FULLSEND detects missing tool while designing experiment
2. FULLSEND creates tool_request YAML
3. FULLSEND publishes to `fullsend:builder_requests`
4. Builder builds the tool
5. Builder publishes completion to `builder:tool_ready`
6. FULLSEND marks experiment as ready
