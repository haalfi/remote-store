# Medallion + Dagster Showcase

End-to-end Bronze/Silver/Gold pipeline with Dagster orchestration, demonstrating 4 remote-store extensions composing over live MeteoSwiss weather data.

{%
   include-markdown "../../examples/medallion_dagster/README.md"
   heading-offset=1
   rewrite-relative-urls=false
%}

## See also

- [Dagster](../dagster.md) — Dagster integration guide
- [Data Lake Patterns](../data-lake-patterns.md) — medallion architecture patterns
- [Architecture: Medallion + Dagster Showcase](../design/research/research-medallion-dagster-showcase.md) — detailed design rationale, store topology, and Dagster asset graph
- [Source: `examples/medallion_dagster/`](https://github.com/haalfi/remote-store/tree/master/examples/medallion_dagster/)
