from typing import Any, NamedTuple

import _dafny as _dafny
import module_ as module_
import System_ as System_

# Module: module_


class default__:
    def __init__(self):
        pass

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
                    d_0___accumulator_ = (d_0___accumulator_) + (1 if ((p)[0]) == (_dafny.CodePoint("/")) else 0)
                    in0_ = _dafny.SeqWithoutIsStrInference((p)[1::])
                    p = in0_
                    raise _dafny.TailCall()
                break

    @staticmethod
    def Depth(root, child):
        if (
            (len(child)) <= ((len(root)) + (1))
            or (_dafny.SeqWithoutIsStrInference((child)[: len(root) :])) != (root)
            or ((child)[len(root)]) != (_dafny.CodePoint("/"))
        ):
            return -1
        elif True:
            d_0_suffix_ = _dafny.SeqWithoutIsStrInference((child)[(len(root)) + (1) : :])
            return default__.SlashCount(d_0_suffix_)

    @staticmethod
    def IsChildOf(child, parent):
        return (
            ((len(child)) > ((len(parent)) + (1)))
            and ((_dafny.SeqWithoutIsStrInference((child)[: len(parent) :])) == (parent))
        ) and (((child)[len(parent)]) == (_dafny.CodePoint("/")))

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
            return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "seekable_read"))


class MemoryBackend(Backend):
    def __init__(self):
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

    @property
    def name(self):
        return self._name

    @property
    def capabilities(self):
        return self._capabilities

    def ctor__(self):
        (self)._name = _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "memory"))
        (self)._capabilities = _dafny.Set(
            {
                Capability_CapRead(),
                Capability_CapWrite(),
                Capability_CapDelete(),
                Capability_CapList(),
                Capability_CapMove(),
                Capability_CapCopy(),
                Capability_CapAtomicWrite(),
                Capability_CapAtomicMove(),
                Capability_CapMetadata(),
                Capability_CapSeekableRead(),
            }
        )
        (self).fs = _dafny.Map({})

    def Exists(self, path):
        r: Result = Result.default()()
        r = Result_Ok((path) in (self.fs))
        return r

    def Read(self, path):
        r: Result = Result.default()()
        if (path) in (self.fs):
            source0_ = (self.fs)[path]
            with _dafny.label("match0"):
                if True:
                    if source0_.is_FileEntry:
                        d_0_content_ = source0_.content
                        r = Result_Ok(d_0_content_)
                        raise _dafny.Break("match0")
                if True:
                    r = Result_Err(Error_InvalidPath(path, (self).name))
                pass
        elif True:
            r = Result_Err(Error_NotFound(path, (self).name))
        return r

    def Write(self, path, content, overwrite):
        r: Result = Result.default()()
        if ((path) in (self.fs)) and (((self.fs)[path]).is_DirEntry):
            r = Result_Err(Error_InvalidPath(path, (self).name))
            return r
        if (((path) in (self.fs)) and (((self.fs)[path]).is_FileEntry)) and (not (overwrite)):
            r = Result_Err(Error_AlreadyExists(path, (self).name))
            return r
        d_0_info_: FileInfo
        d_0_info_ = FileInfo_FileInfo(path, path, len(content))
        (self).fs = (self.fs).set(path, Entry_FileEntry(content, d_0_info_))
        r = Result_Ok(())
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
        if not (((path) in (self.fs)) and (((self.fs)[path]).is_DirEntry)):
            if missing__ok:
                r = Result_Ok(())
            elif True:
                r = Result_Err(Error_NotFound(path, (self).name))
            return r
        if (not (recursive)) and (default__.HasChildren(self.fs, path)):
            r = Result_Err(Error_DirectoryNotEmpty(path, (self).name))
            return r
        if recursive:

            def iife0_():
                coll0_ = _dafny.Map()
                compr_0_: _dafny.Seq
                for compr_0_ in (self.fs).keys.Elements:
                    d_0_k_: _dafny.Seq = compr_0_
                    if Path._Is(d_0_k_):
                        if (((d_0_k_) in (self.fs)) and ((d_0_k_) != (path))) and (
                            not (default__.IsChildOf(d_0_k_, path))
                        ):
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
        if (path) not in (self.fs):
            r = Result_Ok(_dafny.SeqWithoutIsStrInference([]))
            return r
        d_0_result_: _dafny.Seq
        d_0_result_ = _dafny.SeqWithoutIsStrInference([])
        d_1_remaining_: _dafny.Set
        d_1_remaining_ = (self.fs).keys
        while (d_1_remaining_) != (_dafny.Set({})):
            d_2_k_: _dafny.Seq
            with _dafny.label("_ASSIGN_SUCH_THAT_d_0"):
                assign_such_that_0_: _dafny.Seq
                for assign_such_that_0_ in (d_1_remaining_).Elements:
                    d_2_k_ = assign_such_that_0_
                    if Path._Is(d_2_k_):
                        if (d_2_k_) in (d_1_remaining_):
                            raise _dafny.Break("_ASSIGN_SUCH_THAT_d_0")
                raise Exception("assign-such-that search produced no value")
                pass
            d_1_remaining_ = (d_1_remaining_) - (_dafny.Set({d_2_k_}))
            if (((d_2_k_) in (self.fs)) and (((self.fs)[d_2_k_]).is_FileEntry)) and (default__.IsChildOf(d_2_k_, path)):
                d_3_d_: int
                d_3_d_ = default__.Depth(path, d_2_k_)
                d_4_dominated_: bool
                if not (recursive):
                    d_4_dominated_ = (d_3_d_) == (0)
                elif (max__depth) >= (0):
                    d_4_dominated_ = (d_3_d_) <= (max__depth)
                elif True:
                    d_4_dominated_ = True
                if d_4_dominated_:
                    d_5_fi_: FileInfo
                    d_5_fi_ = FileInfo_FileInfo(d_2_k_, d_2_k_, len(((self.fs)[d_2_k_]).content))
                    d_0_result_ = (d_0_result_) + (_dafny.SeqWithoutIsStrInference([d_5_fi_]))
        r = Result_Ok(d_0_result_)
        return r

    def ListFolders(self, path):
        r: Result = Result.default()()
        if (path) not in (self.fs):
            r = Result_Ok(_dafny.SeqWithoutIsStrInference([]))
            return r
        d_0_result_: _dafny.Seq
        d_0_result_ = _dafny.SeqWithoutIsStrInference([])
        d_1_remaining_: _dafny.Set
        d_1_remaining_ = (self.fs).keys
        while (d_1_remaining_) != (_dafny.Set({})):
            d_2_k_: _dafny.Seq
            with _dafny.label("_ASSIGN_SUCH_THAT_d_0"):
                assign_such_that_0_: _dafny.Seq
                for assign_such_that_0_ in (d_1_remaining_).Elements:
                    d_2_k_ = assign_such_that_0_
                    if Path._Is(d_2_k_):
                        if (d_2_k_) in (d_1_remaining_):
                            raise _dafny.Break("_ASSIGN_SUCH_THAT_d_0")
                raise Exception("assign-such-that search produced no value")
                pass
            d_1_remaining_ = (d_1_remaining_) - (_dafny.Set({d_2_k_}))
            if (((d_2_k_) in (self.fs)) and (((self.fs)[d_2_k_]).is_DirEntry)) and (default__.IsChildOf(d_2_k_, path)):
                d_3_fe_: FolderEntry
                d_3_fe_ = FolderEntry_FolderEntry(d_2_k_, d_2_k_)
                d_0_result_ = (d_0_result_) + (_dafny.SeqWithoutIsStrInference([d_3_fe_]))
        r = Result_Ok(d_0_result_)
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

    def Move(self, src, dst, overwrite):
        r: Result = Result.default()()
        if ((src) in (self.fs)) and (((self.fs)[src]).is_DirEntry):
            r = Result_Err(Error_InvalidPath(src, (self).name))
            return r
        if not (((src) in (self.fs)) and (((self.fs)[src]).is_FileEntry)):
            r = Result_Err(Error_NotFound(src, (self).name))
            return r
        if ((dst) in (self.fs)) and (((self.fs)[dst]).is_DirEntry):
            r = Result_Err(Error_InvalidPath(dst, (self).name))
            return r
        if (src) == (dst):
            r = Result_Ok(())
            return r
        if (((dst) in (self.fs)) and (((self.fs)[dst]).is_FileEntry)) and (not (overwrite)):
            r = Result_Err(Error_AlreadyExists(dst, (self).name))
            return r
        d_0_srcEntry_: Entry
        d_0_srcEntry_ = (self.fs)[src]
        d_1_newInfo_: FileInfo
        d_1_newInfo_ = FileInfo_FileInfo(dst, dst, ((d_0_srcEntry_).info).size)
        d_2_newEntry_: Entry
        d_2_newEntry_ = Entry_FileEntry((d_0_srcEntry_).content, d_1_newInfo_)

        def iife0_():
            coll0_ = _dafny.Map()
            compr_0_: _dafny.Seq
            for compr_0_ in (self.fs).keys.Elements:
                d_3_k_: _dafny.Seq = compr_0_
                if ((d_3_k_) in (self.fs)) and ((d_3_k_) != (src)):
                    coll0_[d_3_k_] = (self.fs)[d_3_k_]
            return _dafny.Map(coll0_)

        (self).fs = (iife0_()).set(dst, d_2_newEntry_)
        r = Result_Ok(())
        return r

    def Copy(self, src, dst, overwrite):
        r: Result = Result.default()()
        if ((src) in (self.fs)) and (((self.fs)[src]).is_DirEntry):
            r = Result_Err(Error_InvalidPath(src, (self).name))
            return r
        if not (((src) in (self.fs)) and (((self.fs)[src]).is_FileEntry)):
            r = Result_Err(Error_NotFound(src, (self).name))
            return r
        if ((dst) in (self.fs)) and (((self.fs)[dst]).is_DirEntry):
            r = Result_Err(Error_InvalidPath(dst, (self).name))
            return r
        if (src) == (dst):
            r = Result_Ok(())
            return r
        if (((dst) in (self.fs)) and (((self.fs)[dst]).is_FileEntry)) and (not (overwrite)):
            r = Result_Err(Error_AlreadyExists(dst, (self).name))
            return r
        d_0_srcEntry_: Entry
        d_0_srcEntry_ = (self.fs)[src]
        d_1_newInfo_: FileInfo
        d_1_newInfo_ = FileInfo_FileInfo(dst, dst, ((d_0_srcEntry_).info).size)
        (self).fs = (self.fs).set(dst, Entry_FileEntry((d_0_srcEntry_).content, d_1_newInfo_))
        r = Result_Ok(())
        return r

    def RequireCapability(self, cap):
        r: Result = Result.default()()
        if (cap) in ((self).capabilities):
            r = Result_Ok(())
        elif True:
            r = Result_Err(Error_CapabilityNotSupported(default__.CapabilityName(cap), (self).name))
        return r


class Error:
    @classmethod
    def default(
        cls,
    ):
        return lambda: Error_NotFound(
            _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "")),
            _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "")),
        )

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


class Error_NotFound(Error, NamedTuple("NotFound", [("path", Any), ("backend", Any)])):
    def __dafnystr__(self) -> str:
        return f"Error.NotFound({self.path.VerbatimString(True)}, {self.backend.VerbatimString(True)})"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Error_NotFound) and self.path == __o.path and self.backend == __o.backend

    def __hash__(self) -> int:
        return super().__hash__()


class Error_AlreadyExists(Error, NamedTuple("AlreadyExists", [("path", Any), ("backend", Any)])):
    def __dafnystr__(self) -> str:
        return f"Error.AlreadyExists({self.path.VerbatimString(True)}, {self.backend.VerbatimString(True)})"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Error_AlreadyExists) and self.path == __o.path and self.backend == __o.backend

    def __hash__(self) -> int:
        return super().__hash__()


class Error_PermissionDenied(Error, NamedTuple("PermissionDenied", [("path", Any), ("backend", Any)])):
    def __dafnystr__(self) -> str:
        return f"Error.PermissionDenied({self.path.VerbatimString(True)}, {self.backend.VerbatimString(True)})"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Error_PermissionDenied) and self.path == __o.path and self.backend == __o.backend

    def __hash__(self) -> int:
        return super().__hash__()


class Error_InvalidPath(Error, NamedTuple("InvalidPath", [("path", Any), ("backend", Any)])):
    def __dafnystr__(self) -> str:
        return f"Error.InvalidPath({self.path.VerbatimString(True)}, {self.backend.VerbatimString(True)})"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Error_InvalidPath) and self.path == __o.path and self.backend == __o.backend

    def __hash__(self) -> int:
        return super().__hash__()


class Error_CapabilityNotSupported(
    Error, NamedTuple("CapabilityNotSupported", [("capability", Any), ("backend", Any)])
):
    def __dafnystr__(self) -> str:
        return (
            f"Error.CapabilityNotSupported({self.capability.VerbatimString(True)}, {self.backend.VerbatimString(True)})"
        )

    def __eq__(self, __o: object) -> bool:
        return (
            isinstance(__o, Error_CapabilityNotSupported)
            and self.capability == __o.capability
            and self.backend == __o.backend
        )

    def __hash__(self) -> int:
        return super().__hash__()


class Error_DirectoryNotEmpty(Error, NamedTuple("DirectoryNotEmpty", [("path", Any), ("backend", Any)])):
    def __dafnystr__(self) -> str:
        return f"Error.DirectoryNotEmpty({self.path.VerbatimString(True)}, {self.backend.VerbatimString(True)})"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Error_DirectoryNotEmpty) and self.path == __o.path and self.backend == __o.backend

    def __hash__(self) -> int:
        return super().__hash__()


class Error_BackendUnavailable(Error, NamedTuple("BackendUnavailable", [("backend", Any)])):
    def __dafnystr__(self) -> str:
        return f"Error.BackendUnavailable({self.backend.VerbatimString(True)})"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Error_BackendUnavailable) and self.backend == __o.backend

    def __hash__(self) -> int:
        return super().__hash__()


class Result:
    @classmethod
    def default(
        cls,
    ):
        return lambda: Result_Err(Error.default()())

    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)

    @property
    def is_Ok(self) -> bool:
        return isinstance(self, Result_Ok)

    @property
    def is_Err(self) -> bool:
        return isinstance(self, Result_Err)


class Result_Ok(Result, NamedTuple("Ok", [("value", Any)])):
    def __dafnystr__(self) -> str:
        return f"Result.Ok({_dafny.string_of(self.value)})"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Result_Ok) and self.value == __o.value

    def __hash__(self) -> int:
        return super().__hash__()


class Result_Err(Result, NamedTuple("Err", [("error", Any)])):
    def __dafnystr__(self) -> str:
        return f"Result.Err({_dafny.string_of(self.error)})"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Result_Err) and self.error == __o.error

    def __hash__(self) -> int:
        return super().__hash__()


class Capability:
    @_dafny.classproperty
    def AllSingletonConstructors(cls):
        return [
            Capability_CapRead(),
            Capability_CapWrite(),
            Capability_CapDelete(),
            Capability_CapList(),
            Capability_CapMove(),
            Capability_CapCopy(),
            Capability_CapAtomicWrite(),
            Capability_CapAtomicMove(),
            Capability_CapMetadata(),
            Capability_CapGlob(),
            Capability_CapSeekableRead(),
        ]

    @classmethod
    def default(
        cls,
    ):
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


class Capability_CapRead(Capability, NamedTuple("CapRead", [])):
    def __dafnystr__(self) -> str:
        return "Capability.CapRead"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapRead)

    def __hash__(self) -> int:
        return super().__hash__()


class Capability_CapWrite(Capability, NamedTuple("CapWrite", [])):
    def __dafnystr__(self) -> str:
        return "Capability.CapWrite"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapWrite)

    def __hash__(self) -> int:
        return super().__hash__()


class Capability_CapDelete(Capability, NamedTuple("CapDelete", [])):
    def __dafnystr__(self) -> str:
        return "Capability.CapDelete"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapDelete)

    def __hash__(self) -> int:
        return super().__hash__()


class Capability_CapList(Capability, NamedTuple("CapList", [])):
    def __dafnystr__(self) -> str:
        return "Capability.CapList"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapList)

    def __hash__(self) -> int:
        return super().__hash__()


class Capability_CapMove(Capability, NamedTuple("CapMove", [])):
    def __dafnystr__(self) -> str:
        return "Capability.CapMove"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapMove)

    def __hash__(self) -> int:
        return super().__hash__()


class Capability_CapCopy(Capability, NamedTuple("CapCopy", [])):
    def __dafnystr__(self) -> str:
        return "Capability.CapCopy"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapCopy)

    def __hash__(self) -> int:
        return super().__hash__()


class Capability_CapAtomicWrite(Capability, NamedTuple("CapAtomicWrite", [])):
    def __dafnystr__(self) -> str:
        return "Capability.CapAtomicWrite"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapAtomicWrite)

    def __hash__(self) -> int:
        return super().__hash__()


class Capability_CapAtomicMove(Capability, NamedTuple("CapAtomicMove", [])):
    def __dafnystr__(self) -> str:
        return "Capability.CapAtomicMove"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapAtomicMove)

    def __hash__(self) -> int:
        return super().__hash__()


class Capability_CapMetadata(Capability, NamedTuple("CapMetadata", [])):
    def __dafnystr__(self) -> str:
        return "Capability.CapMetadata"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapMetadata)

    def __hash__(self) -> int:
        return super().__hash__()


class Capability_CapGlob(Capability, NamedTuple("CapGlob", [])):
    def __dafnystr__(self) -> str:
        return "Capability.CapGlob"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapGlob)

    def __hash__(self) -> int:
        return super().__hash__()


class Capability_CapSeekableRead(Capability, NamedTuple("CapSeekableRead", [])):
    def __dafnystr__(self) -> str:
        return "Capability.CapSeekableRead"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Capability_CapSeekableRead)

    def __hash__(self) -> int:
        return super().__hash__()


class Path:
    def __init__(self):
        pass

    @staticmethod
    def default():
        return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "a"))

    def _Is(source__):
        d_0_s_: _dafny.Seq = source__
        return (d_0_s_) != (_dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "")))


class FileInfo:
    @classmethod
    def default(
        cls,
    ):
        return lambda: FileInfo_FileInfo(Path.default(), _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, "")), 0)

    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)

    @property
    def is_FileInfo(self) -> bool:
        return isinstance(self, FileInfo_FileInfo)


class FileInfo_FileInfo(FileInfo, NamedTuple("FileInfo", [("path", Any), ("name", Any), ("size", Any)])):
    def __dafnystr__(self) -> str:
        return f"FileInfo.FileInfo({self.path.VerbatimString(True)}, {self.name.VerbatimString(True)}, {_dafny.string_of(self.size)})"

    def __eq__(self, __o: object) -> bool:
        return (
            isinstance(__o, FileInfo_FileInfo)
            and self.path == __o.path
            and self.name == __o.name
            and self.size == __o.size
        )

    def __hash__(self) -> int:
        return super().__hash__()


class FolderEntry:
    @classmethod
    def default(
        cls,
    ):
        return lambda: FolderEntry_FolderEntry(
            Path.default(), _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, ""))
        )

    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)

    @property
    def is_FolderEntry(self) -> bool:
        return isinstance(self, FolderEntry_FolderEntry)


class FolderEntry_FolderEntry(FolderEntry, NamedTuple("FolderEntry", [("path", Any), ("name", Any)])):
    def __dafnystr__(self) -> str:
        return f"FolderEntry.FolderEntry({self.path.VerbatimString(True)}, {self.name.VerbatimString(True)})"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, FolderEntry_FolderEntry) and self.path == __o.path and self.name == __o.name

    def __hash__(self) -> int:
        return super().__hash__()


class Entry:
    @classmethod
    def default(
        cls,
    ):
        return lambda: Entry_FileEntry(_dafny.Seq({}), FileInfo.default()())

    def __ne__(self, __o: object) -> bool:
        return not self.__eq__(__o)

    @property
    def is_FileEntry(self) -> bool:
        return isinstance(self, Entry_FileEntry)

    @property
    def is_DirEntry(self) -> bool:
        return isinstance(self, Entry_DirEntry)


class Entry_FileEntry(Entry, NamedTuple("FileEntry", [("content", Any), ("info", Any)])):
    def __dafnystr__(self) -> str:
        return f"Entry.FileEntry({_dafny.string_of(self.content)}, {_dafny.string_of(self.info)})"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Entry_FileEntry) and self.content == __o.content and self.info == __o.info

    def __hash__(self) -> int:
        return super().__hash__()


class Entry_DirEntry(Entry, NamedTuple("DirEntry", [])):
    def __dafnystr__(self) -> str:
        return "Entry.DirEntry"

    def __eq__(self, __o: object) -> bool:
        return isinstance(__o, Entry_DirEntry)

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

    def Exists(self, path):
        pass

    def Read(self, path):
        pass

    def Write(self, path, content, overwrite):
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

    def Move(self, src, dst, overwrite):
        pass

    def Copy(self, src, dst, overwrite):
        pass

    def RequireCapability(self, cap):
        pass
