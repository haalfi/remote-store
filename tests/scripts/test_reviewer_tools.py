"""The review pass's tool list works under both GitHub MCP server names (BK-459).

A ``/rvw-pr`` pass gets exactly the ``tools:`` of ``.claude/agents/reviewer.md``
(ADR-0046), and Claude Code drops a name that does not resolve without an error.
The GitHub MCP server is ``MCP_DOCKER`` behind the local Docker gateway and
``github`` in a claude.ai/code session, where its tools are also deferred behind
``ToolSearch``. A list naming one server only left a cloud pass with
``Read, Grep, Glob, Bash`` and nothing to post with (probe, 2026-10-18).

Compares ``reviewer.md`` ``tools:`` (governs: it is the list that takes effect)
with ``rvw-pr/SKILL.md`` ``allowed-tools:``, which only pre-approves and must
name the same tools; the authority is declared in that frontmatter's comment.
The claim space is the governing list's entries; the two server names are
environment facts with no home in the repo, so they are listed here.

Bounds: does not check that either server exposes these tools, or that Claude
Code grants them; that is a fact about the product, measured by spawning the
agent in a fresh session. Not in ``GATE-INVENTORY.md``: the inventory reads
wired commands, and this runs inside the suite. Pure Python, so not
``os_sensitive``.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_AGENT = _ROOT / ".claude" / "agents" / "reviewer.md"
_SKILL = _ROOT / ".claude" / "skills" / "rvw-pr" / "SKILL.md"
_SERVERS = ("MCP_DOCKER", "github")
_MCP = re.compile(r"^mcp__(?P<server>[^_]+(?:_[^_]+)*?)__(?P<tool>.+)$")


def _frontmatter_list(path: Path, key: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)[1]
    match = re.search(rf"^{key}:\s*(.+)$", frontmatter, re.MULTILINE)
    assert match, f"{path.name} has no `{key}:` line"
    return [t.strip() for t in match.group(1).split(",") if t.strip()]


def _agent_tools() -> list[str]:
    return _frontmatter_list(_AGENT, "tools")


def test_allowed_tools_name_the_agents_tools() -> None:
    agent, skill = set(_agent_tools()), set(_frontmatter_list(_SKILL, "allowed-tools"))

    assert sorted(agent - skill) == [], "in reviewer.md tools: but not rvw-pr allowed-tools:"
    assert sorted(skill - agent) == [], "in rvw-pr allowed-tools: but not reviewer.md tools:"


def test_each_github_tool_is_listed_under_both_servers() -> None:
    by_server: dict[str, set[str]] = {s: set() for s in _SERVERS}
    for entry in _agent_tools():
        if match := _MCP.match(entry):
            assert match["server"] in by_server, f"{entry}: server is not one of {_SERVERS}"
            by_server[match["server"]].add(match["tool"])
    every = set().union(*by_server.values())

    assert every, "expected GitHub MCP tools in reviewer.md tools:"
    missing = {s: sorted(every - tools) for s, tools in by_server.items() if every - tools}
    assert missing == {}, f"tools missing under a server prefix: {missing}"


def test_tool_search_is_listed() -> None:
    """A cloud session defers MCP tools, and its reviewer is not granted ToolSearch."""
    assert "ToolSearch" in _agent_tools()


def test_no_editing_spawning_or_wildcard_tool() -> None:
    """ADR-0046: the agent's list is the review pass's restriction."""
    forbidden = [t for t in _agent_tools() if t in {"Edit", "Write", "NotebookEdit", "Agent"} or "*" in t]

    assert forbidden == []
