# API Graph Visualization

An interactive D3 force-directed map of the project's API surface: nodes are
capabilities, classes, methods, packages, extras, and requirements; edges are
the typed relationships between them (`inherits`, `mirrors`, `enables`,
`gates`, `of`, `declares`).

Use it to trace capability chains, explore the backend and extension class
hierarchy, and inspect individual nodes and their direct neighbors.

[Open visualization](graph_viz.html){ .md-button .md-button--primary }

The visualization is self-contained and runs fully in the browser.

## See also

- [Architecture Overview](architecture.md): three-layer design
- [API Reference](../reference/api/index.md): full method and capability reference
- [Capabilities Matrix](../reference/capabilities-matrix.md): per-backend capability support table
