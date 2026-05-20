// BackendContract.dfy. Formal specification of the remote-store backend
// behavioural contract.  Covers the six BK-140 gaps identified in
// research-backend-contract-completeness.md:
//
//   Gap 1  BE-008   Precondition evaluation order
//   Gap 2  BE-021   Canonical error-mapping table
//   Gap 3  BE-014/015  Listing on missing paths yields empty
//   Gap 4  DEPTH-001   Reference depth-counting algorithm
//   Gap 5  BE-018      Move atomicity is backend-dependent
//   Gap 6  SIO-001     Acquire-then-wrap resource safety
//
// This module defines the *abstract* contract.  Concrete refinements
// (MemoryBackend.dfy) prove that an implementation can satisfy every
// postcondition.
//
// Postcondition conventions:
// - All "was it there?" precondition checks use old(fs) so that
//   post-state mutations do not affect error-path reasoning.
// - Error-path frame conditions (fs == old(fs) on error) cannot be
//   encoded as postconditions because `r.Err?` taints method bodies
//   as specification-only in Dafny.  The MemoryBackend refinement
//   preserves fs on error paths by construction (only mutates fs on
//   the success path).  This means the frame condition is verified
//   for the reference implementation but NOT enforced by the abstract
//   contract. See gap coverage table in README.
// - Happy-path postconditions use `ensures <preconditions> ==> r.Ok?`
//   to mandate success when no error condition applies.

// ---------------------------------------------------------------------------
// §1  Error model  (maps _errors.py)
// ---------------------------------------------------------------------------

datatype Error =
  | NotFound(path: string, backend: string)
  | AlreadyExists(path: string, backend: string)
  | PermissionDenied(path: string, backend: string)
  | InvalidPath(path: string, backend: string)
  | CapabilityNotSupported(capability: string, backend: string)
  | DirectoryNotEmpty(path: string, backend: string)
  | BackendUnavailable(backend: string)

datatype Result<T> = Ok(value: T) | Err(error: Error)

// ---------------------------------------------------------------------------
// §2  Capabilities  (maps _capabilities.py)
// ---------------------------------------------------------------------------

datatype Capability =
  | CapRead | CapWrite | CapDelete | CapList | CapMove | CapCopy
  | CapAtomicWrite | CapAtomicMove | CapMetadata | CapGlob | CapSeekableRead
  // ID-151 / spec 045: WriteResult provenance + user metadata gate.
  // CapWriteResultNative is a quality flag (WR-009); does not gate any
  // method. CapUserMetadata is a strict gate on the `metadata=` kwarg
  // (WR-010, ADR-0026).
  | CapWriteResultNative | CapUserMetadata

// CapGlob is defined but the Glob method is intentionally excluded
// from this contract: it is a capability-gated convenience method
// with no unique postcondition structure (it delegates to ListFiles +
// pattern matching).
type CapabilitySet = set<Capability>

// ---------------------------------------------------------------------------
// §3  Data models  (maps _models.py)
// ---------------------------------------------------------------------------

type Path = s: string | s != "" witness "a"

// ID-151 / spec 045: optional rich-field slots on FileInfo and
// WriteResult.  The verifier does not reason about hash algorithms
// or clock values; it reasons about field presence and identity only.
datatype Option<T> = None | Some(value: T)

// Backend-echoed or client-verified content digest (spec 035).
datatype ContentDigest = ContentDigest(kind: string, value: string)

// WriteResult source provenance (WR-004, WR-006).  Native = rich
// fields populated from the backend write response.  Basic = only
// path/size guaranteed.  Sidecar = constructed from a subsequent
// FileInfo read (head()/WriteResultFromFileInfo).
datatype WriteSource = NativeSource | BasicSource | SidecarSource

datatype FileInfo = FileInfo(
  path: Path,
  name: string,
  size: nat,
  // Optional rich fields (spec 045 WR-013 round-trip surface).
  // No `version_id` slot: in v1 backends FileInfo does not carry a
  // version identifier (only WriteResult does, populated from the
  // SDK write response and not round-tripped via get_file_info).
  // Spec 045 WR-008 encodes this: head()-produced WriteResult has
  // version_id = None because there is no FileInfo source.
  //
  // Python-name map (see spec 045 WR-008 table):
  //   last_modified → Python FileInfo.modified_at (field rename).
  //   digest, etag, metadata → same names in Python FileInfo.
  digest: Option<ContentDigest>,
  etag: Option<string>,
  last_modified: Option<int>,
  metadata: Option<map<string, string>>
)

// WR-001a: normative WriteResult field schema.  Every other WR-
// invariant is expressed against this shape.
datatype WriteResult = WriteResult(
  path: Path,
  size: nat,
  digest: Option<ContentDigest>,
  etag: Option<string>,
  version_id: Option<string>,
  last_modified: Option<int>,
  metadata: Option<map<string, string>>,
  source: WriteSource
)

datatype FolderEntry = FolderEntry(
  path: Path,
  name: string
)

datatype FolderInfo = FolderInfo(
  path: Path,
  name: string,
  file_count: nat,
  total_size: nat
)

// Constructor helper for the default rich-field-empty FileInfo: keeps
// refinement code terse when a backend does not populate rich fields.
function BasicFileInfo(path: Path, name: string, size: nat): FileInfo
{
  FileInfo(path, name, size, None, None, None, None)
}

// Whether a metadata mapping should be treated as "user metadata
// supplied" for the purposes of the WR-010 gate (WR-010 empty-mapping
// carve-out: None and {} are both treated as no-metadata).
predicate HasUserMetadata(m: Option<map<string, string>>)
{
  m.Some? && |m.value| > 0
}

// ---------------------------------------------------------------------------
// §4  Filesystem model
// ---------------------------------------------------------------------------

datatype Entry =
  | FileEntry(content: seq<nat>, info: FileInfo)
  | DirEntry

type Filesystem = map<Path, Entry>

predicate IsFile(fs: Filesystem, p: Path)
{
  p in fs && fs[p].FileEntry?
}

predicate IsDir(fs: Filesystem, p: Path)
{
  p in fs && fs[p].DirEntry?
}

predicate PathExists(fs: Filesystem, p: Path)
{
  p in fs
}

// Whether any file or directory in `fs` has `dir` as a parent prefix.
predicate HasChildren(fs: Filesystem, dir: Path)
{
  exists p: Path :: p in fs && IsChildOf(p, dir)
}

lemma EntryPartition(fs: Filesystem, p: Path)
  ensures PathExists(fs, p) <==> (IsFile(fs, p) || IsDir(fs, p))
  ensures !(IsFile(fs, p) && IsDir(fs, p))
{
  if p in fs {
    match fs[p]
    case FileEntry(_, _) =>
      assert IsFile(fs, p);
      assert !IsDir(fs, p);
    case DirEntry =>
      assert IsDir(fs, p);
      assert !IsFile(fs, p);
  }
}

// ---------------------------------------------------------------------------
// §5  Path utilities
// ---------------------------------------------------------------------------

function SlashCount(p: string): nat
{
  if |p| == 0 then 0
  else (if p[0] == '/' then 1 else 0) + SlashCount(p[1..])
}

// Root sentinel: "." represents the virtual root directory.
// Dafny's Path type requires non-empty strings, so the Python
// adapter maps "" → "." at the type boundary, one translation
// point instead of per-method root guards.
const Root: Path := "."

function Depth(root: string, child: string): int
{
  if root == "." then
    (if child == "." then -1 else SlashCount(child))
  else if |child| <= |root| + 1 then -1
  else if child[..|root|] != root then -1
  else if child[|root|] != '/' then -1
  else
    var suffix := child[|root| + 1..];
    SlashCount(suffix)
}

predicate IsChildOf(child: string, parent: string)
{
  if parent == "." then
    child != "."
  else
    |child| > |parent| + 1 &&
    child[..|parent|] == parent &&
    child[|parent|] == '/'
}

// All ancestors of p are directories (no file-as-directory-component).
// Checks only directory-segment-aligned prefixes (those ending with "/" in p).
// A prefix is valid if it either doesn't exist in fs or is a directory, never a file.
predicate AllAncestorsTraversable(fs: Filesystem, p: Path)
{
  forall i: int |
    0 < i < |p| - 1 && p[i] == '/' ::
    !PathExists(fs, p[..i]) || IsDir(fs, p[..i])
}

// ---------------------------------------------------------------------------
// §5b  Aggregate helpers (ID-134)
// ---------------------------------------------------------------------------

// The set of child files under a path.
ghost function ChildFiles(fs: Filesystem, path: Path): set<Path>
{
  set k | k in fs && fs[k].FileEntry? && IsChildOf(k, path)
}

// Convert a finite set to a sequence (ghost, nondeterministic order).
// The multiset-count ensure lets callers prove multiset equality
// between SetToSeq outputs for different sets.
ghost function SetToSeq(s: set<Path>): seq<Path>
  ensures |SetToSeq(s)| == |s|
  ensures forall x :: x in s <==> x in SetToSeq(s)
  ensures forall x :: multiset(SetToSeq(s))[x] == (if x in s then 1 else 0)
  decreases s
{
  if s == {} then []
  else
    var x :| x in s;
    [x] + SetToSeq(s - {x})
}

// Sum file sizes over a sequence of paths (deterministic recursion).
ghost function SumSizesSeq(fs: Filesystem, keys: seq<Path>): nat
  requires forall k | k in keys :: k in fs && fs[k].FileEntry?
{
  if |keys| == 0 then 0
  else fs[keys[0]].info.size + SumSizesSeq(fs, keys[1..])
}

// Sum file sizes over a set: delegates to seq-based sum via SetToSeq.
// Ghost because SetToSeq uses `:|`.
ghost function SumSizes(fs: Filesystem, keys: set<Path>): nat
  requires forall k | k in keys :: k in fs && fs[k].FileEntry?
{
  SumSizesSeq(fs, SetToSeq(keys))
}

// ---------------------------------------------------------------------------
// §6  Backend contract  (abstract trait)
// ---------------------------------------------------------------------------
// Precondition evaluation order (Gap 1 / BE-008) is encoded by the
// implication chain in Write/Delete postconditions.  The first matching
// condition determines the error:
//   1. IsDir(old(fs), path) → InvalidPath   (type check FIRST)
//   2. IsFile(old(fs), path) && !overwrite → AlreadyExists
//   3. otherwise → success (r.Ok?)
// These implications are exclusive by construction: IsDir and IsFile
// are mutually exclusive (EntryPartition lemma), so at most one
// error-path postcondition fires for any given pre-state.

trait Backend {
  const name: string
  const capabilities: CapabilitySet
  var fs: Filesystem

  // ====================================================================
  // exists(path) → bool
  // ====================================================================
  // Returns True iff path exists AND all ancestors are directories.
  // Returns False for missing paths or paths with file-as-directory-component.
  method Exists(path: Path) returns (r: Result<bool>)
    // @spec BE-004
    ensures r.Ok?
    // @spec BE-004
    ensures r.value == (PathExists(fs, path) && AllAncestorsTraversable(fs, path))

  // ====================================================================
  // is_file(path) → bool
  // ====================================================================
  // Returns True iff path is a file AND all ancestors are directories.
  // Returns False for missing paths or paths with file-as-directory-component.
  method IsFileMethod(path: Path) returns (r: Result<bool>)
    // @spec BE-005
    ensures r.Ok?
    // @spec BE-005
    ensures r.value == (IsFile(fs, path) && AllAncestorsTraversable(fs, path))

  // ====================================================================
  // is_folder(path) → bool
  // ====================================================================
  // Returns True iff path is a folder AND all ancestors are directories.
  // Returns False for missing paths or paths with file-as-directory-component.
  method IsFolderMethod(path: Path) returns (r: Result<bool>)
    // @spec BE-005
    ensures r.Ok?
    // @spec BE-005
    ensures r.value == (IsDir(fs, path) && AllAncestorsTraversable(fs, path))

  // ====================================================================
  // read(path) → content  (no modifies: fs unchanged)
  // ====================================================================
  method Read(path: Path) returns (r: Result<seq<nat>>)
    // @spec BE-021
    ensures IsDir(fs, path)       ==> r == Err(InvalidPath(path, name))
    // @spec BE-006
    ensures !PathExists(fs, path) ==> r == Err(NotFound(path, name))
    // @spec BE-006
    ensures IsFile(fs, path)      ==> r == Ok(fs[path].content)

  // ====================================================================
  // write(path, content, overwrite, metadata)
  // ====================================================================
  // Return type widened from Result<()> to Result<WriteResult> per
  // spec 045 WR-001 (ID-151).  The `metadata` parameter carries the
  // WR-010 user-metadata payload; the empty-mapping carve-out is
  // encoded via HasUserMetadata.
  //
  // WR-010 strict gate: HasUserMetadata(metadata) && CapUserMetadata
  // !in capabilities → CapabilityNotSupported before any I/O.
  //
  // Ordering divergence vs the Python implementation: here the WR-010
  // gate fires AFTER the IsDir/IsFile precondition chain, so for a
  // directory-path + non-empty-metadata + non-declaring-backend input
  // the Dafny contract returns InvalidPath while the Python Store layer
  // (which evaluates WR-011 → WR-010 before dispatching to
  // backend.write()) returns CapabilityNotSupported.  This is a known
  // contract-level simplification: Dafny models the Backend trait in
  // isolation; the Store-layer ordering (WR-011) is outside the trait.
  // Tracked in the ID-151 "Out of scope" list.
  method Write(
    path: Path,
    content: seq<nat>,
    overwrite: bool,
    metadata: Option<map<string, string>>
  )
    returns (r: Result<WriteResult>)
    modifies this
    // Gap 1 / BE-008: precondition order — type check first (directory
    // path → InvalidPath).
    // @spec BE-008
    ensures IsDir(old(fs), path)
      ==> r == Err(InvalidPath(path, name))
    // Gap 1 / BE-008: precondition order — overwrite conflict second.
    // @spec BE-008
    ensures !IsDir(old(fs), path) && IsFile(old(fs), path) && !overwrite
      ==> r == Err(AlreadyExists(path, name))
    // WR-010 strict gate: non-empty metadata on a backend without
    // CapUserMetadata → CapabilityNotSupported (pre-I/O).
    // @spec WR-010
    ensures !IsDir(old(fs), path) && (!IsFile(old(fs), path) || overwrite) &&
            HasUserMetadata(metadata) && CapUserMetadata !in capabilities
      ==> r == Err(CapabilityNotSupported(
            CapabilityName(CapUserMetadata), name))
    // BE-008 happy path: no error condition → must succeed.
    // @spec BE-008
    ensures !IsDir(old(fs), path) && (!IsFile(old(fs), path) || overwrite) &&
            (!HasUserMetadata(metadata) || CapUserMetadata in capabilities)
      ==> r.Ok?
    // BE-008: written content is stored verbatim on the success path.
    // @spec BE-008
    ensures r.Ok? ==>
      IsFile(fs, path) && fs[path].content == content
    // WR-001a: WriteResult path and size — the normative field schema.
    // @spec WR-001a
    ensures r.Ok? ==>
      r.value.path == path && r.value.size == |content|
    // WR-004: source is Native iff CapWriteResultNative is declared.
    // @spec WR-004
    ensures r.Ok? ==>
      r.value.source == (
        if CapWriteResultNative in capabilities
        then NativeSource
        else BasicSource)
    // WR-005: Basic source → rich fields are all None.
    // @spec WR-005
    ensures r.Ok? && r.value.source == BasicSource ==>
      r.value.digest.None? && r.value.etag.None? &&
      r.value.version_id.None? && r.value.last_modified.None?
    // WR-012: metadata echo: verbatim when the gate was passed,
    // None otherwise (including the empty-mapping carve-out).
    // @spec WR-012
    ensures r.Ok? ==>
      r.value.metadata == (
        if HasUserMetadata(metadata) && CapUserMetadata in capabilities
        then metadata
        else None)
    // WR-013: user-metadata round-trip: FileInfo carries what was
    // written when the gate was passed.  On a non-declaring backend
    // FileInfo.metadata is None regardless of what was passed.
    // @spec WR-013
    ensures r.Ok? ==>
      fs[path].info.metadata == (
        if HasUserMetadata(metadata) && CapUserMetadata in capabilities
        then metadata
        else None)
    // WR-001a: stored FileInfo reflects the same rich-field shape as
    // WriteResult when CapWriteResultNative is declared.  This
    // postcondition detects *divergence* between WriteResult and the
    // subsequently readable FileInfo: not *absence*: a backend that
    // returns WriteResult with all rich fields None and stores
    // FileInfo with all rich fields None still satisfies this clause
    // vacuously.  Absence of rich-field population by a declaring
    // backend is an empirical quality concern (test assertion, review),
    // not a Dafny-expressible postcondition.
    // @spec WR-001a
    ensures r.Ok? && CapWriteResultNative in capabilities ==>
      fs[path].info.digest == r.value.digest &&
      fs[path].info.etag == r.value.etag &&
      fs[path].info.last_modified == r.value.last_modified

  // ====================================================================
  // delete(path, missing_ok)
  // ====================================================================
  // IsDir → InvalidPath regardless of missing_ok.
  // missing_ok only governs the absent-path case.
  method Delete(path: Path, missing_ok: bool) returns (r: Result<()>)
    modifies this
    // @spec BE-021
    ensures IsDir(old(fs), path)
      ==> r == Err(InvalidPath(path, name))
    // @spec BE-012
    ensures !PathExists(old(fs), path) && !missing_ok
      ==> r == Err(NotFound(path, name))
    // @spec BE-012
    ensures !PathExists(old(fs), path) && missing_ok
      ==> r.Ok?
    // BE-012 happy path: file exists → must succeed.
    // @spec BE-012
    ensures IsFile(old(fs), path) ==> r.Ok?
    // @spec BE-012
    ensures IsFile(old(fs), path) && r.Ok?
      ==> !PathExists(fs, path)

  // ====================================================================
  // delete_folder(path, recursive, missing_ok)
  // ====================================================================
  method DeleteFolder(path: Path, recursive: bool, missing_ok: bool)
    returns (r: Result<()>)
    modifies this
    // File path → InvalidPath (wrong type, symmetric with Delete on dirs).
    // @spec BE-021
    ensures IsFile(old(fs), path)
      ==> r == Err(InvalidPath(path, name))
    // @spec BE-013
    ensures !PathExists(old(fs), path) && !missing_ok
      ==> r == Err(NotFound(path, name))
    // @spec BE-013
    ensures !PathExists(old(fs), path) && missing_ok
      ==> r.Ok?
    // Non-empty directory with recursive=false → DirectoryNotEmpty.
    // @spec BE-013
    ensures IsDir(old(fs), path) && !recursive && HasChildren(old(fs), path)
      ==> r == Err(DirectoryNotEmpty(path, name))
    // BE-013 happy path: empty dir or recursive → must succeed.
    // @spec BE-013
    ensures IsDir(old(fs), path) && (recursive || !HasChildren(old(fs), path))
      ==> r.Ok?
    // On success, directory entry is removed.
    // @spec BE-013
    ensures IsDir(old(fs), path) && r.Ok?
      ==> !IsDir(fs, path)
    // Recursive delete removes all children too.
    // @spec BE-013
    ensures IsDir(old(fs), path) && recursive && r.Ok? ==>
      forall p: Path | IsChildOf(p, path) :: !PathExists(fs, p)

  // ====================================================================
  // list_files(path, recursive, max_depth)
  // ====================================================================
  // Gap 3: never raises NotFound.
  // Gap 4: depth <= max_depth (inclusive).
  // max_depth < 0 means unlimited (no depth filtering).
  // recursive=false constrains results to immediate children (depth 0).
  method ListFiles(path: Path, recursive: bool, max_depth: int)
    returns (r: Result<seq<FileInfo>>)
    // Gap 3 / BE-014: listing is total — never raises NotFound.
    // @spec BE-014
    ensures r.Ok?
    // Gap 3 / BE-014: missing path yields an empty result, not an error.
    // @spec BE-014
    ensures !PathExists(fs, path) ==> r.value == []
    // All results are files that are children of path.
    // @spec BE-014
    ensures r.Ok? ==>
      forall fi | fi in r.value :: IsFile(fs, fi.path) && IsChildOf(fi.path, path)
    // Depth is always non-negative for returned entries (no -1 non-children).
    // @spec BE-014
    ensures r.Ok? ==>
      forall fi | fi in r.value :: Depth(path, fi.path) >= 0
    // recursive=false → only immediate children (depth 0).
    // @spec BE-014
    ensures !recursive && r.Ok? ==>
      forall fi | fi in r.value :: Depth(path, fi.path) == 0
    // Gap 4 / DEPTH-003: backend-native max_depth filtering, inclusive
    // (only when recursive; max_depth < 0 = unlimited).
    // @spec DEPTH-003
    ensures recursive && max_depth >= 0 && r.Ok? ==>
      forall fi | fi in r.value :: Depth(path, fi.path) <= max_depth
    // Completeness: every matching file MUST appear in the result.
    // @spec BE-014
    ensures r.Ok? && PathExists(fs, path) ==>
      forall p: Path | IsFile(fs, p) && IsChildOf(p, path) &&
        (if !recursive then Depth(path, p) == 0
         else if max_depth >= 0 then Depth(path, p) <= max_depth
         else true) ::
        exists fi | fi in r.value :: fi.path == p

  // ====================================================================
  // list_folders(path)
  // ====================================================================
  method ListFolders(path: Path) returns (r: Result<seq<FolderEntry>>)
    // Gap 3 / BE-015: listing is total — never raises NotFound.
    // @spec BE-015
    ensures r.Ok?
    // Gap 3 / BE-015: missing path yields an empty result, not an error.
    // @spec BE-015
    ensures !PathExists(fs, path) ==> r.value == []
    // All results are immediate child directories of path.
    // @spec BE-015
    ensures r.Ok? ==>
      forall fe | fe in r.value :: IsDir(fs, fe.path) && IsChildOf(fe.path, path)
    // Completeness: every immediate child directory MUST appear.
    // @spec BE-015
    ensures r.Ok? && PathExists(fs, path) ==>
      forall p: Path | IsDir(fs, p) && IsChildOf(p, path) ::
        exists fe | fe in r.value :: fe.path == p

  // ====================================================================
  // get_file_info(path) → FileInfo
  // ====================================================================
  method GetFileInfo(path: Path) returns (r: Result<FileInfo>)
    // @spec BE-021
    ensures IsDir(fs, path)       ==> r == Err(InvalidPath(path, name))
    // @spec BE-016
    ensures !PathExists(fs, path) ==> r == Err(NotFound(path, name))
    // @spec BE-016
    ensures IsFile(fs, path)      ==> r.Ok? && r.value == fs[path].info

  // ====================================================================
  // get_folder_info(path) → FolderInfo
  // ====================================================================
  // BE-017: symmetric with GetFileInfo: file path → InvalidPath.
  method GetFolderInfo(path: Path) returns (r: Result<FolderInfo>)
    // @spec BE-021
    ensures IsFile(fs, path)      ==> r == Err(InvalidPath(path, name))
    // @spec BE-017
    ensures !PathExists(fs, path) ==> r == Err(NotFound(path, name))
    // @spec BE-017
    ensures IsDir(fs, path)       ==>
      r.Ok? && r.value.path == path
      && r.value.file_count == |ChildFiles(fs, path)|
      && r.value.total_size == SumSizes(fs, ChildFiles(fs, path))

  // ====================================================================
  // move(src, dst, overwrite)
  // ====================================================================
  // Gap 2: directory src → InvalidPath (not NotFound).
  // Gap 5: atomicity is backend-dependent: backends that guarantee atomic
  //   rename declare CapAtomicMove; others use copy-then-delete.
  //   Postcondition covers only the final state, not intermediate visibility.
  method Move(src: Path, dst: Path, overwrite: bool)
    returns (r: Result<()>)
    modifies this
    // @spec BE-021
    ensures IsDir(old(fs), src)
      ==> r == Err(InvalidPath(src, name))
    // @spec BE-018
    ensures !PathExists(old(fs), src)
      ==> r == Err(NotFound(src, name))
    // Directory destination → InvalidPath (can't overwrite dir with file).
    // @spec BE-021
    ensures IsFile(old(fs), src) && IsDir(old(fs), dst)
      ==> r == Err(InvalidPath(dst, name))
    // @spec BE-018
    ensures IsFile(old(fs), src) && IsFile(old(fs), dst) && !overwrite && src != dst
      ==> r == Err(AlreadyExists(dst, name))
    // BE-018 happy path: file src, dst is not a dir, no overwrite conflict.
    // @spec BE-018
    ensures IsFile(old(fs), src) && !IsDir(old(fs), dst) &&
            (!IsFile(old(fs), dst) || overwrite || src == dst)
      ==> r.Ok?
    // @spec BE-018
    ensures r.Ok? && IsFile(old(fs), src) ==>
      IsFile(fs, dst) &&
      fs[dst].content == old(fs)[src].content &&
      (src != dst ==> !PathExists(fs, src))

  // ====================================================================
  // copy(src, dst, overwrite)
  // ====================================================================
  // Gap 2: directory src → InvalidPath.
  // Self-copy (src == dst) is a no-op, not AlreadyExists.
  method Copy(src: Path, dst: Path, overwrite: bool)
    returns (r: Result<()>)
    modifies this
    // @spec BE-021
    ensures IsDir(old(fs), src)
      ==> r == Err(InvalidPath(src, name))
    // @spec BE-019
    ensures !PathExists(old(fs), src)
      ==> r == Err(NotFound(src, name))
    // @spec BE-021
    ensures IsFile(old(fs), src) && IsDir(old(fs), dst)
      ==> r == Err(InvalidPath(dst, name))
    // @spec BE-019
    ensures IsFile(old(fs), src) && IsFile(old(fs), dst) && !overwrite && src != dst
      ==> r == Err(AlreadyExists(dst, name))
    // BE-019 happy path.
    // @spec BE-019
    ensures IsFile(old(fs), src) && !IsDir(old(fs), dst) &&
            (!IsFile(old(fs), dst) || overwrite || src == dst)
      ==> r.Ok?
    // BK-196 / WR-013: copy preserves user metadata on the destination.
    // Before BK-196 the contract pinned only content, so a refinement
    // that built the destination via BasicFileInfo (metadata dropped)
    // verified cleanly — the exact defect Python carried before BK-192.
    // @spec BE-019, WR-013
    ensures r.Ok? && IsFile(old(fs), src) ==>
      IsFile(fs, src) && IsFile(fs, dst) &&
      fs[dst].content == old(fs)[src].content &&
      fs[dst].info.metadata == old(fs)[src].info.metadata

  // ====================================================================
  // Capability gate
  // ====================================================================
  method RequireCapability(cap: Capability) returns (r: Result<()>)
    // @spec CAP-004
    ensures cap in capabilities ==> r.Ok?
    // @spec CAP-004
    ensures cap !in capabilities ==>
      r == Err(CapabilityNotSupported(CapabilityName(cap), name))
}

// ---------------------------------------------------------------------------
// §7  Capability name helper
// ---------------------------------------------------------------------------

function CapabilityName(c: Capability): string
{
  match c
  case CapRead => "read"
  case CapWrite => "write"
  case CapDelete => "delete"
  case CapList => "list"
  case CapMove => "move"
  case CapCopy => "copy"
  case CapAtomicWrite => "atomic_write"
  case CapAtomicMove => "atomic_move"
  case CapMetadata => "metadata"
  case CapGlob => "glob"
  case CapSeekableRead => "seekable_read"
  case CapWriteResultNative => "write_result_native"
  case CapUserMetadata => "user_metadata"
}

// ---------------------------------------------------------------------------
// §8  Verified properties
// ---------------------------------------------------------------------------

// Gap 2: InvalidPath and NotFound are structurally distinct.
lemma ErrorDiscriminationRead(path: Path, backendName: string)
  ensures var a: Result<()> := Err(InvalidPath(path, backendName));
          var b: Result<()> := Err(NotFound(path, backendName));
          a != b
{
  var a: Result<()> := Err(InvalidPath(path, backendName));
  var b: Result<()> := Err(NotFound(path, backendName));
  assert a != b;
}

// Gap 3: Listing postconditions are total.
lemma ListingIsTotalFunction(fs: Filesystem, path: Path, result: seq<FileInfo>)
  ensures Ok(result).Ok?
  ensures !PathExists(fs, path) ==>
    (var r: Result<seq<FileInfo>> := Ok([]); r.value == [])
{
  assert Ok(result).Ok?;
  if !PathExists(fs, path) {
    var r: Result<seq<FileInfo>> := Ok([]);
    assert r.value == [];
  }
}

// Gap 4: Depth filtering is inclusive.
lemma DepthFilterBoundaryInclusive(root: string, child: string, maxDepth: int)
  requires maxDepth >= 0
  requires Depth(root, child) == maxDepth
  ensures Depth(root, child) <= maxDepth
{
  assert Depth(root, child) == maxDepth;
}

// Write-Read round-trip.
lemma WriteReadConsistency(
  fs: Filesystem, path: Path, content: seq<nat>
)
  requires !IsDir(fs, path)
  requires !IsFile(fs, path)
  ensures var newFs := fs[path := FileEntry(content, BasicFileInfo(path, path, |content|))];
          IsFile(newFs, path) && newFs[path].content == content
{
  var newFs := fs[path := FileEntry(content, BasicFileInfo(path, path, |content|))];
  assert path in newFs;
  assert newFs[path].FileEntry?;
  assert IsFile(newFs, path);
  assert newFs[path].content == content;
}

// Appending one element to a seq-based sum (ID-134).
// Classic induction on |xs|: base |xs|==0 trivial, step follows
// from commutativity of nat addition (a + (b + c) == b + (a + c)).
lemma {:induction false} SumSizesSeqAppend(
  fs: Filesystem, xs: seq<Path>, k: Path
)
  requires forall p | p in xs :: p in fs && fs[p].FileEntry?
  requires k in fs && fs[k].FileEntry?
  ensures SumSizesSeq(fs, xs + [k]) == SumSizesSeq(fs, xs) + fs[k].info.size
  decreases |xs|
{
  if |xs| == 0 {
    assert xs + [k] == [k];
  } else {
    assert (xs + [k])[0] == xs[0];
    assert (xs + [k])[1..] == xs[1..] + [k];
    SumSizesSeqAppend(fs, xs[1..], k);
  }
}

// Removing element at index i from a seq-based sum (ID-134).
// SumSizesSeq(ys) == ys[i].size + SumSizesSeq(ys[..i] + ys[i+1..])
lemma {:induction false} SumSizesSeqRemoveAt(
  fs: Filesystem, ys: seq<Path>, i: int
)
  requires 0 <= i < |ys|
  requires forall p | p in ys :: p in fs && fs[p].FileEntry?
  ensures SumSizesSeq(fs, ys) ==
    fs[ys[i]].info.size + SumSizesSeq(fs, ys[..i] + ys[i+1..])
  decreases i
{
  if i == 0 {
    assert ys[..0] + ys[1..] == ys[1..];
  } else {
    // IH: SumSizesSeq(ys[1..]) == fs[ys[i]].size + SumSizesSeq(ys[1..i] + ys[i+1..])
    SumSizesSeqRemoveAt(fs, ys[1..], i - 1);
    assert ys[1..][..i-1] == ys[1..i];
    assert ys[1..][i..] == ys[i+1..];
    // Connect: ys[..i] + ys[i+1..] starts with ys[0], rest is ys[1..i] + ys[i+1..]
    assert ys[..i] == [ys[0]] + ys[1..i];
    var removed := ys[..i] + ys[i+1..];
    assert removed == [ys[0]] + (ys[1..i] + ys[i+1..]);
    assert removed[0] == ys[0];
    assert removed[1..] == ys[1..i] + ys[i+1..];
    // SumSizesSeq(removed) == fs[ys[0]].size + SumSizesSeq(ys[1..i] + ys[i+1..])
    // SumSizesSeq(ys) == fs[ys[0]].size + SumSizesSeq(ys[1..])  [by def]
    //                 == fs[ys[0]].size + fs[ys[i]].size + SumSizesSeq(ys[1..i] + ys[i+1..])  [by IH]
    // postcondition: fs[ys[i]].size + SumSizesSeq(removed)
    //              = fs[ys[i]].size + fs[ys[0]].size + SumSizesSeq(ys[1..i] + ys[i+1..])
    // Equal by commutativity of nat addition.
  }
}

// Two sequences with the same multiset of elements yield the same sum.
// Induction on |xs|: remove xs[0] from both, recurse.
lemma {:induction false} SumSizesSeqPermutation(
  fs: Filesystem, xs: seq<Path>, ys: seq<Path>
)
  requires forall p | p in xs :: p in fs && fs[p].FileEntry?
  requires forall p | p in ys :: p in fs && fs[p].FileEntry?
  requires multiset(xs) == multiset(ys)
  ensures SumSizesSeq(fs, xs) == SumSizesSeq(fs, ys)
  decreases |xs|
{
  if |xs| == 0 {
    assert |ys| == 0;
  } else {
    var head := xs[0];
    assert head in multiset(ys);
    var i :| 0 <= i < |ys| && ys[i] == head;
    var xs' := xs[1..];
    var ys' := ys[..i] + ys[i+1..];
    // Derive multiset(xs') == multiset(ys') by subtracting head from precondition.
    assert xs == [head] + xs';
    assert ys == ys[..i] + [ys[i]] + ys[i+1..];
    assert multiset(xs') == multiset(xs) - multiset{head};
    assert multiset(ys') == multiset(ys) - multiset{head};
    SumSizesSeqPermutation(fs, xs', ys');
    SumSizesSeqRemoveAt(fs, ys, i);
  }
}

// Adding one element to a set-based SumSizes (ID-134).
// Bridges from set to seq: SetToSeq(s + {k}) is a permutation of
// SetToSeq(s) + [k], and SumSizesSeq is permutation-invariant.
lemma {:induction false} SumSizesAddOne(fs: Filesystem, s: set<Path>, k: Path)
  requires k !in s
  requires forall p | p in (s + {k}) :: p in fs && fs[p].FileEntry?
  ensures SumSizes(fs, s + {k}) == SumSizes(fs, s) + fs[k].info.size
{
  var combined := SetToSeq(s + {k});
  var base := SetToSeq(s);
  // Prove multiset equality pointwise using SetToSeq's count ensure.
  // combined has each element of s+{k} exactly once.
  // base+[k] has each element of s once (from base) plus k once.
  // Since k !in s, both multisets agree on every element.
  assert forall x :: multiset(combined)[x] == multiset(base + [k])[x];
  SumSizesSeqPermutation(fs, combined, base + [k]);
  SumSizesSeqAppend(fs, base, k);
}

// Move is not a no-op when src != dst.
lemma MoveIsNotNoop(
  oldFs: Filesystem, newFs: Filesystem,
  src: Path, dst: Path, content: seq<nat>
)
  requires src != dst
  requires IsFile(oldFs, src)
  requires !PathExists(newFs, src)
  requires IsFile(newFs, dst)
  requires newFs[dst].content == content
  ensures oldFs != newFs
{
  assert src in oldFs;
  assert src !in newFs;
  assert oldFs != newFs;
}

// ---------------------------------------------------------------------------
// §9  WriteResult field mapping  (spec 045, ID-151)
// ---------------------------------------------------------------------------

// WR-008: Store.head() constructs a WriteResult from the FileInfo
// returned by get_file_info().  Modelled as a pure function here
// rather than a Backend method because Store.head() is a Store-layer
// composition over the backend's GetFileInfo (not a backend method
// itself).  `version_id` is hard-coded None because FileInfo carries
// no version_id slot in v1 (spec 045 WR-008 table).
function WriteResultFromFileInfo(info: FileInfo): WriteResult
{
  WriteResult(
    info.path,
    info.size,
    info.digest,
    info.etag,
    None,
    info.last_modified,
    info.metadata,
    SidecarSource
  )
}

// WR-008: pins the Dafny function's field mapping.  Honest scope: this
// lemma anchors WriteResultFromFileInfo to the Dafny FileInfo datatype:
// it does not anchor the Markdown spec table to the Dafny function.
// A reviewer who edits only the Markdown table (spec 045 § WR-008)
// will not get a Dafny failure.  Cross-check between the two is a
// human-review obligation, not a verifier one.
//
// WR-006 negative direction (Write never produces SidecarSource) is
// enforced structurally by Write's postcondition restricting source
// to NativeSource | BasicSource (§6), so no separate lemma is needed
// for that half.
lemma WR008FieldMapping(info: FileInfo)
  // @spec WR-008
  ensures (
    var wr := WriteResultFromFileInfo(info);
    wr.path == info.path
      && wr.size == info.size
      && wr.digest == info.digest
      && wr.etag == info.etag
      && wr.last_modified == info.last_modified
      && wr.metadata == info.metadata
      && wr.version_id.None?
      && wr.source == SidecarSource
  )
{
  var wr := WriteResultFromFileInfo(info);
  assert wr.path == info.path;
  assert wr.version_id == None;
  assert wr.source == SidecarSource;
}

