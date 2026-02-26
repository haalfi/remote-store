#!/bin/bash
set -e

# Install GitHub CLI if not present (Linux containers only — skips on macOS/Windows)
if ! command -v gh &>/dev/null; then
  if [ "$(uname -s)" = "Linux" ]; then
    echo "Installing GitHub CLI..."
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg 2>/dev/null
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      | tee /etc/apt/sources.list.d/github-cli.list >/dev/null
    apt-get update -qq && apt-get install -y -qq gh >/dev/null 2>&1
    echo "GitHub CLI installed."
  else
    echo "Skipping gh install (not Linux). Install manually: https://cli.github.com"
  fi
fi

# Authenticate if GITHUB_TOKEN is set and gh is not already authenticated
if [ -n "$GITHUB_TOKEN" ] && ! gh auth status &>/dev/null; then
  echo "$GITHUB_TOKEN" | gh auth login --with-token
  echo "GitHub CLI authenticated."
fi
