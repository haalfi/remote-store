#!/bin/bash
# SessionStart: print project context — replaces setup-gh.sh

# --- Git status ---
BRANCH=$(git branch --show-current 2>/dev/null)
DIRTY=$(git status --porcelain 2>/dev/null | head -5)
echo "Branch: ${BRANCH:-detached}"
if [ -n "$DIRTY" ]; then
  echo "Working tree: dirty"
  echo "$DIRTY"
else
  echo "Working tree: clean"
fi

# --- Backlog [~] items ---
if [ -f sdd/BACKLOG.md ]; then
  PENDING=$(grep '\[~\]' sdd/BACKLOG.md | head -10)
  if [ -n "$PENDING" ]; then
    echo ""
    echo "In-progress backlog items [~]:"
    echo "$PENDING"
  fi
fi

# --- Tool availability ---
echo ""
if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
  echo "gh CLI: authenticated"
else
  echo "gh CLI: not available — use MCP_DOCKER for GitHub ops"
fi

# --- Install hatch if needed ---
if ! command -v hatch &>/dev/null; then
  pip install hatch >/dev/null 2>&1
  if command -v hatch &>/dev/null; then
    echo "hatch: installed"
  else
    echo "hatch: install failed — gate hooks will not work"
  fi
fi

# --- Install gh on Linux containers if needed ---
if ! command -v gh &>/dev/null && [ "$(uname -s 2>/dev/null)" = "Linux" ]; then
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg 2>/dev/null
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list >/dev/null
  apt-get update -qq && apt-get install -y -qq gh >/dev/null 2>&1
  if [ -n "$GITHUB_TOKEN" ]; then
    echo "$GITHUB_TOKEN" | gh auth login --with-token
    echo "gh CLI: installed and authenticated"
  fi
fi
