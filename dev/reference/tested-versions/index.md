# Tested upper-bound versions

Each `[<extra>]` declares its version range in `pyproject.toml` (a floor always, plus a ceiling only where a known-incompatible major looms — see the comment on `[project.optional-dependencies]` there for the authoritative per-extra ranges). The drift guard (`.github/workflows/drift-guard.yml`) records the last known-good resolution per extra in `infra/drift-locks/` and re-resolves weekly against the latest available versions (including pre-releases) to surface silent transitive upgrades before they reach users.

The table below is the projection of those lock files onto the top-level packages each extra declares. "Tested up to" is the exact version pinned in the lock at capture time — that is what CI was last green against.

## `[arrow]`

*Captured 2026-07-14 on Python 3.13.*

| Package   | Tested up to |
| --------- | ------------ |
| `pyarrow` | `25.0.0`     |

## `[azure]`

*Captured 2026-07-21 on Python 3.13.*

| Package                       | Tested up to |
| ----------------------------- | ------------ |
| `azure-identity`              | `1.26.0b2`   |
| `azure-storage-file-datalake` | `12.25.0`    |

## `[dagster]`

*Captured 2026-07-21 on Python 3.13.*

| Package   | Tested up to |
| --------- | ------------ |
| `dagster` | `1.13.14`    |

## `[graph]`

*Captured 2026-07-21 on Python 3.13.*

| Package           | Tested up to |
| ----------------- | ------------ |
| `httpx`           | `0.28.1`     |
| `msal`            | `1.38.0rc2`  |
| `msal-extensions` | `1.3.1`      |
| `platformdirs`    | `4.10.1`     |

## `[httpx]`

*Captured 2026-07-13 on Python 3.13.*

| Package | Tested up to |
| ------- | ------------ |
| `httpx` | `0.28.1`     |

## `[otel]`

*Captured 2026-07-21 on Python 3.13.*

| Package             | Tested up to |
| ------------------- | ------------ |
| `opentelemetry-api` | `1.44.0`     |

## `[pydantic]`

*Captured 2026-07-13 on Python 3.13.*

| Package             | Tested up to |
| ------------------- | ------------ |
| `pydantic-settings` | `2.14.2`     |

## `[requests]`

*Captured 2026-07-13 on Python 3.13.*

| Package    | Tested up to |
| ---------- | ------------ |
| `requests` | `2.34.2`     |
| `urllib3`  | `2.7.0`      |

## `[s3]`

*Captured 2026-07-21 on Python 3.13.*

| Package | Tested up to |
| ------- | ------------ |
| `s3fs`  | `2026.6.0`   |

## `[s3-pyarrow]`

*Captured 2026-07-21 on Python 3.13.*

| Package   | Tested up to |
| --------- | ------------ |
| `pyarrow` | `25.0.0`     |
| `s3fs`    | `2026.6.0`   |

## `[sftp]`

*Captured 2026-07-13 on Python 3.13.*

| Package    | Tested up to |
| ---------- | ------------ |
| `paramiko` | `5.0.0`      |
| `tenacity` | `9.1.4`      |

## `[sql]`

*Captured 2026-07-13 on Python 3.13.*

| Package      | Tested up to |
| ------------ | ------------ |
| `sqlalchemy` | `2.1.0b3`    |

## `[sql-query]`

*Captured 2026-07-14 on Python 3.13.*

| Package      | Tested up to |
| ------------ | ------------ |
| `pyarrow`    | `25.0.0`     |
| `sqlalchemy` | `2.1.0b3`    |

## `[yaml]`

*Captured 2026-05-25 on Python 3.13.*

| Package  | Tested up to |
| -------- | ------------ |
| `pyyaml` | `6.0.3`      |
