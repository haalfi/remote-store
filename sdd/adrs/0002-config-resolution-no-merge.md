# ADR-0002: Configuration Resolution - No Merging

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

Configuration systems often layer multiple sources (config files, env vars, CLI args, defaults) with complex merge semantics. This creates:

- Non-deterministic behavior depending on environment
- Hard-to-reproduce bugs in CI vs production
- Implicit coupling to deployment environment
- Test fragility (tests affected by host env vars)

## Decision

- **Config-as-code has absolute priority.** A `RegistryConfig` built in code
  is used exclusively — no layering, no merging between configuration sources.
  Chosen so the same code yields the same behavior regardless of host
  environment (determinism; test isolation from stray env vars). *Reverse if*
  determinism becomes a net liability — a first-class multi-source/override
  requirement emerges that user-side pre-processing genuinely cannot serve.
- **Environment variables are never read automatically.** The Registry performs
  no env-var fallback: constructing without a config yields an empty
  `RegistryConfig`, not an env-sourced one. Any env-var sourcing is explicit,
  user-side pre-processing (`resolve_env()`, Pydantic `BaseSettings`) that
  produces the final dict *before* construction; once the config is constructed,
  no further env lookups occur (spec 021 § CFG-021). *Reverse if* a built-in
  env-driven bootstrap is deliberately adopted (which also reopens the
  determinism decision above).
- **Backend defaults apply last, within a single config source.** "No merging"
  forbids combining across sources; it does not forbid a backend filling its
  unset options from its own defaults inside one source. *Reverse if*
  backend-default resolution moves out of config resolution.

## Consequences

- Deterministic: same code = same behavior, regardless of environment
- Test-safe: no env var leakage into tests
- Explicit: configuration is visible in code, not hidden in env
- Trade-off: slightly more verbose config for pure-env deployments (acceptable — those users can build their own config loader and pass `RegistryConfig`)
