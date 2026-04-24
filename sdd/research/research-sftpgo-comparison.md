# Research: SFTPGo — Comparison and Design Insights

**Date:** 2026-04-24
**Context:** External project survey. Not tied to a backlog item.
Prompted by the question of whether SFTPGo belongs in the README comparison
table and what design ideas are worth carrying back.

---

## 1. What SFTPGo Is

[SFTPGo](https://github.com/drakkan/sftpgo) (Go, AGPL-3.0 + commercial) is a
**standalone file-transfer server/daemon** — ~12 k GitHub stars as of this writing, actively
maintained. It sits in front of multiple storage backends and exposes them to
end users via standard protocols: SFTP/SCP, FTPS, HTTP/S, and WebDAV. A REST
API provides programmatic control; a web admin UI and web client handle human
access.

Supported storage backends: local filesystem (plain and encrypted), S3-compatible
(AWS, MinIO, DigitalOcean Spaces, …), Google Cloud Storage, Azure Blob, and
remote SFTP servers.

Key architectural concepts:

- **Users & Groups** — individual accounts with per-user protocol restrictions
  and quota limits; groups simplify bulk administration.
- **Virtual folders** — storage-agnostic mount points that map any backend to
  a user-visible path; a single user can have `/docs` on S3 and `/archive` on
  Azure simultaneously.
- **Data providers** — pluggable persistence for configuration state (MySQL,
  PostgreSQL, CockroachDB, SQLite, memory); enables multi-instance deployments
  with a shared database.
- **Event manager** — comprehensive hook system with synchronous pre-hooks
  (blocking) and asynchronous post-hooks firing webhooks or external programs.

---

## 2. Fundamental Category Difference

SFTPGo and remote-store occupy different categories:

| Dimension | SFTPGo | remote-store |
|-----------|--------|--------------|
| Kind | Network daemon | In-process Python library |
| Client access | SFTP, FTP, HTTP, WebDAV | Python API only |
| Multi-tenancy | Native (per-user quotas, ACLs) | Application must implement |
| Auth | Built-in (MFA, LDAP, AD, SSH keys) | Delegated to application |
| Language | Go | Python |
| Deployment | Run as service, Docker, k8s | `pip install` |

They are **not mutually exclusive**: a team could run SFTPGo to handle protocol
clients (external parties, SFTP partners) while using remote-store internally
for application-layer storage operations against the same S3 bucket.

---

## 3. Design Insights Worth Carrying Back

### 3.1 Unified Folder Structure Across Backends

SFTPGo's virtual-folder model mounts distinct backends at explicit path prefixes:
`/docs` → S3, `/archive` → Azure. Each prefix maps to exactly one backend; there
is no fallthrough.

**ID-121 CompositeStore** is a different concept: it presents a *single unified
folder structure* where all tiers share the same key space. Reads fall through
tiers in order (hot → warm → archive) until the key is found; writes go to the
primary tier only. An optional `match=` pattern can dispatch paths to specific
tiers, but the default is deterministic fallthrough — the caller sees one store
and never knows which tier answered.

The SFTPGo model is therefore not a close analog: path-prefix mounting is a
layout decision (different subtrees live on different backends), while
CompositeStore is a resolution strategy (the same key may exist on any tier,
and priority determines which one wins). There is no current remote-store
counterpart to SFTPGo's path-prefix mounting — that remains a possible future
direction if demand materialises.

### 3.2 Richer Hook Taxonomy

SFTPGo distinguishes a fine-grained set of events:
`pre_upload`, `post_upload`, `post_download`, `post_delete`, `post_rename`,
`pre_login`, `post_login`, `post_connect`, `post_disconnect`, `data_retention`,
`check_password`, `external_auth`, `keyboard_interactive`, `startup`.

Pre-* hooks run synchronously (blocking); post-* hooks run asynchronously. Our
`ext.observe` fires a single `on_operation` callback with an operation enum. If
we ever formalize the observability contract beyond the current ad-hoc callback,
SFTPGo's taxonomy is a practical reference for the event vocabulary.

### 3.3 Transparent Encryption at Rest

SFTPGo supports an encrypted local-filesystem variant (AES-256-GCM, key from
env or secret manager) as a first-class backend. remote-store has no analog.
A wrapping backend that encrypts/decrypts transparently — independent of the
underlying storage — could be a useful extension, particularly for local or
SQL backends where the storage layer itself provides no encryption.

### 3.4 Per-Path Quota and Permission Layers

SFTPGo enforces per-directory quotas and permission overrides at the
storage-service layer, not in application code. This is a natural fit for a
multi-tenant server. For remote-store, equivalent policy would live in
application code or in a future middleware layer — no immediate action, but
worth flagging if a policy/middleware item is ever designed.

---

## 4. README Comparison Table

SFTPGo does **not** belong in the existing comparison table. Every entry in
that table (`fsspec`, `smart_open`, `cloudpathlib`, `obstore`) is a Python
in-process library. The table dimensions (API surface, streaming I/O, async,
runtime deps) do not translate to a Go network daemon — most cells would be
`—` with footnotes, which would mislead a reader choosing a Python library.

The right place is a sentence in the **"What it is not"** section:

> Not a file-transfer server (no SFTP/FTP/WebDAV service such as [SFTPGo](https://github.com/drakkan/sftpgo))

This correctly frames the decision (different problem, not competing) without
distorting the Python-library comparison.

---

## 5. References

- <https://github.com/drakkan/sftpgo>
- <https://docs.sftpgo.com/>
- ID-121 — CompositeStore (research complete)
- `ext.observe` — `remote_store/ext/observe.py`
