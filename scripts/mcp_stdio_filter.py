#!/usr/bin/env python3
"""
Filter stdin for MCP servers that choke on empty lines.
Reads line-by-line, forwards only non-empty lines to stdout.
Run: python scripts/mcp_stdio_filter.py | redis-mcp-server --url redis://localhost:6379/0
Or with uv: python scripts/mcp_stdio_filter.py | uv run redis-mcp-server --url redis://localhost:6379/0
"""
import sys

def main():
    for line in sys.stdin:
        if line.strip():
            sys.stdout.write(line)
            sys.stdout.flush()

if __name__ == "__main__":
    main()
