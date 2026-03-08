# Further Reading

## Spec-Driven Development

The project follows **Spec-Driven Development (SDD)**: every feature starts as
a specification before any code is written. Architecture decisions are recorded
as ADRs, open questions go through RFCs.

- [SDD Process](design/process.md) -- the methodology behind specs, ADRs, and RFCs
- [Design Document](design/design-spec.md) -- code style, conventions, and internal patterns

## Documentation as Code

Documentation follows the same rigour as code. The site is organised using the
[Diataxis](https://diataxis.fr/) framework -- separating tutorials, how-to
guides, reference, and explanation so readers find what they need without
wading through the wrong kind of content.

- [Documentation Master](https://github.com/haalfi/remote-store/blob/master/sdd/DOCUMENTATION.md) -- the authoritative guide for writing and organizing documentation

## Research Documents

Before specifying a feature we explore the design space -- compare libraries,
evaluate trade-offs, and document findings. We present these studies here
because they may be useful to readers facing similar decisions in their own
projects.

Browse the full collection on the [Research](design/research/index.md) page, or
jump to a specific topic:

- [Async Store API](design/research/research-async-store-api.md)
- [Store Config Design](design/research/research-store-config.md)
- [Example Testing](design/research/research-example-testing.md)
- [Logging, Monitoring, Tracing](design/research/research-logging-monitoring-tracing.md)
- [Retry Policy](design/research/research-retry-policy.md)
- [V1 Communication Plan](design/research/research-v1-communication-plan.md)

## Development Story

[DEVELOPMENT_STORY.md](https://github.com/haalfi/remote-store/blob/master/DEVELOPMENT_STORY.md)
captures how the project and package evolved over time -- the timeline, the
tooling choices, and the lessons learned along the way.
