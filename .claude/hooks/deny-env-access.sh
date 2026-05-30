#!/bin/bash
# PreToolUse: block any Bash command that reads a secret `.env` file.
#
# Secret env files (`.env`, `.env.local`) are local-only and must never be
# read by an agent (see `permissions.deny` in .claude/settings.json, which
# covers the Read tool; this hook closes the shell vector: cat/source/less/
# etc. against a secret env file).
#
# Exception — `infra/.env`: `.gitignore` deliberately commits this one
# (`!infra/.env`) as the non-secret single-source-of-truth for local-infra
# ports/creds, and the benchmark/test docs direct agents to read it
# (benchmarks/README.md). It is carved out below so `cat infra/.env` works.
# A nested `infra/.env.local` is still treated as secret and blocked.
#
# Quoted strings are stripped before matching so that `.env` appearing
# inside an *argument* — e.g. a `git commit -m "... .env ..."` message or
# an `echo` — does NOT trip the guard; only a bare `.env` file operand
# does. The match requires `.env` as a path token: preceded by a path
# boundary (start, whitespace, slash, backslash, `=`) and not followed by
# an alphanumeric — so `.env`, `./.env`, and `.env.local` are blocked while
# `.environment`, `.envrc`, and `RS_TEST_LIVE_HNS=1 hatch run ...` pass
# through.
#
# Residual gap (accepted): `.env` hidden inside a quoted string passed to
# an interpreter (e.g. `python -c "open('.env')"`) is stripped along with
# the quotes and so is not caught here. The Read-tool deny in settings.json
# remains the primary guard; this hook is defense-in-depth for the common
# `cat .env` / `source .env` operands.
#
# Latent (templates): a root-level non-secret onboarding template such as
# `.env.example` / `.env.sample` / `.env.template` would also match the
# `.env.` token and be blocked by both this hook and the `Read(./.env.*)`
# deny. None exists in the repo today. If one is ever committed, give it the
# same kind of carve-out `infra/.env` got below.

# Fail closed if jq is missing: without it we cannot inspect the command,
# and a security guard must not silently allow what it cannot check. jq is
# already an established hook dependency (ruff-format.sh, backlog-status-
# brake.sh), so its absence is a setup error worth surfacing loudly.
if ! command -v jq >/dev/null 2>&1; then
  echo "Blocked: jq is required for the .env-access guard but is not on PATH. Install jq (an established hook dependency) and retry." >&2
  exit 2
fi

CMD=$(jq -r '.tool_input.command // empty')

# Strip single- and double-quoted spans so `.env` inside an argument
# (commit messages, echo text) is ignored; only unquoted operands remain.
STRIPPED=$(printf '%s' "$CMD" | awk '
BEGIN {
  in_sq = 0; in_dq = 0
  SQ = sprintf("%c", 39); DQ = sprintf("%c", 34); BS = sprintf("%c", 92)
}
{
  s = $0
  out = ""
  i = 1
  n = length(s)
  while (i <= n) {
    c = substr(s, i, 1)
    if (in_sq) {
      if (c == SQ) in_sq = 0
    } else if (in_dq) {
      if (c == BS && i + 1 <= n) { i += 2; continue }
      if (c == DQ) in_dq = 0
    } else {
      if (c == SQ) in_sq = 1
      else if (c == DQ) in_dq = 1
      else out = out c
    }
    i++
  }
  printf "%s\n", out
}
')

# Carve out the committed, non-secret `infra/.env`: neutralize that exact
# token (forward- or back-slash) before matching, so it no longer looks
# like a `.env` operand. A trailing `.` is excluded from the boundary so
# `infra/.env.local` is left intact and still blocked as a secret. The
# separator is written as an alternation `(/|\\)` rather than a bracket
# `[/\]`, because a lone backslash inside an ERE bracket expression is
# implementation-defined; `\\` in an alternation is portable.
CARVED=$(printf '%s' "$STRIPPED" | sed -E 's#(^|[^A-Za-z0-9_])infra(/|\\)\.env($|[^A-Za-z0-9_.])#\1infra/__INFRA_ENV__\3#g')

if printf '%s' "$CARVED" | grep -qiE '(^|[^A-Za-z0-9_])\.env([^A-Za-z0-9_]|$)'; then
  echo "Blocked: command reads a secret .env file — secret env files (.env, .env.local) are local-only and off-limits to agents. (infra/.env is exempt.) If you need a value, ask the user to export it into the session." >&2
  exit 2
fi
