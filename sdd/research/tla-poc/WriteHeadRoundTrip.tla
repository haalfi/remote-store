------------------------- MODULE WriteHeadRoundTrip -------------------------
(***************************************************************************
  Minimal TLA+ model for spec 045 § WR-008 write-then-head round-trip.

  Question
  --------
  After a successful Store.write(p, data, metadata=m), does Store.head(p)
  produce a WriteResult whose observable fields (size, metadata,
  last_modified) match what was persisted? The non-trivial field is
  WR-008's rename: FileInfo.modified_at (spec 003) becomes
  WriteResult.last_modified (spec 045). WriteResult.source differs by
  design (NATIVE/BASIC vs SIDECAR, per WR-006) and is NOT expected to
  round-trip.

  Scope
  -----
  One action (Write). Head is a pure observation, expressed as a
  function in the invariant rather than a state transition.
  Capabilities: WRITE, WRITE_RESULT_NATIVE, USER_METADATA.

  What is NOT modelled: WR-008 requires head() to be gated on
  Capability.METADATA and raise CapabilityNotSupported when absent.
  Because Head is a pure function here (not an action), that gate
  cannot be expressed as a reachability property — it would need a
  Head action that guards on METADATA_CAP. Only the field-mapping
  half of WR-008 is checked by this module.
***************************************************************************)

EXTENDS Naturals, FiniteSets, TLC

CONSTANTS
    Paths,           \* finite set of path identifiers
    DataSizes,       \* finite set of Nat (possible write sizes)
    MetaValues,      \* finite set of metadata values (excluding sentinel)
    MaxClock         \* Nat — upper bound on timestamps (for state constraint)

WRITE_CAP == "WRITE"
WRITE_RESULT_NATIVE_CAP == "WRITE_RESULT_NATIVE"
USER_META_CAP == "USER_METADATA"
Capabilities == {WRITE_CAP, WRITE_RESULT_NATIVE_CAP, USER_META_CAP}

NO_META == "NO_METADATA_SENTINEL"
ASSUME NO_META \notin MetaValues

NATIVE == "native"
BASIC == "basic"
SIDECAR == "sidecar"

VARIABLES
    written,         \* SUBSET Paths — paths with an observable FS entry
    fi_size,         \* written -> Nat (FileInfo.size, per spec 003)
    fi_mod,          \* written -> Nat (FileInfo.modified_at)
    fi_meta,         \* written -> MetaValues \cup {NO_META}
    wr_size,         \* written -> Nat (last write's returned WriteResult.size)
    wr_mod,          \* written -> Nat (last_modified recorded at write time)
    wr_meta,         \* written -> MetaValues \cup {NO_META}
    wr_source,       \* written -> {NATIVE, BASIC} (from write; never SIDECAR)
    caps,            \* SUBSET Capabilities
    clock            \* Nat — monotonic timestamp counter

vars == <<written, fi_size, fi_mod, fi_meta,
          wr_size, wr_mod, wr_meta, wr_source, caps, clock>>

TypeOK ==
    /\ written \subseteq Paths
    /\ DOMAIN fi_size = written
    /\ DOMAIN fi_mod = written
    /\ DOMAIN fi_meta = written
    /\ DOMAIN wr_size = written
    /\ DOMAIN wr_mod = written
    /\ DOMAIN wr_meta = written
    /\ DOMAIN wr_source = written
    /\ caps \subseteq Capabilities
    /\ clock \in Nat
    /\ \A p \in written:
         /\ fi_size[p] \in Nat
         /\ fi_mod[p] \in Nat
         /\ fi_meta[p] \in MetaValues \cup {NO_META}
         /\ wr_size[p] \in Nat
         /\ wr_mod[p] \in Nat
         /\ wr_meta[p] \in MetaValues \cup {NO_META}
         /\ wr_source[p] \in {NATIVE, BASIC}

Init ==
    /\ written = {}
    /\ fi_size = [p \in {} |-> 0]
    /\ fi_mod = [p \in {} |-> 0]
    /\ fi_meta = [p \in {} |-> NO_META]
    /\ wr_size = [p \in {} |-> 0]
    /\ wr_mod = [p \in {} |-> 0]
    /\ wr_meta = [p \in {} |-> NO_META]
    /\ wr_source = [p \in {} |-> BASIC]
    /\ caps \in SUBSET Capabilities
    /\ WRITE_CAP \in caps
    /\ clock = 0

\* WR-004: source is NATIVE when the backend declares WRITE_RESULT_NATIVE,
\* BASIC otherwise (per WR-009, WRITE_RESULT_NATIVE is independent of METADATA).
\* (WR-005 governs field-population guarantees when source=BASIC; not modelled here.)
WriteSource == IF WRITE_RESULT_NATIVE_CAP \in caps THEN NATIVE ELSE BASIC

\* WR-010: non-empty metadata kwarg requires USER_METADATA.
MetaAllowed(m) == \/ m = NO_META
                  \/ USER_META_CAP \in caps

Write(p, sz, m) ==
    /\ p \in Paths
    /\ sz \in DataSizes
    /\ m \in MetaValues \cup {NO_META}
    /\ WRITE_CAP \in caps
    /\ MetaAllowed(m)
    /\ clock' = clock + 1
    /\ written' = written \cup {p}
    /\ fi_size' = [q \in written' |-> IF q = p THEN sz     ELSE fi_size[q]]
    /\ fi_mod'  = [q \in written' |-> IF q = p THEN clock' ELSE fi_mod[q]]
    /\ fi_meta' = [q \in written' |-> IF q = p THEN m      ELSE fi_meta[q]]
    /\ wr_size' = [q \in written' |-> IF q = p THEN sz     ELSE wr_size[q]]
    /\ wr_mod'  = [q \in written' |-> IF q = p THEN clock' ELSE wr_mod[q]]
    /\ wr_meta' = [q \in written' |-> IF q = p THEN m      ELSE wr_meta[q]]
    /\ wr_source' = [q \in written' |-> IF q = p THEN WriteSource ELSE wr_source[q]]
    /\ UNCHANGED caps

Next ==
    \E p \in Paths, sz \in DataSizes, m \in MetaValues \cup {NO_META}:
        Write(p, sz, m)

Spec == Init /\ [][Next]_vars

\* ==========================================================================
\* The WR-008 mapping: Head(p) constructs a WriteResult from the FileInfo.
\* Field mapping per spec 045 § WR-008 table:
\*   WriteResult.path          = FileInfo.path         (trivial; omitted)
\*   WriteResult.size          = FileInfo.size
\*   WriteResult.last_modified = FileInfo.modified_at  (RENAME)
\*   WriteResult.metadata      = FileInfo.metadata
\*   WriteResult.source        = SIDECAR (always, per WR-006)
\*
\* Breaking this function is the PoC's break-and-catch lever.
\* ==========================================================================
HeadResult(p) ==
    [size          |-> fi_size[p],
     last_modified |-> fi_mod[p],
     metadata      |-> fi_meta[p],
     source        |-> SIDECAR]

LastWriteResult(p) ==
    [size          |-> wr_size[p],
     last_modified |-> wr_mod[p],
     metadata      |-> wr_meta[p],
     source        |-> wr_source[p]]

\* ==========================================================================
\* THE invariants. WriteHeadAgree and HeadIsSidecar are deliberately
\* disjoint: WriteHeadAgree checks the three data fields (size, metadata,
\* last_modified); HeadIsSidecar checks source. A break in one does not
\* trigger the other.
\* ==========================================================================
WriteHeadAgree ==
    \A p \in written:
        /\ HeadResult(p).size          = LastWriteResult(p).size
        /\ HeadResult(p).metadata      = LastWriteResult(p).metadata
        /\ HeadResult(p).last_modified = LastWriteResult(p).last_modified

\* WR-006: head() always yields source = SIDECAR (not NATIVE, not BASIC).
HeadIsSidecar ==
    \A p \in written: HeadResult(p).source = SIDECAR

\* Bound the state space for TLC.
StateConstraint == clock <= MaxClock
=============================================================================
