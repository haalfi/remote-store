// ResourceSafety.dfy: Formal model of resource lifecycle safety.
//
// Covers two BK-140 gaps:
//   Gap 6  SIO-001   Acquire-then-wrap: no handle leaked on wrapper failure
//   Gap 5  BE-018    Move atomicity: intermediate-state model
//
// Best-practice notes:
// - Assert breadcrumbs inside loops guide the solver per-iteration.
// - Each predicate and lemma is self-contained (no implicit state).
// - Safe/Unsafe pairs make the bug pattern verifiably distinct.

// ---------------------------------------------------------------------------
// §1  Handle lifecycle model  (Gap 6 / SIO-001)
// ---------------------------------------------------------------------------

datatype HandleState =
  | Open       // handle acquired, not yet wrapped or closed
  | Wrapped    // handle is inside a wrapper (wrapper owns it)
  | Closed     // handle has been explicitly closed

datatype Resource = Resource(id: nat, state: HandleState)

datatype WrapPipeline = WrapPipeline(
  layers: seq<Resource>,
  failed_at: int             // -1 = all succeeded; >= 0 = failure index
)

// ---------------------------------------------------------------------------
// §1.1  Safety predicates
// ---------------------------------------------------------------------------

// No handle is in the Open state (no leaks).
predicate AllHandlesAccountedFor(pipeline: WrapPipeline)
{
  forall i | 0 <= i < |pipeline.layers| ::
    pipeline.layers[i].state != Open
}

// The safe-wrap protocol's structural invariant.
predicate SafeWrapInvariant(pipeline: WrapPipeline)
{
  if pipeline.failed_at == -1 then
    // Success: every layer is Wrapped.
    forall i | 0 <= i < |pipeline.layers| ::
      pipeline.layers[i].state == Wrapped
  else
    // Failure: the layers sequence is TRUNCATED to only the handles
    // that were actually acquired before the failure.  Handles beyond
    // the failure point were never created and are absent from the
    // sequence: the invariant says nothing about them because they
    // don't exist.  All layers present are Closed (cleaned up).
    0 <= pipeline.failed_at <= |pipeline.layers| &&
    (forall i | 0 <= i < pipeline.failed_at ::
      pipeline.layers[i].state == Closed) &&
    pipeline.failed_at == |pipeline.layers|
}

// ---------------------------------------------------------------------------
// §1.2  Core theorem: SafeWrapInvariant implies no leaks
// ---------------------------------------------------------------------------

lemma SafeWrapImpliesNoLeaks(pipeline: WrapPipeline)
  requires SafeWrapInvariant(pipeline)
  ensures AllHandlesAccountedFor(pipeline)
{
  if pipeline.failed_at == -1 {
    // Success case: all Wrapped.
    assert forall i | 0 <= i < |pipeline.layers| ::
      pipeline.layers[i].state == Wrapped;
    // Wrapped != Open, so no leaks.
    forall i | 0 <= i < |pipeline.layers|
      ensures pipeline.layers[i].state != Open
    {
      assert pipeline.layers[i].state == Wrapped;
    }
  } else {
    // Failure case: all existing layers are Closed.
    assert pipeline.failed_at == |pipeline.layers|;
    forall i | 0 <= i < |pipeline.layers|
      ensures pipeline.layers[i].state != Open
    {
      assert i < pipeline.failed_at;
      assert pipeline.layers[i].state == Closed;
    }
  }
}

// ---------------------------------------------------------------------------
// §1.3  Safe wrapping: models _safe_wrap() from _stream.py
// ---------------------------------------------------------------------------

// Models _safe_wrap(raw, *wrappers) from _stream.py.
// Success path: wrapperCount + 1 layers (raw + all N wrappers), all Wrapped.
// Failure path: failAt + 1 layers (raw + layers created before failure), all Closed.
// Handles never acquired (beyond the failure point) are absent from the sequence.
method SafeWrap(rawId: nat, wrapperCount: nat, failAt: int)
  returns (pipeline: WrapPipeline)
  requires failAt >= -1
  requires failAt == -1 || failAt < wrapperCount as int
  ensures SafeWrapInvariant(pipeline)
  ensures AllHandlesAccountedFor(pipeline)
{
  if failAt == -1 {
    // All wrappers succeed: build a fully Wrapped pipeline.
    var layers: seq<Resource> := [];
    var i := 0;
    while i <= wrapperCount
      invariant 0 <= i <= wrapperCount + 1
      invariant |layers| == i
      invariant forall j | 0 <= j < i :: layers[j].state == Wrapped
      invariant forall j | 0 <= j < i :: layers[j].id == rawId + j
    {
      layers := layers + [Resource(rawId + i, Wrapped)];
      // Breadcrumb: newly added element is Wrapped.
      assert layers[i].state == Wrapped;
      i := i + 1;
    }
    pipeline := WrapPipeline(layers, -1);
    // Verify invariant before calling lemma.
    assert forall j | 0 <= j < |pipeline.layers| ::
      pipeline.layers[j].state == Wrapped;
    assert SafeWrapInvariant(pipeline);
  } else {
    // Wrapper at index `failAt` raises.
    // Layers 0..failAt were acquired then closed during cleanup.
    var layers: seq<Resource> := [];
    var i := 0;
    while i <= failAt
      invariant 0 <= i <= failAt + 1
      invariant |layers| == i
      invariant forall j | 0 <= j < i :: layers[j].state == Closed
      invariant forall j | 0 <= j < i :: layers[j].id == rawId + j
    {
      layers := layers + [Resource(rawId + i, Closed)];
      // Breadcrumb: newly added element is Closed.
      assert layers[i].state == Closed;
      i := i + 1;
    }
    pipeline := WrapPipeline(layers, failAt + 1);
    // Verify: failed_at == |layers| and all Closed.
    assert pipeline.failed_at == |pipeline.layers|;
    assert forall j | 0 <= j < pipeline.failed_at ::
      pipeline.layers[j].state == Closed;
    assert SafeWrapInvariant(pipeline);
  }
  SafeWrapImpliesNoLeaks(pipeline);
}

// ---------------------------------------------------------------------------
// §1.4  Unsafe wrapping: demonstrates the leak (pre-fix pattern)
// ---------------------------------------------------------------------------

method UnsafeWrap(rawId: nat, wrapperCount: nat, failAt: nat)
  returns (pipeline: WrapPipeline)
  requires failAt < wrapperCount
  ensures !AllHandlesAccountedFor(pipeline)  // LEAK proven!
{
  // Raw handle acquired but never closed on failure path.
  var layers: seq<Resource> := [Resource(rawId, Open)];
  assert layers[0].state == Open;  // This is the leak.

  var i: nat := 1;
  while i <= failAt
    invariant 1 <= i <= failAt + 1
    invariant |layers| == i
    invariant layers[0].state == Open  // Leak persists through loop.
    invariant forall j | 1 <= j < i :: layers[j].state == Wrapped
  {
    layers := layers + [Resource(rawId + i, Wrapped)];
    // Breadcrumb: layer 0 is still Open (leaked).
    assert layers[0].state == Open;
    i := i + 1;
  }
  pipeline := WrapPipeline(layers, failAt as int + 1);

  // Prove the leak: layers[0] is Open.
  assert pipeline.layers[0].state == Open;
  assert 0 < |pipeline.layers|;
  // Therefore AllHandlesAccountedFor is false.
}

// ---------------------------------------------------------------------------
// §2  Move atomicity model  (Gap 5 / BE-018)
// ---------------------------------------------------------------------------

datatype MovePhase =
  | Initial
  | CopyDone      // src AND dst both exist (non-atomic intermediate)
  | DeleteDone    // src gone, dst exists (correct final state)
  | Failed(phase: string, reason: string)

// ---------------------------------------------------------------------------
// §2.1  Atomic move: single transition, no intermediate state
// ---------------------------------------------------------------------------

method AtomicMove(srcExists: bool, dstExists: bool, overwrite: bool)
  returns (phase: MovePhase)
  ensures srcExists && (!dstExists || overwrite) ==> phase == DeleteDone
  ensures !srcExists ==> phase.Failed?
  ensures srcExists && dstExists && !overwrite ==> phase.Failed?
{
  if !srcExists {
    phase := Failed("initial", "source not found");
    assert phase.Failed?;
  } else if dstExists && !overwrite {
    phase := Failed("initial", "destination exists");
    assert phase.Failed?;
  } else {
    phase := DeleteDone;
    assert phase == DeleteDone;
  }
}

// ---------------------------------------------------------------------------
// §2.2  Non-atomic move: copy then delete
// ---------------------------------------------------------------------------

method CopyDeleteMove(srcExists: bool, dstExists: bool, overwrite: bool,
                       deleteFails: bool)
  returns (phase: MovePhase)
  ensures srcExists && (!dstExists || overwrite) && !deleteFails
    ==> phase == DeleteDone
  ensures srcExists && (!dstExists || overwrite) && deleteFails
    ==> phase == CopyDone
  ensures !srcExists ==> phase.Failed?
  ensures srcExists && dstExists && !overwrite ==> phase.Failed?
{
  if !srcExists {
    phase := Failed("initial", "source not found");
    assert phase.Failed?;
    return;
  }
  if dstExists && !overwrite {
    phase := Failed("initial", "destination exists");
    assert phase.Failed?;
    return;
  }

  // Phase 1: copy succeeds.
  phase := CopyDone;
  assert phase == CopyDone;

  if deleteFails {
    // Phase 2 failed: both src and dst exist.
    // Backend MUST report this as an error.
    assert phase == CopyDone;
    return;
  }

  // Phase 2: delete succeeds.
  phase := DeleteDone;
  assert phase == DeleteDone;
}

// CopyDone is observably different from DeleteDone.
// A backend that returns success in CopyDone state is lying.
lemma CopyDoneIsNotSuccess(phase: MovePhase)
  requires phase == CopyDone
  ensures phase != DeleteDone
  ensures !phase.Failed?
{
  assert phase.CopyDone?;
  // CopyDone? is not DeleteDone? is not Failed?: disjoint constructors.
}

// Both move strategies agree on the happy path.
lemma MoveFinalStateEquivalence(
  atomicPhase: MovePhase, copyDeletePhase: MovePhase
)
  requires atomicPhase == DeleteDone
  requires copyDeletePhase == DeleteDone
  ensures atomicPhase == copyDeletePhase
{
  // Trivially equal: same constructor, same value.
}

// ---------------------------------------------------------------------------
// §3  Connection lifecycle  (BUG-144 pattern)
// ---------------------------------------------------------------------------

datatype ConnectionState =
  | Created
  | Connected
  | Abandoned   // leaked (bug)
  | Released    // properly closed

method SafeConnect(connectSucceeds: bool)
  returns (state: ConnectionState)
  ensures connectSucceeds ==> state == Connected
  ensures !connectSucceeds ==> state == Released
{
  state := Created;
  assert state == Created;

  if connectSucceeds {
    state := Connected;
    assert state == Connected;
  } else {
    // Connection failed: close the client.
    state := Released;
    assert state == Released;
  }
}

method UnsafeConnect(connectSucceeds: bool)
  returns (state: ConnectionState)
  ensures connectSucceeds ==> state == Connected
  ensures !connectSucceeds ==> state == Abandoned
{
  state := Created;

  if connectSucceeds {
    state := Connected;
  } else {
    // Bug: forgot to close.
    state := Abandoned;
    assert state == Abandoned;  // This is the leak.
  }
}

// Safe connect never abandons.
lemma SafeConnectNeverLeaks(succeeded: bool, state: ConnectionState)
  requires (succeeded ==> state == Connected) &&
           (!succeeded ==> state == Released)
  ensures state != Abandoned
{
  if succeeded {
    assert state == Connected;
  } else {
    assert state == Released;
  }
}

// ---------------------------------------------------------------------------
// §4  PBT cross-reference
// ---------------------------------------------------------------------------
//
// | Dafny method/lemma          | Hypothesis property                 | What it checks               |
// |-----------------------------|-------------------------------------|------------------------------|
// | SafeWrap + SafeWrapInvariant| test_safe_wrap_no_leak              | _safe_wrap never leaks       |
// | UnsafeWrap                  | test_unsafe_wrap_leaks              | pre-fix pattern leaks        |
// | SafeConnect                 | test_sftp_connect_cleanup           | SFTP client closed on failure|
// | CopyDeleteMove              | test_move_copy_delete_partial       | partial move raises error    |
//
// Dafny proves these structurally for all inputs.
// Hypothesis tests the Python implementation with randomised scenarios.
