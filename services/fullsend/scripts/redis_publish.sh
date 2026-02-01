#!/bin/bash
# Redis publish helpers for FULLSEND
# FULLSEND uses these to publish experiments, schedules, and tool requests to Redis
#
# Usage: source this file and call the functions, or invoke directly:
#   ./redis_publish.sh publish_experiment <experiment_file.yaml>
#   ./redis_publish.sh publish_schedule <experiment_id> <cron_expression> [timezone]
#   ./redis_publish.sh publish_tool_request <tool_request_file.yaml>
#   ./redis_publish.sh notify_orchestrator <type> <message_json>
#
# Environment:
#   REDIS_URL - Redis connection URL (default: redis://localhost:6379)

set -e

REDIS_URL="${REDIS_URL:-redis://localhost:6379}"

# Extract host and port from REDIS_URL
# Supports: redis://host:port, redis://host, host:port, host
parse_redis_url() {
    local url="$1"
    # Remove redis:// prefix if present
    url="${url#redis://}"
    # Remove any trailing slashes
    url="${url%/}"
    # Extract host and port
    if [[ "$url" == *":"* ]]; then
        REDIS_HOST="${url%:*}"
        REDIS_PORT="${url##*:}"
    else
        REDIS_HOST="$url"
        REDIS_PORT="6379"
    fi
}

parse_redis_url "$REDIS_URL"

# Helper: run redis-cli with proper connection
redis_cmd() {
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" "$@"
}

# Publish experiment spec to Redis
# Args: <experiment_yaml_file>
# Publishes to: fullsend:experiments channel
# Stores at: experiments:{id} key
publish_experiment() {
    local yaml_file="$1"

    if [[ ! -f "$yaml_file" ]]; then
        echo "Error: Experiment file not found: $yaml_file" >&2
        return 1
    fi

    # Extract experiment ID from YAML (looks for id: field under experiment:)
    local exp_id
    exp_id=$(grep -E '^\s+id:\s*' "$yaml_file" | head -1 | sed 's/.*id:\s*//' | tr -d '"' | tr -d "'" | xargs)

    if [[ -z "$exp_id" ]]; then
        echo "Error: Could not extract experiment ID from $yaml_file" >&2
        return 1
    fi

    # Read the full YAML content
    local yaml_content
    yaml_content=$(cat "$yaml_file")

    # Store experiment in Redis hash
    redis_cmd HSET "experiments:$exp_id" \
        "spec" "$yaml_content" \
        "state" "draft" \
        "created_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        "updated_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    # Publish to channel for subscribers
    local message
    message=$(cat <<EOF
{
  "type": "experiment_created",
  "experiment_id": "$exp_id",
  "source": "fullsend",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "spec_key": "experiments:$exp_id"
}
EOF
)
    redis_cmd PUBLISH "fullsend:experiments" "$message"

    echo "Published experiment: $exp_id"
    echo "  - Stored at: experiments:$exp_id"
    echo "  - Published to: fullsend:experiments"
}

# Publish schedule for an experiment
# Args: <experiment_id> <cron_expression> [timezone]
# Publishes to: fullsend:schedules channel
publish_schedule() {
    local exp_id="$1"
    local cron_expr="$2"
    local timezone="${3:-America/Los_Angeles}"

    if [[ -z "$exp_id" ]] || [[ -z "$cron_expr" ]]; then
        echo "Error: experiment_id and cron_expression required" >&2
        echo "Usage: publish_schedule <experiment_id> <cron_expression> [timezone]" >&2
        return 1
    fi

    local message
    message=$(cat <<EOF
{
  "type": "schedule_created",
  "experiment_id": "$exp_id",
  "schedule": "$cron_expr",
  "timezone": "$timezone",
  "source": "fullsend",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

    # Store schedule in Redis
    redis_cmd HSET "schedules:$exp_id" \
        "cron" "$cron_expr" \
        "timezone" "$timezone" \
        "state" "active" \
        "created_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    # Publish to channel
    redis_cmd PUBLISH "fullsend:schedules" "$message"

    echo "Published schedule for: $exp_id"
    echo "  - Cron: $cron_expr"
    echo "  - Timezone: $timezone"
    echo "  - Stored at: schedules:$exp_id"
    echo "  - Published to: fullsend:schedules"
}

# Publish tool request to Builder
# Args: <tool_request_yaml_file>
# Publishes to: fullsend:builder_requests channel
publish_tool_request() {
    local yaml_file="$1"

    if [[ ! -f "$yaml_file" ]]; then
        echo "Error: Tool request file not found: $yaml_file" >&2
        return 1
    fi

    # Extract request ID and tool name from YAML
    local req_id tool_name
    req_id=$(grep -E '^\s+id:\s*' "$yaml_file" | head -1 | sed 's/.*id:\s*//' | tr -d '"' | tr -d "'" | xargs)
    tool_name=$(grep -E '^\s+name:\s*' "$yaml_file" | head -1 | sed 's/.*name:\s*//' | tr -d '"' | tr -d "'" | xargs)

    if [[ -z "$req_id" ]]; then
        # Generate ID if not present
        req_id="req_$(date +%Y%m%d)_$(date +%s | tail -c 4)"
    fi

    # Read the full YAML content
    local yaml_content
    yaml_content=$(cat "$yaml_file")

    # Store request in Redis
    redis_cmd HSET "tool_requests:$req_id" \
        "spec" "$yaml_content" \
        "state" "pending" \
        "requested_by" "fullsend" \
        "created_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    # Publish to channel
    local message
    message=$(cat <<EOF
{
  "type": "tool_requested",
  "request_id": "$req_id",
  "tool_name": "$tool_name",
  "source": "fullsend",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "spec_key": "tool_requests:$req_id"
}
EOF
)
    redis_cmd PUBLISH "fullsend:builder_requests" "$message"

    echo "Published tool request: $req_id"
    echo "  - Tool: $tool_name"
    echo "  - Stored at: tool_requests:$req_id"
    echo "  - Published to: fullsend:builder_requests"
}

# Notify Orchestrator of status updates
# Args: <type> [additional_json_fields]
# Types: experiment_ready, design_failed, design_started, learning_recorded
# Publishes to: fullsend:to_orchestrator channel
notify_orchestrator() {
    local msg_type="$1"
    shift

    # Build message with any additional fields
    local extra_fields=""
    while [[ $# -gt 0 ]]; do
        extra_fields="$extra_fields, $1"
        shift
    done

    local message
    message=$(cat <<EOF
{
  "type": "$msg_type",
  "source": "fullsend",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"$extra_fields
}
EOF
)

    redis_cmd PUBLISH "fullsend:to_orchestrator" "$message"

    echo "Notified orchestrator: $msg_type"
}

# Publish metrics spec for an experiment
# Args: <experiment_id> <metrics_json>
# Stores at: metrics_specs:{experiment_id} key
# This tells Redis Agent what metrics to track for this experiment
publish_metrics_spec() {
    local exp_id="$1"
    local metrics_json="$2"

    if [[ -z "$exp_id" ]] || [[ -z "$metrics_json" ]]; then
        echo "Error: experiment_id and metrics_json required" >&2
        echo "Usage: publish_metrics_spec <experiment_id> <metrics_json>" >&2
        return 1
    fi

    # Store metrics spec in Redis
    redis_cmd HSET "metrics_specs:$exp_id" \
        "metrics" "$metrics_json" \
        "experiment_id" "$exp_id" \
        "source" "fullsend" \
        "created_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    echo "Published metrics spec for: $exp_id"
    echo "  - Stored at: metrics_specs:$exp_id"
}

# Extract metrics from experiment YAML and publish
# Args: <experiment_yaml_file>
# Extracts the metrics section and stores at metrics_specs:{id}
extract_and_publish_metrics() {
    local yaml_file="$1"

    if [[ ! -f "$yaml_file" ]]; then
        echo "Error: Experiment file not found: $yaml_file" >&2
        return 1
    fi

    # Extract experiment ID
    local exp_id
    exp_id=$(grep -E '^\s+id:\s*' "$yaml_file" | head -1 | sed 's/.*id:\s*//' | tr -d '"' | tr -d "'" | xargs)

    if [[ -z "$exp_id" ]]; then
        echo "Error: Could not extract experiment ID from $yaml_file" >&2
        return 1
    fi

    # Extract metrics section using awk (from metrics: to next top-level key or EOF)
    local metrics_yaml
    metrics_yaml=$(awk '/^[[:space:]]+metrics:/{found=1} found{if(/^[[:space:]]+(success_criteria|failure_criteria|execution|outreach|target):/ && NR>1){exit} print}' "$yaml_file")

    if [[ -z "$metrics_yaml" ]]; then
        echo "No metrics section found in $yaml_file"
        return 0
    fi

    # Store metrics in Redis as raw YAML (simpler, can be parsed by consumers)
    redis_cmd HSET "metrics_specs:$exp_id" \
        "metrics_yaml" "$metrics_yaml" \
        "experiment_id" "$exp_id" \
        "source" "fullsend" \
        "created_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    echo "Published metrics spec for: $exp_id"
    echo "  - Stored at: metrics_specs:$exp_id"
}

# Store a tactical learning
# Args: <learning_text> [experiment_id]
# Stores at: learnings:tactical:{timestamp} key
store_learning() {
    local learning="$1"
    local exp_id="${2:-}"
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local key="learnings:tactical:$timestamp"

    redis_cmd HSET "$key" \
        "text" "$learning" \
        "experiment_id" "$exp_id" \
        "source" "fullsend" \
        "created_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    # Add to sorted set for easy retrieval
    redis_cmd ZADD "learnings:tactical:index" "$(date +%s)" "$key"

    echo "Stored learning at: $key"
}

# Get available tools from Redis
# Returns: JSON array of available tools
get_available_tools() {
    local tools
    tools=$(redis_cmd KEYS "tools:*" 2>/dev/null || echo "")

    if [[ -z "$tools" ]]; then
        echo "[]"
        return
    fi

    echo "["
    local first=true
    while IFS= read -r key; do
        if [[ -n "$key" ]]; then
            local tool_name="${key#tools:}"
            local tool_state
            tool_state=$(redis_cmd HGET "$key" "state" 2>/dev/null || echo "unknown")
            if [[ "$first" == "true" ]]; then
                first=false
            else
                echo ","
            fi
            echo "  {\"name\": \"$tool_name\", \"state\": \"$tool_state\"}"
        fi
    done <<< "$tools"
    echo "]"
}

# Get recent tactical learnings
# Args: [limit] (default: 10)
# Returns: Recent learnings as text
get_recent_learnings() {
    local limit="${1:-10}"

    # Get recent learning keys from sorted set
    local keys
    keys=$(redis_cmd ZREVRANGE "learnings:tactical:index" 0 "$((limit - 1))" 2>/dev/null || echo "")

    if [[ -z "$keys" ]]; then
        echo "No recent learnings found."
        return
    fi

    echo "Recent Tactical Learnings:"
    echo "=========================="
    while IFS= read -r key; do
        if [[ -n "$key" ]]; then
            local text exp_id created_at
            text=$(redis_cmd HGET "$key" "text" 2>/dev/null || echo "")
            exp_id=$(redis_cmd HGET "$key" "experiment_id" 2>/dev/null || echo "")
            created_at=$(redis_cmd HGET "$key" "created_at" 2>/dev/null || echo "")
            echo ""
            echo "- $text"
            [[ -n "$exp_id" ]] && echo "  (from: $exp_id)"
            [[ -n "$created_at" ]] && echo "  (at: $created_at)"
        fi
    done <<< "$keys"
}

# Full publish flow: experiment + schedule + notify orchestrator
# Args: <experiment_yaml_file>
# This is the main entry point for publishing a complete experiment
publish_experiment_full() {
    local yaml_file="$1"

    if [[ ! -f "$yaml_file" ]]; then
        echo "Error: Experiment file not found: $yaml_file" >&2
        return 1
    fi

    # Extract experiment ID
    local exp_id
    exp_id=$(grep -E '^\s+id:\s*' "$yaml_file" | head -1 | sed 's/.*id:\s*//' | tr -d '"' | tr -d "'" | xargs)

    # Extract schedule and timezone
    local schedule timezone
    schedule=$(grep -E '^\s+schedule:\s*' "$yaml_file" | head -1 | sed 's/.*schedule:\s*//' | tr -d '"' | tr -d "'" | xargs)
    timezone=$(grep -E '^\s+timezone:\s*' "$yaml_file" | head -1 | sed 's/.*timezone:\s*//' | tr -d '"' | tr -d "'" | xargs)
    timezone="${timezone:-America/Los_Angeles}"

    # Extract hypothesis for summary
    local hypothesis
    hypothesis=$(grep -E '^\s+hypothesis:\s*' "$yaml_file" | head -1 | sed 's/.*hypothesis:\s*//' | tr -d '"' | xargs)

    echo "=== Publishing Experiment: $exp_id ==="
    echo ""

    # 1. Publish experiment
    publish_experiment "$yaml_file"
    echo ""

    # 2. Extract and publish metrics spec (for Redis Agent)
    extract_and_publish_metrics "$yaml_file"
    echo ""

    # 3. Publish schedule if present
    if [[ -n "$schedule" ]]; then
        publish_schedule "$exp_id" "$schedule" "$timezone"
        echo ""
    fi

    # 4. Notify orchestrator
    notify_orchestrator "experiment_ready" \
        "\"experiment_id\": \"$exp_id\"" \
        "\"summary\": \"$hypothesis\"" \
        "\"has_schedule\": $([ -n "$schedule" ] && echo 'true' || echo 'false')"

    echo ""
    echo "=== Complete ==="
}

# CLI interface
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:-}" in
        publish_experiment)
            publish_experiment "$2"
            ;;
        publish_experiment_full)
            publish_experiment_full "$2"
            ;;
        publish_schedule)
            publish_schedule "$2" "$3" "$4"
            ;;
        publish_tool_request)
            publish_tool_request "$2"
            ;;
        notify_orchestrator)
            shift
            notify_orchestrator "$@"
            ;;
        store_learning)
            store_learning "$2" "$3"
            ;;
        get_tools)
            get_available_tools
            ;;
        get_learnings)
            get_recent_learnings "${2:-10}"
            ;;
        publish_metrics)
            extract_and_publish_metrics "$2"
            ;;
        *)
            echo "FULLSEND Redis Publish Helper"
            echo ""
            echo "Usage: $0 <command> [args]"
            echo ""
            echo "Commands:"
            echo "  publish_experiment <yaml_file>       Publish experiment spec to Redis"
            echo "  publish_experiment_full <yaml_file>  Full flow: experiment + metrics + schedule + notify"
            echo "  publish_schedule <exp_id> <cron> [tz] Publish schedule for experiment"
            echo "  publish_metrics <yaml_file>          Extract and publish metrics spec"
            echo "  publish_tool_request <yaml_file>     Request tool from Builder"
            echo "  notify_orchestrator <type> [fields]  Send status to Orchestrator"
            echo "  store_learning <text> [exp_id]       Store a tactical learning"
            echo "  get_tools                            List available tools"
            echo "  get_learnings [limit]                Get recent learnings"
            echo ""
            echo "Environment:"
            echo "  REDIS_URL  Redis connection (default: redis://localhost:6379)"
            echo ""
            echo "Redis Channels:"
            echo "  fullsend:experiments      - New experiment specs (Executor listens)"
            echo "  fullsend:schedules        - Cron schedules (Executor listens)"
            echo "  fullsend:builder_requests - Tool requests (Builder listens)"
            echo "  fullsend:to_orchestrator  - Status updates (Orchestrator listens)"
            echo ""
            echo "Redis Keys:"
            echo "  experiments:{id}          - Experiment definitions"
            echo "  schedules:{id}            - Schedule configurations"
            echo "  metrics_specs:{id}        - Metrics to track (Redis Agent)"
            echo "  tool_requests:{id}        - Tool request specs"
            echo "  learnings:tactical:*      - Tactical learnings"
            echo "  tools:*                   - Available tools registry"
            echo ""
            echo "Examples:"
            echo "  $0 publish_experiment experiments/exp_001.yaml"
            echo "  $0 publish_experiment_full experiments/exp_001.yaml"
            echo "  $0 publish_schedule exp_001 '0 9 * * MON' 'America/New_York'"
            echo "  $0 publish_metrics experiments/exp_001.yaml"
            echo "  $0 publish_tool_request tool_requests/req_001.yaml"
            echo "  $0 notify_orchestrator experiment_ready '\"experiment_id\": \"exp_001\"'"
            echo "  $0 store_learning 'Template A got 20% response rate' exp_001"
            ;;
    esac
fi
