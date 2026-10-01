// RootPath.dfy. Verified properties of BE-029's root predicate.
//
// BK-388: `AddressesRoot` lives upstream in BackendContract.dfy §5c, because
// the trait's write-shaped postconditions name it.  This module proves what
// the predicate accepts and rejects, and what the trait then guarantees at
// the root, without adding to the trait, in the shape of DepthCounting.dfy:
//   1. Every slash-and-dot spelling of the root addresses it: the six BE-029
//      names, and (RootSpellingCharacterisation) exactly the keys whose
//      every '/'-segment is "" or ".", stated character by character.
//   2. The Root sentinel addresses it.
//   3. On the trait's domain (WellFormedPath) it holds for Root alone, so
//      the trait's root clauses fire on exactly the one well-formed root.
//   4. A backslash key does not address the root (BE-029's stated bound).
//   5. On a live backend the root answers per BE-029's table, derived from
//      the trait alone, so for every refinement.
//   6-7. A raw-key entry for write and the move/copy destination folds
//      every root spelling onto Root and refuses it: BE-029's write clause
//      for the spellings the trait's well-formed domain excludes.  The
//      move/copy source stays on the canonical Root, as BE-029 decides it.
//
// ID-251: MemoryBackend.dfy includes this module, so its non-ghost members
// (§4's RootAnswersPerTable, §5's RootFold, WriteKey, MoveKey, CopyKey)
// compile into the Python oracle.  §5 is the adapter's entry for writes and
// move/copy destinations: a body change here needs module_.py regenerated.

include "BackendContract.dfy"

// ---------------------------------------------------------------------------
// §1  The root spellings
// ---------------------------------------------------------------------------

// Property 1: BE-029 § "Every spelling that addresses it" lists "", ".",
// "./", ".//", "./." and "/"; each has no addressable segment.
lemma RootSpellingsAddressRoot()
  // @spec BE-029
  ensures AddressesRoot("")
  ensures AddressesRoot(".")
  ensures AddressesRoot("./")
  ensures AddressesRoot(".//")
  ensures AddressesRoot("./.")
  ensures AddressesRoot("/")
{
  // Each unfolds one character at a time down to "".
  assert AddressesRoot("");
  assert "/"[1..] == "";
  assert AddressesRoot("/");
  assert "//"[1..] == "/";
  assert AddressesRoot("//");
  assert "./"[1..] == "/";
  assert AddressesRoot("./");
  assert ".//"[1..] == "//";
  assert AddressesRoot(".//");
  assert "."[1..] == "";
  assert AddressesRoot(".");
  assert "/."[1..] == ".";
  assert AddressesRoot("/.");
  assert "./."[1..] == "/.";
  assert AddressesRoot("./.");
}

// A key made only of "" and "." segments, stated per character: every
// character is '/' or '.', and a '.' ends the key or is followed by '/'.
// (A '.' followed by '.' would start a ".." or longer segment, which
// addresses something.)
ghost predicate RootSpelling(s: string)
{
  forall i | 0 <= i < |s| ::
    (s[i] == '/' || s[i] == '.') && (s[i] == '.' ==> i + 1 == |s| || s[i + 1] == '/')
}

// Property 1, universally: AddressesRoot accepts exactly the root spellings,
// so the six above are instances, not the whole of what is proved.
// Induction on |s|, following AddressesRoot's own recursion.
lemma {:induction false} RootSpellingCharacterisation(s: string)
  // @spec BE-029
  ensures AddressesRoot(s) <==> RootSpelling(s)
  decreases |s|
{
  if |s| == 0 {
    assert RootSpelling(s);
  } else {
    RootSpellingCharacterisation(s[1..]);
    // RootSpelling(s) is RootSpelling(s[1..]) plus the condition at index 0.
    assert forall i | 1 <= i < |s| :: s[i] == s[1..][i - 1];
    if s[0] == '/' || (s[0] == '.' && (|s| == 1 || s[1] == '/')) {
      assert AddressesRoot(s) == AddressesRoot(s[1..]);
      assert RootSpelling(s) <==> RootSpelling(s[1..]);
    } else {
      assert !AddressesRoot(s);
      assert !RootSpelling(s);
    }
  }
}

// Property 2: the sentinel the Python adapter maps "" onto is the root.
lemma RootSentinelAddressesRoot()
  // @spec BE-029
  ensures AddressesRoot(Root)
{
  assert Root == ".";
  assert "."[1..] == "";
  assert AddressesRoot("");
}

// ---------------------------------------------------------------------------
// §2  The predicate on the trait's domain
// ---------------------------------------------------------------------------

// Property 3: a well-formed path other than Root never addresses the root.
//
// Proof outline: a well-formed non-root path is non-empty and has no
// leading '/', so AddressesRoot can only accept it through a leading '.'
// followed by the end or by '/'.  The end makes it ".", which is Root; a
// '/' makes "." a leading segment, which PATH-006 (no "." segment) rules
// out.
lemma WellFormedNonRootIsNotRoot(s: string)
  requires WellFormedPath(s)
  requires s != Root
  // @spec BE-029
  ensures !AddressesRoot(s)
{
  assert |s| > 0;
  assert s[0] != '/';
  if AddressesRoot(s) {
    assert s[0] == '.' && (|s| == 1 || s[1] == '/');
    if |s| == 1 {
      assert s == ".";
      assert s == Root;
      assert false;
    } else {
      assert s[..2] == "./";
      assert HasSegment(s, ".");
      assert false;
    }
  }
}

// ---------------------------------------------------------------------------
// §3  The stated bound
// ---------------------------------------------------------------------------

// Property 4: BE-029 § "The rule stops at the slash-and-dot spellings": a
// backslash-only key is not refused, because folding '\' would move the
// addressing the same predicate decides.
lemma BackslashIsNotRoot()
  // @spec BE-029
  ensures !AddressesRoot("\\")
{
  assert "\\"[0] == '\\';
  assert "\\"[0] != '/' && "\\"[0] != '.';
}

// ---------------------------------------------------------------------------
// §4  BE-029's table, derived from the trait
// ---------------------------------------------------------------------------

// Property 5: on any live backend, present container or absent, the root
// answers as BE-029's table says.  A verified client of the trait, so every
// answer is derived from the trait's postconditions and Valid(), for every
// refinement.  It holds only because Valid() keeps Root a DirEntry.
method RootAnswersPerTable(b: Backend)
  returns (e: Result<bool>, d: Result<bool>, f: Result<bool>,
           rd: Result<ReadStream>, fi: Result<FileInfo>, gi: Result<FolderInfo>)
  requires b.Valid() && b.Live()
  // @spec BE-029
  ensures e == Ok(true)
  ensures d == Ok(true)
  ensures f == Ok(false)
  ensures rd == Err(InvalidPath(Root, b.name))
  ensures fi == Err(InvalidPath(Root, b.name))
  ensures gi.Ok?
{
  e := b.Exists(Root);
  d := b.IsFolderMethod(Root);
  f := b.IsFileMethod(Root);
  rd := b.Read(Root);
  fi := b.GetFileInfo(Root);
  gi := b.GetFolderInfo(Root);
}

// ---------------------------------------------------------------------------
// §5  Raw-key entry: every spelling, not just the sentinel
// ---------------------------------------------------------------------------
// The trait takes well-formed Paths, and on that domain AddressesRoot is
// `path == Root` (property 3), so the trait alone says nothing about "./"
// or "/".  BE-029's write clause binds "every spelling that addresses it".
// The entry methods below take the raw key a caller hands a backend, fold
// every root spelling onto Root, and call the trait; their postconditions
// state the refusal for the raw key.  Scope: the write clause (write and
// the move/copy destination), the one clause BE-029 widens past `is_root`.
// The move/copy source is file-shaped and BE-029 decides it with `is_root`,
// so it is not folded: it must be well-formed, and Root is its one root
// spelling.  A non-root key must still be well-formed, as at the trait.

// The keys an entry accepts: any root spelling, or a well-formed path.
ghost predicate EntryKey(key: string)
{
  AddressesRoot(key) || WellFormedPath(key)
}

// Fold every root spelling onto the sentinel; any other key is unchanged.
function RootFold(key: string): Path
  requires EntryKey(key)
{
  if AddressesRoot(key) then Root else key
}

// The fold lands on the trait's domain, keeps root-ness, and is the
// identity on well-formed keys, so a canonical caller sees the trait itself.
lemma RootFoldProperties(key: string)
  requires EntryKey(key)
  // @spec BE-029
  ensures WellFormedPath(RootFold(key))
  ensures AddressesRoot(RootFold(key)) <==> AddressesRoot(key)
  ensures WellFormedPath(key) ==> RootFold(key) == key
{
  RootSentinelAddressesRoot();
  if WellFormedPath(key) && key != Root {
    WellFormedNonRootIsNotRoot(key);
  }
}

// Property 6: a write to any root spelling is refused, with no effect.
method WriteKey(
  b: Backend, key: string, content: seq<nat>, overwrite: bool,
  metadata: Option<map<string, string>>
) returns (r: Result<WriteResult>)
  requires EntryKey(key)
  requires b.Valid()
  modifies b
  ensures b.Valid()
  // @spec BE-020
  ensures !old(b.Live()) ==> r == Err(BackendUnavailable(b.name))
  // @spec BE-029
  ensures old(b.Live()) && AddressesRoot(key)
    ==> (r == Err(InvalidPath(Root, b.name))
         && b.fs == old(b.fs) && b.containerPresent == old(b.containerPresent))
{
  RootFoldProperties(key);
  r := b.Write(RootFold(key), content, overwrite, metadata);
}

// Property 7: a move whose destination is any root spelling, or whose
// source is the root, is refused with no effect; a root destination
// outranks every observed source check (BE-018 carve-out), so a missing
// source cannot answer first.
method MoveKey(b: Backend, src: Path, dst: string, overwrite: bool)
  returns (r: Result<()>)
  requires WellFormedPath(src) && EntryKey(dst)
  requires b.Valid()
  modifies b
  ensures b.Valid()
  // @spec BE-020
  ensures !old(b.Live()) ==> r == Err(BackendUnavailable(b.name))
  // @spec BE-029
  ensures old(b.Live()) && (src == Root || AddressesRoot(dst))
    ==> r == Err(InvalidPath(Root, b.name)) && b.fs == old(b.fs)
{
  RootFoldProperties(dst);
  if src != Root {
    WellFormedNonRootIsNotRoot(src);
  }
  RootSentinelAddressesRoot();
  ghost var phase: MovePhase;
  r, phase := b.Move(src, RootFold(dst), overwrite);
}

// Property 7, for copy.
method CopyKey(b: Backend, src: Path, dst: string, overwrite: bool)
  returns (r: Result<()>)
  requires WellFormedPath(src) && EntryKey(dst)
  requires b.Valid()
  modifies b
  ensures b.Valid()
  // @spec BE-020
  ensures !old(b.Live()) ==> r == Err(BackendUnavailable(b.name))
  // @spec BE-029
  ensures old(b.Live()) && (src == Root || AddressesRoot(dst))
    ==> r == Err(InvalidPath(Root, b.name)) && b.fs == old(b.fs)
{
  RootFoldProperties(dst);
  if src != Root {
    WellFormedNonRootIsNotRoot(src);
  }
  RootSentinelAddressesRoot();
  r := b.Copy(src, RootFold(dst), overwrite);
}
