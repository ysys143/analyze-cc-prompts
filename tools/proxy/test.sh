#!/bin/bash
# Launch Claude Code through the reverse proxy with an isolated HOME

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FAKE_HOME="$SCRIPT_DIR/.claude-home"

# Load API key from .env
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  source "$SCRIPT_DIR/.env"
  set +a
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "Error: ANTHROPIC_API_KEY is not set"
  echo "Set it in proxy/.env or export it before running."
  exit 1
fi

mkdir -p "$FAKE_HOME"

HOME="$FAKE_HOME" \
ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
ANTHROPIC_BASE_URL=http://localhost:8082 \
claude "$@"
