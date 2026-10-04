# API Graph Visualization

An interactive force-directed map of the project's API surface. Nodes are the types and concepts that make up the codebase; edges are the typed relationships between them. The full node and edge taxonomy is defined in the [doc graph model RFC](https://docs.remotestore.dev/stable/explanation/design/rfcs/rfc-0012-doc-graph-model/index.md).

Use it to trace capability chains, explore the class hierarchy, and inspect individual nodes and their direct neighbors. It is built to be explored rather than just looked at:

- **Role-aware nodes:** concrete backends, abstract base classes, and facades are drawn distinctly; `Store`/`AsyncStore` stand out from other facades.
- **Collapse by default:** method nodes are folded into their class so the opening view is capability-level. Double-click a class (or use *Expand all*) to reveal its methods, clustered around it.
- **Detail with deep links:** select any node *or edge* to see its metadata plus jump-to-source links — the source `file:line` and governing spec on GitHub, and the API docs page on this site.
- **Faceted filtering:** text search plus filters for node kind, class role, edge kind, runtime (sync/async), capability, and a selected node's dependency neighbourhood. Facets combine.

[Open visualization](https://docs.remotestore.dev/stable/explanation/graph_viz.html)

The visualization runs fully in the browser, with no server or build step.

## See also

- [Architecture Overview](https://docs.remotestore.dev/stable/explanation/architecture/index.md): three-layer design
- [API Reference](https://docs.remotestore.dev/stable/reference/api/index.md): full method and capability reference
- [Capabilities Matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md): per-backend capability support table
