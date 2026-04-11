// MemoryBackend.dfy — Reference refinement of BackendContract.
//
// Proves that an in-memory implementation satisfies every postcondition
// of the Backend trait.  This is the "model" backend — if Dafny can
// verify it, the contract is satisfiable and internally consistent.

include "BackendContract.dfy"

class MemoryBackend extends Backend {

  constructor ()
    ensures fs == map[Root := DirEntry]
    ensures name == "memory"
    ensures capabilities == {CapRead, CapWrite, CapDelete, CapList, CapMove, CapCopy,
                             CapAtomicWrite, CapAtomicMove, CapMetadata, CapSeekableRead}
  {
    name := "memory";
    capabilities := {CapRead, CapWrite, CapDelete, CapList, CapMove, CapCopy,
                     CapAtomicWrite, CapAtomicMove, CapMetadata, CapSeekableRead};
    fs := map[Root := DirEntry];
  }

  method Exists(path: Path) returns (r: Result<bool>)
    ensures r.Ok?
    ensures r.value == (PathExists(fs, path) && AllAncestorsTraversable(fs, path))
  {
    var path_exists := path in fs;
    var ancestors_ok := AncestorsTraversableCheck(path);
    r := Ok(path_exists && ancestors_ok);
  }

  method IsFileMethod(path: Path) returns (r: Result<bool>)
    ensures r.Ok?
    ensures r.value == (IsFile(fs, path) && AllAncestorsTraversable(fs, path))
  {
    var is_file := path in fs && fs[path].FileEntry?;
    var ancestors_ok := AncestorsTraversableCheck(path);
    r := Ok(is_file && ancestors_ok);
  }

  method IsFolderMethod(path: Path) returns (r: Result<bool>)
    ensures r.Ok?
    ensures r.value == (IsDir(fs, path) && AllAncestorsTraversable(fs, path))
  {
    var is_dir := path in fs && fs[path].DirEntry?;
    var ancestors_ok := AncestorsTraversableCheck(path);
    r := Ok(is_dir && ancestors_ok);
  }

  // Helper to check that all ancestors are traversable (not files)
  // Only checks segment-aligned prefixes (those where path[i] == '/').
  method AncestorsTraversableCheck(path: Path) returns (result: bool)
    ensures result == AllAncestorsTraversable(fs, path)
  {
    result := true;
    if |path| <= 2 {
      return;
    }
    var i := 1;
    while i < |path| - 1
      invariant 1 <= i <= |path| - 1
      // Invariant: result tracks whether all checked ancestors are traversable.
      // When result == true: all ancestors at positions j < i (where path[j]=='/') are traversable.
      // When result == false: a file ancestor was found at position i.
      invariant result == (forall j: int |
        0 < j < i && path[j] == '/' ::
        !PathExists(fs, path[..j]) || IsDir(fs, path[..j]))
    {
      // Check '/' boundary
      if path[i] == '/' {
        var prefix := path[..i];
        if prefix in fs && fs[prefix].FileEntry? {
          result := false;
          break;
        }
      }
      i := i + 1;
    }
  }

  method Read(path: Path) returns (r: Result<seq<nat>>)
    ensures IsDir(fs, path)       ==> r == Err(InvalidPath(path, name))
    ensures !PathExists(fs, path) ==> r == Err(NotFound(path, name))
    ensures IsFile(fs, path)      ==> r == Ok(fs[path].content)
  {
    if path in fs {
      match fs[path]
      case FileEntry(content, _) =>
        assert IsFile(fs, path);
        r := Ok(content);
      case DirEntry =>
        assert IsDir(fs, path);
        r := Err(InvalidPath(path, name));
    } else {
      assert !PathExists(fs, path);
      r := Err(NotFound(path, name));
    }
  }

  // EnsureParents: insert DirEntry for every slash-aligned ancestor of path
  // that does not already exist in fs.  Existing entries are never overwritten.
  method EnsureParents(path: Path)
    modifies this
    ensures forall k | k in old(fs) :: k in fs && fs[k] == old(fs)[k]
    ensures forall i | 0 < i < |path| && path[i] == '/' && path[..i] !in old(fs) ::
      path[..i] in fs && fs[path[..i]].DirEntry?
  {
    var i := 1;
    while i < |path|
      invariant 1 <= i <= |path|
      invariant forall k | k in old(fs) :: k in fs && fs[k] == old(fs)[k]
      invariant forall k | k in fs && k !in old(fs) :: fs[k].DirEntry?
      invariant forall j | 0 < j < i && path[j] == '/' && path[..j] !in old(fs) ::
        path[..j] in fs && fs[path[..j]].DirEntry?
    {
      if path[i] == '/' {
        var prefix := path[..i];
        if prefix !in fs {
          assert prefix !in old(fs);
          // Different-length prefixes are distinct keys.
          assert |prefix| == i;
          assert forall j | 0 < j < i :: |path[..j]| == j && path[..j] != prefix;
          fs := fs[prefix := DirEntry];
        }
      }
      i := i + 1;
    }
  }

  method Write(path: Path, content: seq<nat>, overwrite: bool)
    returns (r: Result<()>)
    modifies this
    ensures IsDir(old(fs), path)
      ==> r == Err(InvalidPath(path, name))
    ensures !IsDir(old(fs), path) && IsFile(old(fs), path) && !overwrite
      ==> r == Err(AlreadyExists(path, name))
    ensures !IsDir(old(fs), path) && (!IsFile(old(fs), path) || overwrite)
      ==> r.Ok?
    ensures r.Ok? ==>
      IsFile(fs, path) && fs[path].content == content
  {
    if path in fs && fs[path].DirEntry? {
      assert IsDir(old(fs), path);
      r := Err(InvalidPath(path, name));
      return;
    }
    assert !IsDir(old(fs), path);

    if path in fs && fs[path].FileEntry? && !overwrite {
      assert IsFile(old(fs), path);
      r := Err(AlreadyExists(path, name));
      return;
    }

    EnsureParents(path);
    var info := FileInfo(path, path, |content|);
    fs := fs[path := FileEntry(content, info)];
    assert IsFile(fs, path);
    assert fs[path].content == content;
    r := Ok(());
  }

  method Delete(path: Path, missing_ok: bool) returns (r: Result<()>)
    modifies this
    ensures IsDir(old(fs), path)
      ==> r == Err(InvalidPath(path, name))
    ensures !PathExists(old(fs), path) && !missing_ok
      ==> r == Err(NotFound(path, name))
    ensures !PathExists(old(fs), path) && missing_ok
      ==> r.Ok?
    ensures IsFile(old(fs), path) ==> r.Ok?
    ensures IsFile(old(fs), path) && r.Ok?
      ==> !PathExists(fs, path)
  {
    if path in fs {
      match fs[path]
      case DirEntry =>
        assert IsDir(old(fs), path);
        r := Err(InvalidPath(path, name));
      case FileEntry(_, _) =>
        assert IsFile(old(fs), path);
        fs := map k | k in fs && k != path :: fs[k];
        assert path !in fs;
        r := Ok(());
    } else {
      assert !PathExists(old(fs), path);
      if missing_ok {
        r := Ok(());
      } else {
        r := Err(NotFound(path, name));
      }
    }
  }

  method DeleteFolder(path: Path, recursive: bool, missing_ok: bool)
    returns (r: Result<()>)
    modifies this
    ensures IsFile(old(fs), path)
      ==> r == Err(InvalidPath(path, name))
    ensures !PathExists(old(fs), path) && !missing_ok
      ==> r == Err(NotFound(path, name))
    ensures !PathExists(old(fs), path) && missing_ok
      ==> r.Ok?
    ensures IsDir(old(fs), path) && !recursive && HasChildren(old(fs), path)
      ==> r == Err(DirectoryNotEmpty(path, name))
    ensures IsDir(old(fs), path) && (recursive || !HasChildren(old(fs), path))
      ==> r.Ok?
    ensures IsDir(old(fs), path) && r.Ok?
      ==> !IsDir(fs, path)
    ensures IsDir(old(fs), path) && recursive && r.Ok? ==>
      forall p: Path | IsChildOf(p, path) :: !PathExists(fs, p)
  {
    // File path → InvalidPath (wrong type).
    if path in fs && fs[path].FileEntry? {
      assert IsFile(old(fs), path);
      r := Err(InvalidPath(path, name));
      return;
    }

    // Not a directory → NotFound or Ok depending on missing_ok.
    if !(path in fs && fs[path].DirEntry?) {
      assert !PathExists(old(fs), path);
      if missing_ok {
        r := Ok(());
      } else {
        r := Err(NotFound(path, name));
      }
      return;
    }
    assert IsDir(old(fs), path);

    // Check for non-empty + non-recursive.
    if !recursive && HasChildren(fs, path) {
      assert HasChildren(old(fs), path);
      r := Err(DirectoryNotEmpty(path, name));
      return;
    }

    if recursive {
      // Remove directory and all children.
      fs := map k | k in fs && k != path && !IsChildOf(k, path) :: fs[k];
    } else {
      // Remove empty directory only.
      fs := map k | k in fs && k != path :: fs[k];
    }
    assert !IsDir(fs, path);
    r := Ok(());
  }

  // ListFiles: non-vacuous iteration with depth + recursive filtering.
  // Includes completeness lower bound: every matching file appears.
  method ListFiles(path: Path, recursive: bool, max_depth: int)
    returns (r: Result<seq<FileInfo>>)
    ensures r.Ok?
    ensures !PathExists(fs, path) ==> r.value == []
    ensures r.Ok? ==>
      forall fi | fi in r.value :: IsFile(fs, fi.path) && IsChildOf(fi.path, path)
    ensures r.Ok? ==>
      forall fi | fi in r.value :: Depth(path, fi.path) >= 0
    ensures !recursive && r.Ok? ==>
      forall fi | fi in r.value :: Depth(path, fi.path) == 0
    ensures recursive && max_depth >= 0 && r.Ok? ==>
      forall fi | fi in r.value :: Depth(path, fi.path) <= max_depth
    ensures r.Ok? && PathExists(fs, path) ==>
      forall p: Path | IsFile(fs, p) && IsChildOf(p, path) &&
        (if !recursive then Depth(path, p) == 0
         else if max_depth >= 0 then Depth(path, p) <= max_depth
         else true) ::
        exists fi | fi in r.value :: fi.path == p
  {
    if path !in fs {
      assert !PathExists(fs, path);
      r := Ok([]);
      return;
    }

    var result: seq<FileInfo> := [];
    ghost var visited: set<Path> := {};
    var remaining := fs.Keys;

    while remaining != {}
      invariant remaining <= fs.Keys
      invariant visited + remaining == fs.Keys
      invariant forall fi | fi in result :: IsFile(fs, fi.path) && IsChildOf(fi.path, path)
      invariant forall fi | fi in result :: Depth(path, fi.path) >= 0
      invariant !recursive ==>
        forall fi | fi in result :: Depth(path, fi.path) == 0
      invariant recursive && max_depth >= 0 ==>
        forall fi | fi in result :: Depth(path, fi.path) <= max_depth
      // Completeness: every matching file in `visited` is in `result`.
      invariant forall p: Path | p in visited && IsFile(fs, p) && IsChildOf(p, path) &&
        (if !recursive then Depth(path, p) == 0
         else if max_depth >= 0 then Depth(path, p) <= max_depth
         else true) ::
        exists fi | fi in result :: fi.path == p
      decreases remaining
    {
      var k :| k in remaining;
      remaining := remaining - {k};
      visited := visited + {k};

      if k in fs && fs[k].FileEntry? && IsChildOf(k, path) {
        var d := Depth(path, k);
        // IsChildOf implies Depth >= 0 (suffix SlashCount is nat).
        assert d >= 0;
        var dominated := if !recursive then d == 0
                         else if max_depth >= 0 then d <= max_depth
                         else true;
        if dominated {
          assert IsFile(fs, k);
          var fi := FileInfo(k, k, |fs[k].content|);
          assert fi.path == k;
          assert IsFile(fs, fi.path);
          assert IsChildOf(fi.path, path);
          assert Depth(path, fi.path) == d;
          assert d >= 0;
          result := result + [fi];
        }
      }
    }

    r := Ok(result);
  }

  method ListFolders(path: Path) returns (r: Result<seq<FolderEntry>>)
    ensures r.Ok?
    ensures !PathExists(fs, path) ==> r.value == []
    ensures r.Ok? ==>
      forall fe | fe in r.value :: IsDir(fs, fe.path) && IsChildOf(fe.path, path)
    ensures r.Ok? && PathExists(fs, path) ==>
      forall p: Path | IsDir(fs, p) && IsChildOf(p, path) ::
        exists fe | fe in r.value :: fe.path == p
  {
    if path !in fs {
      assert !PathExists(fs, path);
      r := Ok([]);
      return;
    }

    var result: seq<FolderEntry> := [];
    var remaining := fs.Keys;
    ghost var visited: set<Path> := {};

    while remaining != {}
      invariant remaining <= fs.Keys
      invariant visited + remaining == fs.Keys
      invariant forall fe | fe in result :: IsDir(fs, fe.path) && IsChildOf(fe.path, path)
      invariant forall p: Path | p in visited && IsDir(fs, p) && IsChildOf(p, path) ::
        exists fe | fe in result :: fe.path == p
      decreases remaining
    {
      var k :| k in remaining;
      remaining := remaining - {k};
      visited := visited + {k};

      if k in fs && fs[k].DirEntry? && IsChildOf(k, path) {
        assert IsDir(fs, k);
        assert IsChildOf(k, path);
        var fe := FolderEntry(k, k);
        assert fe.path == k;
        result := result + [fe];
      }
    }

    r := Ok(result);
  }

  method GetFileInfo(path: Path) returns (r: Result<FileInfo>)
    ensures IsDir(fs, path)       ==> r == Err(InvalidPath(path, name))
    ensures !PathExists(fs, path) ==> r == Err(NotFound(path, name))
    ensures IsFile(fs, path)      ==> r.Ok? && r.value == fs[path].info
  {
    if path in fs {
      match fs[path]
      case FileEntry(_, info) =>
        assert IsFile(fs, path);
        r := Ok(info);
      case DirEntry =>
        assert IsDir(fs, path);
        r := Err(InvalidPath(path, name));
    } else {
      assert !PathExists(fs, path);
      r := Err(NotFound(path, name));
    }
  }

  // GetFolderInfo: symmetric with GetFileInfo — file path → InvalidPath.
  // Computes file_count and total_size by scanning the filesystem.
  method GetFolderInfo(path: Path) returns (r: Result<FolderInfo>)
    ensures IsFile(fs, path)      ==> r == Err(InvalidPath(path, name))
    ensures !PathExists(fs, path) ==> r == Err(NotFound(path, name))
    ensures IsDir(fs, path)       ==>
      r.Ok? && r.value.path == path
      && r.value.file_count == |ChildFiles(fs, path)|
      && r.value.total_size == SumSizes(fs, ChildFiles(fs, path))
  {
    if path in fs {
      match fs[path]
      case DirEntry =>
        assert IsDir(fs, path);
        // Compute file_count and total_size by iterating child files.
        var file_count: nat := 0;
        var total_size: nat := 0;
        var remaining := fs.Keys;
        ghost var visited: set<Path> := {};
        ghost var counted: set<Path> := {};
        while remaining != {}
          invariant remaining <= fs.Keys
          invariant visited == fs.Keys - remaining
          // counted is exactly the child files we've seen so far.
          invariant counted == ChildFiles(fs, path) * visited
          invariant file_count == |counted|
          invariant total_size == SumSizes(fs, counted)
          decreases remaining
        {
          var k :| k in remaining;
          // k is in remaining, so not yet in visited, so not yet in counted.
          assert k !in visited;
          assert k !in counted;
          remaining := remaining - {k};
          visited := visited + {k};
          if k in fs && fs[k].FileEntry? && IsChildOf(k, path) {
            assert k in ChildFiles(fs, path);
            SumSizesAddOneLocal(fs, counted, k);
            counted := counted + {k};
            file_count := file_count + 1;
            total_size := total_size + fs[k].info.size;
          }
        }
        assert visited == fs.Keys;
        assert counted == ChildFiles(fs, path);
        r := Ok(FolderInfo(path, path, file_count, total_size));
      case FileEntry(_, _) =>
        assert IsFile(fs, path);
        r := Err(InvalidPath(path, name));
    } else {
      assert !PathExists(fs, path);
      r := Err(NotFound(path, name));
    }
  }

  // Move: directory src → InvalidPath; missing src → NotFound.
  method Move(src: Path, dst: Path, overwrite: bool)
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
    ensures IsFile(old(fs), src) && !IsDir(old(fs), dst) &&
            (!IsFile(old(fs), dst) || overwrite || src == dst)
      ==> r.Ok?
    ensures r.Ok? && IsFile(old(fs), src) ==>
      IsFile(fs, dst) &&
      fs[dst].content == old(fs)[src].content &&
      (src != dst ==> !PathExists(fs, src))
  {
    // Directory src → InvalidPath.
    if src in fs && fs[src].DirEntry? {
      assert IsDir(old(fs), src);
      r := Err(InvalidPath(src, name));
      return;
    }

    // Missing → NotFound.
    if !(src in fs && fs[src].FileEntry?) {
      assert !PathExists(old(fs), src);
      r := Err(NotFound(src, name));
      return;
    }
    assert IsFile(old(fs), src);

    // Directory dst → InvalidPath.
    if dst in fs && fs[dst].DirEntry? {
      assert IsDir(old(fs), dst);
      r := Err(InvalidPath(dst, name));
      return;
    }

    // Self-move is a no-op.
    if src == dst {
      assert IsFile(fs, dst);
      assert fs[dst].content == old(fs)[src].content;
      r := Ok(());
      return;
    }

    // AlreadyExists check.
    if dst in fs && fs[dst].FileEntry? && !overwrite {
      assert IsFile(old(fs), dst);
      r := Err(AlreadyExists(dst, name));
      return;
    }

    EnsureParents(dst);
    var srcEntry := fs[src];
    var newInfo := FileInfo(dst, dst, srcEntry.info.size);
    var newEntry := FileEntry(srcEntry.content, newInfo);
    fs := (map k | k in fs && k != src :: fs[k])[dst := newEntry];
    assert dst in fs;
    assert fs[dst].content == old(fs)[src].content;
    assert src != dst;
    assert src !in fs;
    r := Ok(());
  }

  // Copy: directory src → InvalidPath; self-copy is no-op.
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
    ensures IsFile(old(fs), src) && !IsDir(old(fs), dst) &&
            (!IsFile(old(fs), dst) || overwrite || src == dst)
      ==> r.Ok?
    ensures r.Ok? && IsFile(old(fs), src) ==>
      IsFile(fs, src) && IsFile(fs, dst) &&
      fs[dst].content == old(fs)[src].content
  {
    // Directory src → InvalidPath.
    if src in fs && fs[src].DirEntry? {
      assert IsDir(old(fs), src);
      r := Err(InvalidPath(src, name));
      return;
    }

    // Missing → NotFound.
    if !(src in fs && fs[src].FileEntry?) {
      assert !PathExists(old(fs), src);
      r := Err(NotFound(src, name));
      return;
    }
    assert IsFile(old(fs), src);

    // Directory dst → InvalidPath.
    if dst in fs && fs[dst].DirEntry? {
      assert IsDir(old(fs), dst);
      r := Err(InvalidPath(dst, name));
      return;
    }

    // Self-copy is a no-op.
    if src == dst {
      assert IsFile(fs, src);
      assert IsFile(fs, dst);
      assert fs[dst].content == old(fs)[src].content;
      r := Ok(());
      return;
    }

    // AlreadyExists check.
    if dst in fs && fs[dst].FileEntry? && !overwrite {
      assert IsFile(old(fs), dst);
      r := Err(AlreadyExists(dst, name));
      return;
    }

    EnsureParents(dst);
    var srcEntry := fs[src];
    var newInfo := FileInfo(dst, dst, srcEntry.info.size);
    fs := fs[dst := FileEntry(srcEntry.content, newInfo)];
    assert dst in fs && fs[dst].FileEntry?;
    assert IsFile(fs, dst);
    assert fs[dst].content == old(fs)[src].content;
    assert src in fs && fs[src] == old(fs)[src];
    assert IsFile(fs, src);
    r := Ok(());
  }

  method RequireCapability(cap: Capability) returns (r: Result<()>)
    ensures cap in capabilities ==> r.Ok?
    ensures cap !in capabilities ==>
      r == Err(CapabilityNotSupported(CapabilityName(cap), name))
  {
    if cap in capabilities {
      r := Ok(());
    } else {
      r := Err(CapabilityNotSupported(CapabilityName(cap), name));
    }
  }
}

// ---------------------------------------------------------------------------
// Local lemma wrappers (Dafny 4.9.1 Boogie bug workaround)
// ---------------------------------------------------------------------------
// SumSizesAddOne from BackendContract.dfy cannot be called directly in
// MemoryBackend methods — Dafny 4.9.1 fails to emit the Boogie procedure
// for lemmas from included files that transitively use `:|` in ghost
// functions (SetToSeq).  These local wrappers reproduce the proofs.

lemma {:induction false} SumSizesAddOneLocal(fs: Filesystem, s: set<Path>, k: Path)
  requires k !in s
  requires forall p | p in (s + {k}) :: p in fs && fs[p].FileEntry?
  ensures SumSizes(fs, s + {k}) == SumSizes(fs, s) + fs[k].info.size
{
  var combined := SetToSeq(s + {k});
  var base := SetToSeq(s);
  assert forall x :: multiset(combined)[x] == multiset(base + [k])[x];
  SumSizesSeqPermutation(fs, combined, base + [k]);
  SumSizesSeqAppend(fs, base, k);
}

// ---------------------------------------------------------------------------
// Verified properties
// ---------------------------------------------------------------------------

lemma WriteReadRoundtrip(fs: Filesystem, path: Path, content: seq<nat>)
  requires !IsDir(fs, path)
  requires !IsFile(fs, path)
  ensures var newFs := fs[path := FileEntry(content, FileInfo(path, path, |content|))];
          IsFile(newFs, path) && newFs[path].content == content
{
  var newFs := fs[path := FileEntry(content, FileInfo(path, path, |content|))];
  assert path in newFs;
  assert newFs[path].FileEntry?;
}

lemma DeleteRemovesPath(fs: Filesystem, path: Path)
  requires IsFile(fs, path)
  ensures var newFs := map k | k in fs && k != path :: fs[k];
          !PathExists(newFs, path)
{
  var newFs := map k | k in fs && k != path :: fs[k];
  assert path !in newFs;
}

lemma MovePreservesContent(
  fs: Filesystem, src: Path, dst: Path, content: seq<nat>, size: nat
)
  requires src != dst
  requires IsFile(fs, src)
  requires fs[src].content == content
  ensures var newFs := (map k | k in fs && k != src :: fs[k])
                        [dst := FileEntry(content, FileInfo(dst, dst, size))];
          IsFile(newFs, dst) &&
          newFs[dst].content == content &&
          !PathExists(newFs, src)
{
  var newFs := (map k | k in fs && k != src :: fs[k])
                [dst := FileEntry(content, FileInfo(dst, dst, size))];
  assert dst in newFs;
  assert newFs[dst].FileEntry?;
  assert src !in newFs;
}

lemma CopyPreservesSource(
  fs: Filesystem, src: Path, dst: Path, content: seq<nat>, size: nat
)
  requires IsFile(fs, src)
  requires fs[src].content == content
  ensures var newFs := fs[dst := FileEntry(content, FileInfo(dst, dst, size))];
          IsFile(newFs, src) && newFs[src].content == content
{
  var newFs := fs[dst := FileEntry(content, FileInfo(dst, dst, size))];
  assert src in newFs;
  if src == dst {
    assert newFs[src].content == content;
  } else {
    assert newFs[src] == fs[src];
  }
}
