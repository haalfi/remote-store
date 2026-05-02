# Explanation

Explanation is understanding-oriented. It discusses the *why* behind design
choices, architectural trade-offs, and how the pieces fit together.

## Architecture and Design

- [Architecture](architecture.md): how the layers fit together (`Store`,
  `Backend`, extensions, and the registry)
- [Concurrency](concurrency.md): the async/sync model, `SyncBackendAdapter`,
  and thread-safety guarantees
- [Security Model](security-model.md): credential handling, trust boundaries,
  and what `remote-store` does and does not protect

## Performance

- [Performance](performance.md): throughput characteristics and guidance on
  choosing between backends

## Design Documents

ADRs, specs, RFCs, and audit reports record past decisions and their rationale.
They are the primary source of truth for why `remote-store` works the way it does.

- [Architecture Decision Records](design/adrs/): binding architectural decisions
- [Specifications](design/specs/): feature specifications
- [RFCs](design/rfcs/): proposals and explorations
- [Research](design/research/): background research and comparisons
- [Audits](design/audits/): code and security reviews
