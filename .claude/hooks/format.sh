#!/usr/bin/env bash
# Formats the file Claude just edited, so every member's Claude produces identical formatting.
# Never blocks Claude: always exits 0.
input=$(cat)
file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null \
  || printf '%s' "$input" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))')
[ -z "$file" ] || [ ! -f "$file" ] && exit 0

case "$file" in
  *.py)
    (cd "$CLAUDE_PROJECT_DIR" && uv run ruff format "$file" && uv run ruff check --fix "$file") >/dev/null 2>&1 ;;
esac
exit 0
