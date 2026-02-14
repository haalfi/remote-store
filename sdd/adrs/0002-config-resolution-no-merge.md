# ADR-0002: Configuration Resolution — No Merging

## Status

Accepted

## Context

Configuration systems often layer multiple sources (config files, env vars, CLI args, defaults) with complex merge semantics. This creates:

- Non-deterministic behavior depending on environment
- Hard-to-reproduce bugs in CI vs production
- Implicit coupling to deployment environment
- Test fragility (tests affected by host env vars)

## Decision

**Config-as-code has absolute priority. No merging, no env var overrides.**

Resolution rules:

1. If `RegistryConfig` is provided in code → use it exclusively
2. If no config is provided → environment variables may be used as a fallback
3. No layering, no merging between sources
4. Backend defaults apply last (within a single config source)

## Consequences

- Deterministic: same code = same behavior, regardless of environment
- Test-safe: no env var leakage into tests
- Explicit: configuration is visible in code, not hidden in env
- Trade-off: slightly more verbose config for pure-env deployments (acceptable — those users can build their own config loader and pass `RegistryConfig`)
