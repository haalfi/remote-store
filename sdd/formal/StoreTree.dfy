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
//
// Not modelled here: links (A.7), refusals as observations (A.8), listings and
// their omissions (A.3), and changes under an operation (A.9).  A hierarchical
// encoding with folder objects is the tree itself, so §3 covers its writes.

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
}
