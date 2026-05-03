# Graph IR Visualization

An interactive D3 force-directed map of the project's graph IR: nodes are
capabilities, classes, methods, packages, extras, and requirements; edges are
the typed relationships between them (`inherits`, `mirrors`, `enables`,
`gates`, `of`, `declares`).

Use it to trace capability chains, explore the backend and extension class
hierarchy, and inspect individual nodes and their direct neighbors.

[Open visualization](graph_viz.html){ .md-button .md-button--primary }

The visualization is self-contained and runs fully in the browser — no server
required. Scroll to zoom, drag to pan, click a node to highlight its neighbors.

## See also

- [Architecture Overview](architecture.md) — three-layer design and error hierarchy
- [Capabilities Matrix](../reference/capabilities-matrix.md) — per-backend capability support table
