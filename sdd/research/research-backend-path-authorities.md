# Research: What each backend's authority allows in a path or key

**Date:** 2026-10-21
**Status:** Research complete — a reference table, with one dated measurement (§ 5)

---

## 1. Purpose

Every storage backend has its own rules for what a path or key may be. Those
rules live in different authorities: an RFC, the POSIX standard, vendor
documentation, an expired Internet-Draft. They are stated in different units
(bytes, UTF-16 units, characters, segment counts), and they are often recalled
from memory rather than read.

This document is a reference: for each externally governed backend, what its
own authoritative source permits in a path or key, with the source cited.
§ 2 to § 4 record the external authorities only. § 5 adds one dated
measurement of what services and local implementations did, labelled as a
measurement and not an authority. The document decides nothing and states
nothing about what remote-store accepts.

**Scope.** The externally governed backends of remote-store v0.33.0
(`FEATURES.md` § Backends): `local`, `s3`, `s3-pyarrow`, `azure`, `sftp`,
`graph`, `http`. `memory`, `sql-blob` and `sql-query` have no external
authority; their key rules are remote-store-defined.

**Derivation.** Every claim comes from a primary source fetched on 2026-10-21
(WebFetch, or Python `urllib` / `pdftotext` for POSIX, Apple and Python
pages). Every quote in § 3 was then checked word for word against the raw
text of a source its subsection lists, on 2026-10-22, by
[`bk-484-key-model/probes/check_quotes.py`](bk-484-key-model/probes/check_quotes.py),
which folds only whitespace, typographic quote marks and dashes: 85 of 85
found. The check corrected three quotes, narrowed one date and added the
four sources it found missing. Points that no primary source settles after two rounds
of search are marked "Not documented" and listed in § 4. Statements from SDK
source, SDK issue trackers or emulators are labelled as such.

---

## 2. Reference table

One row per backend and namespace model, with the same questions asked of
each. Each cell is derived from the subsection of § 3 for that backend; a
cell marked "measured" comes from § 5.

| Backend | Authority | Unit, max length | Hierarchy, separator | Forbidden | Avoid (advisory) | `.` / `..` | Empty segment, `//` | Trailing `/` | Case | Encoding |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| URI layer (`http`, Graph URLs) | RFC 3986 §2, §3.3, §5.2.4, §6.2 | — (no path or segment limit; RFC 9110 §4.1 RECOMMENDS ≥ 8000-octet URI support, a floor) | Hierarchical syntax, `/`; segments opaque | Anything outside `pchar` must be percent-encoded | — | Removed on resolution; `..` above root silently dropped | Grammatical; `//` forbidden at path start without authority | Grammatical | Path case-sensitive | Octets; `%2F` ≠ `/`; `%2E` normalises to `.` (inference, § 3.1) |
| `local` POSIX / Linux | POSIX.1-2024 §3.146, §3.254, §4.16; Linux `limits.h` | Bytes; component ≤ `NAME_MAX`, path ≤ `PATH_MAX`, both per filesystem (`pathconf`); Linux header constants 255 and 4096 (incl. NUL) | Real directories, `/` | NUL, `/` in a component | Leading `-` (§3.264); non-portable names may fail `EILSEQ`; newline (Issue 8 RATIONALE) | Resolved by the OS; `/..` = `/` | `a//b` = `a/b`; leading `//` implementation-defined (Linux: same as `/`) | Must resolve to a directory | Case-sensitive | Opaque bytes |
| `local` macOS APFS | Apple APFS FAQ; APFS Reference; xnu `syslimits.h` | UTF-8 bytes; `NAME_MAX` 255 (Apple: FS may exceed), `PATH_MAX` 1024 | As POSIX | Invalid UTF-8; Unicode 9.0-unassigned code points | — | As POSIX | As POSIX | As POSIX | Case-insensitive by default (case-sensitive variant exists) | Normalisation-preserving, normalisation-insensitive |
| `local` macOS HFS+ | Apple TN1150 | 255 UTF-16 code units | As POSIX | — | — | As POSIX | As POSIX | As POSIX | Case-insensitive (HFSX: sensitive) | Stored decomposed (NFD variant, Unicode 3.2) |
| `local` Windows / NTFS | MS "Naming Files, Paths, and Namespaces"; "Maximum Path Length Limitation"; .NET "File path formats" | UTF-16 units ("Unicode characters"); component ≤ 255 (volume-reported); path 260 (`MAX_PATH`) or ≈ 32 767 with `\\?\` or long-path opt-in | Real directories, `\` (`/` converted) | `< > : " / \ \| ? *`, NUL, 1–31; device names `CON PRN AUX NUL COM1–9 COM¹²³ LPT1–9 LPT¹²³`, also with any extension | Trailing space or `.` (stripped by normalisation) | Resolved by Win32 normalisation, not past root; `\\?\` disables | Separators after the first two collapse | Trailing `.`/space survives only before a separator | Case-insensitive, case-preserving; per-directory case sensitivity opt-in | Opaque WCHARs, no normalisation |
| Python `pathlib.PurePosixPath` (lexical model, not a backend) | Python 3.15 `pathlib` docs | — (none of its own) | `/`; no I/O | — | — | `.` collapsed; `..` kept (only `resolve()` removes it) | `a//b` → `a/b`; leading `//` kept, `///` → `/` | Dropped | Case-sensitive (`PureWindowsPath`: insensitive) | `str`; POSIX filenames decoded with `surrogateescape` |
| `s3`, `s3-pyarrow` general-purpose bucket | AWS "Naming Amazon S3 objects"; `PutObject`; `ListObjectsV2` | UTF-8 bytes; key 1–1024 | Flat; `/` is only a convention | `..` where cumulative `..` count exceeds preceding normal segments (REST, CLI, SDK, console) | Period-only segments; control chars 0–31, 127; `\ { } ^ % \` [ ] " < > ~ # \|`; bytes 128–255 | Stored literally if valid (see Forbidden); tools may normalise | Not documented; SDK issue reports indicate stored literally (§ 3.6) | Allowed (REST/SDK; console cannot upload) | Case-sensitive | UTF-8; list needs `encoding-type=url` for XML-unsafe chars |
| S3 directory bucket (Express One Zone) | AWS "Working with directory buckets"; "Differences for directory buckets" | UTF-8 bytes; key ≤ 1024 | Real directories; `/` only delimiter; prefixes must end in `/` | `DeleteObjects` keys: all-whitespace, control chars except `\n \t \r` | — | Not documented (live probe) | Not documented (live probe) | Not documented (live probe) for PUT; `RenameObject` fails on it | Not documented for directory buckets (general-purpose keys are case-sensitive) | UTF-8; listing unsorted |
| `azure` flat namespace | MS "Naming and Referencing Containers, Blobs, and Metadata" | Characters; blob name 1–1024; ≤ 254 segments | Flat; virtual hierarchy via any delimiter | Control chars 0x00–0x1F, invalid Unicode code points; URL-invalid chars may fail | Names or segments ending in `.`, `/`, `\`; U+0080–009F and noncharacters | Not documented (live probe) (only "no segment should end with `.`") | Not documented (live probe) | Avoid | Case-sensitive | Reserved URL chars must be escaped |
| `azure` HNS (ADLS Gen2) | Same page; ADLS "Path - Create"; Data Lake known issues | Characters; name 1–1024; ≤ 63 segments incl. account and container | Real directories; `/` only delimiter | As flat | As flat; measured: a trailing `.` is stripped and `\` becomes `/` (§ 5) | Not documented; measured: resolved by the service, `..` before authorisation (§ 5) | Not documented; measured: collapsed, a leading `/` dropped (§ 5) | Avoid; measured: PUT refused, `InvalidUri` (§ 5) | Case-sensitive | As flat |
| `sftp` (protocol v3, OpenSSH) | draft-ietf-secsh-filexfer-02 §6.2; OpenSSH `PROTOCOL` §4 | — (protocol sets none; server FS rules apply) | `/` assumed; relative to home | — (no syntax defined) | — | Servers SHOULD treat as parent/current | Not defined (server FS); an empty *path* is the home directory | — | Server FS | Opaque strings (UTF-8 only from v6, which OpenSSH lacks) |
| `graph` (OneDrive / SharePoint) | MS "Restrictions and limitations"; SharePoint limits; Graph "Addressing driveItems" | Characters; decoded path ≤ 400 | Folders, addressed by `/` paths | `" * : < > ? / \ \|`; `#` `%` on some business tenants; names `.lock CON PRN AUX NUL COM0–9 LPT0–9 _vti_ desktop.ini`; `~$` prefix; `_vti_` anywhere; leading/trailing spaces; folder ending in `.` and name starting with `~` (Graph page only) | — | Not documented | Not documented | Not documented | Path lookup case-insensitive, case-preserving | Percent-encoded UTF-8 per RFC 3986 |

---

## 3. Survey: the authority per backend

### 3.1 URI layer: RFC 3986, RFC 8089, RFC 9110 / 9112

Applies to `http` and to Graph request URLs.

- **Grammar** (RFC 3986 §3.3, §2.1–§2.3): `segment = *pchar`,
  `pchar = unreserved / pct-encoded / sub-delims / ":" / "@"`. "Aside from
  dot-segments in hierarchical paths, a path segment is considered opaque by
  the generic syntax."
- **Empty segments** are grammatical (`segment` may be empty). §3.3: without an
  authority, "the path cannot begin with two slash characters".
- **Dot segments** are removed by `remove_dot_segments` (§5.2.4). `/../g`
  resolves to `http://a/g` (§5.4.2), so `..` above root is dropped silently,
  not an error.
- **Length**: no path, segment or URI limit appears in RFC 3986 (negative
  finding from a full-text search; the only figure is 255 for host names,
  §3.2.2). RFC 9110 §4.1: "It is RECOMMENDED that all senders and recipients
  support, at a minimum, URIs with lengths of 8000 octets". RFC 9112 §3 gives
  the same floor for request lines and the `414` obligation ("MUST respond with
  a 414"). RFC 9110 §15.5.15 only defines the status.
- **Case**: scheme and host are case-insensitive, other components
  case-sensitive (§6.2.2.1).
- **Encoding equivalence**: "URIs that differ in the replacement of a reserved
  character with its corresponding percent-encoded octet are not equivalent"
  (§2.2). So `a%2Fb` is one segment and `a/b` two. Unreserved octets may be
  decoded at any time (§2.4, §6.2.2.2). Since `.` is unreserved, `%2E%2E`
  normalises to `..` (inference from those two clauses).
- **Server namespace**: "Each origin defines its own namespace" (RFC 9110
  §4.3.1). Beyond URI syntax, the HTTP server's path rules are opaque.
- **RFC 8089 (`file:`)**: §2 ABNF; system-specific operations in **Appendix D**
  (D.1 POSIX, D.2 DOS/Windows, D.3 Mac OS X); drive letters and UNC as
  nonstandard variants in **Appendix E** (E.2, E.3); collected nonstandard ABNF
  in Appendix F. §4: names "SHOULD be encoded as octets according to the UTF-8
  character encoding scheme".
- **Status**: RFC 3986 is STD 66, updated by RFC 7320 and RFC 8820, not
  obsoleted. Datatracker searches for "3986bis", "3986" and "uri" (active and
  expired drafts) found no revision of the generic syntax. The nearest attempt,
  draft-ietf-6man-rfc6874bis (IPv6 zone IDs only), is "Expired (IESG: Dead)";
  its latest revision is dated 2023-07-02.

Sources:

- <https://www.rfc-editor.org/rfc/rfc3986.html>
- <https://www.rfc-editor.org/rfc/rfc8089.html>
- <https://www.rfc-editor.org/rfc/rfc9110.html>
- <https://www.rfc-editor.org/rfc/rfc9112.html>
- <https://datatracker.ietf.org/doc/draft-ietf-6man-rfc6874bis/>

### 3.2 POSIX and Linux

Sections in POSIX.1-2024 (Issue 8) and Issue 7 are numbered differently; cite
one edition.

| Term | Issue 8 | Issue 7 |
| --- | --- | --- |
| Filename | 3.146 | 3.170 |
| Pathname | 3.254 | 3.271 |
| Path Prefix | 3.256 | 3.273 |
| Portable Filename Character Set | 3.265 | 3.282 |
| Pathname Resolution | 4.16 | 4.13 |

- **Filename** (3.146): "A sequence of bytes consisting of 1 to {NAME_MAX}
  bytes used to name a file. The bytes composing the name shall not contain the
  <NUL> or <slash> characters." Issue 7 uses the same wording.
- **Pathname** (3.254): "Multiple successive <slash> characters are considered
  to be the same as one <slash>, except it is implementation-defined whether
  the case of exactly two leading <slash> characters is treated specially."
- **Trailing slash** (4.16): such a pathname "shall not be resolved
  successfully unless the last pathname component before the trailing <slash>
  characters resolves … to an existing directory or a directory entry that is
  to be created for a directory".
- **Dot-dot at root** (4.16): "in the root directory, dot-dot may refer to the
  root directory itself." A null pathname "shall not be successfully resolved".
- **Portable set** (3.265): `A–Z a–z 0–9 . _ -`. Applications "should avoid
  using filenames that have the <hyphen-minus> character as the first
  character" (3.264).
- **Issue 8 newline change**: not a ban. `open()` RATIONALE: implementations
  "are encouraged to" report `[EILSEQ]` when creating a name containing a
  newline byte (Austin Group Defect 251). The normative part (Defect 293) is
  only an `[EILSEQ]` error for a non-portable name that "cannot be created".
  The same entry appears on `mkdir`, `rename`, `link`, `symlink`, `mkfifo`,
  `mknod`, `bind`. Existing names are untouched.
- **Limits** (`limits.h`): `_POSIX_NAME_MAX` 14, `_POSIX_PATH_MAX` 256; XSI
  minimums `_XOPEN_NAME_MAX` 255, `_XOPEN_PATH_MAX` 1024.
- **Linux**: `NAME_MAX 255`, `PATH_MAX 4096` (incl. NUL) in
  `include/uapi/linux/limits.h`. The header comment says "chars", but ext4
  stores "an arbitrary byte string", and "file names cannot be longer than 255
  bytes".
  `NAME_MAX` is per filesystem in practice (`pathconf(_PC_NAME_MAX)`).
  `path_resolution(7)`: empty pathname gives `ENOENT`; "/.." is the same as
  "/". Neither `path_resolution(7)` nor the kernel's path-lookup docs mention
  a leading `//`; the kernel source treats it as `/`: `fs/namei.c`
  `link_path_walk()` skips every leading slash
  (`do { name++; } while (unlikely(*name == '/'));`) after `path_init()` has
  jumped to root.

Sources:

- <https://pubs.opengroup.org/onlinepubs/9799919799/basedefs/V1_chap03.html>
- <https://pubs.opengroup.org/onlinepubs/9799919799/basedefs/V1_chap04.html>
- <https://pubs.opengroup.org/onlinepubs/9799919799/basedefs/limits.h.html>
- <https://pubs.opengroup.org/onlinepubs/9799919799/functions/open.html>
- <https://man7.org/linux/man-pages/man7/path_resolution.7.html>
- <https://docs.kernel.org/filesystems/ext4/directory.html>
- <https://raw.githubusercontent.com/torvalds/linux/master/fs/namei.c>

### 3.3 macOS

- **APFS** (FAQ): "APFS accepts only valid UTF-8 encoded filenames for
  creation, and preserves both case and normalization of the filename on disk
  in all variants." Case-insensitive is the macOS default. Since High Sierra,
  APFS "is normalization-insensitive in both the case-insensitive and
  case-sensitive variants". It rejects code points unassigned in Unicode 9.0.
  The early iOS 10.3 / Sierra-preview case-sensitive APFS was
  normalisation-sensitive.
- **APFS on disk** (Reference PDF, rev. 2020-06-22): names are
  null-terminated UTF-8; the length field is 10 bits; the lookup hash uses NFD
  then CRC-32C. No 255 limit is stated.
- **xnu** `syslimits.h`: `NAME_MAX 255` ("max bytes in a file name") with the
  note "Many filesystems (including HFS & APFS) may support names longer than
  `NAME_MAX` bytes", and `PATH_MAX 1024`.
- **HFS+** (TN1150): "up to 255 Unicode characters", typed `HFSUniStr255` of
  16-bit units. "HFS Plus stores strings fully decomposed and in canonical
  order", compares case-insensitively; HFSX is case-sensitive. U+2000–U+2FFF
  are not fully decomposed, so it is an NFD variant, not exact NFD.
- **`:` ↔ `/` mapping**: no Apple documentation page states it (File System
  Programming Guide and TN1150 are silent). Apple's own source does: xnu
  `bsd/vfs/vfs_utfconv.c`, "In Mac OS X the slash is illegal in a file name.
  So for us the colon is a slash and a slash is a colon"; HFS
  `core/hfs_catalog.c` passes `':'` as the alternate slash. An Apple DTS
  engineer on the developer forums: a file created as `Hello/Cruel/World!.txt`
  through the Carbon API lists as `Hello:Cruel:World!.txt` in `ls`. So `:` is a
  legal POSIX-layer character that the Finder shows as `/`.

Sources:

- <https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/APFS_Guide/FAQ/FAQ.html>
- <https://developer.apple.com/support/downloads/Apple-File-System-Reference.pdf>
- <https://developer.apple.com/library/archive/technotes/tn/tn1150.html>
- <https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/bsd/sys/syslimits.h>
- <https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/bsd/vfs/vfs_utfconv.c>
- <https://raw.githubusercontent.com/apple-oss-distributions/hfs/main/core/hfs_catalog.c>
- <https://developer.apple.com/forums/thread/850144>

### 3.4 Windows

- **Reserved characters** (Naming Files): `< > : " / \ | ? *`, NUL, and 1–31
  "except for alternate data streams".
- **Reserved names**: "CON, PRN, AUX, NUL, COM1 … COM9, COM¹, COM², COM³,
  LPT1 … LPT9, LPT¹, LPT², and LPT³". With any extension too: "NUL.txt and
  NUL.tar.gz are both equivalent to NUL". COM0 and LPT0 are **not** on the
  list (OneDrive's list does include them, see § 3.9).
- **Trailing space or period**: "Do not end a file or directory name with a
  space or a period", framed as a shell/UI limitation. In practice Win32
  normalisation (.NET "File path formats" § Path normalization) removes a
  single trailing period from each segment and, when the path has no trailing
  separator, all trailing periods and spaces from the last segment. A name
  like `hidden.` is reachable only through `\\?\`.
- **Separators**: `/` is converted to `\` except under `\\?\`; "a series of
  slashes that follow the first two slashes are collapsed into a single slash".
- **Dot segments**: "Parent directories are only removed if they aren't past
  the root of the path." `\\?\` disables all parsing.
- **Length** (Maximum Path Length Limitation): `MAX_PATH` 260 including drive
  and NUL; extended paths about 32 767 ("approximate"); components "commonly
  255", really the volume's `lpMaximumComponentLength`. The filesystem
  comparison page gives 32 760 and 255 "Unicode characters" for NTFS, exFAT
  and FAT32; the ReFS overview gives 255 "Unicode characters" per name and
  "32K Unicode characters" per path, the same as NTFS. Removing `MAX_PATH` needs **both** `LongPathsEnabled = 1` and the
  `longPathAware` manifest element. Directory creation without opt-in is
  limited to `MAX_PATH − 12`.
- **Case**: case-insensitive and case-preserving. Per-directory case
  sensitivity via `fsutil file setCaseSensitiveInfo` since Windows 10 build
  17107, NTFS only, on empty directories.
- **Encoding**: "the file system treats path and file names as an opaque
  sequence of WCHARs", with no Unicode normalisation.
- **Python**: `os.path.isreserved` (Windows, 3.13+) approximates these rules
  and is deliberately over-inclusive (adds `CONIN$`, `CONOUT$`).
  `PurePath.is_reserved()` was removed in 3.15.

Sources:

- <https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file>
- <https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation>
- <https://learn.microsoft.com/en-us/dotnet/standard/io/file-path-formats>
- <https://learn.microsoft.com/en-us/windows/win32/fileio/filesystem-functionality-comparison>
- <https://learn.microsoft.com/en-us/windows/wsl/case-sensitivity>
- <https://learn.microsoft.com/en-us/windows-server/storage/refs/refs-overview>
- <https://docs.python.org/3/library/os.path.html>

### 3.5 Python: `pathlib`, `os.path` and filename decoding

Python is not a backend, but its path model is the one developers bring to a
key. `pathlib` and `os.path` normalise lexically, without touching a
filesystem, and they disagree with each other and with the backends above.
Docs as of Python 3.15.1.

**Pure paths do no I/O.** "Pure path objects provide path-handling operations
which don't actually access a filesystem." `PurePosixPath` and
`PureWindowsPath` can be instantiated on any system.

**Construction** (`PurePath(*pathsegments)`): "Spurious slashes and single dots
are collapsed, but double dots (`'..'`) and leading double slashes (`'//'`) are
not, since this would change the meaning of a path for various reasons (e.g.
symbolic links, UNC paths)". More than two leading slashes collapse to one
(`PurePosixPath('///etc').root` is `'/'`). Trailing slashes are dropped: "pathlib
normalizes `Path("my_folder/")` to `Path("my_folder")`". An empty path is `.`:
"When *pathsegments* is empty or consists only of empty strings, the current
directory is assumed". "If a segment is an absolute path, all previous segments
are ignored". `..` is removed only by `Path.resolve()` ("this is the only method
to do so"), which touches the filesystem.

**`os.path.normpath`** goes further: it collapses "redundant separators and
up-level references so that `A//B`, `A/B/`, `A/./B` and `A/foo/../B` all become
`A/B`. This string manipulation may change the meaning of a path that contains
symbolic links." On Windows it also converts `/` to `\`.

| Input | `PurePosixPath` | `os.path.normpath` (POSIX) | Same key on S3 / Azure flat? |
| --- | --- | --- | --- |
| `a//b` | `a/b` | `a/b` | Distinct (§ 3.6, § 3.7) |
| `a/./b` | `a/b` | `a/b` | Distinct, if stored literally |
| `a/../b` | `a/../b` | `b` | Distinct; S3 checks the `..` count rule |
| `a/` | `a` | `a` | Distinct; `a/` is an S3 folder marker |
| `//a` | `//a` | `//a` | Distinct |
| `` (empty) | `.` | `.` | No key (S3 minimum length 1) |

The two Python columns were run on CPython 3.14.8 (`PurePosixPath(s)` and
`posixpath.normpath(s)` for each input) and match the 3.15 docs. The last column
is the gap: inputs pathlib treats as equal can be distinct keys on a flat
store.

**Case** follows the flavour: `PurePosixPath('foo') == PurePosixPath('FOO')` is
`False`, `PureWindowsPath('foo') == PureWindowsPath('FOO')` is `True`. Matching
(`full_match`, `glob`) follows the same platform default, overridable with
`case_sensitive=` (3.12+). `os.path.normcase` lowercases on Windows and returns
the path unchanged elsewhere. No case or Unicode normalisation happens on
POSIX, and the pathlib docs never mention Unicode normalisation.

**Windows flavour**: UNC shares count as drives
(`PureWindowsPath('//host/share/foo.txt').drive` is `\\host\share`), a rooted
segment such as `\foo` keeps the current drive, and `/` is accepted on input
and rendered as `\`. Reserved-name checks moved to `os.path.isreserved`
(§ 3.4).

**URIs**: `Path.as_uri()` and `Path.from_uri()` produce and parse `file:` URIs
"conforming to RFC 8089", absolute paths only. "File URIs are not portable
across machines with different filesystem encodings."

**Filename decoding.** Paths are `str`. On POSIX, Python decodes filenames with
the filesystem encoding and `surrogateescape`: undecodable bytes ≥ 128 become
lone surrogates U+DC80–U+DCFF and round-trip on encode (PEP 383; `os` docs).
Windows uses `surrogatepass`. UTF-8 mode is the default from Python 3.15 (PEP
686); on macOS the filesystem encoding is UTF-8 regardless. So a
surrogate-escaped `str` round-trips on Linux, while APFS refuses to create the
non-UTF-8 name (follows from the APFS FAQ; not run). `bytes(path)` gives the
`os.fsencode()` form, "only recommended under Unix"; pathlib, unlike `os`,
accepts no `bytes` paths.

Sources:

- <https://docs.python.org/3/library/pathlib.html>
- <https://docs.python.org/3/library/os.path.html>
- <https://docs.python.org/3/library/os.html>
- <https://docs.python.org/3/c-api/init_config.html>
- <https://peps.python.org/pep-0383/>

### 3.6 Amazon S3

**General-purpose buckets** ("Naming Amazon S3 objects"):

- "a sequence of Unicode characters encoded in UTF-8, with a maximum length of
  1,024 bytes"; prefix and delimiter count toward it. `PutObject`: minimum
  length 1. "Object key names are case sensitive."
- "The Amazon S3 data model is a flat structure … There is no hierarchy of
  subbuckets or subfolders." Console folders are zero-byte `prefix/` objects.
- "You can use any UTF-8 character in an object key name." The page then grades
  characters: **safe** (`0-9 a-z A-Z ! - _ . * ' ( )`), **might require special
  handling** (`& $ @ = ; / : + , ?`, space, 0x00–0x1F, 0x7F), **avoid**
  (`\ { } ^ % \` [ ] " < > ~ # |`, bytes 128–255).
- **Hard `..` rule**, all access paths: keys with `../` "are valid if, when
  parsed left-to-right, the cumulative count of relative path segments never
  exceeds the number of non-relative path elements encountered".
  `videos/2014/../../video1.wmv` is valid, `videos/../../video1.wmv` is not.
- **Period-only segments** (`.`, `..`): avoid; tools may resolve them.
- **Console-only limits**: keys with a `./` prefix and keys ending in `/`
  cannot be uploaded through the console (REST, CLI and SDK can); console
  download strips trailing periods.
- **XML**: `ListObjectsV2` cannot carry characters such as 0–10 in XML 1.0;
  `encoding-type=url` encodes `Delimiter`, `Prefix`, `Key`, `StartAfter`. In
  XML request bodies CR/CRLF normalise to LF unless entity-encoded.
- Keys sort "lexicographically by their UTF-8 encoded byte values".

**Directory buckets** (S3 Express One Zone):

- "organize data hierarchically into directories". "The only supported
  delimiter is a forward slash (`/`)." Directories are created with the first
  key and empty ones are deleted recursively on object delete.
- `ListObjectsV2`: prefixes must end in `/`; results unsorted; no `StartAfter`.
- `DeleteObjects` keys "must contain at least one non-white space character"
  and "cannot contain Unicode control characters, except for" `\n \t \r`.
- `RenameObject` "will not succeed on objects that end with the slash (`/`)".
- "Directories are created during `PutObject` or `CreateMultiPartUpload`
  operations and automatically removed when they become empty"; "There is no
  upper limit to the number of objects and subdirectories in a directory"
  (performance design patterns page). No maximum depth or per-segment length
  is documented.
- **Not documented by AWS** (second search, 2026-10-21, covering the
  directory-bucket user-guide pages, the `PutObject`, `ListObjectsV2`,
  `DeleteObjects` and `RenameObject` API pages, and web searches): `//` or
  empty segments; `.` or `..` segments, including whether the general-purpose
  `..` counting rule applies; `PutObject` of a key ending in `/`; leading `/`.
  These are settled only by a live probe against a directory bucket.

**`//` in general-purpose buckets**: no AWS document states it. AWS SDK issue
reports (aws/aws-cli#6253, aws/aws-sdk-go#2559, not AWS-staff statements)
show `A` and `//A` as distinct objects, and SDK-side URI cleaning as the cause
of 404s on such keys. Indicative only.

Sources:

- <https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-keys.html>
- <https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-folders.html>
- <https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html>
- <https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html>
- <https://docs.aws.amazon.com/AmazonS3/latest/userguide/directory-buckets-overview.html>
- <https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-express-differences.html>
- <https://docs.aws.amazon.com/AmazonS3/latest/userguide/directory-buckets-objects-rename.html>
- <https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-express-optimizing-performance-design-patterns.html>

### 3.7 Azure Blob Storage and ADLS Gen2

"Naming and Referencing Containers, Blobs, and Metadata" (updated 2026-07-21):

- Violations fail with `400 Bad Request`. Some characters "are not valid in URL
  paths even when encoded" and may fail.
- **Blob name**: "any combination of characters", 1–1024 characters (legacy
  emulator: 256), case-sensitive, reserved URL characters escaped. Control
  characters 0x00–0x1F and invalid code points "are also not allowed".
- **Segments**: flat accounts ≤ 254; HNS accounts ≤ 63 "including path segments
  for account name and container name".
- **Advisory**: "Avoid blob names that end with a dot (.), a forward slash (/),
  a backslash (\), or a sequence or combination of the two. No path segments
  should end with a dot (.)." Same note for HNS directory names. Not a
  rejection.
- **Not recommended**: U+0080–U+009F (with gaps), U+FDD1–U+FDEF, U+FFF0–U+FFFF,
  U+nFFFE/nFFFF: they "may fail UTF-8 or MBCS decoding".
- **Flat by default**: a delimiter creates a virtual hierarchy; `/a`, `/a.txt`,
  `/a/b`, `/a/b.txt` coexist.
- **HNS**: real directories; directory names 1–1024 characters, case-sensitive.
  `/` is the only supported delimiter (Data Lake known issues). HNS cannot be
  reverted to flat. "Path - Create" gives no path constraint beyond the
  `InvalidResourceName` and `PathConflict` errors.
- **Container / filesystem names** (the source of the often-misattributed "63"):
  3–63 characters, lowercase letters, digits, `-`, no `--`; ADLS also allows a
  leading `$` (for `$root`).
- **HNS lengths**: the only documented limits are 1–1024 characters per
  directory name and the 63-segment cap; a Microsoft Q&A answer by a `-MSFT`
  handle confirms "the max depth of directories are 63 (including account name
  and container name) not 254". No per-segment 255 limit exists in ADLS docs;
  that figure belongs to Azure Files: "Individual components in the path can
  be a maximum of 255 characters in length" (Naming and Referencing Shares,
  Directories, Files, and Metadata).
- **Trailing dots, Azure Files only**: the Files naming page states that by
  default "dot (.) characters at the end of directory and file names in
  request URLs are ignored or left out", unless the `x-ms-allow-trailing-dot`
  header is set (version 2022-11-02 on). No Blob or Data Lake page states the
  same for blob names; a search on 2026-10-22 found none. § 5 measured it on
  an HNS account.
- **Backslash**: no learn.microsoft.com page states a conversion. A merged
  Microsoft PR in azure-sdk-for-python (#48883, 2026-09-04) states "The service
  canonicalizes `\` to `/` when it rebuilds the signed resource to validate the
  signature"; the .NET SDK's `BlobSasBuilder.GetCanonicalName` does
  `blobName.Replace("\\", "/")`. That is signature validation; whether the
  stored name changes is not stated.
- **Client side, Python SDK** (azure-storage-blob 12.31.0,
  azure-storage-file-datalake 12.26.0, requests 2.34.2, urllib3 2.8.0; URL
  captured by patching `requests.Session.send`, no network):
    - The SDK quotes names with `quote(name, safe='~/')` and does not
      normalise, but urllib3's `parse_url` removes dot segments before
      sending: `a/./b` → `/c/a/b`, `a/../b` → `/c/b`, and `x/../../b` → `/b`,
      a request **outside the container**, for both blob and datalake
      clients.
    - `%2E` is no workaround: the SDK re-quotes it to `%252E`, storing the
      literal text `%2E`.
    - `a//b` is sent unchanged. The datalake path client strips leading and
      trailing `/` (`path_name.strip("/")`); `BlobClient` does not.
    - `\` is sent as `%5C`, unconverted.
- **Not documented by Microsoft** (second search, 2026-10-21): how the service
  treats raw `.`, `..`, `//` or `\` in a name on either endpoint. Azurite
  (non-authoritative) stores `//` literally and converts `\` to `/` with the
  comment "Azure Storage Server will replace '\' with '/' in the blob names"
  (its quote marks rendered as `'` here).
  Settled only by a live probe that bypasses client normalisation (for example
  `curl --path-as-is`). § 5 records such a probe against an HNS account; the
  flat namespace is still unmeasured.

Sources:

- <https://learn.microsoft.com/en-us/rest/api/storageservices/naming-and-referencing-containers--blobs--and-metadata>
- <https://learn.microsoft.com/en-us/rest/api/storageservices/datalakestoragegen2/path/create>
- <https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-known-issues>
- <https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-namespace>
- <https://learn.microsoft.com/en-us/rest/api/storageservices/naming-and-referencing-shares--directories--files--and-metadata>
- <https://learn.microsoft.com/en-us/answers/questions/234817/data-lake-storage-gen2-this-operation-is-not-permi>
- <https://github.com/Azure/azure-sdk-for-python/pull/48883>
- <https://raw.githubusercontent.com/Azure/Azurite/main/src/blob/middlewares/blobStorageContext.middleware.ts>

### 3.8 SFTP

- **What runs in practice**: OpenSSH implements protocol version 3, defined in
  draft-ietf-secsh-filexfer-**02** (`PROTOCOL` §4; openssh.org specs page).
- **§6.2 File Names** (-02): "This protocol represents file names as strings."
  "File names are assumed to use the slash ('/') character as a directory
  separator." Absolute names start at the filesystem root, others are relative
  to the user's home. "Servers SHOULD interpret a path name component '..' as
  referring to the parent directory, and '.' as referring to the current
  directory." "An empty path name is valid, and it refers to the user's default
  directory". "Otherwise, no syntax is defined for file names by this
  specification."
- **Encoding**: none specified for names in v3 (UTF-8 appears only for status
  messages). UTF-8 filenames come with v6 (draft -13: "A server that does not
  send this extension MUST send all filenames encoded in UTF-8"), which OpenSSH
  does not implement.
- **REALPATH** (§6.11) canonicalises to an absolute path; the canonical form is
  server-defined.
- **OpenSSH extensions**: `posix-rename@openssh.com` (v3 `RENAME` is not POSIX
  rename), `hardlink@openssh.com`, `expand-path@openssh.com` (tilde expansion),
  `home-directory`, `limits@openssh.com`. `SSH_FXP_SYMLINK` arguments are
  reversed relative to the draft and that order was kept.
- **IETF status**: the SSHM working group charter includes documenting SFTP
  "as they are currently implemented", but there is no adopted document.
  `draft-ietf-sshm-filexfer` does not exist. The only candidate is the expired
  individual draft `draft-spaghetti-sshm-filexfer-00` (2025-07-01), still v3,
  still "no syntax is defined for file names", adding that servers must stop
  `..` escaping access limits.
- **Consequence**: the effective rules are the **server's filesystem** (usually
  POSIX, see § 3.2), reached through opaque strings.

Sources:

- <https://datatracker.ietf.org/doc/html/draft-ietf-secsh-filexfer-02>
- <https://datatracker.ietf.org/doc/html/draft-ietf-secsh-filexfer-13>
- <https://www.openssh.org/specs.html>
- <https://raw.githubusercontent.com/openssh/openssh-portable/master/PROTOCOL>
- <https://datatracker.ietf.org/wg/sshm/about/>
- <https://datatracker.ietf.org/doc/draft-spaghetti-sshm-filexfer/>

### 3.9 Microsoft Graph (OneDrive, SharePoint)

- **Invalid characters** (Restrictions and limitations): `" * : < > ? / \ |`;
  "You can't use leading and trailing spaces in file or folder names." `#` and
  `%` are unsupported in some organisations until an admin enables them.
- **Invalid names**: ".lock, CON, PRN, AUX, NUL, COM0 - COM9, LPT0 - LPT9,
  _vti_, desktop.ini, any filename starting with ~$"; "_vti_" is banned anywhere
  in a name. A folder name cannot start with `゛` or `ဧ`. Whether a reserved
  name with an extension (`CON.txt`) is blocked is not documented by Microsoft
  (second search, including KB 2933738, which covers only the legacy groove.exe
  client); needs a test upload.
- **Path length**: decoded. SharePoint limits service description
  (2026-10-06): "The entire decoded file path, including the file name, can't
  contain more than 400 characters … The limit applies to the combination of
  the folder path and file name after decoding." A Microsoft Q&A staff answer
  (2024-08-01) agrees: "the path length of a file is calculated based on
  decoding." The count is over the server-relative path ("The server relative
  path to a file or folder has a total maximum of 400 characters", migration
  assessment docs). One support article contradicts this on the same page: its
  table says "decoded", its how-to section says "special characters are
  URL-encoded and count toward the 400-character limit".
- **Case**: "File system path identifiers used with colons … and filenames
  specified in the URL … are *not* case-sensitive"; "`:/Folder-A/Foo.txt` is
  treated the same as `:/folder-a/foo.TXT`". Names are stored and returned as
  given. That `a.txt` and `A.txt` cannot coexist in one folder follows from
  case-insensitive lookup; no page states it outright.
- **URL length**: no general Graph limit is documented. Two pages give 2,048
  characters in narrow contexts: Graph known issues, for `$filter` with
  advanced query capabilities; and the OneDrive file-handlers page (ms.date
  2017-09-10), on activation URLs, "less than the maximum URL length of 2048
  characters", without saying which component imposes that maximum.
- **Graph addressing**: colon syntax `/drive/root:/path/to/file:/content`.
  "Microsoft Graph expects that URLs conform to RFC 3986"; characters outside
  `pchar` (e.g. `#`, space) must be percent-encoded; encode the segment, not
  the whole URL. Path addresses break on rename or move; item IDs do not.
- **Graph reserved ABNF**: `/ \ * < > ? : |`, business adds `# %`. Omits `"`,
  which the support page lists. The Graph page alone adds "Folder names can't
  end with a period" and "File or folder names cannot begin with a tilde".

Sources:

- <https://support.microsoft.com/en-us/office/restrictions-and-limitations-in-onedrive-and-sharepoint-64883a5d-228e-48f5-b3d2-eb39e07630fa>
- <https://support.microsoft.com/en-us/onedrive/what-are-file-path-length-limits>
- <https://learn.microsoft.com/en-us/office365/servicedescriptions/sharepoint-online-service-description/sharepoint-online-limits>
- <https://learn.microsoft.com/en-us/answers/questions/1850459/sharepoint-file-path-length-encoded-or-decoded>
- <https://learn.microsoft.com/en-us/sharepointmigration/migration-assessment-scan-long-onedrive-urls>
- <https://learn.microsoft.com/en-us/onedrive/developer/rest-api/concepts/case-sensitivity?view=odsp-graph-online>
- <https://learn.microsoft.com/en-us/graph/onedrive-addressing-driveitems>
- <https://learn.microsoft.com/en-us/graph/known-issues>
- <https://learn.microsoft.com/en-us/onedrive/developer/file-handlers/?view=odsp-graph-online>

---

## 4. Open points

No source settles these, after two rounds of search:

- S3 directory buckets: `//`, empty, `.`, `..` segments; PUT of a key ending
  in `/`; leading `/`. AWS documents none of these; needs a live probe. § 5's
  probe covers them, but its 2026-10-22 run could not create a bucket.
- S3 general-purpose: `//` stored literally (indicative SDK issue reports
  only). § 5's probe covers it; the same run was refused at authentication.
- Azure flat namespace: service treatment of raw `.`, `..`, `//` and `\`.
  Microsoft documents none; needs a live probe with an unnormalised request
  path. The HNS endpoint is measured in § 5; Azurite, a flat emulator, is not
  an authority for the service.
- Graph: whether a reserved name with an extension (`CON.txt`) is blocked.
  Microsoft documents it nowhere; needs a test upload.
- Graph: that `a.txt` and `A.txt` cannot coexist is inferred from
  case-insensitive lookup, not stated.
- Graph: `.`, `..` and empty segments in a path, and a trailing `/`. No
  Microsoft page cited in § 3.9 states them, and a web search on 2026-10-22
  found none; needs a live probe.

---

## 5. Measured: raw keys against a service and local implementations (2026-10-22)

This section is not an authority. It records what one Azure account and three
local implementations did with eleven raw keys on one day.

**Method.** The script is
[`bk-484-key-model/probes/probe_paths.py`](bk-484-key-model/probes/probe_paths.py),
and its output is
[`results-2026-10-22.json`](bk-484-key-model/probes/results-2026-10-22.json),
which carries no account, resource, region or zone name.

- For each key, the script sends a PUT byte for byte through `http.client`,
  so no SDK or urllib3 step rewrites the path (§ 3.7).
- It then lists the target and sends a GET on the same raw path.
- Azure requests use a container SAS and `x-ms-version: 2023-11-03`. S3
  requests are signed with botocore's `S3SigV4Auth`, which leaves the path
  as is.
- SFTP goes through paramiko, which sends path strings unchanged. The
  directories `a`, `e` and `g` are created first, because POSIX resolution is
  physical.
- Each target gets a fresh bucket, container or folder, deleted afterwards.

**Targets.**

- An Azure storage account with HNS (`is_hns_enabled` true), through the
  blob endpoint. The DFS endpoint was not probed.
- Azurite 3.35.0, a flat emulator.
- MinIO, Chainguard image `latest-dev`, unpinned.
- OpenSSH in `atmoz/sftp:alpine`, chrooted with home `/`.

AWS was not measured. The general-purpose bucket's `CreateBucket` was refused
with `InvalidAccessKeyId` (the stored key no longer exists). The directory
bucket's `CreateBucket` was refused with `AccessDenied` in all six zone IDs
tried, with the same key, so whether the account's policy would allow a
directory bucket is not known.

| Key sent | Azure HNS (service) | Azurite (emulator) | MinIO | OpenSSH |
| --- | --- | --- | --- | --- |
| `p/plain` (control) | stored as sent | as sent | as sent | as sent |
| `p/...` | PUT 400 `InvalidUri`; a GET on the path answers 200 | as sent | as sent | as sent |
| `p/a//b` | `p/a/b` | as sent | 400 `XMinioInvalidObjectName` | `a/b` |
| `p//c` | `p/c` | as sent | 400 `XMinioInvalidObjectName` | `c` |
| `p/./d` | `p/d` | as sent | 400 `XMinioInvalidResourceName` | `d` |
| `p/e/../f` | `p/f` | as sent | 400 `XMinioInvalidResourceName` | `f` |
| `p/g/` | PUT 400 `InvalidUri` | as sent | as sent | refused (`SSH_FX_FAILURE`) |
| `/p/h` | `p/h` | as sent | `p/h` | the same file as `p/h` |
| `p/i\j` | `p/i/j`, and a directory `p/i` | `p/i/j` | as sent | as sent |
| `p/k.` | `p/k` | as sent | as sent | as sent |
| `p/../../x` | 403 `AuthenticationFailed` | as sent | 400 `XMinioInvalidResourceName` | refused (`EACCES`) |

OpenSSH names are relative to the probe folder. Both local runs gave the same
results.

**Readings.**

- **The Azure HNS service rewrites a raw path.** It collapses empty segments,
  drops a leading `/`, removes `.`, resolves `..`, converts `\` to `/` and
  strips a trailing `.`. Each rewritten key was stored under a name other than
  the one sent, with no error. Microsoft documents the trailing-dot rule only
  for Azure Files (§ 3.7). The `p/...` row fits dot-stripping leaving an
  empty name, and the 200 on its GET fits that GET reaching the directory `p`.
  Both are inferences; neither was probed separately.
- **On Azure, `..` resolves before authorisation.** The 403 means the
  resolved path lay outside the container the SAS covers. Under a credential
  that covers the whole account (an account key or an account SAS), the same
  request would be authorised against the resolved path. That is an
  inference; it was not run.
- **Azurite differs from the service on every row except the control and
  `\`.** It stores the other keys as sent.
- **MinIO refuses empty, `.` and `..` segments and drops a leading `/`.**
  What AWS does with these remains open (§ 4).
- **OpenSSH resolves paths in the server's filesystem.** A `..` above the
  chroot root lands at the root (`/..` is `/`, § 3.2), where the write was
  refused by permission, not by a path rule.

---

## 6. Using this reference

§ 2 is the overview; cite the § 3 subsection, not the table, for any claim
that rests on a backend's rule. Treat the points of § 4 as unknown, not as
permitted. § 5 is one day's measurement of one instance per target; cite it
as such, never as a rule.
