# SQLQueryBackend

API reference for `SQLQueryBackend` --- read-only SQL query materializer that
maps path keys to SQL queries and serializes results to Parquet, CSV, or Arrow
IPC.

::: remote_store.backends.SQLQueryBackend
    options:
      show_bases: false

## Serialization

::: remote_store.backends.ResultSerializer
    options:
      show_bases: false

::: remote_store.backends.ArrowSerializer
    options:
      show_bases: false
