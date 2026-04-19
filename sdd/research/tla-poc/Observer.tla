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

    (I1)  EventPerCompletedOp            - landed
    (I2)  RoutingByOpClass               - landed
    (I3a) ClassHookOutcomeIndependent    - this commit
    (I3b) ErrorHookFiresOnErrorOnly      - this commit
    (I4)  ErrorAlwaysReraise             - follow-up
    (I5)  AfterHookExceptionIsolated     - follow-up

  The decomposition note's I3 bundles two independently-falsifiable
  claims (outcome-independence for the per-op hook; on_error fires iff
  error). Per the authoring rules those are separate invariants here.
  The note will be reconciled once all invariants have landed.

  Each subsequent invariant is added as its own commit, expanding the
  state (adding variables / actions) only as the new invariant requires.
***************************************************************************)

EXTENDS Naturals, Sequences, FiniteSets, TLC

CONSTANTS
    Ops,             \* set of operation names
    HookClasses,     \* set of per-op hook classes (OBS-003a: read/write/...)
    ClassOf,         \* [Ops -> HookClasses] — OBS-003a mapping
    Outcomes,        \* {"success", "error"}
    MaxCalls

VARIABLES
    inner_calls,     \* Nat - how many times the inner method was invoked
    any_events,      \* Seq - events dispatched to the on_any hook
    class_events,    \* [HookClasses -> Seq] - events per per-op hook bucket
    error_events     \* Seq - events dispatched to the on_error hook

vars == <<inner_calls, any_events, class_events, error_events>>

\* Shape of an observer event. "outcome" lands in I3 so that the
\* per-op and error hooks can be reasoned about independently.
EventShape == {"op", "outcome"}

TypeOK ==
    /\ inner_calls \in Nat
    /\ \A i \in 1..Len(any_events):
           /\ DOMAIN any_events[i] = EventShape
           /\ any_events[i].op \in Ops
           /\ any_events[i].outcome \in Outcomes
    /\ DOMAIN class_events = HookClasses
    /\ \A c \in HookClasses:
           \A i \in 1..Len(class_events[c]):
               /\ DOMAIN class_events[c][i] = EventShape
               /\ class_events[c][i].op \in Ops
               /\ class_events[c][i].outcome \in Outcomes
    /\ \A i \in 1..Len(error_events):
           /\ DOMAIN error_events[i] = EventShape
           /\ error_events[i].op \in Ops
           /\ error_events[i].outcome \in Outcomes

Init ==
    /\ inner_calls = 0
    /\ any_events = <<>>
    /\ class_events = [c \in HookClasses |-> <<>>]
    /\ error_events = <<>>

\* Call(op, outcome): one store operation completes. The inner method
\* runs, on_any fires, the matching on_<op> fires (regardless of
\* outcome — OBS-003 step 6/7, clarified in this PR), and on_error
\* fires iff outcome = "error".
Call(op, outcome) ==
    /\ op \in Ops
    /\ outcome \in Outcomes
    /\ LET evt == [op |-> op, outcome |-> outcome] IN
       /\ inner_calls' = inner_calls + 1
       /\ any_events' = Append(any_events, evt)
       /\ class_events' =
              [class_events EXCEPT
                  ![ClassOf[op]] = Append(class_events[ClassOf[op]], evt)]
       /\ error_events' =
              IF outcome = "error"
              THEN Append(error_events, evt)
              ELSE error_events

Next == \E op \in Ops, outcome \in Outcomes: Call(op, outcome)

Spec == Init /\ [][Next]_vars

\* ==========================================================================
\* Invariants
\* ==========================================================================

\* (I1) EventPerCompletedOp — exactly one on_any event per inner call.
\* Break-and-catch:
\*   - any_events' = any_events (skip append) -> violated.
\*   - any_events' = Append(Append(any_events, e), e) (double-fire) -> violated.
EventPerCompletedOp == Len(any_events) = inner_calls

\* (I2) RoutingByOpClass — every event in a per-op hook bucket has an op
\* whose OBS-003a class equals that bucket.
\* Break-and-catch:
\*   - Append to a non-matching class -> violated.
RoutingByOpClass ==
    \A c \in HookClasses:
        \A i \in 1..Len(class_events[c]):
            ClassOf[class_events[c][i].op] = c

\* (I3a) ClassHookOutcomeIndependent — the per-op hook fires for every
\* call whose op is in that class, irrespective of outcome. Derived
\* from any_events so no separate per-call history is needed.
\* Break-and-catch:
\*   - Skip class_events append on error -> violated.
ClassCallCount(c) ==
    Cardinality({i \in 1..Len(any_events) : ClassOf[any_events[i].op] = c})

ClassHookOutcomeIndependent ==
    \A c \in HookClasses: Len(class_events[c]) = ClassCallCount(c)

\* (I3b) ErrorHookFiresOnErrorOnly — on_error fires for every error
\* call and only for error calls.
\* Break-and-catch:
\*   - Append to error_events on success -> violated (content).
\*   - Skip append on error -> violated (count).
ErrorCallCount ==
    Cardinality({i \in 1..Len(any_events) : any_events[i].outcome = "error"})

ErrorHookFiresOnErrorOnly ==
    /\ Len(error_events) = ErrorCallCount
    /\ \A i \in 1..Len(error_events): error_events[i].outcome = "error"

StateConstraint == inner_calls <= MaxCalls
=============================================================================
