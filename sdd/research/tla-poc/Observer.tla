--------------------------- MODULE Observer ---------------------------
(***************************************************************************
  TLA+ model of the ObservedStore dispatch contract (spec 019 § OBS-003,
  OBS-003a, OBS-009).

  Aim
  ---
  OBS-003 bundles several independently-falsifiable claims behind a
  9-step override recipe plus three postconditions. The point of this
  module is the same as WR018ProxyForwarding: *force the bundled claims
  apart*. Each independent claim becomes a separately named invariant,
  and a one-line mutation of the model must trigger exactly that
  invariant and no others. If rows collapse, the claims were not
  actually orthogonal.

  Invariants (derived in
  sdd/research/research-id-147-obs003-decomposition.md):

    (I1) EventPerCompletedOp        - landed
    (I2) RoutingByOpClass           - this commit
    (I3) HookOutcomeContract        - follow-up
    (I4) ErrorAlwaysReraise         - follow-up
    (I5) AfterHookExceptionIsolated - follow-up

  Each subsequent invariant is added as its own commit, expanding the
  state (adding variables / actions) only as the new invariant requires.
  State stays minimal: no premature modelling of op classes, outcomes,
  or hook exceptions until the invariant that needs them lands.
***************************************************************************)

EXTENDS Naturals, Sequences, FiniteSets, TLC

CONSTANTS
    Ops,             \* set of operation names
    HookClasses,     \* set of per-op hook classes (OBS-003a: read/write/...)
    ClassOf,         \* [Ops -> HookClasses] — OBS-003a mapping
    MaxCalls

VARIABLES
    inner_calls,     \* Nat - how many times the inner method was invoked
    any_events,      \* Seq - events dispatched to the on_any hook
    class_events     \* [HookClasses -> Seq] - events per per-op hook bucket

vars == <<inner_calls, any_events, class_events>>

\* Shape of an on_any event. Minimal for I1 - only the operation name
\* matters. I3 will add an outcome field.
EventShape == {"op"}

TypeOK ==
    /\ inner_calls \in Nat
    /\ \A i \in 1..Len(any_events):
           /\ DOMAIN any_events[i] = EventShape
           /\ any_events[i].op \in Ops
    /\ DOMAIN class_events = HookClasses
    /\ \A c \in HookClasses:
           \A i \in 1..Len(class_events[c]):
               /\ DOMAIN class_events[c][i] = EventShape
               /\ class_events[c][i].op \in Ops

Init ==
    /\ inner_calls = 0
    /\ any_events = <<>>
    /\ class_events = [c \in HookClasses |-> <<>>]

\* Call(op): one store operation completes through the ObservedStore
\* proxy. The inner method runs (inner_calls bumps by 1), on_any fires
\* once, and the matching on_<op> hook fires once (appended to the
\* ClassOf[op] bucket). Outcome is not modelled yet because I1/I2 are
\* outcome-independent (OBS-003 step 6/7 fire regardless of outcome).
Call(op) ==
    /\ op \in Ops
    /\ inner_calls' = inner_calls + 1
    /\ any_events' = Append(any_events, [op |-> op])
    /\ class_events' =
           [class_events EXCEPT
               ![ClassOf[op]] = Append(class_events[ClassOf[op]], [op |-> op])]

Next == \E op \in Ops: Call(op)

Spec == Init /\ [][Next]_vars

\* ==========================================================================
\* Invariants
\* ==========================================================================

\* (I1) EventPerCompletedOp — exactly one on_any event per inner call.
\* Break-and-catch:
\*   - any_events' = any_events (skip append) -> violated.
\*   - any_events' = Append(Append(any_events, e), e) (double-fire) -> violated.
\*   - inner_calls' = inner_calls (skip bump) -> violated.
EventPerCompletedOp == Len(any_events) = inner_calls

\* (I2) RoutingByOpClass — every event in a per-op hook bucket has an op
\* whose OBS-003a class equals that bucket. Catches a proxy that routes
\* an operation to the wrong hook (e.g. read → on_write). Does not
\* check count; a separate count invariant could be added if
\* break-and-catch reveals a gap (see decomposition note § 8).
\* Break-and-catch:
\*   - Append to ClassOf[op] neighbour instead of ClassOf[op] -> violated.
RoutingByOpClass ==
    \A c \in HookClasses:
        \A i \in 1..Len(class_events[c]):
            ClassOf[class_events[c][i].op] = c

StateConstraint == inner_calls <= MaxCalls
=============================================================================
