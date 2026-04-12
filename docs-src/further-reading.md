# Further Reading

For readers who want to understand *why* remote-store is shaped the way it is:
the methodology, the decisions, and the research behind the code.

## Spec-Driven Development

Every feature starts as a specification. Architecture decisions are recorded
as ADRs; open design questions go through RFCs. The trail is kept on purpose:
any behavior in the library can be traced back to the document that defined it.

- [SDD Process](design/process.md): specs, ADRs, and RFCs as a workflow
- [Specs](design/specs/): the contract for each feature
- [Architecture Decision Records](design/adrs/): decisions made, with context
- [RFCs](design/rfcs/): proposals and explorations

## Code and testing conventions

- [Design Document](design/design-spec.md): code style, naming, internal patterns
- [Testing Standards](design/testing-standards.md): what "tested" means here

## Documentation philosophy

Documentation is held to the same standard as code: reviewed, versioned, and
organised so readers find the right *kind* of page for their task. The site
follows the [Diataxis](https://diataxis.fr/) framework: tutorials, how-to
guides, reference, and explanation kept apart on purpose.

- [Documentation Standards](https://github.com/haalfi/remote-store/blob/master/sdd/DOCUMENTATION.md): structure and placement rules
- [Content Rules](https://github.com/haalfi/remote-store/blob/master/sdd/CONTENT-RULES.md): how we keep prose accurate over time

## Research

Before specifying a feature we survey the design space: compare libraries,
evaluate trade-offs, document findings. These studies may be useful to readers
facing similar decisions in their own projects.

Browse the full collection on the [Research](design/research/) page.

## Project history

- [Development Story](development-story.md): how the project and tooling evolved
- [Changelog](changelog.md): the release-by-release record

## Community and policy

- [Contributing](contributing.md): how to propose changes
- [Security policy](https://github.com/haalfi/remote-store/blob/master/SECURITY.md): reporting vulnerabilities
- [Code of Conduct](https://github.com/haalfi/remote-store/blob/master/CODE_OF_CONDUCT.md)
- [Citation](https://github.com/haalfi/remote-store/blob/master/CITATION.cff): how to cite remote-store
