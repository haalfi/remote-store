--------------------------- MODULE Observer ---------------------------
(***************************************************************************
  TLA+ model of the ObservedStore dispatch contract — OBS-003 step 6/7
  (every completed op fires on_any + matching on_<op> regardless of
  outcome) and OBS-003a (per-op hook class routing) from spec 019.

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

    (I1)  EventPerCompletedOp
    (I2)  RoutingByOpClass
    (I3a) ClassHookOutcomeIndependent
    (I3b) ErrorHookFiresOnErrorOnly
    (I4)  ErrorAlwaysReraise
    (I5)  AfterHookExceptionIsolated

  I3 is split into I3a/I3b because the note's original I3 bundled two
  independently-falsifiable claims (per-op-hook outcome independence
  and error-hook fires iff error). I4 and I5 are the error-path and
  success-path halves of "hooks never change what the caller sees",
  kept apart so a break on one path cannot accidentally satisfy the
  other. Every invariant has a corresponding § 8 break-and-catch row
  in the note.

  Scope caveat (authoring vs checked invariants)
  ----------------------------------------------
  `Call` is a single atomic action that couples every variable by
  construction, so all six invariants hold vacuously on the unmutated
  spec — TLC on `MC3` always passes green. That makes this module an
  *authoring* artefact in the sense of `sdd/formal/README.md` rule 3:
  the `verify-tla` CI job catches future edits to `Call` (or to the
  invariant bodies) that break internal consistency, but it does *not*
  catch regressions in the Python `observe.py` implementation — there
  is no automated link between the two layers.

  In particular, OBS-009's behavioural claims ("fire on_error then
  re-raise", "after-hook exceptions are suppressed, around exceptions
  propagate") are not directly representable in the current action
  shape, because `Call` has no `HookRaise` sub-action that can attempt
  to alter `visible_outcomes`. I4 and I5 verify the structural
  property `visible == inner` on each path; a faithful OBS-009
  behavioural check is deferred as a follow-up once a real regression
  motivates the model extension (ID-150 revisit).
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
    error_events,    \* Seq - events dispatched to the on_error hook
    visible_outcomes \* Seq - outcome observed by the caller (post-proxy)

vars == <<inner_calls, any_events, class_events, error_events, visible_outcomes>>

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
    /\ \A i \in 1..Len(visible_outcomes): visible_outcomes[i] \in Outcomes

Init ==
    /\ inner_calls = 0
    /\ any_events = <<>>
    /\ class_events = [c \in HookClasses |-> <<>>]
    /\ error_events = <<>>
    /\ visible_outcomes = <<>>

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
       /\ visible_outcomes' = Append(visible_outcomes, outcome)

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

\* (I4) ErrorAlwaysReraise — every inner-method error surfaces as an
\* error to the caller. Shadows OBS-009's claim that the original
\* exception always re-raises, but at this model's level of detail.
\* The current Call action has no HookRaise sub-action, so I4 here is
\* a *structural* check on the action body (visible == inner on error
\* paths), not a behavioural check that a raising after-hook is
\* suppressed. The seeded mutation in § 8 exercises the structural
\* property; a faithful OBS-009 behavioural check would require a
\* non-deterministic hook-raise action and is a follow-up if a real
\* regression surfaces (`sdd/formal/README.md` rule 3).
\* Break-and-catch:
\*   - visible_outcomes' appends "success" on the error branch -> violated.
ErrorAlwaysReraise ==
    \A i \in 1..Len(any_events):
        any_events[i].outcome = "error" => visible_outcomes[i] = "error"

\* (I5) AfterHookExceptionIsolated — every inner-method success surfaces
\* as a success to the caller. Success-side mirror of I4 and subject to
\* the same caveat: without a HookRaise sub-action this is a structural
\* check on Call (visible == inner on success paths), not a behavioural
\* proof that a raising after-hook leaves the observable outcome
\* unchanged. The split between I4 and I5 is orthogonal at the level of
\* seeded mutations (error-path and success-path mutations each trigger
\* only their own invariant), not at the level of the underlying
\* physical claims.
\* Break-and-catch:
\*   - visible_outcomes' appends "error" on the success branch -> violated.
AfterHookExceptionIsolated ==
    \A i \in 1..Len(any_events):
        any_events[i].outcome = "success" => visible_outcomes[i] = "success"

StateConstraint == inner_calls <= MaxCalls
=============================================================================
