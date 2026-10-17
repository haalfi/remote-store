import sys
from typing import Callable, Any, TypeVar, NamedTuple
from math import floor
from itertools import count

import module_ as module_
import _dafny as _dafny
import System_ as System_

# Module: KernelProtocol

class default__:
    def  __init__(self):
        pass

    @staticmethod
    def KernelStep(b, c):
        pat_let_tv0_ = b
        source0_ = c
        if True:
            if source0_.is_CloseCall:
                def iife0_(_pat_let0_0):
                    def iife1_(d_0_dt__update__tmp_h0_):
                        def iife2_(_pat_let1_0):
                            def iife3_(d_1_dt__update_hdriverCloses_h0_):
                                def iife4_(_pat_let2_0):
                                    def iife5_(d_2_dt__update_hstate_h0_):
                                        return KernelBackend_KernelBackend((d_0_dt__update__tmp_h0_).posture, d_2_dt__update_hstate_h0_, d_1_dt__update_hdriverCloses_h0_)
                                    return iife5_(_pat_let2_0)
                                return iife4_(KernelBackendState_BClosed())
                            return iife3_(_pat_let1_0)
                        return iife2_(((pat_let_tv0_).driverCloses) + (1))
                    return iife1_(_pat_let0_0)
                return (iife0_(b), KernelAnswer_Done())
        if True:
            if (((b).state) == (KernelBackendState_BClosed())) and (((b).posture) == (ClosePosture_Terminal())):
                return (b, KernelAnswer_Unavailable())
            elif True:
                return (b, KernelAnswer_Done())

    @staticmethod
    def KernelRun(b, calls):
        while True:
            with _dafny.label():
                if (len(calls)) == (0):
                    return b
                elif True:
                    in0_ = (default__.KernelStep(b, (calls)[0]))[0]
                    in1_ = _dafny.SeqWithoutIsStrInference((calls)[1::])
                    b = in0_
                    calls = in1_
                    raise _dafny.TailCall()
                break

    @staticmethod
    def KernelCloseCount(calls):
        d_0___accumulator_ = 0
        while True:
            with _dafny.label():
                if (len(calls)) == (0):
                    return (0) + (d_0___accumulator_)
                elif True:
                    d_0___accumulator_ = (d_0___accumulator_) + ((1 if ((calls)[0]) == (KernelCall_CloseCall()) else 0))
                    in0_ = _dafny.SeqWithoutIsStrInference((calls)[1::])
                    calls = in0_
                    raise _dafny.TailCall()
                break

    @staticmethod
    def AtAnExit(exit, before):
        return (((((before).stream) in (_dafny.Set({KernelStreamState_SOpen(), KernelStreamState_SClosed()}))) and (((before).iter_) != (CallerIterState_IClosed()))) and (not ((exit) == (KernelExitPath_GateRefused())) or (((((before).stream) == (KernelStreamState_SClosed())) and (((before).handle) == (WriteHandleState_HNone()))) and (((before).iter_) == (CallerIterState_IUnstarted()))))) and (not ((exit) == (KernelExitPath_Success())) or (((before).iter_) != (CallerIterState_ISuspended())))

    @staticmethod
    def KernelExit(exit, before, closable):
        after: KernelResources = KernelResources.default()()
        d_0_stream_: KernelStreamState
        d_0_stream_ = (before).stream
        if (d_0_stream_) == (KernelStreamState_SOpen()):
            if (exit) == (KernelExitPath_Faulted(True)):
                d_0_stream_ = KernelStreamState_SReleased()
            elif True:
                d_0_stream_ = KernelStreamState_SClosed()
        d_1_handle_: WriteHandleState
        d_1_handle_ = (before).handle
        if (d_1_handle_) == (WriteHandleState_HOpen()):
            if (exit) == (KernelExitPath_Success()):
                d_1_handle_ = WriteHandleState_HCommitted()
            elif True:
                d_1_handle_ = WriteHandleState_HAborted()
        d_2_iter_: CallerIterState
        d_2_iter_ = (before).iter_
        if (((exit) not in (_dafny.Set({KernelExitPath_Success(), KernelExitPath_GateRefused()}))) and (closable)) and ((d_2_iter_) == (CallerIterState_ISuspended())):
            d_2_iter_ = CallerIterState_IClosed()
        after = KernelResources_KernelResources(d_0_stream_, d_1_handle_, d_2_iter_)
        return after

    @staticmethod
    def KernelClean(r, closable):
        return ((((r).stream) != (KernelStreamState_SOpen())) and (((r).handle) != (WriteHandleState_HOpen()))) and (not (closable) or (((r).iter_) != (CallerIterState_ISuspended())))

    @staticmethod
    def CleanupOnEveryExit(exit, before, closable):
        after: KernelResources = KernelResources.default()()
        out0_: KernelResources
        out0_ = default__.KernelExit(exit, before, closable)
        after = out0_
        return after


class ClosePosture:
    @_dafny.classproperty
    def AllSingletonConstructors(cls):
        return [ClosePosture_Reusable(), ClosePosture_Terminal()]
    @classmethod
    def default(cls, ):
        return lambda: ClosePosture_Reusable()
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_Reusable(self) -> bool:
        return isinstance(self, ClosePosture_Reusable)
    @property
    def is_Terminal(self) -> bool:
        return isinstance(self, ClosePosture_Terminal)

class ClosePosture_Reusable(ClosePosture, NamedTuple('Reusable', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.ClosePosture.Reusable'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, ClosePosture_Reusable)
    def __hash__(self) -> int:
        return super().__hash__()

class ClosePosture_Terminal(ClosePosture, NamedTuple('Terminal', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.ClosePosture.Terminal'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, ClosePosture_Terminal)
    def __hash__(self) -> int:
        return super().__hash__()


class KernelBackendState:
    @_dafny.classproperty
    def AllSingletonConstructors(cls):
        return [KernelBackendState_BOpen(), KernelBackendState_BClosed()]
    @classmethod
    def default(cls, ):
        return lambda: KernelBackendState_BOpen()
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_BOpen(self) -> bool:
        return isinstance(self, KernelBackendState_BOpen)
    @property
    def is_BClosed(self) -> bool:
        return isinstance(self, KernelBackendState_BClosed)

class KernelBackendState_BOpen(KernelBackendState, NamedTuple('BOpen', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.KernelBackendState.BOpen'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, KernelBackendState_BOpen)
    def __hash__(self) -> int:
        return super().__hash__()

class KernelBackendState_BClosed(KernelBackendState, NamedTuple('BClosed', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.KernelBackendState.BClosed'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, KernelBackendState_BClosed)
    def __hash__(self) -> int:
        return super().__hash__()


class KernelCall:
    @_dafny.classproperty
    def AllSingletonConstructors(cls):
        return [KernelCall_CloseCall(), KernelCall_LiveCall()]
    @classmethod
    def default(cls, ):
        return lambda: KernelCall_CloseCall()
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_CloseCall(self) -> bool:
        return isinstance(self, KernelCall_CloseCall)
    @property
    def is_LiveCall(self) -> bool:
        return isinstance(self, KernelCall_LiveCall)

class KernelCall_CloseCall(KernelCall, NamedTuple('CloseCall', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.KernelCall.CloseCall'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, KernelCall_CloseCall)
    def __hash__(self) -> int:
        return super().__hash__()

class KernelCall_LiveCall(KernelCall, NamedTuple('LiveCall', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.KernelCall.LiveCall'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, KernelCall_LiveCall)
    def __hash__(self) -> int:
        return super().__hash__()


class KernelAnswer:
    @_dafny.classproperty
    def AllSingletonConstructors(cls):
        return [KernelAnswer_Done(), KernelAnswer_Unavailable()]
    @classmethod
    def default(cls, ):
        return lambda: KernelAnswer_Done()
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_Done(self) -> bool:
        return isinstance(self, KernelAnswer_Done)
    @property
    def is_Unavailable(self) -> bool:
        return isinstance(self, KernelAnswer_Unavailable)

class KernelAnswer_Done(KernelAnswer, NamedTuple('Done', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.KernelAnswer.Done'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, KernelAnswer_Done)
    def __hash__(self) -> int:
        return super().__hash__()

class KernelAnswer_Unavailable(KernelAnswer, NamedTuple('Unavailable', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.KernelAnswer.Unavailable'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, KernelAnswer_Unavailable)
    def __hash__(self) -> int:
        return super().__hash__()


class KernelBackend:
    @classmethod
    def default(cls, ):
        return lambda: KernelBackend_KernelBackend(ClosePosture.default()(), KernelBackendState.default()(), int(0))
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_KernelBackend(self) -> bool:
        return isinstance(self, KernelBackend_KernelBackend)

class KernelBackend_KernelBackend(KernelBackend, NamedTuple('KernelBackend', [('posture', Any), ('state', Any), ('driverCloses', Any)])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.KernelBackend.KernelBackend({_dafny.string_of(self.posture)}, {_dafny.string_of(self.state)}, {_dafny.string_of(self.driverCloses)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, KernelBackend_KernelBackend) and self.posture == __o.posture and self.state == __o.state and self.driverCloses == __o.driverCloses
    def __hash__(self) -> int:
        return super().__hash__()


class KernelExitPath:
    @classmethod
    def default(cls, ):
        return lambda: KernelExitPath_Success()
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_Success(self) -> bool:
        return isinstance(self, KernelExitPath_Success)
    @property
    def is_GateRefused(self) -> bool:
        return isinstance(self, KernelExitPath_GateRefused)
    @property
    def is_Faulted(self) -> bool:
        return isinstance(self, KernelExitPath_Faulted)
    @property
    def is_Cancelled(self) -> bool:
        return isinstance(self, KernelExitPath_Cancelled)

class KernelExitPath_Success(KernelExitPath, NamedTuple('Success', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.KernelExitPath.Success'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, KernelExitPath_Success)
    def __hash__(self) -> int:
        return super().__hash__()

class KernelExitPath_GateRefused(KernelExitPath, NamedTuple('GateRefused', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.KernelExitPath.GateRefused'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, KernelExitPath_GateRefused)
    def __hash__(self) -> int:
        return super().__hash__()

class KernelExitPath_Faulted(KernelExitPath, NamedTuple('Faulted', [('dead', Any)])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.KernelExitPath.Faulted({_dafny.string_of(self.dead)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, KernelExitPath_Faulted) and self.dead == __o.dead
    def __hash__(self) -> int:
        return super().__hash__()

class KernelExitPath_Cancelled(KernelExitPath, NamedTuple('Cancelled', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.KernelExitPath.Cancelled'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, KernelExitPath_Cancelled)
    def __hash__(self) -> int:
        return super().__hash__()


class KernelStreamState:
    @_dafny.classproperty
    def AllSingletonConstructors(cls):
        return [KernelStreamState_SOpen(), KernelStreamState_SClosed(), KernelStreamState_SReleased()]
    @classmethod
    def default(cls, ):
        return lambda: KernelStreamState_SOpen()
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_SOpen(self) -> bool:
        return isinstance(self, KernelStreamState_SOpen)
    @property
    def is_SClosed(self) -> bool:
        return isinstance(self, KernelStreamState_SClosed)
    @property
    def is_SReleased(self) -> bool:
        return isinstance(self, KernelStreamState_SReleased)

class KernelStreamState_SOpen(KernelStreamState, NamedTuple('SOpen', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.KernelStreamState.SOpen'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, KernelStreamState_SOpen)
    def __hash__(self) -> int:
        return super().__hash__()

class KernelStreamState_SClosed(KernelStreamState, NamedTuple('SClosed', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.KernelStreamState.SClosed'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, KernelStreamState_SClosed)
    def __hash__(self) -> int:
        return super().__hash__()

class KernelStreamState_SReleased(KernelStreamState, NamedTuple('SReleased', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.KernelStreamState.SReleased'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, KernelStreamState_SReleased)
    def __hash__(self) -> int:
        return super().__hash__()


class WriteHandleState:
    @_dafny.classproperty
    def AllSingletonConstructors(cls):
        return [WriteHandleState_HNone(), WriteHandleState_HOpen(), WriteHandleState_HCommitted(), WriteHandleState_HAborted()]
    @classmethod
    def default(cls, ):
        return lambda: WriteHandleState_HNone()
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_HNone(self) -> bool:
        return isinstance(self, WriteHandleState_HNone)
    @property
    def is_HOpen(self) -> bool:
        return isinstance(self, WriteHandleState_HOpen)
    @property
    def is_HCommitted(self) -> bool:
        return isinstance(self, WriteHandleState_HCommitted)
    @property
    def is_HAborted(self) -> bool:
        return isinstance(self, WriteHandleState_HAborted)

class WriteHandleState_HNone(WriteHandleState, NamedTuple('HNone', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.WriteHandleState.HNone'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, WriteHandleState_HNone)
    def __hash__(self) -> int:
        return super().__hash__()

class WriteHandleState_HOpen(WriteHandleState, NamedTuple('HOpen', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.WriteHandleState.HOpen'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, WriteHandleState_HOpen)
    def __hash__(self) -> int:
        return super().__hash__()

class WriteHandleState_HCommitted(WriteHandleState, NamedTuple('HCommitted', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.WriteHandleState.HCommitted'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, WriteHandleState_HCommitted)
    def __hash__(self) -> int:
        return super().__hash__()

class WriteHandleState_HAborted(WriteHandleState, NamedTuple('HAborted', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.WriteHandleState.HAborted'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, WriteHandleState_HAborted)
    def __hash__(self) -> int:
        return super().__hash__()


class CallerIterState:
    @_dafny.classproperty
    def AllSingletonConstructors(cls):
        return [CallerIterState_IUnstarted(), CallerIterState_ISuspended(), CallerIterState_IExhausted(), CallerIterState_IClosed()]
    @classmethod
    def default(cls, ):
        return lambda: CallerIterState_IUnstarted()
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_IUnstarted(self) -> bool:
        return isinstance(self, CallerIterState_IUnstarted)
    @property
    def is_ISuspended(self) -> bool:
        return isinstance(self, CallerIterState_ISuspended)
    @property
    def is_IExhausted(self) -> bool:
        return isinstance(self, CallerIterState_IExhausted)
    @property
    def is_IClosed(self) -> bool:
        return isinstance(self, CallerIterState_IClosed)

class CallerIterState_IUnstarted(CallerIterState, NamedTuple('IUnstarted', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.CallerIterState.IUnstarted'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, CallerIterState_IUnstarted)
    def __hash__(self) -> int:
        return super().__hash__()

class CallerIterState_ISuspended(CallerIterState, NamedTuple('ISuspended', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.CallerIterState.ISuspended'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, CallerIterState_ISuspended)
    def __hash__(self) -> int:
        return super().__hash__()

class CallerIterState_IExhausted(CallerIterState, NamedTuple('IExhausted', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.CallerIterState.IExhausted'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, CallerIterState_IExhausted)
    def __hash__(self) -> int:
        return super().__hash__()

class CallerIterState_IClosed(CallerIterState, NamedTuple('IClosed', [])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.CallerIterState.IClosed'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, CallerIterState_IClosed)
    def __hash__(self) -> int:
        return super().__hash__()


class KernelResources:
    @classmethod
    def default(cls, ):
        return lambda: KernelResources_KernelResources(KernelStreamState.default()(), WriteHandleState.default()(), CallerIterState.default()())
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_KernelResources(self) -> bool:
        return isinstance(self, KernelResources_KernelResources)

class KernelResources_KernelResources(KernelResources, NamedTuple('KernelResources', [('stream', Any), ('handle', Any), ('iter_', Any)])):
    def __dafnystr__(self) -> str:
        return f'KernelProtocol.KernelResources.KernelResources({_dafny.string_of(self.stream)}, {_dafny.string_of(self.handle)}, {_dafny.string_of(self.iter_)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, KernelResources_KernelResources) and self.stream == __o.stream and self.handle == __o.handle and self.iter_ == __o.iter_
    def __hash__(self) -> int:
        return super().__hash__()

