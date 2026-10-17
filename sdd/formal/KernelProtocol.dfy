// KernelProtocol.dfy. The interaction protocol on the kernel  (BE-033, BK-449).
//
// The parties' states as spec 003 BE-033 tables them, for the session-less
// kernel classes (`DriverBackend`, `AsyncDriverBackend`); the `Session` row is
// fixed at RFC-0017 D3 step 2 and is not modelled. `ResourceSafety.dfy` §1 and
// §3 model the classes before the kernel. This file stands alone: nothing
// includes it, so it adds nothing to the Dafny oracle's compiled module.
// Hypothesis twin: `tests/_kernel/test_protocol_stateful.py`.
//
// A call is reduced to what decides the protocol: whether it is `close`, and
// for a live call the exit it takes. A `LiveCall` is a call the closed guard
// covers, a live operation past its capability gates or `unwrap`; the
// addressing members are never refused and are not modelled. `KernelExit` maps
// every exit the kernel observes onto the resources' states after its cleanup,
// and the lemmas are BE-033's invariants:
//   I1  TerminalCloseAbsorbs:   after a terminal close every LiveCall is
//                               Unavailable and the state stays Closed;
//   I2  CloseIsForwardedAndIdempotent: close twice is close once in state, and
//                               the driver sees every call;
//   I3  CleanupOnEveryExit:     no handle open, no stream open unless its
//                               failure condemned the connection, no caller
//                               iterator with `aclose` suspended, on every exit.

datatype ClosePosture = Reusable | Terminal
datatype KernelBackendState = BOpen | BClosed
datatype KernelCall = CloseCall | LiveCall
datatype KernelAnswer = Done | Unavailable

// Backend: (posture, state, driver close count). The closed guard refuses a
// live call only under a terminal posture (BE-020); close always reaches the
// driver.
datatype KernelBackend = KernelBackend(posture: ClosePosture, state: KernelBackendState, driverCloses: nat)

function KernelStep(b: KernelBackend, c: KernelCall): (KernelBackend, KernelAnswer)
{
  match c
  case CloseCall => (b.(state := BClosed, driverCloses := b.driverCloses + 1), Done)
  case LiveCall =>
    if b.state == BClosed && b.posture == Terminal then (b, Unavailable) else (b, Done)
}

function KernelRun(b: KernelBackend, calls: seq<KernelCall>): KernelBackend
  decreases |calls|
{
  if |calls| == 0 then b else KernelRun(KernelStep(b, calls[0]).0, calls[1..])
}

function KernelCloseCount(calls: seq<KernelCall>): nat
  decreases |calls|
{
  if |calls| == 0 then 0 else (if calls[0] == CloseCall then 1 else 0) + KernelCloseCount(calls[1..])
}

// I1: Closed under a terminal posture is absorbing, and every live call in it
// answers Unavailable.
lemma TerminalCloseAbsorbs(b: KernelBackend, calls: seq<KernelCall>)
  requires b.posture == Terminal && b.state == BClosed
  ensures KernelRun(b, calls).state == BClosed
  ensures KernelRun(b, calls).posture == Terminal
  ensures forall i | 0 <= i < |calls| && calls[i] == LiveCall ::
            KernelStep(KernelRun(b, calls[..i]), LiveCall).1 == Unavailable
  decreases |calls|
  // @spec BE-033
{
  if |calls| > 0 {
    var next := KernelStep(b, calls[0]).0;
    assert next.state == BClosed && next.posture == Terminal;
    TerminalCloseAbsorbs(next, calls[1..]);
    forall i | 0 <= i < |calls| && calls[i] == LiveCall
      ensures KernelStep(KernelRun(b, calls[..i]), LiveCall).1 == Unavailable
    {
      if i == 0 {
        assert calls[..0] == [];
      } else {
        assert calls[..i][1..] == calls[1..][..i-1];
        assert calls[1..][i-1] == calls[i];
      }
    }
  }
}

// A reusable backend is never refused: close leaves it usable (BE-020).
lemma ReusableNeverRefuses(b: KernelBackend)
  requires b.posture == Reusable
  ensures KernelStep(b, LiveCall).1 == Done
  // @spec BE-033
{
}

// I2: close ∘ close = close in the kernel's state, and the kernel forwards
// every close, so idempotence is the driver's duty, not a short-circuit.
lemma CloseIsForwardedAndIdempotent(b: KernelBackend, calls: seq<KernelCall>)
  ensures KernelStep(KernelStep(b, CloseCall).0, CloseCall).0.state == KernelStep(b, CloseCall).0.state
  ensures KernelRun(b, calls).driverCloses == b.driverCloses + KernelCloseCount(calls)
  decreases |calls|
  // @spec BE-033
{
  if |calls| > 0 {
    CloseIsForwardedAndIdempotent(KernelStep(b, calls[0]).0, calls[1..]);
  }
}

// The exits the kernel observes on a live call. `dead` is the driver's
// connection_dead verdict on the failure; a cancel is a BaseException, so it
// takes the failure exit without a verdict.
datatype KernelExitPath = Success | GateRefused | Faulted(dead: bool) | Cancelled

datatype KernelStreamState = SOpen | SClosed | SReleased   // SReleased: condemned, let go unclosed (SIO-010)
datatype WriteHandleState = HNone | HOpen | HCommitted | HAborted
datatype CallerIterState = IUnstarted | ISuspended | IExhausted | IClosed

datatype KernelResources = KernelResources(stream: KernelStreamState, handle: WriteHandleState, iter: CallerIterState)

// Each party's state after the kernel's cleanup, for each exit. The abort's
// own failure is logged, not modelled: the handle leaves HOpen either way, and
// the write's error is the one raised. `closable` is whether the caller's
// iterator has `aclose`: one without it is left where the kernel stopped. The
// kernel takes the iterator with its first chunk, so a failure before that
// leaves it IUnstarted, the caller's to retry with.
method KernelExit(exit: KernelExitPath, before: KernelResources, closable: bool) returns (after: KernelResources)
  requires before.stream in {SOpen, SClosed}
  requires exit == GateRefused ==> before.handle == HNone && before.iter == IUnstarted
  ensures before.stream == SOpen ==>
            after.stream == (if exit == Faulted(true) then SReleased else SClosed)
  ensures before.stream == SClosed ==> after.stream == SClosed
  ensures after.handle != HOpen
  ensures exit != Success && before.handle == HOpen ==> after.handle == HAborted
  ensures exit == GateRefused ==> after.iter == IUnstarted   // the caller's still
  ensures exit == Success ==> after.iter == IExhausted
  ensures exit != Success && before.iter == IUnstarted ==> after.iter == IUnstarted
  ensures exit !in {Success, GateRefused} && closable && before.iter != IUnstarted ==>
            after.iter in {IExhausted, IClosed}
  ensures exit !in {Success, GateRefused} && !closable ==> after.iter == before.iter
  // @spec BE-033
{
  var stream := before.stream;
  if stream == SOpen {
    stream := if exit == Faulted(true) then SReleased else SClosed;
  }
  var handle := before.handle;
  if handle == HOpen {
    handle := if exit == Success then HCommitted else HAborted;
  }
  var iter := before.iter;
  if exit == Success {
    iter := IExhausted;   // a write that succeeded took every chunk
  } else if exit != GateRefused && closable && iter == ISuspended {
    iter := IClosed;
  }
  after := KernelResources(stream, handle, iter);
}

// I3: no exit leaves a resource the kernel opened or took open, except a stream
// whose failure condemned the connection, released without a second wait, and
// a caller iterator without `aclose`, which stays the caller's to finish.
predicate KernelClean(r: KernelResources, closable: bool)
{
  r.stream != SOpen && r.handle != HOpen && (closable ==> r.iter != ISuspended)
}

method CleanupOnEveryExit(exit: KernelExitPath, before: KernelResources, closable: bool)
  returns (after: KernelResources)
  requires before.stream in {SOpen, SClosed}
  requires exit == GateRefused ==> before.handle == HNone && before.iter == IUnstarted
  ensures KernelClean(after, closable)
  // @spec BE-033
{
  after := KernelExit(exit, before, closable);
}
