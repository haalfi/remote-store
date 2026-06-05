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

// ID-191: the trait's Move postcondition pins `CapAtomicMove in capabilities
// ==> ObservableForAtomicMove(phase)` on a ghost output from `ResourceSafety.dfy`
// § 2.3.  The include makes the MovePhase / MoveContract / ObservableForAtomicMove
// symbols visible here; the dependency is one-way (ResourceSafety.dfy is
// standalone), so no cycle.
include "ResourceSafety.dfy"

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
  | ResourceLocked(path: string, backend: string)

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
  // ID-188 / spec SIO-009: lazy-read quality flag. Stub variant — no
  // enforceable Read postcondition. The Dafny model materialises content
  // as `seq<nat>`; "no I/O before first read" is a runtime protocol
  // property over the BinaryIO stream wrapper, not a property of the
  // returned bytes the contract reasons about. Declared so the Dafny
  // capability set tracks the Python `Capability.LAZY_READ` member at
  // parity; load-bearing checks live in Python conformance (SIO-009).
  | CapLazyRead

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

// ID-188 / spec SIO-008: Read returns content plus the seekability flag
// of the BinaryIO wrapper the Python adapter will hand back. The Dafny
// model is intentionally minimal — `seekable` tracks the single quality
// flag the contract reasons about (CapSeekableRead). A lazy/eager flag is
// not modelled here: see CapLazyRead's stub-variant note in §2.
datatype ReadStream = ReadStream(content: seq<nat>, seekable: bool)

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
// §5a  Path well-formedness and native-path resolution  (ID-190)
// ---------------------------------------------------------------------------
// WellFormedPath characterises a *normalised* path.  A non-root
// well-formed path is a fixed point of RemotePath._normalize
// (src/remote_store/_path.py) — a string normalisation accepts and
// returns unchanged: no backslash,
// no "." or ".." segment, no leading/trailing or doubled slash, no null
// byte, non-empty.  Every Path reaching a Backend operation has already
// cleared RemotePath construction, so the contract methods below take
// WellFormedPath as a precondition assumption: the contract reasons
// about normalised input only.  Before ID-190 the contract treated
// paths as opaque non-empty strings and these rules lived in Python
// alone, so the oracle could not certify a path-normalisation test.
//
// The Root sentinel "." is well-formed by fiat (PATH-015): it is the
// canonical root value the Python adapter maps "" onto, even though
// RemotePath(".") as constructor input is rejected (PATH-006 strips the
// "." segment, PATH-008 then rejects the empty result).
//
// Scope: as a `requires`, WellFormedPath is an *assumption*, not a
// checked obligation.  It weakens what each method body must prove, and
// nothing here establishes that callers pass a well-formed path — so the
// contract does not *reject* a malformed path, it just says nothing
// about one.  The predicate becomes load-bearing only once a future item
// makes a postcondition or a path-construction refinement depend on it.

// `sub` occurs somewhere in `s`.
ghost predicate ContainsSub(s: string, sub: string)
{
  exists i {:trigger s[i..i + |sub|]} :: 0 <= i <= |s| - |sub| && s[i..i + |sub|] == sub
}

// `seg` occurs in `s` as a complete '/'-delimited segment: the whole
// string, a leading segment, a trailing segment, or an interior one.
ghost predicate HasSegment(s: string, seg: string)
{
  s == seg
  || (|s| >= |seg| + 1 && s[..|seg| + 1] == seg + "/")
  || (|s| >= |seg| + 1 && s[|s| - |seg| - 1..] == "/" + seg)
  || ContainsSub(s, "/" + seg + "/")
}

// PATH-002 -- PATH-008: `s` is a normalised, well-formed path.
ghost predicate WellFormedPath(s: string)
{
  s == Root                                  // PATH-015: root sentinel
  || (
    |s| > 0                                  // PATH-008: non-empty
    && '\0' !in s                            // PATH-007: no null byte
    && '\\' !in s                            // PATH-002: no backslash
    && s[0] != '/'                           // PATH-004: no leading slash
    && s[|s| - 1] != '/'                     // PATH-004: no trailing slash
    && !ContainsSub(s, "//")                 // PATH-005: no doubled slash
    && !HasSegment(s, ".")                   // PATH-006: no "." segment
    && !HasSegment(s, "..")                  // PATH-003: no ".." segment
  )
}

// to_key / native_path model the bidirectional conversion between a
// backend-native path and a backend-relative key (spec 010; BE-023 /
// BE-025).  `root` is the backend's native prefix — a filesystem root,
// an S3 bucket, an SFTP base_path; the empty root models the
// identity-default backends (MemoryBackend, the plain Backend ABC).
// NativePathRoundTrip in §8 proves the round-trip identity, which holds
// for every key including the empty key (BK-234).

// native_path(key): prepend the backend root to a relative key.  An
// empty key resolves to the root itself (NPR-021).
ghost function NativePath(root: string, key: string): string
{
  if key == "" then root
  else if root == "" then key
  else root + "/" + key
}

// to_key(native): strip the backend root prefix (NPR-005).  A `root + "/"`
// prefix is stripped to the trailing key; the bare root (no trailing key)
// maps to "" — the inverse of native_path("") returning the root (NPR-021).
// Any other path is returned unchanged (best-effort).  BK-234 aligned all
// rooted backends (Local, SFTP, S3, Azure) on this bare-root branch so the
// round-trip holds for the empty key too.
ghost function ToKey(root: string, native: string): string
{
  if root == "" then native
  else if |native| > |root| && native[..|root| + 1] == root + "/"
    then native[|root| + 1..]
  else if native == root then ""
  else native
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
  // §6.0  Class invariant: fs well-formedness  (ID-209)
  // ====================================================================
  // Valid() says every key in fs has all its slash-aligned ancestors
  // *materialised* as DirEntry — strictly stronger than the
  // AllAncestorsTraversable predicate's "absent OR DirEntry" disjunct.
  // The strengthening is load-bearing: a weaker "absent OR DirEntry"
  // version is broken by a Write that inserts a FileEntry at an
  // already-absent slash-aligned ancestor of some existing key (e.g.
  // old(fs) holds "foo/bar" with "foo" absent — both Valid() under the
  // weak form; writing "foo" as a FileEntry then breaks
  // AllAncestorsTraversable for "foo/bar").  The strong form rules out
  // that edge case in old(fs), matching real backends where EnsureParents
  // (Memory) / parent.mkdir(parents=True) (Local) / sftp mkdir-walk
  // (SFTP) always materialises every parent directory on a successful
  // write — see the empirical probe in ID-209's trace.
  //
  // Consequence for ID-184: the
  // `!AllAncestorsTraversable(fs, path) ==> r.value == []` disjunct on
  // ListFiles / ListFolders becomes a logical consequence of Valid()
  // rather than a defensive postcondition against an unreachable state.
  //
  // Maintenance: declared as `requires Valid() ensures Valid()` on every
  // mutating method (Write, Delete, DeleteFolder, Move, Copy).  Read-only
  // methods (Exists, IsFileMethod, IsFolderMethod, Read, ListFiles,
  // ListFolders, GetFileInfo, GetFolderInfo, RequireCapability) do not
  // mutate fs, so they neither require nor must re-establish Valid() —
  // their callers do.  Write is the load-bearing case: its new
  // `!AllAncestorsTraversable(old(fs), path) ==> InvalidPath` clause is
  // exactly what prevents a successful Write from inserting a FileEntry
  // under a path whose ancestor is already a file, which is the only
  // public-API way a refinement could break Valid() under the strong
  // form.
  predicate Valid()
    reads this
  {
    forall p :: p in fs ==>
      forall i: int | 0 < i < |p| - 1 && p[i] == '/' ::
        IsDir(fs, p[..i])
  }

  // ValidImpliesAllAncestorsTraversable: a structural consequence used by
  // the ID-184 listing semantics.  Stated once at the trait so refinements
  // and clients can rely on it without re-deriving in each method.
  lemma ValidImpliesAllAncestorsTraversable(p: Path)
    requires Valid()
    requires p in fs
    ensures AllAncestorsTraversable(fs, p)
  {
    // Strong Valid() gives IsDir at every slash-aligned ancestor;
    // IsDir implies PathExists ∧ ¬FileEntry, which is the (absent OR
    // DirEntry) disjunct AllAncestorsTraversable demands.
  }

  // ====================================================================
  // exists(path) → bool
  // ====================================================================
  // Returns True iff path exists AND all ancestors are directories.
  // Returns False for missing paths or paths with file-as-directory-component.
  method Exists(path: Path) returns (r: Result<bool>)
    requires WellFormedPath(path)
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
    requires WellFormedPath(path)
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
    requires WellFormedPath(path)
    // @spec BE-005
    ensures r.Ok?
    // @spec BE-005
    ensures r.value == (IsDir(fs, path) && AllAncestorsTraversable(fs, path))

  // ====================================================================
  // read(path) → ReadStream  (no modifies: fs unchanged)
  // ====================================================================
  // ID-188 / spec SIO-008: Read returns a ReadStream that carries both
  // the file content and the seekability flag of the BinaryIO wrapper
  // the Python adapter hands back. The seekability postcondition is
  // capability-gated: declaring CapSeekableRead obliges the refinement
  // to produce a seekable stream on every successful read.
  method Read(path: Path) returns (r: Result<ReadStream>)
    requires WellFormedPath(path)
    // @spec BE-021
    ensures IsDir(fs, path)       ==> r == Err(InvalidPath(path, name))
    // @spec BE-006
    ensures !PathExists(fs, path) ==> r == Err(NotFound(path, name))
    // @spec BE-006
    ensures IsFile(fs, path)      ==> r.Ok? && r.value.content == fs[path].content
    // @spec SIO-008
    ensures r.Ok? && CapSeekableRead in capabilities ==> r.value.seekable

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
    requires WellFormedPath(path)
    requires Valid()
    modifies this
    ensures Valid()
    // Gap 1 / BE-008: precondition order — type check first (directory
    // path → InvalidPath).
    // @spec BE-008
    ensures IsDir(old(fs), path)
      ==> r == Err(InvalidPath(path, name))
    // ID-209 / BE-008: precondition order — path-validity also covers a
    // file-ancestor in the path.  Mutually exclusive with IsDir / IsFile
    // (both imply path in old(fs), and Valid() then forces
    // AllAncestorsTraversable), so this clause and the existing IsDir /
    // overwrite-conflict / WR-010 / happy-path clauses can never
    // contradict each other.  Closes the trait totality gap left by
    // ID-184: Write now rejects the structurally unreachable input
    // explicitly rather than EnsureParents'ing into a Valid()-breaking
    // state.
    // @spec BE-008
    ensures !AllAncestorsTraversable(old(fs), path)
      ==> r == Err(InvalidPath(path, name))
    // Gap 1 / BE-008: precondition order — overwrite conflict second.
    // @spec BE-008
    ensures !IsDir(old(fs), path) && IsFile(old(fs), path) && !overwrite
      ==> r == Err(AlreadyExists(path, name))
    // WR-010 strict gate: non-empty metadata on a backend without
    // CapUserMetadata → CapabilityNotSupported (pre-I/O).  ID-209 tightens
    // the guard with AllAncestorsTraversable so this clause stays
    // mutually exclusive with the new file-ancestor clause above.
    // @spec WR-010
    ensures !IsDir(old(fs), path) && (!IsFile(old(fs), path) || overwrite) &&
            AllAncestorsTraversable(old(fs), path) &&
            HasUserMetadata(metadata) && CapUserMetadata !in capabilities
      ==> r == Err(CapabilityNotSupported(
            CapabilityName(CapUserMetadata), name))
    // BE-008 happy path: no error condition → must succeed.  ID-209 adds
    // the AllAncestorsTraversable conjunct for the same reason as the
    // WR-010 guard above.
    // @spec BE-008
    ensures !IsDir(old(fs), path) && (!IsFile(old(fs), path) || overwrite) &&
            AllAncestorsTraversable(old(fs), path) &&
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
    requires WellFormedPath(path)
    requires Valid()
    modifies this
    ensures Valid()
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
    requires WellFormedPath(path)
    requires Valid()
    modifies this
    ensures Valid()
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
  // ID-184: a non-traversable ancestor (a file in path's prefix chain)
  //   yields an empty listing, matching Exists/IsFileMethod/IsFolderMethod
  //   semantics where `AllAncestorsTraversable` gates reachability.
  method ListFiles(path: Path, recursive: bool, max_depth: int)
    returns (r: Result<seq<FileInfo>>)
    requires WellFormedPath(path)
    // Gap 3 / BE-014: listing is total — never raises NotFound.
    // @spec BE-014
    ensures r.Ok?
    // Gap 3 / BE-014 (ID-184): missing path OR a non-traversable ancestor
    // yields an empty result, never an error.
    // @spec BE-014
    ensures !PathExists(fs, path) || !AllAncestorsTraversable(fs, path)
      ==> r.value == []
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
    // Completeness (ID-184): every matching file MUST appear in the result,
    // gated on path being reachable (exists AND ancestors traversable) —
    // the symmetric tightening of the missing-path early-return above.
    // @spec BE-014
    ensures r.Ok? && PathExists(fs, path) && AllAncestorsTraversable(fs, path) ==>
      forall p: Path | IsFile(fs, p) && IsChildOf(p, path) &&
        (if !recursive then Depth(path, p) == 0
         else if max_depth >= 0 then Depth(path, p) <= max_depth
         else true) ::
        exists fi | fi in r.value :: fi.path == p

  // ====================================================================
  // list_folders(path)
  // ====================================================================
  // ID-184: a non-traversable ancestor yields an empty listing, see
  // ListFiles for the rationale.
  method ListFolders(path: Path) returns (r: Result<seq<FolderEntry>>)
    requires WellFormedPath(path)
    // Gap 3 / BE-015: listing is total — never raises NotFound.
    // @spec BE-015
    ensures r.Ok?
    // Gap 3 / BE-015 (ID-184): missing path OR a non-traversable ancestor
    // yields an empty result, never an error.
    // @spec BE-015
    ensures !PathExists(fs, path) || !AllAncestorsTraversable(fs, path)
      ==> r.value == []
    // All results are immediate child directories of path.
    // @spec BE-015
    ensures r.Ok? ==>
      forall fe | fe in r.value :: IsDir(fs, fe.path) && IsChildOf(fe.path, path)
    // Completeness (ID-184): every immediate child directory MUST appear,
    // gated on path being reachable.
    // @spec BE-015
    ensures r.Ok? && PathExists(fs, path) && AllAncestorsTraversable(fs, path) ==>
      forall p: Path | IsDir(fs, p) && IsChildOf(p, path) ::
        exists fe | fe in r.value :: fe.path == p

  // ====================================================================
  // get_file_info(path) → FileInfo
  // ====================================================================
  method GetFileInfo(path: Path) returns (r: Result<FileInfo>)
    requires WellFormedPath(path)
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
    requires WellFormedPath(path)
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
  //   ID-191: a `ghost phase: MovePhase` return reflects the runtime
  //   terminal state; CapAtomicMove-declaring refinements must satisfy
  //   ObservableForAtomicMove(phase), excluding CopyDone and Initial.
  //   The ghost output is erased at compile time, so module_.py and the
  //   DafnyOracleBackend adapter are unaffected.
  method Move(src: Path, dst: Path, overwrite: bool)
    returns (r: Result<()>, ghost phase: MovePhase)
    requires WellFormedPath(src)
    requires WellFormedPath(dst)
    requires Valid()
    modifies this
    ensures Valid()
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
    // ID-209 / BE-018: file-ancestor in dst → InvalidPath.  Symmetric with
    // Write's file-ancestor clause: a Move that inserts a FileEntry at dst
    // would otherwise break Valid() in exactly the same way a Write does.
    // Mutually exclusive with the IsDir(dst) clause above (a DirEntry at
    // dst implies, via Valid(), that all ancestors of dst are
    // DirEntries).
    // @spec BE-018
    ensures IsFile(old(fs), src) && !AllAncestorsTraversable(old(fs), dst)
      ==> r == Err(InvalidPath(dst, name))
    // @spec BE-018
    ensures IsFile(old(fs), src) && IsFile(old(fs), dst) && !overwrite && src != dst
      ==> r == Err(AlreadyExists(dst, name))
    // BE-018 happy path: file src, dst is not a dir, no overwrite conflict,
    // dst's ancestors are all traversable (ID-209 conjunct).
    // @spec BE-018
    ensures IsFile(old(fs), src) && !IsDir(old(fs), dst) &&
            AllAncestorsTraversable(old(fs), dst) &&
            (!IsFile(old(fs), dst) || overwrite || src == dst)
      ==> r.Ok?
    // BK-232 / WR-013: move preserves user metadata on the destination.
    // Before BK-232 the contract pinned only content, so a refinement
    // that built the destination via BasicFileInfo (metadata dropped)
    // verified cleanly — the exact defect Python carried before BK-192.
    // @spec BE-018, WR-013
    ensures r.Ok? && IsFile(old(fs), src) ==>
      IsFile(fs, dst) &&
      fs[dst].content == old(fs)[src].content &&
      fs[dst].info.metadata == old(fs)[src].info.metadata &&
      (src != dst ==> !PathExists(fs, src))
    // ID-191 / BE-018 § Atomicity: every successful Move terminates in the
    // DeleteDone phase regardless of capability.  The phase label is
    // semantically literal for `src != dst` (final state is
    // src-gone-dst-present); for self-move (`src == dst`) the underlying
    // state is single-file-preserved (both technically present because they
    // are the same path), and DeleteDone here is a *nominal* label
    // satisfying the postcondition without modelling a distinct SelfMove
    // variant.  Refinements assign this branch via the early `src == dst`
    // return path; readers should not infer src-gone semantics in that case.
    // @spec BE-018
    ensures r.Ok? ==> phase == DeleteDone
    // ID-191 / BE-018 § Atomicity: a backend declaring CapAtomicMove MUST
    // expose a phase that satisfies the observable-contract predicate —
    // ObservableForAtomicMove(phase) excludes both CopyDone (src gone, dst
    // not yet written: the partial-state a non-atomic backend may
    // transiently sit in) and Initial (pre-move).  A refinement that
    // declares CapAtomicMove but tries to assign phase := CopyDone in any
    // branch fails to verify; this is the structural binding from the §
    // 2.3 ResourceSafety contract into the Backend trait.
    //
    // Honest scope: this clause closes the "declares CapAtomicMove and
    // lies about phase" direction of BE-018 Gap 5.  It does NOT close the
    // converse direction — a refinement that uses a runtime
    // copy-then-delete protocol but omits CapAtomicMove from its
    // capabilities set will satisfy this postcondition vacuously, and is
    // free to assign `phase := DeleteDone` on success without ever
    // modelling the CopyDone transient state.  Capability declaration
    // remains an honour-system claim at the backend level.  The full
    // closure of Gap 5 would require either (a) a mechanical link from
    // implementation shape to capability declaration (out of scope for the
    // current trait abstraction, which models the contract not the
    // implementation strategy), or (b) a downstream conformance test that
    // probes for partial-failure behaviour on backends that DON'T declare
    // atomicity — which is the BACKLOG's existing "non-atomic backends
    // MUST surface partial failure as a raise" prose, not a new Dafny
    // postcondition.
    // @spec BE-018
    ensures CapAtomicMove in capabilities ==> ObservableForAtomicMove(phase)

  // ====================================================================
  // copy(src, dst, overwrite)
  // ====================================================================
  // Gap 2: directory src → InvalidPath.
  // Self-copy (src == dst) is a no-op, not AlreadyExists.
  method Copy(src: Path, dst: Path, overwrite: bool)
    returns (r: Result<()>)
    requires WellFormedPath(src)
    requires WellFormedPath(dst)
    requires Valid()
    modifies this
    ensures Valid()
    // @spec BE-021
    ensures IsDir(old(fs), src)
      ==> r == Err(InvalidPath(src, name))
    // @spec BE-019
    ensures !PathExists(old(fs), src)
      ==> r == Err(NotFound(src, name))
    // @spec BE-021
    ensures IsFile(old(fs), src) && IsDir(old(fs), dst)
      ==> r == Err(InvalidPath(dst, name))
    // ID-209 / BE-019: file-ancestor in dst → InvalidPath.  Symmetric with
    // Move's file-ancestor clause above and Write's file-ancestor clause,
    // for the same Valid()-preservation reason.
    // @spec BE-019
    ensures IsFile(old(fs), src) && !AllAncestorsTraversable(old(fs), dst)
      ==> r == Err(InvalidPath(dst, name))
    // @spec BE-019
    ensures IsFile(old(fs), src) && IsFile(old(fs), dst) && !overwrite && src != dst
      ==> r == Err(AlreadyExists(dst, name))
    // BE-019 happy path.  ID-209 adds the AllAncestorsTraversable
    // conjunct for the same reason as Move's happy-path guard.
    // @spec BE-019
    ensures IsFile(old(fs), src) && !IsDir(old(fs), dst) &&
            AllAncestorsTraversable(old(fs), dst) &&
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
  case CapLazyRead => "lazy_read"
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

// NPR-020: native_path is a right inverse of to_key for every key.  For a
// non-empty key, to_key strips exactly the `root + "/"` that native_path
// prepended, recovering the key.  For the empty key, native_path("")
// resolves to the bare root (NPR-021) and to_key of the bare root is ""
// (NPR-005, BK-234 bare-root branch), so the identity holds there too.  The
// identity-default backends (root == "") satisfy it trivially.  This
// backend-level identity is the base case future Store-Backend composition
// reasoning builds on: Store.to_key / Store.native_path (NPR-010, STORE-012)
// layer the store root_path on top of it.
//
// BK-234 reconciled NPR-005 and NPR-020's "for all valid keys" wording by
// aligning all rooted backends (Local, SFTP, S3, Azure) on the bare-root →
// "" branch, so the lemma now holds unconditionally — no empty-key carve-out.
lemma NativePathRoundTrip(root: string, key: string)
  // @spec NPR-020
  ensures ToKey(root, NativePath(root, key)) == key
{
  if root == "" {
    assert NativePath(root, key) == key;
    assert ToKey(root, key) == key;
  } else if key == "" {
    assert NativePath(root, key) == root;
    assert ToKey(root, root) == "";
  } else {
    var native := NativePath(root, key);
    assert native == root + "/" + key;
    assert |root + "/"| == |root| + 1;
    assert |native| == |root| + 1 + |key|;
    assert native[..|root| + 1] == root + "/";
    assert native[|root| + 1..] == key;
    assert ToKey(root, native) == native[|root| + 1..];
  }
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

