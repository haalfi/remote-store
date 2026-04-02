# Research: OpenRouter.ai Integration for Claude Code Workflow

**Date:** 2026-04-02
**Status:** Analysis complete — no action recommended at this time

---

## 1. What is OpenRouter?

OpenRouter.ai is a unified API gateway that routes requests to 300+ LLM models
from 60+ providers (OpenAI, Anthropic, Google, Meta, Mistral, etc.) through a
single OpenAI-compatible endpoint. Key capabilities:

- **Single API key** for all providers
- **Automatic failover** between providers during outages
- **Cost-based routing** — pick the cheapest provider for a given model
- **BYOK mode** — Bring Your Own Key for direct provider billing
- **Zero data retention** option
- **Centralized billing** and usage monitoring across models/teams

As of early 2026: 30T+ tokens/month processed, 5M+ users, SDKs for
TypeScript, Python, Go, Java.

---

## 2. Current AI Usage in remote-store

The `remote-store` library has **zero LLM dependencies** in its source code —
it is a file storage abstraction layer. All AI usage is in the **development
workflow** via Claude Code:

| Component | Location | Purpose |
|-----------|----------|---------|
| 7 custom skills | `.claude/skills/` | `/pr`, `/review-pr`, `/fix-pr`, `/audit`, `/orchestrate`, `/release`, `/preview` |
| Multi-agent orchestration | `/orchestrate` skill | 4 parallel domain-expert subagents |
| GitHub MCP servers | `github-pat`, `MCP_DOCKER` | PR creation, review, thread resolution |
| Hooks | `.claude/settings.json` | Session init, commit gating, auto-formatting |
| ollama reference | `DEVELOPMENT_STORY.md` | Mentioned for local GPU-accelerated bulk tasks |

---

## 3. Integration Feasibility

### 3.1 Claude Code + OpenRouter

Claude Code supports routing through OpenRouter by setting two environment
variables:

```bash
export ANTHROPIC_BASE_URL=https://openrouter.ai/api
export ANTHROPIC_API_KEY=<openrouter-key>
```

This uses OpenRouter's "Anthropic Skin" — no proxy or code changes needed.
Provides automatic failover if Anthropic's API is temporarily unavailable.

### 3.2 Model switching

OpenRouter exposes `/model` switching mid-session, allowing cheaper models for
low-stakes tasks. However, Claude Code subagents (used by `/orchestrate`) must
all run the same model family — there is no per-agent model routing in the
Claude Code architecture today.

---

## 4. Evaluation Against Current Workflow

| Scenario | OpenRouter value | Relevance | Verdict |
|----------|-----------------|-----------|---------|
| Failover during Anthropic outages | Automatic rerouting | Low — outages are rare | Nice-to-have |
| Centralized team billing | Single invoice, usage dashboard | Only if multiple devs share billing | Not needed (single-dev today) |
| Switch models mid-session | Access to non-Claude models | Skills/hooks assume Claude capabilities | Risk of breakage |
| Cheaper models for bulk tasks | Cost savings on routine work | ollama already covers this locally | Redundant |
| Add LLM features to the library | Product feature | `remote_store` is a storage lib | Not applicable |
| CI/CD with Claude Code Action | Failover in CI pipelines | CI has no AI steps currently | Not applicable |
| Per-subagent model routing | Route simple experts to cheaper models | Claude Code doesn't support this | Blocked by architecture |

---

## 5. Comparison with Existing ollama Approach

`DEVELOPMENT_STORY.md` mentions using an ollama MCP server for delegating bulk
tasks to local GPU-accelerated models. This overlaps with OpenRouter's
cheaper-model routing:

| Dimension | ollama (local) | OpenRouter (cloud) |
|-----------|---------------|-------------------|
| Cost | Free after hardware | Pay per token |
| Latency | Low (local GPU) | Network round-trip |
| Privacy | Full local control | Depends on provider policy |
| Model variety | Limited by VRAM | 300+ models |
| Setup | Requires local GPU | Environment variables only |
| Availability | Depends on local machine | Always available |

OpenRouter would complement (not replace) ollama for scenarios where local GPU
is unavailable (e.g., cloud-based development sessions on claude.ai/code).

---

## 6. Conclusion

**No actionable integration at this time.** The remote-store development
workflow is tightly coupled to Claude Code's native capabilities, and the
library itself has no LLM dependencies.

OpenRouter becomes relevant if:

1. **Anthropic reliability** becomes a concern — trivial to enable as a
   failover proxy via environment variables.
2. **Team scaling** — multiple developers need centralized billing and usage
   monitoring across Claude Code sessions.
3. **Claude Code adds per-agent model routing** — would unlock cost
   optimization in the `/orchestrate` multi-agent workflow.
4. **Cloud dev sessions** need access to cheaper models without local GPU
   (replaces ollama for those environments).

None of these conditions apply today. Revisit if the development team grows or
if Claude Code's architecture evolves to support heterogeneous model routing.
