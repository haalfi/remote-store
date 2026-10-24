# 054 Profiles: Backend Key Languages
<!-- doc: dual dest=explanation/design/specs/054-store-key-profiles.md -->

**What each backend holds as a key, per axis of [spec 054](../054-store-key.md)'s
L_b (KEY-006), each cell from a cited authority or a dated measurement.** A
cell bounds L_b for that backend; the spec's clauses do not change with it.
Sources are the sections of
[`research-backend-path-authorities.md`](../../research/research-backend-path-authorities.md)
(§ 3 authorities, § 5 measurements of 2026-10-22); "not documented" is its § 4,
unknown rather than permitted.

## Axes

| Axis | What it bounds |
| --- | --- |
| `\` separator | Whether the backend reads `\` as a separator natively, which fixes Sep to {`/`, `\`} (KEY-009). |
| Refused characters | Code points a name may not hold, beyond L_floor's U+0000 and `\`. |
| Reserved names | Names refused whole. |
| Name length | The longest name, in the backend's unit. |
| Key length | The longest whole key, in the backend's unit, the backend's own location for the store included (KEY-A-01). |
| Segment count | The most names in one key. |
| Rewrites | Names the backend stores under another spelling; by KEY-006 none of them is in L_b, judged at every segment. |
| Name equality | Spec 051 § Name equality, recorded here because it constrains siblings, not L_b. |

## Memory, Local, S3, SFTP

| Axis | Memory | Local: Linux | Local: macOS APFS | Local: Windows NTFS | S3 general-purpose | S3 directory bucket | SFTP (OpenSSH) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `\` separator | — | — | — | yes (§ 3.4) | — | — | the server's file system (§ 3.8) |
| Refused characters | — | — (§ 3.2) | code points unassigned in Unicode 9.0 (§ 3.3) | `< > : " \| ? *`, U+0001 to U+001F (§ 3.4) | — (§ 3.6) | in a `DeleteObjects` key, control characters but `\n \t \r` (§ 3.6) | the server's file system (§ 3.8) |
| Reserved names | — | — | — | `CON PRN AUX NUL COM1`–`COM9 COM¹²³ LPT1`–`LPT9 LPT¹²³`, also with any extension (§ 3.4) | — | in a `DeleteObjects` key, all-whitespace (§ 3.6) | the server's file system (§ 3.8) |
| Name length | — | 255 bytes, `NAME_MAX` per file system (§ 3.2) | 255 UTF-8 bytes; a file system may allow more (§ 3.3) | 255 UTF-16 units, per volume (§ 3.4) | — | not documented (§ 3.6) | the server's file system (§ 3.8) |
| Key length | — | 4096 bytes with the terminating NUL, `PATH_MAX` (§ 3.2) | 1024 bytes, `PATH_MAX` (§ 3.3) | 260 UTF-16 units with drive and NUL, about 32 767 with long paths opted in (§ 3.4) | 1024 UTF-8 bytes (§ 3.6) | 1024 UTF-8 bytes (§ 3.6) | the server's file system (§ 3.8) |
| Segment count | — | — | — | — | — | not documented (§ 3.6) | — |
| Rewrites | — | — (§ 3.2) | — (normalisation-preserving, § 3.3); HFS+ stores names decomposed (§ 3.3) | a segment ending in a single `.` loses it; the last segment loses all trailing `.` and spaces (§ 3.4) | — (§ 3.6) | not documented (§ 3.6) | the server's file system (§ 3.8) |
| Name equality | exact | exact (§ 3.2) | case-insensitive by default, normalisation-insensitive (§ 3.3) | case-insensitive, case-preserving (§ 3.4) | exact (§ 3.6) | not documented (§ 3.6) | the server's file system (§ 3.8) |

Memory has no external authority (authorities doc § 1): its language is
L_core, and its cells record no limit rather than a measured one. A cell
reading "the server's file system" takes the matching Local column for the
server's platform. OpenSSH on Linux stored the § 5 table's three keys in
L_floor, `p/plain`, `p/...` and `p/k.`, as sent.
