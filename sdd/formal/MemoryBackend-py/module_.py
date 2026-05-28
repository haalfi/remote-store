import sys
from typing import Callable, Any, TypeVar, NamedTuple
from math import floor
from itertools import count

import module_ as module_
import _dafny as _dafny
import System_ as System_

# Module: module_

class Error:
    @classmethod
    def default(cls, ):
        return lambda: Error_NotFound(_dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "")), _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "")))
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_NotFound(self) -> bool:
        return isinstance(self, Error_NotFound)
    @property
    def is_AlreadyExists(self) -> bool:
        return isinstance(self, Error_AlreadyExists)
    @property
    def is_PermissionDenied(self) -> bool:
        return isinstance(self, Error_PermissionDenied)
    @property
    def is_InvalidPath(self) -> bool:
        return isinstance(self, Error_InvalidPath)
    @property
    def is_CapabilityNotSupported(self) -> bool:
        return isinstance(self, Error_CapabilityNotSupported)
    @property
    def is_DirectoryNotEmpty(self) -> bool:
        return isinstance(self, Error_DirectoryNotEmpty)
    @property
    def is_BackendUnavailable(self) -> bool:
        return isinstance(self, Error_BackendUnavailable)

class Error_NotFound(Error, NamedTuple('NotFound', [('path', Any), ('backend', Any)])):
    def __dafnystr__(self) -> str:
        return f'Error.NotFound({self.path.VerbatimString(True)}, {self.backend.VerbatimString(True)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Error_NotFound) and self.path == __o.path and self.backend == __o.backend
    def __hash__(self) -> int:
        return super().__hash__()

class Error_AlreadyExists(Error, NamedTuple('AlreadyExists', [('path', Any), ('backend', Any)])):
    def __dafnystr__(self) -> str:
        return f'Error.AlreadyExists({self.path.VerbatimString(True)}, {self.backend.VerbatimString(True)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Error_AlreadyExists) and self.path == __o.path and self.backend == __o.backend
    def __hash__(self) -> int:
        return super().__hash__()

class Error_PermissionDenied(Error, NamedTuple('PermissionDenied', [('path', Any), ('backend', Any)])):
    def __dafnystr__(self) -> str:
        return f'Error.PermissionDenied({self.path.VerbatimString(True)}, {self.backend.VerbatimString(True)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Error_PermissionDenied) and self.path == __o.path and self.backend == __o.backend
    def __hash__(self) -> int:
        return super().__hash__()

class Error_InvalidPath(Error, NamedTuple('InvalidPath', [('path', Any), ('backend', Any)])):
    def __dafnystr__(self) -> str:
        return f'Error.InvalidPath({self.path.VerbatimString(True)}, {self.backend.VerbatimString(True)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Error_InvalidPath) and self.path == __o.path and self.backend == __o.backend
    def __hash__(self) -> int:
        return super().__hash__()

class Error_CapabilityNotSupported(Error, NamedTuple('CapabilityNotSupported', [('capability', Any), ('backend', Any)])):
    def __dafnystr__(self) -> str:
        return f'Error.CapabilityNotSupported({self.capability.VerbatimString(True)}, {self.backend.VerbatimString(True)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Error_CapabilityNotSupported) and self.capability == __o.capability and self.backend == __o.backend
    def __hash__(self) -> int:
        return super().__hash__()

class Error_DirectoryNotEmpty(Error, NamedTuple('DirectoryNotEmpty', [('path', Any), ('backend', Any)])):
    def __dafnystr__(self) -> str:
        return f'Error.DirectoryNotEmpty({self.path.VerbatimString(True)}, {self.backend.VerbatimString(True)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Error_DirectoryNotEmpty) and self.path == __o.path and self.backend == __o.backend
    def __hash__(self) -> int:
        return super().__hash__()

class Error_BackendUnavailable(Error, NamedTuple('BackendUnavailable', [('backend', Any)])):
    def __dafnystr__(self) -> str:
        return f'Error.BackendUnavailable({self.backend.VerbatimString(True)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Error_BackendUnavailable) and self.backend == __o.backend
    def __hash__(self) -> int:
        return super().__hash__()


class Result:
    @classmethod
    def default(cls, ):
        return lambda: Result_Err(Error.default()())
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_Ok(self) -> bool:
        return isinstance(self, Result_Ok)
    @property
    def is_Err(self) -> bool:
        return isinstance(self, Result_Err)

class Result_Ok(Result, NamedTuple('Ok', [('value', Any)])):
    def __dafnystr__(self) -> str:
        return f'Result.Ok({_dafny.string_of(self.value)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Result_Ok) and self.value == __o.value
    def __hash__(self) -> int:
        return super().__hash__()

class Result_Err(Result, NamedTuple('Err', [('error', Any)])):
    def __dafnystr__(self) -> str:
        return f'Result.Err({_dafny.string_of(self.error)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Result_Err) and self.error == __o.error
    def __hash__(self) -> int:
        return super().__hash__()


class Capability:
    @_dafny.classproperty
    def AllSingletonConstructors(cls):
        return [Capability_CapRead(), Capability_CapWrite(), Capability_CapDelete(), Capability_CapList(), Capability_CapMove(), Capability_CapCopy(), Capability_CapAtomicWrite(), Capability_CapAtomicMove(), Capability_CapMetadata(), Capability_CapGlob(), Capability_CapSeekableRead(), Capability_CapWriteResultNative(), Capability_CapUserMetadata(), Capability_CapLazyRead()]
    @classmethod
    def default(cls, ):
        return lambda: Capability_CapRead()
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_CapRead(self) -> bool:
        return isinstance(self, Capability_CapRead)
    @property
    def is_CapWrite(self) -> bool:
        return isinstance(self, Capability_CapWrite)
    @property
    def is_CapDelete(self) -> bool:
        return isinstance(self, Capability_CapDelete)
    @property
    def is_CapList(self) -> bool:
        return isinstance(self, Capability_CapList)
    @property
    def is_CapMove(self) -> bool:
        return isinstance(self, Capability_CapMove)
    @property
    def is_CapCopy(self) -> bool:
        return isinstance(self, Capability_CapCopy)
    @property
    def is_CapAtomicWrite(self) -> bool:
        return isinstance(self, Capability_CapAtomicWrite)
    @property
    def is_CapAtomicMove(self) -> bool:
        return isinstance(self, Capability_CapAtomicMove)
    @property
    def is_CapMetadata(self) -> bool:
        return isinstance(self, Capability_CapMetadata)
    @property
    def is_CapGlob(self) -> bool:
        return isinstance(self, Capability_CapGlob)
    @property
    def is_CapSeekableRead(self) -> bool:
        return isinstance(self, Capability_CapSeekableRead)
    @property
    def is_CapWriteResultNative(self) -> bool:
        return isinstance(self, Capability_CapWriteResultNative)
    @property
    def is_CapUserMetadata(self) -> bool:
        return isinstance(self, Capability_CapUserMetadata)
    @property
    def is_CapLazyRead(self) -> bool:
        return isinstance(self, Capability_CapLazyRead)

class Capability_CapRead(Capability, NamedTuple('CapRead', [])):
    def __dafnystr__(self) -> str:
        return f'Capability.CapRead'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapRead)
    def __hash__(self) -> int:
        return super().__hash__()

class Capability_CapWrite(Capability, NamedTuple('CapWrite', [])):
    def __dafnystr__(self) -> str:
        return f'Capability.CapWrite'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapWrite)
    def __hash__(self) -> int:
        return super().__hash__()

class Capability_CapDelete(Capability, NamedTuple('CapDelete', [])):
    def __dafnystr__(self) -> str:
        return f'Capability.CapDelete'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapDelete)
    def __hash__(self) -> int:
        return super().__hash__()

class Capability_CapList(Capability, NamedTuple('CapList', [])):
    def __dafnystr__(self) -> str:
        return f'Capability.CapList'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapList)
    def __hash__(self) -> int:
        return super().__hash__()

class Capability_CapMove(Capability, NamedTuple('CapMove', [])):
    def __dafnystr__(self) -> str:
        return f'Capability.CapMove'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapMove)
    def __hash__(self) -> int:
        return super().__hash__()

class Capability_CapCopy(Capability, NamedTuple('CapCopy', [])):
    def __dafnystr__(self) -> str:
        return f'Capability.CapCopy'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapCopy)
    def __hash__(self) -> int:
        return super().__hash__()

class Capability_CapAtomicWrite(Capability, NamedTuple('CapAtomicWrite', [])):
    def __dafnystr__(self) -> str:
        return f'Capability.CapAtomicWrite'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapAtomicWrite)
    def __hash__(self) -> int:
        return super().__hash__()

class Capability_CapAtomicMove(Capability, NamedTuple('CapAtomicMove', [])):
    def __dafnystr__(self) -> str:
        return f'Capability.CapAtomicMove'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapAtomicMove)
    def __hash__(self) -> int:
        return super().__hash__()

class Capability_CapMetadata(Capability, NamedTuple('CapMetadata', [])):
    def __dafnystr__(self) -> str:
        return f'Capability.CapMetadata'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapMetadata)
    def __hash__(self) -> int:
        return super().__hash__()

class Capability_CapGlob(Capability, NamedTuple('CapGlob', [])):
    def __dafnystr__(self) -> str:
        return f'Capability.CapGlob'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapGlob)
    def __hash__(self) -> int:
        return super().__hash__()

class Capability_CapSeekableRead(Capability, NamedTuple('CapSeekableRead', [])):
    def __dafnystr__(self) -> str:
        return f'Capability.CapSeekableRead'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapSeekableRead)
    def __hash__(self) -> int:
        return super().__hash__()

class Capability_CapWriteResultNative(Capability, NamedTuple('CapWriteResultNative', [])):
    def __dafnystr__(self) -> str:
        return f'Capability.CapWriteResultNative'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapWriteResultNative)
    def __hash__(self) -> int:
        return super().__hash__()

class Capability_CapUserMetadata(Capability, NamedTuple('CapUserMetadata', [])):
    def __dafnystr__(self) -> str:
        return f'Capability.CapUserMetadata'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapUserMetadata)
    def __hash__(self) -> int:
        return super().__hash__()

class Capability_CapLazyRead(Capability, NamedTuple('CapLazyRead', [])):
    def __dafnystr__(self) -> str:
        return f'Capability.CapLazyRead'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapLazyRead)
    def __hash__(self) -> int:
        return super().__hash__()


class Path:
    def  __init__(self):
        pass

    @staticmethod
    def default():
        return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "a"))
    def _Is(source__):
        d_0_s_: _dafny.Seq = source__
        return (d_0_s_) != (_dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "")))

class Option:
    @classmethod
    def default(cls, ):
        return lambda: Option_None()
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_None(self) -> bool:
        return isinstance(self, Option_None)
    @property
    def is_Some(self) -> bool:
        return isinstance(self, Option_Some)

class Option_None(Option, NamedTuple('None_', [])):
    def __dafnystr__(self) -> str:
        return f'Option.None'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Option_None)
    def __hash__(self) -> int:
        return super().__hash__()

class Option_Some(Option, NamedTuple('Some', [('value', Any)])):
    def __dafnystr__(self) -> str:
        return f'Option.Some({_dafny.string_of(self.value)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Option_Some) and self.value == __o.value
    def __hash__(self) -> int:
        return super().__hash__()


class ContentDigest:
    @classmethod
    def default(cls, ):
        return lambda: ContentDigest_ContentDigest(_dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "")), _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "")))
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_ContentDigest(self) -> bool:
        return isinstance(self, ContentDigest_ContentDigest)

class ContentDigest_ContentDigest(ContentDigest, NamedTuple('ContentDigest', [('kind', Any), ('value', Any)])):
    def __dafnystr__(self) -> str:
        return f'ContentDigest.ContentDigest({self.kind.VerbatimString(True)}, {self.value.VerbatimString(True)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, ContentDigest_ContentDigest) and self.kind == __o.kind and self.value == __o.value
    def __hash__(self) -> int:
        return super().__hash__()


class WriteSource:
    @_dafny.classproperty
    def AllSingletonConstructors(cls):
        return [WriteSource_NativeSource(), WriteSource_BasicSource(), WriteSource_SidecarSource()]
    @classmethod
    def default(cls, ):
        return lambda: WriteSource_NativeSource()
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_NativeSource(self) -> bool:
        return isinstance(self, WriteSource_NativeSource)
    @property
    def is_BasicSource(self) -> bool:
        return isinstance(self, WriteSource_BasicSource)
    @property
    def is_SidecarSource(self) -> bool:
        return isinstance(self, WriteSource_SidecarSource)

class WriteSource_NativeSource(WriteSource, NamedTuple('NativeSource', [])):
    def __dafnystr__(self) -> str:
        return f'WriteSource.NativeSource'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, WriteSource_NativeSource)
    def __hash__(self) -> int:
        return super().__hash__()

class WriteSource_BasicSource(WriteSource, NamedTuple('BasicSource', [])):
    def __dafnystr__(self) -> str:
        return f'WriteSource.BasicSource'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, WriteSource_BasicSource)
    def __hash__(self) -> int:
        return super().__hash__()

class WriteSource_SidecarSource(WriteSource, NamedTuple('SidecarSource', [])):
    def __dafnystr__(self) -> str:
        return f'WriteSource.SidecarSource'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, WriteSource_SidecarSource)
    def __hash__(self) -> int:
        return super().__hash__()


class FileInfo:
    @classmethod
    def default(cls, ):
        return lambda: FileInfo_FileInfo(Path.default(), _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "")), int(0), Option.default()(), Option.default()(), Option.default()(), Option.default()())
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_FileInfo(self) -> bool:
        return isinstance(self, FileInfo_FileInfo)

class FileInfo_FileInfo(FileInfo, NamedTuple('FileInfo', [('path', Any), ('name', Any), ('size', Any), ('digest', Any), ('etag', Any), ('last__modified', Any), ('metadata', Any)])):
    def __dafnystr__(self) -> str:
        return f'FileInfo.FileInfo({self.path.VerbatimString(True)}, {self.name.VerbatimString(True)}, {_dafny.string_of(self.size)}, {_dafny.string_of(self.digest)}, {_dafny.string_of(self.etag)}, {_dafny.string_of(self.last__modified)}, {_dafny.string_of(self.metadata)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, FileInfo_FileInfo) and self.path == __o.path and self.name == __o.name and self.size == __o.size and self.digest == __o.digest and self.etag == __o.etag and self.last__modified == __o.last__modified and self.metadata == __o.metadata
    def __hash__(self) -> int:
        return super().__hash__()


class WriteResult:
    @classmethod
    def default(cls, ):
        return lambda: WriteResult_WriteResult(Path.default(), int(0), Option.default()(), Option.default()(), Option.default()(), Option.default()(), Option.default()(), WriteSource.default()())
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_WriteResult(self) -> bool:
        return isinstance(self, WriteResult_WriteResult)

class WriteResult_WriteResult(WriteResult, NamedTuple('WriteResult', [('path', Any), ('size', Any), ('digest', Any), ('etag', Any), ('version__id', Any), ('last__modified', Any), ('metadata', Any), ('source', Any)])):
    def __dafnystr__(self) -> str:
        return f'WriteResult.WriteResult({self.path.VerbatimString(True)}, {_dafny.string_of(self.size)}, {_dafny.string_of(self.digest)}, {_dafny.string_of(self.etag)}, {_dafny.string_of(self.version__id)}, {_dafny.string_of(self.last__modified)}, {_dafny.string_of(self.metadata)}, {_dafny.string_of(self.source)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, WriteResult_WriteResult) and self.path == __o.path and self.size == __o.size and self.digest == __o.digest and self.etag == __o.etag and self.version__id == __o.version__id and self.last__modified == __o.last__modified and self.metadata == __o.metadata and self.source == __o.source
    def __hash__(self) -> int:
        return super().__hash__()


class FolderEntry:
    @classmethod
    def default(cls, ):
        return lambda: FolderEntry_FolderEntry(Path.default(), _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "")))
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_FolderEntry(self) -> bool:
        return isinstance(self, FolderEntry_FolderEntry)

class FolderEntry_FolderEntry(FolderEntry, NamedTuple('FolderEntry', [('path', Any), ('name', Any)])):
    def __dafnystr__(self) -> str:
        return f'FolderEntry.FolderEntry({self.path.VerbatimString(True)}, {self.name.VerbatimString(True)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, FolderEntry_FolderEntry) and self.path == __o.path and self.name == __o.name
    def __hash__(self) -> int:
        return super().__hash__()


class FolderInfo:
    @classmethod
    def default(cls, ):
        return lambda: FolderInfo_FolderInfo(Path.default(), _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "")), int(0), int(0))
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_FolderInfo(self) -> bool:
        return isinstance(self, FolderInfo_FolderInfo)

class FolderInfo_FolderInfo(FolderInfo, NamedTuple('FolderInfo', [('path', Any), ('name', Any), ('file__count', Any), ('total__size', Any)])):
    def __dafnystr__(self) -> str:
        return f'FolderInfo.FolderInfo({self.path.VerbatimString(True)}, {self.name.VerbatimString(True)}, {_dafny.string_of(self.file__count)}, {_dafny.string_of(self.total__size)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, FolderInfo_FolderInfo) and self.path == __o.path and self.name == __o.name and self.file__count == __o.file__count and self.total__size == __o.total__size
    def __hash__(self) -> int:
        return super().__hash__()


class Entry:
    @classmethod
    def default(cls, ):
        return lambda: Entry_FileEntry(_dafny.Seq({}), FileInfo.default()())
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_FileEntry(self) -> bool:
        return isinstance(self, Entry_FileEntry)
    @property
    def is_DirEntry(self) -> bool:
        return isinstance(self, Entry_DirEntry)

class Entry_FileEntry(Entry, NamedTuple('FileEntry', [('content', Any), ('info', Any)])):
    def __dafnystr__(self) -> str:
        return f'Entry.FileEntry({_dafny.string_of(self.content)}, {_dafny.string_of(self.info)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Entry_FileEntry) and self.content == __o.content and self.info == __o.info
    def __hash__(self) -> int:
        return super().__hash__()

class Entry_DirEntry(Entry, NamedTuple('DirEntry', [])):
    def __dafnystr__(self) -> str:
        return f'Entry.DirEntry'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Entry_DirEntry)
    def __hash__(self) -> int:
        return super().__hash__()


class ReadStream:
    @classmethod
    def default(cls, ):
        return lambda: ReadStream_ReadStream(_dafny.Seq({}), False)
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_ReadStream(self) -> bool:
        return isinstance(self, ReadStream_ReadStream)

class ReadStream_ReadStream(ReadStream, NamedTuple('ReadStream', [('content', Any), ('seekable', Any)])):
    def __dafnystr__(self) -> str:
        return f'ReadStream.ReadStream({_dafny.string_of(self.content)}, {_dafny.string_of(self.seekable)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, ReadStream_ReadStream) and self.content == __o.content and self.seekable == __o.seekable
    def __hash__(self) -> int:
        return super().__hash__()


class HandleState:
    @_dafny.classproperty
    def AllSingletonConstructors(cls):
        return [HandleState_Open(), HandleState_Wrapped(), HandleState_Closed()]
    @classmethod
    def default(cls, ):
        return lambda: HandleState_Open()
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_Open(self) -> bool:
        return isinstance(self, HandleState_Open)
    @property
    def is_Wrapped(self) -> bool:
        return isinstance(self, HandleState_Wrapped)
    @property
    def is_Closed(self) -> bool:
        return isinstance(self, HandleState_Closed)

class HandleState_Open(HandleState, NamedTuple('Open', [])):
    def __dafnystr__(self) -> str:
        return f'HandleState.Open'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, HandleState_Open)
    def __hash__(self) -> int:
        return super().__hash__()

class HandleState_Wrapped(HandleState, NamedTuple('Wrapped', [])):
    def __dafnystr__(self) -> str:
        return f'HandleState.Wrapped'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, HandleState_Wrapped)
    def __hash__(self) -> int:
        return super().__hash__()

class HandleState_Closed(HandleState, NamedTuple('Closed', [])):
    def __dafnystr__(self) -> str:
        return f'HandleState.Closed'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, HandleState_Closed)
    def __hash__(self) -> int:
        return super().__hash__()


class Resource:
    @classmethod
    def default(cls, ):
        return lambda: Resource_Resource(int(0), HandleState.default()())
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_Resource(self) -> bool:
        return isinstance(self, Resource_Resource)

class Resource_Resource(Resource, NamedTuple('Resource', [('id_', Any), ('state', Any)])):
    def __dafnystr__(self) -> str:
        return f'Resource.Resource({_dafny.string_of(self.id_)}, {_dafny.string_of(self.state)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Resource_Resource) and self.id_ == __o.id_ and self.state == __o.state
    def __hash__(self) -> int:
        return super().__hash__()


class WrapPipeline:
    @classmethod
    def default(cls, ):
        return lambda: WrapPipeline_WrapPipeline(_dafny.Seq({}), int(0))
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_WrapPipeline(self) -> bool:
        return isinstance(self, WrapPipeline_WrapPipeline)

class WrapPipeline_WrapPipeline(WrapPipeline, NamedTuple('WrapPipeline', [('layers', Any), ('failed__at', Any)])):
    def __dafnystr__(self) -> str:
        return f'WrapPipeline.WrapPipeline({_dafny.string_of(self.layers)}, {_dafny.string_of(self.failed__at)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, WrapPipeline_WrapPipeline) and self.layers == __o.layers and self.failed__at == __o.failed__at
    def __hash__(self) -> int:
        return super().__hash__()


class MovePhase:
    @classmethod
    def default(cls, ):
        return lambda: MovePhase_Initial()
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_Initial(self) -> bool:
        return isinstance(self, MovePhase_Initial)
    @property
    def is_CopyDone(self) -> bool:
        return isinstance(self, MovePhase_CopyDone)
    @property
    def is_DeleteDone(self) -> bool:
        return isinstance(self, MovePhase_DeleteDone)
    @property
    def is_Failed(self) -> bool:
        return isinstance(self, MovePhase_Failed)

class MovePhase_Initial(MovePhase, NamedTuple('Initial', [])):
    def __dafnystr__(self) -> str:
        return f'MovePhase.Initial'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, MovePhase_Initial)
    def __hash__(self) -> int:
        return super().__hash__()

class MovePhase_CopyDone(MovePhase, NamedTuple('CopyDone', [])):
    def __dafnystr__(self) -> str:
        return f'MovePhase.CopyDone'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, MovePhase_CopyDone)
    def __hash__(self) -> int:
        return super().__hash__()

class MovePhase_DeleteDone(MovePhase, NamedTuple('DeleteDone', [])):
    def __dafnystr__(self) -> str:
        return f'MovePhase.DeleteDone'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, MovePhase_DeleteDone)
    def __hash__(self) -> int:
        return super().__hash__()

class MovePhase_Failed(MovePhase, NamedTuple('Failed', [('phase', Any), ('reason', Any)])):
    def __dafnystr__(self) -> str:
        return f'MovePhase.Failed({self.phase.VerbatimString(True)}, {self.reason.VerbatimString(True)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, MovePhase_Failed) and self.phase == __o.phase and self.reason == __o.reason
    def __hash__(self) -> int:
        return super().__hash__()


class MoveContract:
    @classmethod
    def default(cls, ):
        return lambda: MoveContract_ObservedDeleteDone()
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_ObservedDeleteDone(self) -> bool:
        return isinstance(self, MoveContract_ObservedDeleteDone)
    @property
    def is_ObservedFailed(self) -> bool:
        return isinstance(self, MoveContract_ObservedFailed)

class MoveContract_ObservedDeleteDone(MoveContract, NamedTuple('ObservedDeleteDone', [])):
    def __dafnystr__(self) -> str:
        return f'MoveContract.ObservedDeleteDone'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, MoveContract_ObservedDeleteDone)
    def __hash__(self) -> int:
        return super().__hash__()

class MoveContract_ObservedFailed(MoveContract, NamedTuple('ObservedFailed', [('reason', Any)])):
    def __dafnystr__(self) -> str:
        return f'MoveContract.ObservedFailed({self.reason.VerbatimString(True)})'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, MoveContract_ObservedFailed) and self.reason == __o.reason
    def __hash__(self) -> int:
        return super().__hash__()


class ConnectionState:
    @_dafny.classproperty
    def AllSingletonConstructors(cls):
        return [ConnectionState_Created(), ConnectionState_Connected(), ConnectionState_Abandoned(), ConnectionState_Released()]
    @classmethod
    def default(cls, ):
        return lambda: ConnectionState_Created()
    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)
    @property
    def is_Created(self) -> bool:
        return isinstance(self, ConnectionState_Created)
    @property
    def is_Connected(self) -> bool:
        return isinstance(self, ConnectionState_Connected)
    @property
    def is_Abandoned(self) -> bool:
        return isinstance(self, ConnectionState_Abandoned)
    @property
    def is_Released(self) -> bool:
        return isinstance(self, ConnectionState_Released)

class ConnectionState_Created(ConnectionState, NamedTuple('Created', [])):
    def __dafnystr__(self) -> str:
        return f'ConnectionState.Created'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, ConnectionState_Created)
    def __hash__(self) -> int:
        return super().__hash__()

class ConnectionState_Connected(ConnectionState, NamedTuple('Connected', [])):
    def __dafnystr__(self) -> str:
        return f'ConnectionState.Connected'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, ConnectionState_Connected)
    def __hash__(self) -> int:
        return super().__hash__()

class ConnectionState_Abandoned(ConnectionState, NamedTuple('Abandoned', [])):
    def __dafnystr__(self) -> str:
        return f'ConnectionState.Abandoned'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, ConnectionState_Abandoned)
    def __hash__(self) -> int:
        return super().__hash__()

class ConnectionState_Released(ConnectionState, NamedTuple('Released', [])):
    def __dafnystr__(self) -> str:
        return f'ConnectionState.Released'
    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, ConnectionState_Released)
    def __hash__(self) -> int:
        return super().__hash__()

class Backend:
    pass
    @property
    def fs(self):
        return self._fs
    @fs.setter
    def fs(self, value):
        self._fs = value
    @staticmethod
    def Valid(self):
        def lambda0_(forall_var_0_):
            def lambda1_(forall_var_1_):
                d_1_i_: int = forall_var_1_
                return not ((((0) < (d_1_i_)) and ((d_1_i_) < ((len(d_0_p_)) - (1)))) and (((d_0_p_)[d_1_i_]) == (_dafny.CodePoint('/')))) or (default__.IsDir(self.fs, _dafny.SeqWithoutIsStrInference((d_0_p_)[:d_1_i_:])))

            d_0_p_: _dafny.Seq = forall_var_0_
            if Path._Is(d_0_p_):
                return not ((d_0_p_) in (self.fs)) or (_dafny.quantifier(_dafny.IntegerRange((0) + (1), (len(d_0_p_)) - (1)), True, lambda1_))
            elif True:
                return True

        return _dafny.quantifier((self.fs).keys.Elements, True, lambda0_)

    def Exists(self, path):
        pass

    def IsFileMethod(self, path):
        pass

    def IsFolderMethod(self, path):
        pass

    def Read(self, path):
        pass

    def Write(self, path, content, overwrite, metadata):
        pass

    def Delete(self, path, missing__ok):
        pass

    def DeleteFolder(self, path, recursive, missing__ok):
        pass

    def ListFiles(self, path, recursive, max__depth):
        pass

    def ListFolders(self, path):
        pass

    def GetFileInfo(self, path):
        pass

    def GetFolderInfo(self, path):
        pass

    def Move(self, src, dst, overwrite):
        pass

    def Copy(self, src, dst, overwrite):
        pass

    def RequireCapability(self, cap):
        pass


class default__:
    def  __init__(self):
        pass

    @staticmethod
    def BasicFileInfo(path, name, size):
        return FileInfo_FileInfo(path, name, size, Option_None(), Option_None(), Option_None(), Option_None())

    @staticmethod
    def HasUserMetadata(m):
        return ((m).is_Some) and ((len((m).value)) > (0))

    @staticmethod
    def IsFile(fs, p):
        return ((p) in (fs)) and (((fs)[p]).is_FileEntry)

    @staticmethod
    def IsDir(fs, p):
        return ((p) in (fs)) and (((fs)[p]).is_DirEntry)

    @staticmethod
    def PathExists(fs, p):
        return (p) in (fs)

    @staticmethod
    def HasChildren(fs, dir_):
        def lambda0_(exists_var_0_):
            d_0_p_: _dafny.Seq = exists_var_0_
            if Path._Is(d_0_p_):
                return ((d_0_p_) in (fs)) and (default__.IsChildOf(d_0_p_, dir_))
            elif True:
                return False

        return _dafny.quantifier((fs).keys.Elements, False, lambda0_)

    @staticmethod
    def SlashCount(p):
        d_0___accumulator_ = 0
        while True:
            with _dafny.label():
                if (len(p)) == (0):
                    return (0) + (d_0___accumulator_)
                elif True:
                    d_0___accumulator_ = (d_0___accumulator_) + ((1 if ((p)[0]) == (_dafny.CodePoint('/')) else 0))
                    in0_ = _dafny.SeqWithoutIsStrInference((p)[1::])
                    p = in0_
                    raise _dafny.TailCall()
                break

    @staticmethod
    def Depth(root, child):
        if (root) == (_dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "."))):
            if (child) == (_dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "."))):
                return -1
            elif True:
                return default__.SlashCount(child)
        elif (len(child)) <= ((len(root)) + (1)):
            return -1
        elif (_dafny.SeqWithoutIsStrInference((child)[:len(root):])) != (root):
            return -1
        elif ((child)[len(root)]) != (_dafny.CodePoint('/')):
            return -1
        elif True:
            d_0_suffix_ = _dafny.SeqWithoutIsStrInference((child)[(len(root)) + (1)::])
            return default__.SlashCount(d_0_suffix_)

    @staticmethod
    def IsChildOf(child, parent):
        if (parent) == (_dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "."))):
            return (child) != (_dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, ".")))
        elif True:
            return (((len(child)) > ((len(parent)) + (1))) and ((_dafny.SeqWithoutIsStrInference((child)[:len(parent):])) == (parent))) and (((child)[len(parent)]) == (_dafny.CodePoint('/')))

    @staticmethod
    def AllAncestorsTraversable(fs, p):
        def lambda0_(forall_var_0_):
            d_0_i_: int = forall_var_0_
            return not ((((0) < (d_0_i_)) and ((d_0_i_) < ((len(p)) - (1)))) and (((p)[d_0_i_]) == (_dafny.CodePoint('/')))) or ((not(default__.PathExists(fs, _dafny.SeqWithoutIsStrInference((p)[:d_0_i_:])))) or (default__.IsDir(fs, _dafny.SeqWithoutIsStrInference((p)[:d_0_i_:]))))

        return _dafny.quantifier(_dafny.IntegerRange((0) + (1), (len(p)) - (1)), True, lambda0_)

    @staticmethod
    def CapabilityName(c):
        source0_ = c
        if True:
            if source0_.is_CapRead:
                return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "read"))
        if True:
            if source0_.is_CapWrite:
                return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "write"))
        if True:
            if source0_.is_CapDelete:
                return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "delete"))
        if True:
            if source0_.is_CapList:
                return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "list"))
        if True:
            if source0_.is_CapMove:
                return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "move"))
        if True:
            if source0_.is_CapCopy:
                return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "copy"))
        if True:
            if source0_.is_CapAtomicWrite:
                return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "atomic_write"))
        if True:
            if source0_.is_CapAtomicMove:
                return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "atomic_move"))
        if True:
            if source0_.is_CapMetadata:
                return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "metadata"))
        if True:
            if source0_.is_CapGlob:
                return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "glob"))
        if True:
            if source0_.is_CapSeekableRead:
                return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "seekable_read"))
        if True:
            if source0_.is_CapWriteResultNative:
                return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "write_result_native"))
        if True:
            if source0_.is_CapUserMetadata:
                return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "user_metadata"))
        if True:
            return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "lazy_read"))

    @staticmethod
    def WriteResultFromFileInfo(info):
        return WriteResult_WriteResult((info).path, (info).size, (info).digest, (info).etag, Option_None(), (info).last__modified, (info).metadata, WriteSource_SidecarSource())

    @staticmethod
    def AllHandlesAccountedFor(pipeline):
        def lambda0_(forall_var_0_):
            d_0_i_: int = forall_var_0_
            return not (((0) <= (d_0_i_)) and ((d_0_i_) < (len((pipeline).layers)))) or (((((pipeline).layers)[d_0_i_]).state) != (HandleState_Open()))

        return _dafny.quantifier(_dafny.IntegerRange(0, len((pipeline).layers)), True, lambda0_)

    @staticmethod
    def SafeWrapInvariant(pipeline):
        if ((pipeline).failed__at) == (-1):
            def lambda0_(forall_var_0_):
                d_0_i_: int = forall_var_0_
                return not (((0) <= (d_0_i_)) and ((d_0_i_) < (len((pipeline).layers)))) or (((((pipeline).layers)[d_0_i_]).state) == (HandleState_Wrapped()))

            return _dafny.quantifier(_dafny.IntegerRange(0, len((pipeline).layers)), True, lambda0_)
        elif True:
            def lambda1_(forall_var_1_):
                d_1_i_: int = forall_var_1_
                return not (((0) <= (d_1_i_)) and ((d_1_i_) < ((pipeline).failed__at))) or (((((pipeline).layers)[d_1_i_]).state) == (HandleState_Closed()))

            return ((((0) <= ((pipeline).failed__at)) and (((pipeline).failed__at) <= (len((pipeline).layers)))) and (_dafny.quantifier(_dafny.IntegerRange(0, (pipeline).failed__at), True, lambda1_))) and (((pipeline).failed__at) == (len((pipeline).layers)))

    @staticmethod
    def SafeWrap(rawId, wrapperCount, failAt):
        pipeline: WrapPipeline = WrapPipeline.default()()
        if (failAt) == (-1):
            d_0_layers_: _dafny.Seq
            d_0_layers_ = _dafny.SeqWithoutIsStrInference([])
            d_1_i_: int
            d_1_i_ = 0
            while (d_1_i_) <= (wrapperCount):
                d_0_layers_ = (d_0_layers_) + (_dafny.SeqWithoutIsStrInference([Resource_Resource((rawId) + (d_1_i_), HandleState_Wrapped())]))
                d_1_i_ = (d_1_i_) + (1)
            pipeline = WrapPipeline_WrapPipeline(d_0_layers_, -1)
        elif True:
            d_2_layers_: _dafny.Seq
            d_2_layers_ = _dafny.SeqWithoutIsStrInference([])
            d_3_i_: int
            d_3_i_ = 0
            while (d_3_i_) <= (failAt):
                d_2_layers_ = (d_2_layers_) + (_dafny.SeqWithoutIsStrInference([Resource_Resource((rawId) + (d_3_i_), HandleState_Closed())]))
                d_3_i_ = (d_3_i_) + (1)
            pipeline = WrapPipeline_WrapPipeline(d_2_layers_, (failAt) + (1))
        return pipeline

    @staticmethod
    def UnsafeWrap(rawId, wrapperCount, failAt):
        pipeline: WrapPipeline = WrapPipeline.default()()
        d_0_layers_: _dafny.Seq
        d_0_layers_ = _dafny.SeqWithoutIsStrInference([Resource_Resource(rawId, HandleState_Open())])
        d_1_i_: int
        d_1_i_ = 1
        while (d_1_i_) <= (failAt):
            d_0_layers_ = (d_0_layers_) + (_dafny.SeqWithoutIsStrInference([Resource_Resource((rawId) + (d_1_i_), HandleState_Wrapped())]))
            d_1_i_ = (d_1_i_) + (1)
        pipeline = WrapPipeline_WrapPipeline(d_0_layers_, (failAt) + (1))
        return pipeline

    @staticmethod
    def AtomicMove(srcExists, dstExists, overwrite):
        phase: MovePhase = MovePhase.default()()
        if not(srcExists):
            phase = MovePhase_Failed(_dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "initial")), _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "source not found")))
        elif (dstExists) and (not(overwrite)):
            phase = MovePhase_Failed(_dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "initial")), _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "destination exists")))
        elif True:
            phase = MovePhase_DeleteDone()
        return phase

    @staticmethod
    def CopyDeleteMove(srcExists, dstExists, overwrite, deleteFails):
        phase: MovePhase = MovePhase.default()()
        if not(srcExists):
            phase = MovePhase_Failed(_dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "initial")), _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "source not found")))
            return phase
        if (dstExists) and (not(overwrite)):
            phase = MovePhase_Failed(_dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "initial")), _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "destination exists")))
            return phase
        phase = MovePhase_CopyDone()
        if deleteFails:
            return phase
        phase = MovePhase_DeleteDone()
        return phase

    @staticmethod
    def ObservableForAtomicMove(phase):
        return ((phase) != (MovePhase_CopyDone())) and ((phase) != (MovePhase_Initial()))

    @staticmethod
    def Observe(phase):
        source0_ = phase
        if True:
            if source0_.is_DeleteDone:
                return MoveContract_ObservedDeleteDone()
        if True:
            d_0_reason_ = source0_.reason
            return MoveContract_ObservedFailed(d_0_reason_)

    @staticmethod
    def AtomicMoveIsObservable(srcExists, dstExists, overwrite):
        phase: MovePhase = MovePhase.default()()
        out0_: MovePhase
        out0_ = default__.AtomicMove(srcExists, dstExists, overwrite)
        phase = out0_
        return phase

    @staticmethod
    def SafeConnect(connectSucceeds):
        state: ConnectionState = ConnectionState.default()()
        state = ConnectionState_Created()
        if connectSucceeds:
            state = ConnectionState_Connected()
        elif True:
            state = ConnectionState_Released()
        return state

    @staticmethod
    def UnsafeConnect(connectSucceeds):
        state: ConnectionState = ConnectionState.default()()
        state = ConnectionState_Created()
        if connectSucceeds:
            state = ConnectionState_Connected()
        elif True:
            state = ConnectionState_Abandoned()
        return state

    @_dafny.classproperty
    def Root(instance):
        return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "."))

class MemoryBackend(Backend):
    def  __init__(self):
        self._fs: _dafny.Map = _dafny.Map({})
        self._name: _dafny.Seq = _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, ""))
        self._capabilities: _dafny.Set = _dafny.Set({})
        pass

    def __dafnystr__(self) -> str:
        return "_module.MemoryBackend"
    @property
    def fs(self):
        return self._fs
    @fs.setter
    def fs(self, value):
        self._fs = value
    def Valid(self):
        return Backend.Valid(self)

    @property
    def name(self):
        return self._name
    @property
    def capabilities(self):
        return self._capabilities
    def ctor__(self):
        (self)._name = _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "memory"))
        (self)._capabilities = _dafny.Set({Capability_CapRead(), Capability_CapWrite(), Capability_CapDelete(), Capability_CapList(), Capability_CapMove(), Capability_CapCopy(), Capability_CapAtomicWrite(), Capability_CapAtomicMove(), Capability_CapMetadata(), Capability_CapSeekableRead(), Capability_CapWriteResultNative(), Capability_CapUserMetadata()})
        (self).fs = _dafny.Map({default__.Root: Entry_DirEntry()})

    def Exists(self, path):
        r: Result = Result.default()()
        d_0_path__exists_: bool
        d_0_path__exists_ = (path) in (self.fs)
        d_1_ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(path)
        d_1_ancestors__ok_ = out0_
        r = Result_Ok((d_0_path__exists_) and (d_1_ancestors__ok_))
        return r

    def IsFileMethod(self, path):
        r: Result = Result.default()()
        d_0_is__file_: bool
        d_0_is__file_ = ((path) in (self.fs)) and (((self.fs)[path]).is_FileEntry)
        d_1_ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(path)
        d_1_ancestors__ok_ = out0_
        r = Result_Ok((d_0_is__file_) and (d_1_ancestors__ok_))
        return r

    def IsFolderMethod(self, path):
        r: Result = Result.default()()
        d_0_is__dir_: bool
        d_0_is__dir_ = ((path) in (self.fs)) and (((self.fs)[path]).is_DirEntry)
        d_1_ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(path)
        d_1_ancestors__ok_ = out0_
        r = Result_Ok((d_0_is__dir_) and (d_1_ancestors__ok_))
        return r

    def AncestorsTraversableCheck(self, path):
        result: bool = False
        result = True
        if (len(path)) <= (2):
            return result
        d_0_i_: int
        d_0_i_ = 1
        with _dafny.label("0"):
            while (d_0_i_) < ((len(path)) - (1)):
                with _dafny.c_label("0"):
                    if ((path)[d_0_i_]) == (_dafny.CodePoint('/')):
                        d_1_prefix_: _dafny.Seq
                        d_1_prefix_ = _dafny.SeqWithoutIsStrInference((path)[:d_0_i_:])
                        if ((d_1_prefix_) in (self.fs)) and (((self.fs)[d_1_prefix_]).is_FileEntry):
                            result = False
                            raise _dafny.Break("0")
                    d_0_i_ = (d_0_i_) + (1)
                    pass
            pass
        return result

    def Read(self, path):
        r: Result = Result.default()()
        if (path) in (self.fs):
            source0_ = (self.fs)[path]
            with _dafny.label("match0"):
                if True:
                    if source0_.is_FileEntry:
                        d_0_content_ = source0_.content
                        r = Result_Ok(ReadStream_ReadStream(d_0_content_, True))
                        raise _dafny.Break("match0")
                if True:
                    r = Result_Err(Error_InvalidPath(path, (self).name))
                pass
        elif True:
            r = Result_Err(Error_NotFound(path, (self).name))
        return r

    def EnsureParents(self, path):
        d_0_i_: int
        d_0_i_ = 1
        while (d_0_i_) < (len(path)):
            if ((path)[d_0_i_]) == (_dafny.CodePoint('/')):
                d_1_prefix_: _dafny.Seq
                d_1_prefix_ = _dafny.SeqWithoutIsStrInference((path)[:d_0_i_:])
                if (d_1_prefix_) not in (self.fs):
                    (self).fs = (self.fs).set(d_1_prefix_, Entry_DirEntry())
                elif True:
                    pass
            d_0_i_ = (d_0_i_) + (1)

    def Write(self, path, content, overwrite, metadata):
        r: Result = Result.default()()
        if ((path) in (self.fs)) and (((self.fs)[path]).is_DirEntry):
            r = Result_Err(Error_InvalidPath(path, (self).name))
            return r
        if (((path) in (self.fs)) and (((self.fs)[path]).is_FileEntry)) and (not(overwrite)):
            r = Result_Err(Error_AlreadyExists(path, (self).name))
            return r
        d_0_ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(path)
        d_0_ancestors__ok_ = out0_
        if not(d_0_ancestors__ok_):
            r = Result_Err(Error_InvalidPath(path, (self).name))
            return r
        if (default__.HasUserMetadata(metadata)) and ((Capability_CapUserMetadata()) not in ((self).capabilities)):
            r = Result_Err(Error_CapabilityNotSupported(default__.CapabilityName(Capability_CapUserMetadata()), (self).name))
            return r
        (self).EnsureParents(path)
        d_1_stored__metadata_: Option
        if (default__.HasUserMetadata(metadata)) and ((Capability_CapUserMetadata()) in ((self).capabilities)):
            d_1_stored__metadata_ = metadata
        elif True:
            d_1_stored__metadata_ = Option_None()
        d_2_ts_: Option
        if (Capability_CapWriteResultNative()) in ((self).capabilities):
            d_2_ts_ = Option_Some(0)
        elif True:
            d_2_ts_ = Option_None()
        d_3_info_: FileInfo
        d_3_info_ = FileInfo_FileInfo(path, path, len(content), Option_None(), Option_None(), d_2_ts_, d_1_stored__metadata_)
        (self).fs = (self.fs).set(path, Entry_FileEntry(content, d_3_info_))
        d_4_wr__source_: WriteSource
        if (Capability_CapWriteResultNative()) in ((self).capabilities):
            d_4_wr__source_ = WriteSource_NativeSource()
        elif True:
            d_4_wr__source_ = WriteSource_BasicSource()
        r = Result_Ok(WriteResult_WriteResult(path, len(content), Option_None(), Option_None(), Option_None(), d_2_ts_, d_1_stored__metadata_, d_4_wr__source_))
        return r

    def Delete(self, path, missing__ok):
        r: Result = Result.default()()
        if (path) in (self.fs):
            source0_ = (self.fs)[path]
            with _dafny.label("match0"):
                if True:
                    if source0_.is_DirEntry:
                        r = Result_Err(Error_InvalidPath(path, (self).name))
                        raise _dafny.Break("match0")
                if True:
                    def iife0_():
                        coll0_ = _dafny.Map()
                        compr_0_: _dafny.Seq
                        for compr_0_ in (self.fs).keys.Elements:
                            d_0_k_: _dafny.Seq = compr_0_
                            if Path._Is(d_0_k_):
                                if ((d_0_k_) in (self.fs)) and ((d_0_k_) != (path)):
                                    coll0_[d_0_k_] = (self.fs)[d_0_k_]
                        return _dafny.Map(coll0_)
                    (self).fs = iife0_()
                    
                    r = Result_Ok(())
                pass
        elif True:
            if missing__ok:
                r = Result_Ok(())
            elif True:
                r = Result_Err(Error_NotFound(path, (self).name))
        return r

    def DeleteFolder(self, path, recursive, missing__ok):
        r: Result = Result.default()()
        if ((path) in (self.fs)) and (((self.fs)[path]).is_FileEntry):
            r = Result_Err(Error_InvalidPath(path, (self).name))
            return r
        if not(((path) in (self.fs)) and (((self.fs)[path]).is_DirEntry)):
            if missing__ok:
                r = Result_Ok(())
            elif True:
                r = Result_Err(Error_NotFound(path, (self).name))
            return r
        if (not(recursive)) and (default__.HasChildren(self.fs, path)):
            r = Result_Err(Error_DirectoryNotEmpty(path, (self).name))
            return r
        if recursive:
            def iife0_():
                coll0_ = _dafny.Map()
                compr_0_: _dafny.Seq
                for compr_0_ in (self.fs).keys.Elements:
                    d_0_k_: _dafny.Seq = compr_0_
                    if Path._Is(d_0_k_):
                        if (((d_0_k_) in (self.fs)) and ((d_0_k_) != (path))) and (not(default__.IsChildOf(d_0_k_, path))):
                            coll0_[d_0_k_] = (self.fs)[d_0_k_]
                return _dafny.Map(coll0_)
            (self).fs = iife0_()
            
        elif True:
            def iife1_():
                coll1_ = _dafny.Map()
                compr_1_: _dafny.Seq
                for compr_1_ in (self.fs).keys.Elements:
                    d_1_k_: _dafny.Seq = compr_1_
                    if Path._Is(d_1_k_):
                        if ((d_1_k_) in (self.fs)) and ((d_1_k_) != (path)):
                            coll1_[d_1_k_] = (self.fs)[d_1_k_]
                return _dafny.Map(coll1_)
            (self).fs = iife1_()
            
        r = Result_Ok(())
        return r

    def ListFiles(self, path, recursive, max__depth):
        r: Result = Result.default()()
        d_0_ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(path)
        d_0_ancestors__ok_ = out0_
        if ((path) not in (self.fs)) or (not(d_0_ancestors__ok_)):
            r = Result_Ok(_dafny.SeqWithoutIsStrInference([]))
            return r
        d_1_result_: _dafny.Seq
        d_1_result_ = _dafny.SeqWithoutIsStrInference([])
        d_2_remaining_: _dafny.Set
        d_2_remaining_ = (self.fs).keys
        while (d_2_remaining_) != (_dafny.Set({})):
            d_3_k_: _dafny.Seq
            with _dafny.label("_ASSIGN_SUCH_THAT_d_0"):
                assign_such_that_0_: _dafny.Seq
                for assign_such_that_0_ in (d_2_remaining_).Elements:
                    d_3_k_ = assign_such_that_0_
                    if Path._Is(d_3_k_):
                        if (d_3_k_) in (d_2_remaining_):
                            raise _dafny.Break("_ASSIGN_SUCH_THAT_d_0")
                raise Exception("assign-such-that search produced no value")
                pass
            d_2_remaining_ = (d_2_remaining_) - (_dafny.Set({d_3_k_}))
            if (((d_3_k_) in (self.fs)) and (((self.fs)[d_3_k_]).is_FileEntry)) and (default__.IsChildOf(d_3_k_, path)):
                d_4_d_: int
                d_4_d_ = default__.Depth(path, d_3_k_)
                d_5_dominated_: bool
                if not(recursive):
                    d_5_dominated_ = (d_4_d_) == (0)
                elif (max__depth) >= (0):
                    d_5_dominated_ = (d_4_d_) <= (max__depth)
                elif True:
                    d_5_dominated_ = True
                if d_5_dominated_:
                    d_6_fi_: FileInfo
                    d_6_fi_ = default__.BasicFileInfo(d_3_k_, d_3_k_, len(((self.fs)[d_3_k_]).content))
                    d_1_result_ = (d_1_result_) + (_dafny.SeqWithoutIsStrInference([d_6_fi_]))
        r = Result_Ok(d_1_result_)
        return r

    def ListFolders(self, path):
        r: Result = Result.default()()
        d_0_ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(path)
        d_0_ancestors__ok_ = out0_
        if ((path) not in (self.fs)) or (not(d_0_ancestors__ok_)):
            r = Result_Ok(_dafny.SeqWithoutIsStrInference([]))
            return r
        d_1_result_: _dafny.Seq
        d_1_result_ = _dafny.SeqWithoutIsStrInference([])
        d_2_remaining_: _dafny.Set
        d_2_remaining_ = (self.fs).keys
        while (d_2_remaining_) != (_dafny.Set({})):
            d_3_k_: _dafny.Seq
            with _dafny.label("_ASSIGN_SUCH_THAT_d_0"):
                assign_such_that_0_: _dafny.Seq
                for assign_such_that_0_ in (d_2_remaining_).Elements:
                    d_3_k_ = assign_such_that_0_
                    if Path._Is(d_3_k_):
                        if (d_3_k_) in (d_2_remaining_):
                            raise _dafny.Break("_ASSIGN_SUCH_THAT_d_0")
                raise Exception("assign-such-that search produced no value")
                pass
            d_2_remaining_ = (d_2_remaining_) - (_dafny.Set({d_3_k_}))
            if (((d_3_k_) in (self.fs)) and (((self.fs)[d_3_k_]).is_DirEntry)) and (default__.IsChildOf(d_3_k_, path)):
                d_4_fe_: FolderEntry
                d_4_fe_ = FolderEntry_FolderEntry(d_3_k_, d_3_k_)
                d_1_result_ = (d_1_result_) + (_dafny.SeqWithoutIsStrInference([d_4_fe_]))
        r = Result_Ok(d_1_result_)
        return r

    def GetFileInfo(self, path):
        r: Result = Result.default()()
        if (path) in (self.fs):
            source0_ = (self.fs)[path]
            with _dafny.label("match0"):
                if True:
                    if source0_.is_FileEntry:
                        d_0_info_ = source0_.info
                        r = Result_Ok(d_0_info_)
                        raise _dafny.Break("match0")
                if True:
                    r = Result_Err(Error_InvalidPath(path, (self).name))
                pass
        elif True:
            r = Result_Err(Error_NotFound(path, (self).name))
        return r

    def GetFolderInfo(self, path):
        r: Result = Result.default()()
        if (path) in (self.fs):
            source0_ = (self.fs)[path]
            with _dafny.label("match0"):
                if True:
                    if source0_.is_DirEntry:
                        d_0_file__count_: int
                        d_0_file__count_ = 0
                        d_1_total__size_: int
                        d_1_total__size_ = 0
                        d_2_remaining_: _dafny.Set
                        d_2_remaining_ = (self.fs).keys
                        while (d_2_remaining_) != (_dafny.Set({})):
                            d_3_k_: _dafny.Seq
                            with _dafny.label("_ASSIGN_SUCH_THAT_d_0"):
                                assign_such_that_0_: _dafny.Seq
                                for assign_such_that_0_ in (d_2_remaining_).Elements:
                                    d_3_k_ = assign_such_that_0_
                                    if Path._Is(d_3_k_):
                                        if (d_3_k_) in (d_2_remaining_):
                                            raise _dafny.Break("_ASSIGN_SUCH_THAT_d_0")
                                raise Exception("assign-such-that search produced no value")
                                pass
                            d_2_remaining_ = (d_2_remaining_) - (_dafny.Set({d_3_k_}))
                            if (((d_3_k_) in (self.fs)) and (((self.fs)[d_3_k_]).is_FileEntry)) and (default__.IsChildOf(d_3_k_, path)):
                                d_0_file__count_ = (d_0_file__count_) + (1)
                                d_1_total__size_ = (d_1_total__size_) + ((((self.fs)[d_3_k_]).info).size)
                        r = Result_Ok(FolderInfo_FolderInfo(path, path, d_0_file__count_, d_1_total__size_))
                        raise _dafny.Break("match0")
                if True:
                    r = Result_Err(Error_InvalidPath(path, (self).name))
                pass
        elif True:
            r = Result_Err(Error_NotFound(path, (self).name))
        return r

    def Move(self, src, dst, overwrite):
        r: Result = Result.default()()
        if ((src) in (self.fs)) and (((self.fs)[src]).is_DirEntry):
            r = Result_Err(Error_InvalidPath(src, (self).name))
            return r
        if not(((src) in (self.fs)) and (((self.fs)[src]).is_FileEntry)):
            r = Result_Err(Error_NotFound(src, (self).name))
            return r
        if ((dst) in (self.fs)) and (((self.fs)[dst]).is_DirEntry):
            r = Result_Err(Error_InvalidPath(dst, (self).name))
            return r
        if (src) == (dst):
            r = Result_Ok(())
            return r
        d_0_dst__ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(dst)
        d_0_dst__ancestors__ok_ = out0_
        if not(d_0_dst__ancestors__ok_):
            r = Result_Err(Error_InvalidPath(dst, (self).name))
            return r
        if (((dst) in (self.fs)) and (((self.fs)[dst]).is_FileEntry)) and (not(overwrite)):
            r = Result_Err(Error_AlreadyExists(dst, (self).name))
            return r
        d_1_srcEntry_: Entry
        d_1_srcEntry_ = (self.fs)[src]
        (self).EnsureParents(dst)
        d_2_newInfo_: FileInfo
        d_2_newInfo_ = FileInfo_FileInfo(dst, dst, ((d_1_srcEntry_).info).size, Option_None(), Option_None(), Option_None(), ((d_1_srcEntry_).info).metadata)
        d_3_newEntry_: Entry
        d_3_newEntry_ = Entry_FileEntry((d_1_srcEntry_).content, d_2_newInfo_)
        def iife0_():
            coll0_ = _dafny.Map()
            compr_0_: _dafny.Seq
            for compr_0_ in (self.fs).keys.Elements:
                d_4_k_: _dafny.Seq = compr_0_
                if Path._Is(d_4_k_):
                    if ((d_4_k_) in (self.fs)) and ((d_4_k_) != (src)):
                        coll0_[d_4_k_] = (self.fs)[d_4_k_]
            return _dafny.Map(coll0_)
        (self).fs = iife0_()
        
        (self).fs = (self.fs).set(dst, d_3_newEntry_)
        r = Result_Ok(())
        return r

    def Copy(self, src, dst, overwrite):
        r: Result = Result.default()()
        if ((src) in (self.fs)) and (((self.fs)[src]).is_DirEntry):
            r = Result_Err(Error_InvalidPath(src, (self).name))
            return r
        if not(((src) in (self.fs)) and (((self.fs)[src]).is_FileEntry)):
            r = Result_Err(Error_NotFound(src, (self).name))
            return r
        if ((dst) in (self.fs)) and (((self.fs)[dst]).is_DirEntry):
            r = Result_Err(Error_InvalidPath(dst, (self).name))
            return r
        if (src) == (dst):
            r = Result_Ok(())
            return r
        d_0_dst__ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(dst)
        d_0_dst__ancestors__ok_ = out0_
        if not(d_0_dst__ancestors__ok_):
            r = Result_Err(Error_InvalidPath(dst, (self).name))
            return r
        if (((dst) in (self.fs)) and (((self.fs)[dst]).is_FileEntry)) and (not(overwrite)):
            r = Result_Err(Error_AlreadyExists(dst, (self).name))
            return r
        d_1_srcEntry_: Entry
        d_1_srcEntry_ = (self.fs)[src]
        (self).EnsureParents(dst)
        d_2_newInfo_: FileInfo
        d_2_newInfo_ = FileInfo_FileInfo(dst, dst, ((d_1_srcEntry_).info).size, Option_None(), Option_None(), Option_None(), ((d_1_srcEntry_).info).metadata)
        (self).fs = (self.fs).set(dst, Entry_FileEntry((d_1_srcEntry_).content, d_2_newInfo_))
        r = Result_Ok(())
        return r

    def RequireCapability(self, cap):
        r: Result = Result.default()()
        if (cap) in ((self).capabilities):
            r = Result_Ok(())
        elif True:
            r = Result_Err(Error_CapabilityNotSupported(default__.CapabilityName(cap), (self).name))
        return r


class MemoryBackendMinimal(Backend):
    def  __init__(self):
        self._fs: _dafny.Map = _dafny.Map({})
        self._name: _dafny.Seq = _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, ""))
        self._capabilities: _dafny.Set = _dafny.Set({})
        pass

    def __dafnystr__(self) -> str:
        return "_module.MemoryBackendMinimal"
    @property
    def fs(self):
        return self._fs
    @fs.setter
    def fs(self, value):
        self._fs = value
    def Valid(self):
        return Backend.Valid(self)

    @property
    def name(self):
        return self._name
    @property
    def capabilities(self):
        return self._capabilities
    def ctor__(self):
        (self)._name = _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "memory-minimal"))
        (self)._capabilities = _dafny.Set({Capability_CapRead(), Capability_CapWrite(), Capability_CapDelete(), Capability_CapList(), Capability_CapMove(), Capability_CapCopy(), Capability_CapAtomicWrite(), Capability_CapAtomicMove(), Capability_CapMetadata(), Capability_CapSeekableRead()})
        (self).fs = _dafny.Map({default__.Root: Entry_DirEntry()})

    def Exists(self, path):
        r: Result = Result.default()()
        d_0_path__exists_: bool
        d_0_path__exists_ = (path) in (self.fs)
        d_1_ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(path)
        d_1_ancestors__ok_ = out0_
        r = Result_Ok((d_0_path__exists_) and (d_1_ancestors__ok_))
        return r

    def IsFileMethod(self, path):
        r: Result = Result.default()()
        d_0_is__file_: bool
        d_0_is__file_ = ((path) in (self.fs)) and (((self.fs)[path]).is_FileEntry)
        d_1_ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(path)
        d_1_ancestors__ok_ = out0_
        r = Result_Ok((d_0_is__file_) and (d_1_ancestors__ok_))
        return r

    def IsFolderMethod(self, path):
        r: Result = Result.default()()
        d_0_is__dir_: bool
        d_0_is__dir_ = ((path) in (self.fs)) and (((self.fs)[path]).is_DirEntry)
        d_1_ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(path)
        d_1_ancestors__ok_ = out0_
        r = Result_Ok((d_0_is__dir_) and (d_1_ancestors__ok_))
        return r

    def AncestorsTraversableCheck(self, path):
        result: bool = False
        result = True
        if (len(path)) <= (2):
            return result
        d_0_i_: int
        d_0_i_ = 1
        with _dafny.label("0"):
            while (d_0_i_) < ((len(path)) - (1)):
                with _dafny.c_label("0"):
                    if ((path)[d_0_i_]) == (_dafny.CodePoint('/')):
                        d_1_prefix_: _dafny.Seq
                        d_1_prefix_ = _dafny.SeqWithoutIsStrInference((path)[:d_0_i_:])
                        if ((d_1_prefix_) in (self.fs)) and (((self.fs)[d_1_prefix_]).is_FileEntry):
                            result = False
                            raise _dafny.Break("0")
                    d_0_i_ = (d_0_i_) + (1)
                    pass
            pass
        return result

    def Read(self, path):
        r: Result = Result.default()()
        if (path) in (self.fs):
            source0_ = (self.fs)[path]
            with _dafny.label("match0"):
                if True:
                    if source0_.is_FileEntry:
                        d_0_content_ = source0_.content
                        r = Result_Ok(ReadStream_ReadStream(d_0_content_, True))
                        raise _dafny.Break("match0")
                if True:
                    r = Result_Err(Error_InvalidPath(path, (self).name))
                pass
        elif True:
            r = Result_Err(Error_NotFound(path, (self).name))
        return r

    def EnsureParents(self, path):
        d_0_i_: int
        d_0_i_ = 1
        while (d_0_i_) < (len(path)):
            if ((path)[d_0_i_]) == (_dafny.CodePoint('/')):
                d_1_prefix_: _dafny.Seq
                d_1_prefix_ = _dafny.SeqWithoutIsStrInference((path)[:d_0_i_:])
                if (d_1_prefix_) not in (self.fs):
                    (self).fs = (self.fs).set(d_1_prefix_, Entry_DirEntry())
                elif True:
                    pass
            d_0_i_ = (d_0_i_) + (1)

    def Write(self, path, content, overwrite, metadata):
        r: Result = Result.default()()
        if ((path) in (self.fs)) and (((self.fs)[path]).is_DirEntry):
            r = Result_Err(Error_InvalidPath(path, (self).name))
            return r
        if (((path) in (self.fs)) and (((self.fs)[path]).is_FileEntry)) and (not(overwrite)):
            r = Result_Err(Error_AlreadyExists(path, (self).name))
            return r
        d_0_ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(path)
        d_0_ancestors__ok_ = out0_
        if not(d_0_ancestors__ok_):
            r = Result_Err(Error_InvalidPath(path, (self).name))
            return r
        if (default__.HasUserMetadata(metadata)) and ((Capability_CapUserMetadata()) not in ((self).capabilities)):
            r = Result_Err(Error_CapabilityNotSupported(default__.CapabilityName(Capability_CapUserMetadata()), (self).name))
            return r
        (self).EnsureParents(path)
        d_1_stored__metadata_: Option
        if (default__.HasUserMetadata(metadata)) and ((Capability_CapUserMetadata()) in ((self).capabilities)):
            d_1_stored__metadata_ = metadata
        elif True:
            d_1_stored__metadata_ = Option_None()
        d_2_info_: FileInfo
        d_2_info_ = FileInfo_FileInfo(path, path, len(content), Option_None(), Option_None(), Option_None(), d_1_stored__metadata_)
        (self).fs = (self.fs).set(path, Entry_FileEntry(content, d_2_info_))
        d_3_wr__source_: WriteSource
        if (Capability_CapWriteResultNative()) in ((self).capabilities):
            d_3_wr__source_ = WriteSource_NativeSource()
        elif True:
            d_3_wr__source_ = WriteSource_BasicSource()
        r = Result_Ok(WriteResult_WriteResult(path, len(content), Option_None(), Option_None(), Option_None(), Option_None(), d_1_stored__metadata_, d_3_wr__source_))
        return r

    def Delete(self, path, missing__ok):
        r: Result = Result.default()()
        if (path) in (self.fs):
            source0_ = (self.fs)[path]
            with _dafny.label("match0"):
                if True:
                    if source0_.is_DirEntry:
                        r = Result_Err(Error_InvalidPath(path, (self).name))
                        raise _dafny.Break("match0")
                if True:
                    def iife0_():
                        coll0_ = _dafny.Map()
                        compr_0_: _dafny.Seq
                        for compr_0_ in (self.fs).keys.Elements:
                            d_0_k_: _dafny.Seq = compr_0_
                            if Path._Is(d_0_k_):
                                if ((d_0_k_) in (self.fs)) and ((d_0_k_) != (path)):
                                    coll0_[d_0_k_] = (self.fs)[d_0_k_]
                        return _dafny.Map(coll0_)
                    (self).fs = iife0_()
                    
                    r = Result_Ok(())
                pass
        elif True:
            if missing__ok:
                r = Result_Ok(())
            elif True:
                r = Result_Err(Error_NotFound(path, (self).name))
        return r

    def DeleteFolder(self, path, recursive, missing__ok):
        r: Result = Result.default()()
        if ((path) in (self.fs)) and (((self.fs)[path]).is_FileEntry):
            r = Result_Err(Error_InvalidPath(path, (self).name))
            return r
        if not(((path) in (self.fs)) and (((self.fs)[path]).is_DirEntry)):
            if missing__ok:
                r = Result_Ok(())
            elif True:
                r = Result_Err(Error_NotFound(path, (self).name))
            return r
        if (not(recursive)) and (default__.HasChildren(self.fs, path)):
            r = Result_Err(Error_DirectoryNotEmpty(path, (self).name))
            return r
        if recursive:
            def iife0_():
                coll0_ = _dafny.Map()
                compr_0_: _dafny.Seq
                for compr_0_ in (self.fs).keys.Elements:
                    d_0_k_: _dafny.Seq = compr_0_
                    if Path._Is(d_0_k_):
                        if (((d_0_k_) in (self.fs)) and ((d_0_k_) != (path))) and (not(default__.IsChildOf(d_0_k_, path))):
                            coll0_[d_0_k_] = (self.fs)[d_0_k_]
                return _dafny.Map(coll0_)
            (self).fs = iife0_()
            
        elif True:
            def iife1_():
                coll1_ = _dafny.Map()
                compr_1_: _dafny.Seq
                for compr_1_ in (self.fs).keys.Elements:
                    d_1_k_: _dafny.Seq = compr_1_
                    if Path._Is(d_1_k_):
                        if ((d_1_k_) in (self.fs)) and ((d_1_k_) != (path)):
                            coll1_[d_1_k_] = (self.fs)[d_1_k_]
                return _dafny.Map(coll1_)
            (self).fs = iife1_()
            
        r = Result_Ok(())
        return r

    def ListFiles(self, path, recursive, max__depth):
        r: Result = Result.default()()
        d_0_ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(path)
        d_0_ancestors__ok_ = out0_
        if ((path) not in (self.fs)) or (not(d_0_ancestors__ok_)):
            r = Result_Ok(_dafny.SeqWithoutIsStrInference([]))
            return r
        d_1_result_: _dafny.Seq
        d_1_result_ = _dafny.SeqWithoutIsStrInference([])
        d_2_remaining_: _dafny.Set
        d_2_remaining_ = (self.fs).keys
        while (d_2_remaining_) != (_dafny.Set({})):
            d_3_k_: _dafny.Seq
            with _dafny.label("_ASSIGN_SUCH_THAT_d_0"):
                assign_such_that_0_: _dafny.Seq
                for assign_such_that_0_ in (d_2_remaining_).Elements:
                    d_3_k_ = assign_such_that_0_
                    if Path._Is(d_3_k_):
                        if (d_3_k_) in (d_2_remaining_):
                            raise _dafny.Break("_ASSIGN_SUCH_THAT_d_0")
                raise Exception("assign-such-that search produced no value")
                pass
            d_2_remaining_ = (d_2_remaining_) - (_dafny.Set({d_3_k_}))
            if (((d_3_k_) in (self.fs)) and (((self.fs)[d_3_k_]).is_FileEntry)) and (default__.IsChildOf(d_3_k_, path)):
                d_4_d_: int
                d_4_d_ = default__.Depth(path, d_3_k_)
                d_5_dominated_: bool
                if not(recursive):
                    d_5_dominated_ = (d_4_d_) == (0)
                elif (max__depth) >= (0):
                    d_5_dominated_ = (d_4_d_) <= (max__depth)
                elif True:
                    d_5_dominated_ = True
                if d_5_dominated_:
                    d_6_fi_: FileInfo
                    d_6_fi_ = default__.BasicFileInfo(d_3_k_, d_3_k_, len(((self.fs)[d_3_k_]).content))
                    d_1_result_ = (d_1_result_) + (_dafny.SeqWithoutIsStrInference([d_6_fi_]))
        r = Result_Ok(d_1_result_)
        return r

    def ListFolders(self, path):
        r: Result = Result.default()()
        d_0_ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(path)
        d_0_ancestors__ok_ = out0_
        if ((path) not in (self.fs)) or (not(d_0_ancestors__ok_)):
            r = Result_Ok(_dafny.SeqWithoutIsStrInference([]))
            return r
        d_1_result_: _dafny.Seq
        d_1_result_ = _dafny.SeqWithoutIsStrInference([])
        d_2_remaining_: _dafny.Set
        d_2_remaining_ = (self.fs).keys
        while (d_2_remaining_) != (_dafny.Set({})):
            d_3_k_: _dafny.Seq
            with _dafny.label("_ASSIGN_SUCH_THAT_d_0"):
                assign_such_that_0_: _dafny.Seq
                for assign_such_that_0_ in (d_2_remaining_).Elements:
                    d_3_k_ = assign_such_that_0_
                    if Path._Is(d_3_k_):
                        if (d_3_k_) in (d_2_remaining_):
                            raise _dafny.Break("_ASSIGN_SUCH_THAT_d_0")
                raise Exception("assign-such-that search produced no value")
                pass
            d_2_remaining_ = (d_2_remaining_) - (_dafny.Set({d_3_k_}))
            if (((d_3_k_) in (self.fs)) and (((self.fs)[d_3_k_]).is_DirEntry)) and (default__.IsChildOf(d_3_k_, path)):
                d_4_fe_: FolderEntry
                d_4_fe_ = FolderEntry_FolderEntry(d_3_k_, d_3_k_)
                d_1_result_ = (d_1_result_) + (_dafny.SeqWithoutIsStrInference([d_4_fe_]))
        r = Result_Ok(d_1_result_)
        return r

    def GetFileInfo(self, path):
        r: Result = Result.default()()
        if (path) in (self.fs):
            source0_ = (self.fs)[path]
            with _dafny.label("match0"):
                if True:
                    if source0_.is_FileEntry:
                        d_0_info_ = source0_.info
                        r = Result_Ok(d_0_info_)
                        raise _dafny.Break("match0")
                if True:
                    r = Result_Err(Error_InvalidPath(path, (self).name))
                pass
        elif True:
            r = Result_Err(Error_NotFound(path, (self).name))
        return r

    def GetFolderInfo(self, path):
        r: Result = Result.default()()
        if (path) in (self.fs):
            source0_ = (self.fs)[path]
            with _dafny.label("match0"):
                if True:
                    if source0_.is_DirEntry:
                        d_0_file__count_: int
                        d_0_file__count_ = 0
                        d_1_total__size_: int
                        d_1_total__size_ = 0
                        d_2_remaining_: _dafny.Set
                        d_2_remaining_ = (self.fs).keys
                        while (d_2_remaining_) != (_dafny.Set({})):
                            d_3_k_: _dafny.Seq
                            with _dafny.label("_ASSIGN_SUCH_THAT_d_0"):
                                assign_such_that_0_: _dafny.Seq
                                for assign_such_that_0_ in (d_2_remaining_).Elements:
                                    d_3_k_ = assign_such_that_0_
                                    if Path._Is(d_3_k_):
                                        if (d_3_k_) in (d_2_remaining_):
                                            raise _dafny.Break("_ASSIGN_SUCH_THAT_d_0")
                                raise Exception("assign-such-that search produced no value")
                                pass
                            d_2_remaining_ = (d_2_remaining_) - (_dafny.Set({d_3_k_}))
                            if (((d_3_k_) in (self.fs)) and (((self.fs)[d_3_k_]).is_FileEntry)) and (default__.IsChildOf(d_3_k_, path)):
                                d_0_file__count_ = (d_0_file__count_) + (1)
                                d_1_total__size_ = (d_1_total__size_) + ((((self.fs)[d_3_k_]).info).size)
                        r = Result_Ok(FolderInfo_FolderInfo(path, path, d_0_file__count_, d_1_total__size_))
                        raise _dafny.Break("match0")
                if True:
                    r = Result_Err(Error_InvalidPath(path, (self).name))
                pass
        elif True:
            r = Result_Err(Error_NotFound(path, (self).name))
        return r

    def Move(self, src, dst, overwrite):
        r: Result = Result.default()()
        if ((src) in (self.fs)) and (((self.fs)[src]).is_DirEntry):
            r = Result_Err(Error_InvalidPath(src, (self).name))
            return r
        if not(((src) in (self.fs)) and (((self.fs)[src]).is_FileEntry)):
            r = Result_Err(Error_NotFound(src, (self).name))
            return r
        if ((dst) in (self.fs)) and (((self.fs)[dst]).is_DirEntry):
            r = Result_Err(Error_InvalidPath(dst, (self).name))
            return r
        if (src) == (dst):
            r = Result_Ok(())
            return r
        d_0_dst__ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(dst)
        d_0_dst__ancestors__ok_ = out0_
        if not(d_0_dst__ancestors__ok_):
            r = Result_Err(Error_InvalidPath(dst, (self).name))
            return r
        if (((dst) in (self.fs)) and (((self.fs)[dst]).is_FileEntry)) and (not(overwrite)):
            r = Result_Err(Error_AlreadyExists(dst, (self).name))
            return r
        d_1_srcEntry_: Entry
        d_1_srcEntry_ = (self.fs)[src]
        (self).EnsureParents(dst)
        d_2_newInfo_: FileInfo
        d_2_newInfo_ = FileInfo_FileInfo(dst, dst, ((d_1_srcEntry_).info).size, Option_None(), Option_None(), Option_None(), ((d_1_srcEntry_).info).metadata)
        d_3_newEntry_: Entry
        d_3_newEntry_ = Entry_FileEntry((d_1_srcEntry_).content, d_2_newInfo_)
        def iife0_():
            coll0_ = _dafny.Map()
            compr_0_: _dafny.Seq
            for compr_0_ in (self.fs).keys.Elements:
                d_4_k_: _dafny.Seq = compr_0_
                if Path._Is(d_4_k_):
                    if ((d_4_k_) in (self.fs)) and ((d_4_k_) != (src)):
                        coll0_[d_4_k_] = (self.fs)[d_4_k_]
            return _dafny.Map(coll0_)
        (self).fs = iife0_()
        
        (self).fs = (self.fs).set(dst, d_3_newEntry_)
        r = Result_Ok(())
        return r

    def Copy(self, src, dst, overwrite):
        r: Result = Result.default()()
        if ((src) in (self.fs)) and (((self.fs)[src]).is_DirEntry):
            r = Result_Err(Error_InvalidPath(src, (self).name))
            return r
        if not(((src) in (self.fs)) and (((self.fs)[src]).is_FileEntry)):
            r = Result_Err(Error_NotFound(src, (self).name))
            return r
        if ((dst) in (self.fs)) and (((self.fs)[dst]).is_DirEntry):
            r = Result_Err(Error_InvalidPath(dst, (self).name))
            return r
        if (src) == (dst):
            r = Result_Ok(())
            return r
        d_0_dst__ancestors__ok_: bool
        out0_: bool
        out0_ = (self).AncestorsTraversableCheck(dst)
        d_0_dst__ancestors__ok_ = out0_
        if not(d_0_dst__ancestors__ok_):
            r = Result_Err(Error_InvalidPath(dst, (self).name))
            return r
        if (((dst) in (self.fs)) and (((self.fs)[dst]).is_FileEntry)) and (not(overwrite)):
            r = Result_Err(Error_AlreadyExists(dst, (self).name))
            return r
        d_1_srcEntry_: Entry
        d_1_srcEntry_ = (self.fs)[src]
        (self).EnsureParents(dst)
        d_2_newInfo_: FileInfo
        d_2_newInfo_ = FileInfo_FileInfo(dst, dst, ((d_1_srcEntry_).info).size, Option_None(), Option_None(), Option_None(), ((d_1_srcEntry_).info).metadata)
        (self).fs = (self.fs).set(dst, Entry_FileEntry((d_1_srcEntry_).content, d_2_newInfo_))
        r = Result_Ok(())
        return r

    def RequireCapability(self, cap):
        r: Result = Result.default()()
        if (cap) in ((self).capabilities):
            r = Result_Ok(())
        elif True:
            r = Result_Err(Error_CapabilityNotSupported(default__.CapabilityName(cap), (self).name))
        return r


