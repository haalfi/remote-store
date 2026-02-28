<!-- No benchmark data yet -- regenerate with: hatch run bench-report-comparative-md -->

*Run benchmarks and generate this file:*

```bash
docker compose -f benchmarks/infra/docker-compose.yml up -d --wait
hatch run bench-save
hatch run bench-report-comparative-md
```
