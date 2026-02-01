# Experiment Spec YAML Format

This document defines the YAML format for FULLSEND experiment specifications.

## Full Template

```yaml
experiment:
  # Required: Unique identifier (format: exp_YYYYMMDD_short_name)
  id: exp_20240115_github_stars

  # Required: What you're testing (specific, testable statement)
  hypothesis: "CTOs who starred competitor repos are high-intent prospects"

  # Auto-generated timestamp
  created_at: "2024-01-15T10:30:00Z"

  # State machine: draft | ready | running | completed | failed | archived
  state: draft

  # --- TARGET ---
  target:
    # Required: Who exactly you're reaching out to
    description: "CTOs and technical founders who starred competitor/product repo"

    # Required: Estimated list size
    size: 500

    # Required: Where leads come from (tool/API/manual)
    source: "GitHub API via github_stargazer_scraper tool"

    # Optional: Filtering criteria applied to raw leads
    filters:
      - has_email: true
      - has_company: true
      - title_contains: ["CTO", "Founder", "CEO", "VP Eng"]

  # --- EXECUTION ---
  execution:
    # Required: Tool that executes this experiment
    tool: github_stargazer_scraper

    # Required: Parameters passed to the tool
    params:
      repo: "competitor/product"
      limit: 500

    # Required: Cron expression for scheduling
    schedule: "0 9 * * MON"

    # Optional: Timezone (defaults to UTC)
    timezone: "America/Los_Angeles"

  # --- OUTREACH ---
  outreach:
    # Required: Channel type
    channel: email  # email | linkedin | twitter | cold_call

    # Optional: Who the message comes from
    sender: "jake@company.com"

    # Required for email: Subject line with optional {{variables}}
    subject: "Quick question about {{company}}"

    # Required: The actual message template (no placeholders for content!)
    template: |
      Hi {{first_name}},

      Noticed you starred {{repo}} - looks like you're exploring dev tools.

      We built something similar but focused on making API integrations
      10x faster with AI-generated schemas.

      Would love to get your take on it. 15 min this week?

      Jake

  # --- METRICS ---
  metrics:
    # Counter: raw count of events
    - name: emails_sent
      type: counter

    - name: emails_opened
      type: counter

    # Percentage: computed from other metrics
    - name: open_rate
      type: percentage
      formula: "emails_opened / emails_sent"

    - name: replies
      type: counter

    # Percentage with threshold
    - name: response_rate
      type: percentage
      formula: "replies / emails_sent"
      success_threshold: 0.10

    - name: meetings_booked
      type: counter

  # --- SUCCESS/FAILURE CRITERIA ---
  # When to declare the experiment a win
  success_criteria:
    - response_rate > 0.10
    - meetings_booked >= 3

  # When to stop early (guardrails)
  failure_criteria:
    - response_rate < 0.02 after 100 sends
    - unsubscribe_rate > 0.05
    - bounce_rate > 0.10
```

## Field Reference

### experiment (root)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | string | yes | Unique ID format: `exp_YYYYMMDD_short_name` |
| hypothesis | string | yes | Specific, testable statement |
| created_at | ISO8601 | auto | Creation timestamp |
| state | enum | yes | draft, ready, running, completed, failed, archived |

### target

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| description | string | yes | Who you're targeting |
| size | integer | yes | Estimated lead count |
| source | string | yes | Tool or method to get leads |
| filters | list | no | Criteria to filter leads |

### execution

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| tool | string | yes | Tool name to execute |
| params | object | yes | Parameters for the tool |
| schedule | cron | yes | Cron expression |
| timezone | string | no | IANA timezone (default: UTC) |

### outreach

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| channel | enum | yes | email, linkedin, twitter, cold_call |
| sender | string | no | Sender identity |
| subject | string | email only | Email subject line |
| template | string | yes | **Actual message content** |

### metrics

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | yes | Metric identifier |
| type | enum | yes | counter, percentage, duration |
| formula | string | percentage | How to compute |
| success_threshold | number | no | When to consider success |

### success_criteria / failure_criteria

List of conditions expressed as simple comparisons:
- `metric_name > value`
- `metric_name >= value`
- `metric_name < value after N sends`

## Metric Types

- **counter**: Raw count (emails_sent: 150)
- **percentage**: Computed ratio (open_rate: 0.45)
- **duration**: Time measurement (avg_response_time: "2h 15m")

## State Machine

```
draft → ready → running → completed
                    ↓
                  failed
                    ↓
                archived
```

- **draft**: Experiment designed, not yet approved
- **ready**: Approved and scheduled
- **running**: Currently executing
- **completed**: Finished with results
- **failed**: Stopped due to failure criteria
- **archived**: Historical record

## Naming Conventions

### Experiment ID
Format: `exp_YYYYMMDD_short_name`
- Date when experiment was created
- Short descriptive name (snake_case, 2-4 words)

Examples:
- `exp_20240115_github_stars`
- `exp_20240120_linkedin_cto_dm`
- `exp_20240201_product_hunt_launch`

### Tool Names
Format: `snake_case_action_target`

Examples:
- `github_stargazer_scraper`
- `linkedin_profile_enricher`
- `resend_email_sender`

---

## Real Examples

### Example 1: GitHub Stargazers Email Campaign

```yaml
experiment:
  id: exp_20240115_anthropic_stargazers
  hypothesis: "Developers who starred anthropic/claude are interested in AI dev tools and will respond to a direct outreach about API integration challenges"
  created_at: "2024-01-15T10:30:00Z"
  state: draft

  target:
    description: "Software engineers and tech leads who starred the anthropic/claude repository in the last 90 days"
    size: 200
    source: "GitHub API via github_stargazer_scraper tool"
    filters:
      - has_email: true
      - starred_within_days: 90
      - min_followers: 10
      - bio_contains: ["engineer", "developer", "architect", "lead"]

  execution:
    tool: github_stargazer_scraper
    params:
      repo: "anthropic/claude"
      limit: 500
      extract_emails: true
    schedule: "0 9 * * MON"
    timezone: "America/New_York"

  outreach:
    channel: email
    sender: "alex@devtools.io"
    subject: "Saw you starred anthropic/claude"
    template: |
      Hey {{first_name}},

      I noticed you recently starred the Claude repo - guessing you're
      building something with LLMs.

      We're working on DevTools.io, which auto-generates API schemas
      from natural language. Basically, you describe what you want and
      it writes the OpenAPI spec + client SDKs.

      A few Claude users told us the hardest part of building AI apps
      isn't the AI - it's wiring up all the other APIs. That resonated
      with us.

      Would you be open to a 15-min call? I'd love to hear what you're
      building and see if our tool could help.

      - Alex
      Founder, DevTools.io

      P.S. If you reply with "SHOW ME", I'll send a 2-min demo video instead.

  metrics:
    - name: emails_sent
      type: counter
    - name: emails_delivered
      type: counter
    - name: emails_opened
      type: counter
    - name: open_rate
      type: percentage
      formula: "emails_opened / emails_delivered"
    - name: replies
      type: counter
    - name: reply_rate
      type: percentage
      formula: "replies / emails_delivered"
      success_threshold: 0.08
    - name: demo_requests
      type: counter
    - name: meetings_booked
      type: counter

  success_criteria:
    - reply_rate > 0.08
    - meetings_booked >= 5
    - demo_requests >= 10

  failure_criteria:
    - reply_rate < 0.02 after 50 sends
    - unsubscribe_rate > 0.03
    - bounce_rate > 0.15
    - spam_complaints > 0
```

### Example 2: LinkedIn DM to Y Combinator Founders

```yaml
experiment:
  id: exp_20240201_yc_founder_dm
  hypothesis: "YC founders building in the API/developer tools space will respond to a peer-to-peer message about integration pain points"
  created_at: "2024-02-01T14:00:00Z"
  state: draft

  target:
    description: "Technical founders from YC W24 and S23 batches building developer tools or APIs"
    size: 75
    source: "Manual curation from YC directory + LinkedIn Sales Navigator"
    filters:
      - role_contains: ["Founder", "CEO", "CTO"]
      - company_stage: "seed"
      - company_category: ["developer tools", "API", "infrastructure"]
      - has_linkedin: true

  execution:
    tool: linkedin_dm_sender
    params:
      daily_limit: 15
      connection_request_first: true
      delay_between_messages_hours: 4
    schedule: "0 10 * * TUE,THU"
    timezone: "America/Los_Angeles"

  outreach:
    channel: linkedin
    sender: "jordan-founder-profile"
    template: |
      Hi {{first_name}} - saw {{company}} in the YC directory. Congrats
      on the batch!

      We're also YC (W22) and building in the dev tools space. Quick
      question: how are you handling third-party API integrations for
      {{company}}? We keep hearing it's a huge time sink for early
      teams.

      Would love to swap notes if you're open to it. No pitch, just
      curious what's working for you.

  metrics:
    - name: connection_requests_sent
      type: counter
    - name: connections_accepted
      type: counter
    - name: accept_rate
      type: percentage
      formula: "connections_accepted / connection_requests_sent"
    - name: messages_sent
      type: counter
    - name: replies_received
      type: counter
    - name: reply_rate
      type: percentage
      formula: "replies_received / messages_sent"
      success_threshold: 0.20
    - name: calls_scheduled
      type: counter

  success_criteria:
    - accept_rate > 0.40
    - reply_rate > 0.20
    - calls_scheduled >= 3

  failure_criteria:
    - accept_rate < 0.15 after 30 requests
    - reply_rate < 0.05 after 20 messages
    - linkedin_restrictions_triggered > 0
```

### Example 3: Product Hunt Commenters Outreach

```yaml
experiment:
  id: exp_20240210_ph_commenters
  hypothesis: "People who commented on competitor launches on Product Hunt are actively evaluating solutions and will respond to a friendly alternative pitch"
  created_at: "2024-02-10T09:00:00Z"
  state: draft

  target:
    description: "Users who left substantive comments on competitor Product Hunt launches in the past 60 days"
    size: 150
    source: "Product Hunt API via ph_commenter_scraper tool"
    filters:
      - comment_length_min: 50
      - has_twitter: true
      - is_maker: false
      - comment_sentiment: ["positive", "curious"]

  execution:
    tool: ph_commenter_scraper
    params:
      product_slugs:
        - "competitor-product-1"
        - "competitor-product-2"
        - "alternative-tool-3"
      days_back: 60
      min_comment_length: 50
    schedule: "0 8 15 * *"
    timezone: "UTC"

  outreach:
    channel: twitter
    sender: "@devtools_io"
    template: |
      Hey {{twitter_handle}}! Saw your comment on {{product_name}}'s
      PH launch about {{comment_topic}}.

      We just shipped something that might solve that exact problem -
      auto-generates API clients from plain English descriptions.

      Mind if I DM you a quick demo?

  metrics:
    - name: tweets_sent
      type: counter
    - name: replies_received
      type: counter
    - name: reply_rate
      type: percentage
      formula: "replies_received / tweets_sent"
      success_threshold: 0.05
    - name: dm_permissions
      type: counter
    - name: demos_sent
      type: counter
    - name: signups
      type: counter

  success_criteria:
    - reply_rate > 0.05
    - dm_permissions >= 10
    - signups >= 3

  failure_criteria:
    - reply_rate < 0.01 after 50 tweets
    - blocks_or_reports > 2
    - account_restricted: true
```

### Example 4: Conference Attendee Follow-up

```yaml
experiment:
  id: exp_20240301_api_world_followup
  hypothesis: "Attendees of API World 2024 who visited the 'integration challenges' track will convert at 2x the rate of cold outreach"
  created_at: "2024-03-01T11:00:00Z"
  state: draft

  target:
    description: "API World 2024 attendees who registered for sessions on API integration, developer experience, or API management"
    size: 300
    source: "Conference attendee list (purchased) + LinkedIn enrichment"
    filters:
      - attended_sessions:
          - "Scaling API Integrations"
          - "Developer Experience Best Practices"
          - "API-First Architecture"
      - job_level: ["senior", "lead", "director", "vp"]
      - company_size_min: 50

  execution:
    tool: conference_followup_emailer
    params:
      conference_name: "API World 2024"
      batch_size: 50
      personalization_level: "high"
    schedule: "0 7 * * MON,WED,FRI"
    timezone: "America/Los_Angeles"

  outreach:
    channel: email
    sender: "maya@devtools.io"
    subject: "Loved your question at API World"
    template: |
      Hi {{first_name}},

      I was at API World last week and saw you attended the
      "{{session_name}}" session. Great questions from the audience
      on that one.

      I'm building DevTools.io - we're tackling exactly the problem
      that came up: how do you maintain dozens of API integrations
      without drowning in boilerplate?

      Our approach: describe the integration in plain English, we
      generate the SDK. Updates are automatic when the API changes.

      I put together a 3-min walkthrough specifically for folks who
      care about this stuff: {{demo_link}}

      Worth a look? Happy to jump on a call if you have questions.

      Maya
      Co-founder, DevTools.io

      P.S. We're offering API World attendees 3 months free if they
      want to try it. Just reply "INTERESTED" and I'll set you up.

  metrics:
    - name: emails_sent
      type: counter
    - name: emails_opened
      type: counter
    - name: open_rate
      type: percentage
      formula: "emails_opened / emails_sent"
      success_threshold: 0.40
    - name: demo_video_views
      type: counter
    - name: replies
      type: counter
    - name: reply_rate
      type: percentage
      formula: "replies / emails_sent"
      success_threshold: 0.12
    - name: trial_signups
      type: counter
    - name: meetings_booked
      type: counter

  success_criteria:
    - open_rate > 0.40
    - reply_rate > 0.12
    - trial_signups >= 15
    - meetings_booked >= 8

  failure_criteria:
    - open_rate < 0.20 after 100 sends
    - reply_rate < 0.03 after 100 sends
    - unsubscribe_rate > 0.02
```

---

## Validation Rules

Before an experiment spec is marked `ready`, it must pass these checks:

1. **ID format**: Matches `exp_YYYYMMDD_[a-z_]+`
2. **Hypothesis**: Between 20-500 characters, ends with testable claim
3. **Target size**: Positive integer, reasonable for channel (email: 50-5000, linkedin: 20-200)
4. **Template content**: No placeholder markers like `{{PLACEHOLDER}}` or `[INSERT HERE]`
5. **Metrics defined**: At least `*_sent` and `*_rate` metrics present
6. **Success criteria**: At least one measurable condition
7. **Failure criteria**: At least one guardrail condition
8. **Schedule**: Valid cron expression

## Anti-Patterns to Avoid

❌ **Vague hypothesis**
```yaml
hypothesis: "This might work well"
```

✅ **Specific hypothesis**
```yaml
hypothesis: "CTOs who starred competitor repos respond at 2x the rate of cold LinkedIn outreach"
```

❌ **Placeholder template**
```yaml
template: |
  Hi {{name}},

  [INSERT VALUE PROP HERE]

  [INSERT CTA HERE]
```

✅ **Real template**
```yaml
template: |
  Hi {{first_name}},

  Saw you starred the Claude repo - guessing you're building with LLMs.
  We auto-generate API schemas from natural language. 15 min to chat?

  - Alex
```

❌ **Missing failure criteria**
```yaml
success_criteria:
  - meetings_booked >= 5
failure_criteria: []  # Dangerous - no guardrails!
```

✅ **Proper guardrails**
```yaml
failure_criteria:
  - reply_rate < 0.02 after 50 sends
  - unsubscribe_rate > 0.03
  - spam_complaints > 0
```
