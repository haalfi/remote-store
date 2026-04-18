---------------------- MODULE WR018ProxyForwarding ----------------------
(***************************************************************************
  Minimal TLA+ model for spec 045 § WR-018 (proxy stack forwarding).

  Aim
  ---
  WR-018 bundles four independent claims into a single Markdown
  paragraph. The point of translating it to TLA+ is not to check the
  claims (they are individually obvious) but to *force them apart* —
  each independent claim must become a separately named invariant.
  If a reader of the Markdown can hold all four at once and spot every
  inconsistency, the spec is fine as-is; if not, the number of
  invariants here is evidence that the spec item is N items pretending
  to be one.

  The four claims extracted from WR-018
  -------------------------------------
  (I1) Return-type widening: every proxy layer's write returns a
       WriteResult record, not None.
  (I2) Unchanged forwarding: the WriteResult the caller sees equals the
       WriteResult the backend produced, field-by-field — the union of
       "no substitute", "no mutate", "no synthesise".
  (I3) Cache invalidation: successful write on p removes p from the
       cache layer's tracked set.
  (I4) Event emission: each successful write produces exactly one event
       at the observe layer, carrying the forwarded WriteResult.

  Spec § WR-018 also asserts head() forwarding; head is not modelled
  here because it has its own module (WriteHeadRoundTrip). Keeping the
  modules disjoint is itself the discipline the PoC is evaluating.
***************************************************************************)

EXTENDS Naturals, Sequences, FiniteSets, TLC

CONSTANTS Paths, DataSizes, MaxClock

BASIC == "basic"

VARIABLES
    fs,              \* backend ground truth: Path -> [size, modified]
    backend_wr,      \* Path -> WriteResult produced by the backend
    cache_wr,        \* Path -> WriteResult observed at the cache layer's boundary
    observe_wr,      \* Path -> WriteResult observed at the top (observe layer)
    cache_paths,     \* SUBSET Paths — paths currently tracked by the cache layer
    events,          \* Seq — events appended by the observe layer
    write_count,     \* Nat — total successful writes (for I4's per-write cardinality)
    clock

vars == <<fs, backend_wr, cache_wr, observe_wr,
          cache_paths, events, write_count, clock>>

MkWR(p, sz, ts) ==
    [path |-> p, size |-> sz, last_modified |-> ts, source |-> BASIC]

WrittenPaths == DOMAIN backend_wr

WriteResultShape == {"path", "size", "last_modified", "source"}

TypeOK ==
    /\ DOMAIN fs \subseteq Paths
    /\ WrittenPaths \subseteq Paths
    /\ DOMAIN cache_wr = WrittenPaths
    /\ DOMAIN observe_wr = WrittenPaths
    /\ cache_paths \subseteq Paths
    /\ write_count \in Nat
    /\ clock \in Nat

Init ==
    /\ fs = [p \in {} |-> 0]
    /\ backend_wr = [p \in {} |-> 0]
    /\ cache_wr = [p \in {} |-> 0]
    /\ observe_wr = [p \in {} |-> 0]
    /\ cache_paths \in SUBSET Paths    \* cache may hold pre-existing entries
    /\ events = <<>>
    /\ write_count = 0
    /\ clock = 0

\* Write(p, sz): one atomic stack-wide transition.
\*   - Backend computes wr_b, cache forwards it as wr_c, observe forwards as wr_o.
\*   - Cache layer invalidates its entry for p.
\*   - Observe layer appends an event carrying wr_o.
Write(p, sz) ==
    /\ p \in Paths
    /\ sz \in DataSizes
    /\ clock' = clock + 1
    /\ LET wr_b == MkWR(p, sz, clock')
           wr_c == wr_b           \* cache layer forwards (I2)
           wr_o == wr_c           \* observe layer forwards (I2)
           new_fs_dom == DOMAIN fs \cup {p}
           new_wr_dom == WrittenPaths \cup {p}
       IN
          /\ fs' = [q \in new_fs_dom |->
                      IF q = p THEN [size |-> sz, modified |-> clock']
                               ELSE fs[q]]
          /\ backend_wr' = [q \in new_wr_dom |->
                              IF q = p THEN wr_b ELSE backend_wr[q]]
          /\ cache_wr' = [q \in new_wr_dom |->
                            IF q = p THEN wr_c ELSE cache_wr[q]]
          /\ observe_wr' = [q \in new_wr_dom |->
                              IF q = p THEN wr_o ELSE observe_wr[q]]
          /\ cache_paths' = cache_paths \ {p}                \* I3
          /\ events' = Append(events, [path |-> p, write_result |-> wr_o])
          /\ write_count' = write_count + 1

Next == \E p \in Paths, sz \in DataSizes: Write(p, sz)

Spec == Init /\ [][Next]_vars

\* ==========================================================================
\* The four WR-018 claims, as independent invariants.
\* ==========================================================================

\* (I1) Return-type widening. Every layer's write returned a WriteResult
\*      record with the expected shape — not None.
ReturnTypeIsWriteResult ==
    \A p \in WrittenPaths:
        /\ DOMAIN backend_wr[p] = WriteResultShape
        /\ DOMAIN cache_wr[p]   = WriteResultShape
        /\ DOMAIN observe_wr[p] = WriteResultShape

\* (I2) Unchanged forwarding. Top-level result equals bottom-level, field
\*      by field. This single equality subsumes "no substitute",
\*      "no mutate", and "no synthesise" — the Markdown's triple phrasing
\*      is one claim, not three.
ProxyForwardUnchanged ==
    \A p \in WrittenPaths:
        /\ observe_wr[p] = cache_wr[p]
        /\ cache_wr[p]   = backend_wr[p]

\* (I3) Cache invalidation. Successful write removes p from cache tracking.
\*      Note: this holds for every written path regardless of whether the
\*      cache contained it beforehand — invalidation is unconditional.
CacheInvalidated ==
    \A p \in WrittenPaths: p \notin cache_paths

\* (I4) Event emission. Exactly one event per successful write; every event
\*      carries the forwarded WriteResult; event path is a written path.
EventPerWrite ==
    /\ Len(events) = write_count
    /\ \A i \in 1..Len(events):
           LET e == events[i] IN
           /\ e.path \in WrittenPaths
           /\ DOMAIN e.write_result = WriteResultShape
           /\ e.write_result.path = e.path

StateConstraint == clock <= MaxClock
=============================================================================
