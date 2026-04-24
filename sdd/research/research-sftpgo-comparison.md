# Research: SFTPGo — Comparison and Design Insights

**Date:** 2026-04-24
**Context:** External project survey. Not tied to a backlog item.
Prompted by the question of whether SFTPGo belongs in the README comparison
table and what design ideas are worth carrying back.

---

## 1. What SFTPGo Is

[SFTPGo](https://github.com/drakkan/sftpgo) (Go, AGPL-3.0 + commercial) is a
**standalone file-transfer server/daemon** — roughly 27 k GitHub stars, actively
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

### 3.1 Path-Namespace Composition Across Backends

SFTPGo's virtual-folder model lets a single user see multiple backends under a
unified path tree (`/docs` → S3, `/archive` → Azure). This is structurally
similar to the CompositeStore idea in **ID-121**, but orthogonal: CompositeStore
stacks backends on the *same* path for fallthrough reads, whereas SFTPGo mounts
them at *different* paths. A future `NamespaceStore` or mount-map concept could
fill that gap — one path prefix dispatches to one child store, another prefix to
another. Not a blocker for ID-121, but worth noting as a follow-on direction.

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

> Not a file-transfer server — if you need external clients (SFTP partners,
> browser users) to access your storage via SFTP, FTPS, or WebDAV, look at
> [SFTPGo](https://github.com/drakkan/sftpgo).

This correctly frames the decision (different problem, not competing) without
distorting the Python-library comparison.

---

## 5. References

- <https://github.com/drakkan/sftpgo>
- <https://docs.sftpgo.com/>
- ID-121 — CompositeStore (research complete)
- `ext.observe` — `remote_store/ext/observe.py`
