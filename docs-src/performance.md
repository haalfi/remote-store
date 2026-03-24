{%
   include-markdown "../guides/performance.md"
   rewrite-relative-urls=false
%}

## Detailed Comparative Tables

Per-backend tables comparing remote-store, raw SDK, and fsspec for each
operation. Generated with `hatch run bench-report-comparative-md`.

{%
   include-markdown "../benchmarks/results/comparative.md"
   rewrite-relative-urls=false
%}
