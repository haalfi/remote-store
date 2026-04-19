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

    (I1) EventPerCompletedOp        - this commit
    (I2) RoutingByOpClass           - follow-up
    (I3) HookOutcomeContract        - follow-up
    (I4) ErrorAlwaysReraise         - follow-up
    (I5) AfterHookExceptionIsolated - follow-up

  Each subsequent invariant is added as its own commit, expanding the
  state (adding variables / actions) only as the new invariant requires.
  State stays minimal: no premature modelling of op classes, outcomes,
  or hook exceptions until the invariant that needs them lands.
***************************************************************************)

EXTENDS Naturals, Sequences, FiniteSets, TLC

CONSTANTS Ops, MaxCalls

VARIABLES
    inner_calls,   \* Nat     - how many times the inner method was invoked
    any_events     \* Seq     - events dispatched to the on_any hook

vars == <<inner_calls, any_events>>

\* Shape of an on_any event. Deliberately minimal for I1 - only the
\* operation name matters. I2 will add an op-class field; I3 will add
\* an outcome field; etc.
EventShape == {"op"}

TypeOK ==
    /\ inner_calls \in Nat
    /\ \A i \in 1..Len(any_events):
           /\ DOMAIN any_events[i] = EventShape
           /\ any_events[i].op \in Ops

Init ==
    /\ inner_calls = 0
    /\ any_events = <<>>

\* Call(op): one store operation completes through the ObservedStore
\* proxy. The inner method runs (inner_calls bumps by 1) and on_any
\* fires exactly once, appending an event for this operation. Outcome
\* (success vs. error) is not modelled yet because I1 is
\* outcome-independent (OBS-003 step 7 fires regardless of outcome, per
\* the step 6/7 clarification).
Call(op) ==
    /\ op \in Ops
    /\ inner_calls' = inner_calls + 1
    /\ any_events' = Append(any_events, [op |-> op])

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

StateConstraint == inner_calls <= MaxCalls
=============================================================================
