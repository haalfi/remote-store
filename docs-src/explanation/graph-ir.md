# API Graph Visualization

An interactive force-directed map of the project's API surface. Nodes are the
types and concepts that make up the codebase; edges are the typed relationships
between them. The full node and edge taxonomy is defined in the
[doc graph model RFC](../../sdd/rfcs/rfc-0012-doc-graph-model.md).

Use it to trace capability chains, explore the class hierarchy, and inspect
individual nodes and their direct neighbors.

[Open visualization](graph_viz.html){ .md-button .md-button--primary }

The visualization runs fully in the browser, with no server or build step.

## See also

- [Architecture Overview](architecture.md): three-layer design
- [API Reference](../reference/api/index.md): full method and capability reference
- [Capabilities Matrix](../reference/capabilities-matrix.md): per-backend capability support table
