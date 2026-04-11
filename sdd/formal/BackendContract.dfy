// BackendContract.dfy — Formal specification of the remote-store backend
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
//   contract — see gap coverage table in README.
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

// CapGlob is defined but the Glob method is intentionally excluded
// from this contract — it is a capability-gated convenience method
// with no unique postcondition structure (it delegates to ListFiles +
// pattern matching).
type CapabilitySet = set<Capability>

// ---------------------------------------------------------------------------
// §3  Data models  (maps _models.py)
// ---------------------------------------------------------------------------

type Path = s: string | s != "" witness "a"

datatype FileInfo = FileInfo(
  path: Path,
  name: string,
  size: nat
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
// adapter maps "" → "." at the type boundary — one translation
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

// Recursive sum of file sizes over a finite set of paths.
// Ghost because `:|` is nondeterministic and not compilable.
// Order-independence is proved by SumSizesRemove.
ghost function SumSizes(fs: Filesystem, keys: set<Path>): nat
  requires forall k | k in keys :: k in fs && fs[k].FileEntry?
  decreases keys
{
  if keys == {} then 0
  else
    var k :| k in keys;
    fs[k].info.size + SumSizes(fs, keys - {k})
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
    ensures r.Ok?
    ensures r.value == (PathExists(fs, path) && AllAncestorsTraversable(fs, path))

  // ====================================================================
  // is_file(path) → bool
  // ====================================================================
  // Returns True iff path is a file AND all ancestors are directories.
  // Returns False for missing paths or paths with file-as-directory-component.
  method IsFileMethod(path: Path) returns (r: Result<bool>)
    ensures r.Ok?
    ensures r.value == (IsFile(fs, path) && AllAncestorsTraversable(fs, path))

  // ====================================================================
  // is_folder(path) → bool
  // ====================================================================
  // Returns True iff path is a folder AND all ancestors are directories.
  // Returns False for missing paths or paths with file-as-directory-component.
  method IsFolderMethod(path: Path) returns (r: Result<bool>)
    ensures r.Ok?
    ensures r.value == (IsDir(fs, path) && AllAncestorsTraversable(fs, path))

  // ====================================================================
  // read(path) → content  (no modifies — fs unchanged)
  // ====================================================================
  method Read(path: Path) returns (r: Result<seq<nat>>)
    ensures IsDir(fs, path)       ==> r == Err(InvalidPath(path, name))
    ensures !PathExists(fs, path) ==> r == Err(NotFound(path, name))
    ensures IsFile(fs, path)      ==> r == Ok(fs[path].content)

  // ====================================================================
  // write(path, content, overwrite)
  // ====================================================================
  method Write(path: Path, content: seq<nat>, overwrite: bool)
    returns (r: Result<()>)
    modifies this
    ensures IsDir(old(fs), path)
      ==> r == Err(InvalidPath(path, name))
    ensures !IsDir(old(fs), path) && IsFile(old(fs), path) && !overwrite
      ==> r == Err(AlreadyExists(path, name))
    // Happy path: no error condition → must succeed.
    ensures !IsDir(old(fs), path) && (!IsFile(old(fs), path) || overwrite)
      ==> r.Ok?
    ensures r.Ok? ==>
      IsFile(fs, path) && fs[path].content == content

  // ====================================================================
  // delete(path, missing_ok)
  // ====================================================================
  // IsDir → InvalidPath regardless of missing_ok.
  // missing_ok only governs the absent-path case.
  method Delete(path: Path, missing_ok: bool) returns (r: Result<()>)
    modifies this
    ensures IsDir(old(fs), path)
      ==> r == Err(InvalidPath(path, name))
    ensures !PathExists(old(fs), path) && !missing_ok
      ==> r == Err(NotFound(path, name))
    ensures !PathExists(old(fs), path) && missing_ok
      ==> r.Ok?
    // Happy path: file exists → must succeed.
    ensures IsFile(old(fs), path) ==> r.Ok?
    ensures IsFile(old(fs), path) && r.Ok?
      ==> !PathExists(fs, path)

  // ====================================================================
  // delete_folder(path, recursive, missing_ok)
  // ====================================================================
  method DeleteFolder(path: Path, recursive: bool, missing_ok: bool)
    returns (r: Result<()>)
    modifies this
    // File path → InvalidPath (wrong type, symmetric with Delete on dirs).
    ensures IsFile(old(fs), path)
      ==> r == Err(InvalidPath(path, name))
    ensures !PathExists(old(fs), path) && !missing_ok
      ==> r == Err(NotFound(path, name))
    ensures !PathExists(old(fs), path) && missing_ok
      ==> r.Ok?
    // Non-empty directory with recursive=false → DirectoryNotEmpty.
    ensures IsDir(old(fs), path) && !recursive && HasChildren(old(fs), path)
      ==> r == Err(DirectoryNotEmpty(path, name))
    // Happy path: empty dir or recursive → must succeed.
    ensures IsDir(old(fs), path) && (recursive || !HasChildren(old(fs), path))
      ==> r.Ok?
    // On success, directory entry is removed.
    ensures IsDir(old(fs), path) && r.Ok?
      ==> !IsDir(fs, path)
    // Recursive delete removes all children too.
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
    ensures r.Ok?
    ensures !PathExists(fs, path) ==> r.value == []
    // All results are files that are children of path.
    ensures r.Ok? ==>
      forall fi | fi in r.value :: IsFile(fs, fi.path) && IsChildOf(fi.path, path)
    // Depth is always non-negative for returned entries (no -1 non-children).
    ensures r.Ok? ==>
      forall fi | fi in r.value :: Depth(path, fi.path) >= 0
    // recursive=false → only immediate children (depth 0).
    ensures !recursive && r.Ok? ==>
      forall fi | fi in r.value :: Depth(path, fi.path) == 0
    // max_depth filtering (only when recursive; max_depth < 0 = unlimited).
    ensures recursive && max_depth >= 0 && r.Ok? ==>
      forall fi | fi in r.value :: Depth(path, fi.path) <= max_depth
    // Completeness: every matching file MUST appear in the result.
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
    ensures r.Ok?
    ensures !PathExists(fs, path) ==> r.value == []
    // All results are immediate child directories of path.
    ensures r.Ok? ==>
      forall fe | fe in r.value :: IsDir(fs, fe.path) && IsChildOf(fe.path, path)
    // Completeness: every immediate child directory MUST appear.
    ensures r.Ok? && PathExists(fs, path) ==>
      forall p: Path | IsDir(fs, p) && IsChildOf(p, path) ::
        exists fe | fe in r.value :: fe.path == p

  // ====================================================================
  // get_file_info(path) → FileInfo
  // ====================================================================
  method GetFileInfo(path: Path) returns (r: Result<FileInfo>)
    ensures IsDir(fs, path)       ==> r == Err(InvalidPath(path, name))
    ensures !PathExists(fs, path) ==> r == Err(NotFound(path, name))
    ensures IsFile(fs, path)      ==> r.Ok? && r.value == fs[path].info

  // ====================================================================
  // get_folder_info(path) → FolderInfo
  // ====================================================================
  // BE-017: symmetric with GetFileInfo — file path → InvalidPath.
  method GetFolderInfo(path: Path) returns (r: Result<FolderInfo>)
    ensures IsFile(fs, path)      ==> r == Err(InvalidPath(path, name))
    ensures !PathExists(fs, path) ==> r == Err(NotFound(path, name))
    ensures IsDir(fs, path)       ==> r.Ok? && r.value.path == path

  // ====================================================================
  // move(src, dst, overwrite)
  // ====================================================================
  // Gap 2: directory src → InvalidPath (not NotFound).
  // Gap 5: atomicity is backend-dependent — backends that guarantee atomic
  //   rename declare CapAtomicMove; others use copy-then-delete.
  //   Postcondition covers only the final state, not intermediate visibility.
  method Move(src: Path, dst: Path, overwrite: bool)
    returns (r: Result<()>)
    modifies this
    ensures IsDir(old(fs), src)
      ==> r == Err(InvalidPath(src, name))
    ensures !PathExists(old(fs), src)
      ==> r == Err(NotFound(src, name))
    // Directory destination → InvalidPath (can't overwrite dir with file).
    ensures IsFile(old(fs), src) && IsDir(old(fs), dst)
      ==> r == Err(InvalidPath(dst, name))
    ensures IsFile(old(fs), src) && IsFile(old(fs), dst) && !overwrite && src != dst
      ==> r == Err(AlreadyExists(dst, name))
    // Happy path: file src, dst is not a dir, no overwrite conflict.
    ensures IsFile(old(fs), src) && !IsDir(old(fs), dst) &&
            (!IsFile(old(fs), dst) || overwrite || src == dst)
      ==> r.Ok?
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
    ensures IsDir(old(fs), src)
      ==> r == Err(InvalidPath(src, name))
    ensures !PathExists(old(fs), src)
      ==> r == Err(NotFound(src, name))
    ensures IsFile(old(fs), src) && IsDir(old(fs), dst)
      ==> r == Err(InvalidPath(dst, name))
    ensures IsFile(old(fs), src) && IsFile(old(fs), dst) && !overwrite && src != dst
      ==> r == Err(AlreadyExists(dst, name))
    // Happy path.
    ensures IsFile(old(fs), src) && !IsDir(old(fs), dst) &&
            (!IsFile(old(fs), dst) || overwrite || src == dst)
      ==> r.Ok?
    ensures r.Ok? && IsFile(old(fs), src) ==>
      IsFile(fs, src) && IsFile(fs, dst) &&
      fs[dst].content == old(fs)[src].content

  // ====================================================================
  // Capability gate
  // ====================================================================
  method RequireCapability(cap: Capability) returns (r: Result<()>)
    ensures cap in capabilities ==> r.Ok?
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
  ensures var newFs := fs[path := FileEntry(content, FileInfo(path, path, |content|))];
          IsFile(newFs, path) && newFs[path].content == content
{
  var newFs := fs[path := FileEntry(content, FileInfo(path, path, |content|))];
  assert path in newFs;
  assert newFs[path].FileEntry?;
  assert IsFile(newFs, path);
  assert newFs[path].content == content;
}

// Any element can be factored out of SumSizes (ID-134).
// The `:|` in SumSizes picks an opaque element; this lemma proves the
// sum is the same regardless of which element we factor out.
// Proof: for the non-trivial case, prove the IH for every possible
// element the function could have picked, via `forall` statements.
lemma {:induction false} SumSizesRemove(fs: Filesystem, keys: set<Path>, x: Path)
  requires x in keys
  requires forall k | k in keys :: k in fs && fs[k].FileEntry?
  ensures SumSizes(fs, keys) == fs[x].info.size + SumSizes(fs, keys - {x})
  decreases keys
{
  if keys != {x} {
    // |keys| >= 2.  SumSizes(keys) unfolds to fs[y].size + SumSizes(keys - {y})
    // for some y chosen by `:|`.  We don't know if y == x, so prove the
    // IH for all possible y != x and let the solver pick the right one.
    forall y | y in keys && y != x
      ensures SumSizes(fs, keys - {y}) == fs[x].info.size + SumSizes(fs, keys - {y} - {x})
    {
      assert x in keys - {y};
      SumSizesRemove(fs, keys - {y}, x);
    }
    forall y | y in keys && y != x
      ensures SumSizes(fs, keys - {x}) == fs[y].info.size + SumSizes(fs, keys - {x} - {y})
    {
      assert y in keys - {x};
      SumSizesRemove(fs, keys - {x}, y);
    }
  }
}

// Corollary: adding one element to SumSizes (ID-134).
lemma {:induction false} SumSizesAddOne(fs: Filesystem, s: set<Path>, k: Path)
  requires k !in s
  requires forall p | p in (s + {k}) :: p in fs && fs[p].FileEntry?
  ensures SumSizes(fs, s + {k}) == SumSizes(fs, s) + fs[k].info.size
{
  assert k in s + {k};
  SumSizesRemove(fs, s + {k}, k);
  assert (s + {k}) - {k} == s;
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
