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
PENDING=""
if [ -f sdd/BACKLOG.md ]; then
  # Anchor to item headers: '[~]' also appears in the status legend and in
  # section prose, and an unanchored grep reports those as in-progress items.
  PENDING=$(grep '^- \[~\] ' sdd/BACKLOG.md | head -10)
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

# Helper: true only inside a Linux root container (claude.ai/code).
# On-prem sessions (macOS, non-root Linux) skip auto-installs.
_is_linux_container() { [ "$(uname -s)" = "Linux" ] && [ "$(id -u)" = "0" ]; }

# --- Install hatch if needed ---
if ! command -v hatch &>/dev/null; then
  if _is_linux_container; then
    if command -v uv &>/dev/null; then
      uv tool install hatch >/dev/null 2>&1
    else
      python3 -m pip install hatch >/dev/null 2>&1
    fi
    if command -v hatch &>/dev/null; then
      echo "hatch: installed"
    else
      echo "hatch: install failed — gate hooks will not work"
    fi
  else
    echo "hatch: not found — install via pipx/pip (gate hooks will not work)"
  fi
fi

# --- Install Dafny if .dfy files exist in the repo ---
DAFNY_VERSION="4.11.0"
if ! command -v dafny &>/dev/null && ls sdd/formal/*.dfy &>/dev/null; then
  if _is_linux_container; then
    echo "dafny: not found — installing v${DAFNY_VERSION}..."
    _TMP=$(mktemp -d)
    _ZIP="dafny-${DAFNY_VERSION}-x64-ubuntu-22.04.zip"
    _URL="https://github.com/dafny-lang/dafny/releases/download/v${DAFNY_VERSION}/${_ZIP}"
    if ! curl -fsSL --max-time 120 "$_URL" -o "$_TMP/$_ZIP" 2>/dev/null; then
      rm -rf "$_TMP"
      echo "dafny: download failed — see sdd/CLAUDE-REFERENCE.md § Local toolchain"
    elif ! command -v unzip &>/dev/null || ! unzip -q "$_TMP/$_ZIP" -d "$_TMP" 2>/dev/null; then
      rm -rf "$_TMP"
      echo "dafny: extract failed (unzip missing or corrupt zip) — see sdd/CLAUDE-REFERENCE.md § Local toolchain"
    else
      mkdir -p /usr/local/lib/dafny
      cp -r "$_TMP/dafny/." /usr/local/lib/dafny/
      # Wrapper in /usr/local/bin ensures co-located DLLs are resolved
      # via the real binary path regardless of how dafny is invoked.
      printf '#!/bin/bash\nexec /usr/local/lib/dafny/dafny "$@"\n' \
        > /usr/local/bin/dafny
      chmod +x /usr/local/bin/dafny
      rm -rf "$_TMP"
      if command -v dafny &>/dev/null; then
        echo "dafny: installed v${DAFNY_VERSION}"
      else
        echo "dafny: install failed — see sdd/CLAUDE-REFERENCE.md § Local toolchain"
      fi
    fi
  else
    echo "dafny: not found natively — use Docker: bash scripts/dafny_verify.sh (verify) or bash scripts/dafny_translate.sh (codegen)"
  fi
fi

# --- Install Alloy if .als files exist in the repo ---
# Bump together with the list in scripts/alloy_check.sh.
ALLOY_VERSION="6.2.0"
ALLOY_SHA256="6037cbeee0e8423c1c468447ed10f5fcf2f2743a2ffc39cb1c81f2905c0fdb9d"
if ! command -v alloy &>/dev/null && ls sdd/formal/alloy/*.als &>/dev/null; then
  if _is_linux_container && command -v java &>/dev/null; then
    echo "alloy: not found — installing v${ALLOY_VERSION}..."
    _TMP=$(mktemp -d)
    _JAR="org.alloytools.alloy.dist-${ALLOY_VERSION}.jar"
    _URL="https://repo1.maven.org/maven2/org/alloytools/org.alloytools.alloy.dist/${ALLOY_VERSION}/${_JAR}"
    if ! curl -fsSL --max-time 120 "$_URL" -o "$_TMP/$_JAR" 2>/dev/null; then
      echo "alloy: download failed — see sdd/formal/README.md § Running the verifier"
    elif ! echo "${ALLOY_SHA256}  $_TMP/$_JAR" | sha256sum --check --quiet 2>/dev/null; then
      echo "alloy: checksum mismatch — not installed"
    else
      mkdir -p /usr/local/lib/alloy
      cp "$_TMP/$_JAR" /usr/local/lib/alloy/alloy.jar
      printf '#!/bin/bash\nexec java --enable-native-access=ALL-UNNAMED -jar /usr/local/lib/alloy/alloy.jar "$@"\n' \
        > /usr/local/bin/alloy
      chmod +x /usr/local/bin/alloy
      if [ "$(alloy version 2>/dev/null | tail -n 1)" = "$ALLOY_VERSION" ]; then
        echo "alloy: installed v${ALLOY_VERSION}"
      else
        echo "alloy: install failed — see sdd/formal/README.md § Running the verifier"
      fi
    fi
    rm -rf "$_TMP"
  elif _is_linux_container; then
    echo "alloy: not installed (no java on PATH) — sdd/formal/alloy/ cannot be checked in this session"
  else
    echo "alloy: not found natively — bash scripts/alloy_check.sh falls back to Docker; native setup in sdd/formal/README.md § Running the verifier"
  fi
fi

# --- Lean: report only, never install ---
# A claude.ai/code container is fresh each session, so an install here would
# download and unpack the toolchain at every session start; its size and how
# it was measured: sdd/formal/README.md § Running the verifier (maintainer
# decision, 2026-10-13).
if ! command -v lean &>/dev/null && [ -f sdd/formal/lean/lean-toolchain ]; then
  if _is_linux_container; then
    echo "lean: not installed — sdd/formal/lean/ cannot be checked in this session; native setup in sdd/formal/README.md § Running the verifier"
  else
    echo "lean: not found — bash scripts/lean_check.sh falls back to Docker; native setup in sdd/formal/README.md § Running the verifier"
  fi
fi

# --- Install gh on Linux containers if needed ---
if ! command -v gh &>/dev/null && _is_linux_container; then
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
