// StoreTree.dfy. RFC-0021's model: the store is a tree, and each backend
// encodes it (BK-432).  A sketch verified before the RFC's acceptance; it
// checks the RFC's prose and is not yet wired into BackendContract.dfy.
//
//   §1  The tree: keys name at most one node; Valid() in BackendContract.dfy
//       states the same invariant over its string paths.
//   §2  Resolution: what a key resolves to (A.1).
//   §3  A write at the tree level, and that it keeps the tree valid when the
//       key resolves to an item or to nothing (A.4, A.5's write column).
//   §4  The flat encoding: a set of item keys, its partial decode, and that
//       decoding yields a valid tree (A.2).
//   §5  What a flat driver observes agrees with the tree: a key in the raw set
//       is an item, a raw key below it makes it a folder, a raw key above it
//       puts it through an item (A.3, A.5).
//   §6  A flat write guarded by A.4's two checks keeps the encoding decodable
//       and agrees with the tree's write; the checks fail exactly where the
//       tree answers InvalidPath (D4).
//   §7  A flat delete keeps the encoding decodable, and a flat encoding holds
//       no empty folder (A.6).
//   §8  After the stat that finds no item, a flat listing of k/ returns
//       exactly the tree's children of k (A.3, A.5's folder-read column).
//   §9  A recursive delete_folder by walking deletes what its listings return
//       below k, an entry the listing omits keeps the folder non-empty, and
//       an item above k hides nothing (A.3's stated limit).
//   §10 A flat move or copy, its destination checked by A.4, keeps the
//       encoding decodable and moves or copies exactly that item.
//   §11 Refusals as observations (A.8): for every call, namespace and row,
//       the kernel's answer after a refusal in the probe set is the refusal
//       or the A.5 result of the row actually there, and only a result A.8
//       rule 4 allows (a row where the call must refuse, or a listing's
//       empty result on a row that holds nothing); and every such row is
//       typed.
//
// Not modelled here: links (A.7), a listing's omissions as observed page by
// page (A.3's order obligation), and changes under an operation (A.9).  A
// hierarchical encoding with folder objects is the tree itself, so §3 covers
// its writes.

module StoreTree {

  // -------------------------------------------------------------------------
  // §1  The tree
  // -------------------------------------------------------------------------

  type Key = seq<string>

  predicate ProperPrefix(p: Key, k: Key) {
    |p| < |k| && k[..|p|] == p
  }

  datatype Kind = Item | Folder

  type Tree = map<Key, Kind>

  // The root is a folder, and every proper prefix of a node's key is a
  // folder: nothing lives below an item.
  ghost predicate ValidTree(t: Tree) {
    && [] in t && t[[]] == Folder
    && forall k, i :: k in t && 0 <= i < |k| ==> k[..i] in t && t[k[..i]] == Folder
  }

  // -------------------------------------------------------------------------
  // §2  Resolution
  // -------------------------------------------------------------------------

  datatype Res = RItem | RFolder | RNothing | RThroughItem

  ghost predicate ItemAbove(t: Tree, k: Key) {
    exists i :: 0 <= i < |k| && k[..i] in t && t[k[..i]] == Item
  }

  ghost function Resolve(t: Tree, k: Key): Res {
    if k in t then (if t[k] == Item then RItem else RFolder)
    else if ItemAbove(t, k) then RThroughItem
    else RNothing
  }

  // -------------------------------------------------------------------------
  // §3  A write at the tree level
  // -------------------------------------------------------------------------

  ghost function Prefixes(k: Key): set<Key> {
    set i | 0 <= i < |k| :: k[..i]
  }

  // The item at k, its missing parents created as folders.
  ghost function TreeWrite(t: Tree, k: Key): Tree {
    map j | j in t.Keys + Prefixes(k) + {k} :: if j == k then Item else if j in t then t[j] else Folder
  }

  lemma TreeWriteKeepsValid(t: Tree, k: Key)
    requires ValidTree(t) && k != []
    requires Resolve(t, k) == RItem || Resolve(t, k) == RNothing
    ensures ValidTree(TreeWrite(t, k))
  {
    var w := TreeWrite(t, k);
    // Every proper prefix of k that t holds is a folder.
    forall i | 0 <= i < |k| && k[..i] in t
      ensures t[k[..i]] == Folder
    {
      if k in t {
      } else {
        assert !ItemAbove(t, k);
      }
    }
    assert k[..0] == [];
    assert [] in Prefixes(k);
    forall j, i | j in w && 0 <= i < |j|
      ensures j[..i] in w && w[j[..i]] == Folder
    {
      if j == k {
        assert j[..i] in Prefixes(k);
      } else if j in t {
        assert j[..i] in t && t[j[..i]] == Folder;
        if j[..i] == k {
          assert k in t && t[k] == Folder;
        }
      } else {
        var m :| 0 <= m < |k| && j == k[..m];
        assert j[..i] == k[..i];
        assert j[..i] in Prefixes(k);
      }
    }
  }

  // -------------------------------------------------------------------------
  // §4  The flat encoding
  // -------------------------------------------------------------------------

  // A flat store's raw state: the keys of its items.  It has no folder
  // objects; a folder is any proper prefix of an item's key.
  type Flat = set<Key>

  // A.2: the raw state decodes when no item lies below another item's key.
  ghost predicate FlatDecodable(r: Flat) {
    && [] !in r
    && forall a, b :: a in r && b in r ==> !ProperPrefix(a, b)
  }

  ghost function FlatKeys(r: Flat): set<Key> {
    {[]} + (set b, i | b in r && 0 <= i <= |b| :: b[..i])
  }

  ghost function FlatDecode(r: Flat): Tree {
    map j | j in FlatKeys(r) :: if j in r then Item else Folder
  }

  lemma InFlatKeys(r: Flat, b: Key, i: int)
    requires b in r && 0 <= i <= |b|
    ensures b[..i] in FlatKeys(r)
  {}

  lemma FlatDecodeValid(r: Flat)
    requires FlatDecodable(r)
    ensures ValidTree(FlatDecode(r))
  {
    var t := FlatDecode(r);
    forall j, i | j in t && 0 <= i < |j|
      ensures j[..i] in t && t[j[..i]] == Folder
    {
      var b, m :| b in r && 0 <= m <= |b| && j == b[..m];
      assert j[..i] == b[..i];
      InFlatKeys(r, b, i);
      if b[..i] in r {
        assert ProperPrefix(b[..i], b);
      }
    }
  }

  // -------------------------------------------------------------------------
  // §5  What a flat driver observes agrees with the tree
  // -------------------------------------------------------------------------

  lemma FlatResolve(r: Flat, k: Key)
    requires FlatDecodable(r) && k != []
    // A lookup of k (one stat) sees an item exactly when the tree has one.
    ensures (k in r) <==> Resolve(FlatDecode(r), k) == RItem
    // A listing of k/ (list_page(k, limit=1)) is non-empty exactly when the
    // tree has a folder at k.
    ensures (exists b :: b in r && ProperPrefix(k, b)) <==> Resolve(FlatDecode(r), k) == RFolder
    // A stat of an ancestor finds an item exactly when the tree puts k
    // through an item.
    ensures (exists i :: 0 <= i < |k| && k[..i] in r) <==> Resolve(FlatDecode(r), k) == RThroughItem
  {
    var t := FlatDecode(r);
    if k in r {
      InFlatKeys(r, k, |k|);
      assert k[..|k|] == k;
    }
    if b :| b in r && ProperPrefix(k, b) {
      InFlatKeys(r, b, |k|);
      assert k !in r;
    }
    if k in t && k !in r {
      var b, m :| b in r && 0 <= m <= |b| && k == b[..m];
      if m == |b| {
        assert k == b;
      }
      assert ProperPrefix(k, b);
    }
    if i :| 0 <= i < |k| && k[..i] in r {
      if k in t {
        var b, m :| b in r && 0 <= m <= |b| && k == b[..m];
        assert k[..i] == b[..i];
        assert ProperPrefix(b[..i], b);
      }
      InFlatKeys(r, k[..i], |k[..i]|);
      assert k[..i][..|k[..i]|] == k[..i];
      assert ItemAbove(t, k);
    }
    if Resolve(t, k) == RThroughItem {
      var i :| 0 <= i < |k| && k[..i] in t && t[k[..i]] == Item;
      assert k[..i] in r;
    }
  }

  // -------------------------------------------------------------------------
  // §6  A flat write, guarded by A.4's checks
  // -------------------------------------------------------------------------

  // A.4's two checks: no ancestor of k is an item (one stat per ancestor),
  // and nothing lies below k (one list_page(k, limit=1)).
  ghost predicate FlatWriteChecks(r: Flat, k: Key) {
    && (forall i :: 0 <= i < |k| ==> k[..i] !in r)
    && (forall b :: b in r ==> !ProperPrefix(k, b))
  }

  // D4: the checks pass exactly where the tree's write column does not
  // answer InvalidPath.
  lemma FlatWriteChecksAreTheTree(r: Flat, k: Key)
    requires FlatDecodable(r) && k != []
    ensures FlatWriteChecks(r, k) <==>
      (Resolve(FlatDecode(r), k) == RItem || Resolve(FlatDecode(r), k) == RNothing)
  {
    FlatResolve(r, k);
  }

  lemma FlatWriteKeepsDecodable(r: Flat, k: Key)
    requires FlatDecodable(r) && k != [] && FlatWriteChecks(r, k)
    ensures FlatDecodable(r + {k})
  {
    forall a, b | a in r + {k} && b in r + {k}
      ensures !ProperPrefix(a, b)
    {
      if a in r && b == k && ProperPrefix(a, k) {
        assert k[..|a|] == a;
      }
    }
  }

  lemma FlatWriteCommutes(r: Flat, k: Key)
    requires FlatDecodable(r) && k != [] && FlatWriteChecks(r, k)
    ensures FlatDecode(r + {k}) == TreeWrite(FlatDecode(r), k)
  {
    var t := FlatDecode(r);
    var lhs := FlatDecode(r + {k});
    var rhs := TreeWrite(t, k);
    forall j | j in FlatKeys(r + {k})
      ensures j in t.Keys + Prefixes(k) + {k}
    {
      if j != [] {
        var b, m :| b in r + {k} && 0 <= m <= |b| && j == b[..m];
        if b == k {
          if m == |k| {
            assert j == k;
          } else {
            assert j in Prefixes(k);
          }
        } else {
          InFlatKeys(r, b, m);
        }
      }
    }
    forall j | j in t.Keys + Prefixes(k) + {k}
      ensures j in FlatKeys(r + {k})
    {
      if j == k {
        InFlatKeys(r + {k}, k, |k|);
        assert k[..|k|] == k;
      } else if j in Prefixes(k) {
        var i :| 0 <= i < |k| && j == k[..i];
        InFlatKeys(r + {k}, k, i);
      } else if j != [] {
        var b, m :| b in r && 0 <= m <= |b| && j == b[..m];
        InFlatKeys(r + {k}, b, m);
      }
    }
    assert lhs.Keys == rhs.Keys;
    forall j | j in lhs.Keys
      ensures lhs[j] == rhs[j]
    {
      if j != k && j !in t {
        // j is a proper prefix of k, which the checks keep out of r.
        assert j in Prefixes(k);
        var i :| 0 <= i < |k| && j == k[..i];
        assert j !in r;
      }
    }
  }

  // -------------------------------------------------------------------------
  // §7  A flat delete, and empty folders
  // -------------------------------------------------------------------------

  lemma FlatDeleteKeepsDecodable(r: Flat, k: Key)
    requires FlatDecodable(r)
    ensures FlatDecodable(r - {k})
  {}

  // A.6: a flat encoding holds no empty folder.  Every folder but the root
  // has an item below it, so deleting the last one makes the folder vanish.
  lemma FlatFoldersHoldItems(r: Flat, j: Key)
    requires FlatDecodable(r)
    requires j in FlatDecode(r) && j != [] && FlatDecode(r)[j] == Folder
    ensures exists b :: b in r && ProperPrefix(j, b)
  {
    var b, m :| b in r && 0 <= m <= |b| && j == b[..m];
    if m == |b| {
      assert j == b;
    }
    assert ProperPrefix(j, b);
  }

  // The items a tree holds.  On a flat encoding they are the raw keys.
  ghost function Items(t: Tree): set<Key> {
    set j | j in t && t[j] == Item
  }

  lemma FlatItems(r: Flat)
    requires FlatDecodable(r)
    ensures Items(FlatDecode(r)) == r
  {
    forall j | j in r
      ensures j in Items(FlatDecode(r))
    {
      InFlatKeys(r, j, |j|);
      assert j[..|j|] == j;
    }
  }

  // -------------------------------------------------------------------------
  // §8  Folder-read on a flat encoding
  // -------------------------------------------------------------------------

  // The tree's children of a folder k: the nodes one segment below it.
  ghost function Children(t: Tree, k: Key): set<Key> {
    set j | j in t && |j| == |k| + 1 && ProperPrefix(k, j)
  }

  // A flat listing of k/ with a delimiter: one segment of every raw key
  // below k.
  ghost function FlatChildren(r: Flat, k: Key): set<Key> {
    set b | b in r && ProperPrefix(k, b) :: b[..|k| + 1]
  }

  // A.3, A.5: after the stat that finds no item at k, a flat listing of k/
  // returns exactly the tree's children of k.  When the stat finds an item,
  // the tree's folder-read answers empty (§5), so the listing is not read.
  lemma FlatListingIsTheTree(r: Flat, k: Key)
    requires FlatDecodable(r) && k !in r
    ensures FlatChildren(r, k) == Children(FlatDecode(r), k)
  {
    var t := FlatDecode(r);
    forall c | c in FlatChildren(r, k)
      ensures c in Children(t, k)
    {
      var b :| b in r && ProperPrefix(k, b) && c == b[..|k| + 1];
      InFlatKeys(r, b, |k| + 1);
      assert c[..|k|] == b[..|k|];
    }
    forall c | c in Children(t, k)
      ensures c in FlatChildren(r, k)
    {
      var b, m :| b in r && 0 <= m <= |b| && c == b[..m];
      assert m == |k| + 1;
      assert b[..|k|] == c[..|k|];
      assert ProperPrefix(k, b);
    }
  }

  // -------------------------------------------------------------------------
  // §9  delete_folder on a flat encoding
  // -------------------------------------------------------------------------

  // A walk of k/ sees only what its listings return, so a raw key below k is
  // visible to it when no item lies between k and that key.  An item above k
  // is never listed, so it hides nothing: A.3's stated limit for flat folder
  // operations below an item.
  ghost predicate VisibleBelow(r: Flat, k: Key, b: Key) {
    forall a :: a in r && ProperPrefix(k, a) ==> !ProperPrefix(a, b)
  }

  // A recursive delete_folder by walking: it deletes every raw key below k
  // that its listings return, and nothing else.
  ghost function FlatDeleteTree(r: Flat, k: Key): Flat {
    set b | b in r && !(ProperPrefix(k, b) && VisibleBelow(r, k, b))
  }

  // On a decodable encoding every raw key is visible, so the walk removes
  // the whole subtree and the tree's items below k.
  lemma FlatDeleteTreeIsTheTree(r: Flat, k: Key)
    requires FlatDecodable(r) && k !in r
    ensures FlatDecodable(FlatDeleteTree(r, k))
    ensures Items(FlatDecode(FlatDeleteTree(r, k))) ==
      Items(FlatDecode(r)) - (set b | b in Items(FlatDecode(r)) && ProperPrefix(k, b))
    ensures forall b :: b in FlatDeleteTree(r, k) ==> !ProperPrefix(k, b)
  {
    FlatItems(r);
    FlatItems(FlatDeleteTree(r, k));
  }

  // A.3: an omitted raw key keeps the folder non-empty.  An item i the walk
  // lists below k is deleted, and a raw key b below i, which the listing
  // omits, is kept, so k/ still holds b and the kernel answers
  // DirectoryNotEmpty from its listing.
  lemma OmittedKeepsFolderNonEmpty(r: Flat, k: Key, i: Key, b: Key)
    requires i in r && b in r && ProperPrefix(k, i) && ProperPrefix(i, b)
    requires VisibleBelow(r, k, i)
    ensures i !in FlatDeleteTree(r, k)
    ensures b in FlatDeleteTree(r, k) && ProperPrefix(k, b)
  {
    assert b[..|k|] == i[..|k|];
  }

  // The stated limit, made explicit: an item above k hides nothing from the
  // walk, so a raw key below k is deleted even when the tree would put k
  // through an item.
  lemma ItemAboveHidesNothing(r: Flat, k: Key, a: Key, b: Key)
    requires a in r && b in r && ProperPrefix(a, k) && ProperPrefix(k, b)
    requires forall c :: c in r && ProperPrefix(k, c) ==> !ProperPrefix(c, b)
    ensures b !in FlatDeleteTree(r, k)
  {}

  // -------------------------------------------------------------------------
  // §10  move and copy on a flat encoding
  // -------------------------------------------------------------------------

  // A move of item src to dst, the destination checked by A.4 before src is
  // removed, keeps the encoding decodable and moves exactly that item.
  lemma FlatMoveIsTheTree(r: Flat, src: Key, dst: Key)
    requires FlatDecodable(r) && src in r && dst != [] && dst != src
    requires FlatWriteChecks(r, dst)
    ensures FlatDecodable((r - {src}) + {dst})
    ensures Items(FlatDecode((r - {src}) + {dst})) == (Items(FlatDecode(r)) - {src}) + {dst}
  {
    FlatWriteKeepsDecodable(r - {src}, dst);
    FlatItems(r);
    FlatItems((r - {src}) + {dst});
  }

  // A copy is a write of the source's content to dst (§6).
  lemma FlatCopyIsTheTree(r: Flat, src: Key, dst: Key)
    requires FlatDecodable(r) && src in r && dst != []
    requires FlatWriteChecks(r, dst)
    ensures FlatDecodable(r + {dst})
    ensures FlatDecode(r + {dst}) == TreeWrite(FlatDecode(r), dst)
  {
    FlatWriteKeepsDecodable(r, dst);
    FlatWriteCommutes(r, dst);
  }

  // -------------------------------------------------------------------------
  // §11  Refusals as observations (A.8)
  // -------------------------------------------------------------------------
  //
  // A driver call refused in the probe set may arrive on any row: drivers owe
  // no rule about how a refusal is typed, except the two A.8 names, and a
  // denial or a dead connection can meet an existing item as well as a
  // missing one.  The kernel then probes, concludes a row, and replaces the
  // refusal with that row's A.5 result only where A.8 rule 4 allows it: on a
  // row where the call must refuse, or, for a listing, on a row that holds
  // nothing.  The lemmas: whatever the actual row, the answer is the refusal
  // itself or the A.5 result of the row that is really there.

  // What is at the key, one level finer than Res: a folder is empty or not.
  datatype Row = AtItem | AtEmptyFolder | AtFullFolder | AtNothing | AtThroughItem

  // A.2's property that decides what one stat sees.
  datatype Namespace = FlatNs | HierNs

  // Every driver call A.8's tables name.  move, copy and rename are a source
  // read as Get and a destination written as Put.
  datatype Call =
    | Get | Delete
    | Put(overwrite: bool)
    | EnsureParents
    | RemoveFolder | DeleteTree
    | ListFirstPage

  datatype Answer =
    | Ok | EmptyListing | ENotFound | EInvalidPath | EAlreadyExists | EDirectoryNotEmpty

  // A.5's result for each call and row.
  function A5(c: Call, row: Row): Answer {
    match c
    case Get | Delete =>
      (match row
       case AtItem => Ok
       case AtEmptyFolder | AtFullFolder => EInvalidPath
       case AtNothing | AtThroughItem => ENotFound)
    case Put(overwrite) =>
      (match row
       case AtItem => if overwrite then Ok else EAlreadyExists
       case AtEmptyFolder | AtFullFolder | AtThroughItem => EInvalidPath
       case AtNothing => Ok)
    case EnsureParents =>
      (match row
       case AtThroughItem => EInvalidPath
       case _ => Ok)
    case RemoveFolder =>
      (match row
       case AtItem => EInvalidPath
       case AtEmptyFolder => Ok
       case AtFullFolder => EDirectoryNotEmpty
       case AtNothing | AtThroughItem => ENotFound)
    case DeleteTree =>
      (match row
       case AtItem => EInvalidPath
       case AtEmptyFolder | AtFullFolder => Ok
       case AtNothing | AtThroughItem => ENotFound)
    case ListFirstPage =>
      (match row
       case AtEmptyFolder | AtFullFolder => Ok
       case AtItem | AtNothing | AtThroughItem => EmptyListing)
  }

  // The rows on which the call must refuse: A.8's driver obligations.
  predicate MustRefuse(c: Call, row: Row) {
    A5(c, row) != Ok && A5(c, row) != EmptyListing
  }

  // A.8 rule 4: the results a probe may put in place of a refusal.
  predicate MaySubstitute(c: Call, row: Row) {
    MustRefuse(c, row) || A5(c, row) == EmptyListing
  }

  // What the probe calls see at each row.
  datatype StatSees = SeesItem | SeesFolder | SeesNone

  function Stat(ns: Namespace, row: Row): StatSees {
    match row
    case AtItem => SeesItem
    case AtEmptyFolder | AtFullFolder => if ns == HierNs then SeesFolder else SeesNone
    case AtNothing | AtThroughItem => SeesNone
  }

  predicate ListNonEmpty(row: Row) {
    row == AtFullFolder
  }

  predicate AncestorIsItem(row: Row) {
    row == AtThroughItem
  }

  // The refusal's shape, where an obligation reads it.
  datatype Shape = NotFoundOrInvalidPath | OtherShape

  // The rows a call can meet at all.  A flat encoding holds no empty folder
  // (§7).  A flat write runs A.4's checks first, so its key is no folder and
  // nothing above it is an item.  A flat listing runs after A.3's stat found
  // no item.  ensure_parents runs only with folder objects, on a
  // hierarchical namespace.
  predicate Possible(ns: Namespace, c: Call, row: Row) {
    && !(ns == FlatNs && row == AtEmptyFolder)
    && !(ns == FlatNs && c.Put? && (row == AtFullFolder || row == AtThroughItem))
    && !(ns == FlatNs && c == ListFirstPage && row == AtItem)
    && !(ns == FlatNs && c == EnsureParents)
  }

  // A.8's flat listing obligation: a flat list_page answers NotFound or
  // InvalidPath only when nothing lies under the prefix.
  predicate Obligation(ns: Namespace, c: Call, row: Row, sh: Shape) {
    (ns == FlatNs && c == ListFirstPage && sh == NotFoundOrInvalidPath) ==>
      (row == AtNothing || row == AtThroughItem)
  }

  datatype Option<T> = None | Some(value: T)

  // The kernel's probe after a refusal, as A.8's tables state it: the row it
  // concludes, or None when it leaves the refusal standing.
  function Probe(ns: Namespace, c: Call, row: Row, sh: Shape): Option<Row> {
    var s := Stat(ns, row);
    match c
    case Get | Delete =>
      if s == SeesItem then Some(AtItem)
      else if s == SeesFolder then Some(AtFullFolder)
      else if ns == FlatNs && ListNonEmpty(row) then Some(AtFullFolder)
      else Some(AtNothing)
    case Put(_) =>
      if s == SeesItem then Some(AtItem)
      else if ns == FlatNs then None
      else if s == SeesFolder then Some(AtFullFolder)
      else if AncestorIsItem(row) then Some(AtThroughItem)
      else Some(AtNothing)
    case EnsureParents =>
      if AncestorIsItem(row) then Some(AtThroughItem) else None
    case RemoveFolder | DeleteTree =>
      if ns == FlatNs then
        // BE-031's flat order: list first, stat only after an empty listing.
        if ListNonEmpty(row) then Some(AtFullFolder)
        else if s == SeesItem then Some(AtItem)
        else Some(AtNothing)
      else if s == SeesItem then Some(AtItem)
      else if s == SeesNone then Some(AtNothing)
      else if ListNonEmpty(row) then Some(AtFullFolder)
      else Some(AtEmptyFolder)
    case ListFirstPage =>
      if ns == FlatNs then
        // The only call that sees a flat folder is the listing that just
        // failed, so the obligation reads its shape.
        if sh == NotFoundOrInvalidPath then Some(AtNothing) else None
      else if s == SeesFolder then None
      else if s == SeesItem then Some(AtItem)
      else Some(AtNothing)
  }

  function KernelAnswer(ns: Namespace, c: Call, row: Row, sh: Shape): Option<Answer> {
    var p := Probe(ns, c, row, sh);
    if p.Some? && MaySubstitute(c, p.value) then Some(A5(c, p.value)) else None
  }

  // A.8 rule 4: the answer after a refusal is the refusal (None) or the A.5
  // result of the row actually there, and only a result the rule allows: so
  // a delete refused on an existing item is never reported as NotFound, which
  // missing_ok would turn into success, and a listing refused on a folder that
  // holds entries is never reported as empty.
  lemma RefusalAnswersAreTrue(ns: Namespace, c: Call, row: Row, sh: Shape)
    requires Possible(ns, c, row) && Obligation(ns, c, row, sh)
    ensures KernelAnswer(ns, c, row, sh).Some? ==>
      MaySubstitute(c, row) && KernelAnswer(ns, c, row, sh).value == A5(c, row)
  {}

  // And the probe is not idle: wherever the call must refuse, or a listing's
  // row holds nothing, the kernel types the refusal.  The flat listing
  // depends on its shape, since the only call that sees a flat folder is
  // the listing that failed.
  lemma RefusalsAreTyped(ns: Namespace, c: Call, row: Row, sh: Shape)
    requires Possible(ns, c, row) && MaySubstitute(c, row)
    requires (ns == FlatNs && c == ListFirstPage) ==> sh == NotFoundOrInvalidPath
    ensures KernelAnswer(ns, c, row, sh) == Some(A5(c, row))
  {}
}
