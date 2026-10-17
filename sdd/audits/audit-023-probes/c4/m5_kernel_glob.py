"""Kernel glob vs list_files on a first-call refusal in the probe set (A.5 / A.8).

A hierarchical driver whose wire reports ENOTDIR as InvalidPath (A.8: a wire's
ENOTDIR may arrive as any probe-set shape) for a pattern whose literal prefix
passes through an item.
"""

from remote_store import Capability, CapabilitySet
from remote_store._errors import InvalidPath, PermissionDenied
from remote_store._kernel._model import Entry
from remote_store._kernel.backend import DriverBackend
from remote_store.backends._memory import MemoryDriver


class GlobDriver(MemoryDriver):
    mode = "invalid"

    def glob(self, pattern):
        prefix = pattern.split("*")[0].rstrip("/")
        node = self._tree.traverse(prefix.rsplit("/", 1)[0]) if "/" in prefix else self._tree.root
        from remote_store.backends._memory_tree import FileEntry

        if isinstance(node, FileEntry) or (node is None and self._tree.traverse(prefix.split("/")[0]) is not None):
            if self.mode == "invalid":
                raise InvalidPath(f"Not a directory: {prefix}", path=prefix)
            raise PermissionDenied(f"denied: {prefix}", path=prefix)
        return iter(())

    def list_page(self, prefix, *, delimiter, cursor=None, limit=None, follow_links=True):
        node = self._tree.traverse(prefix.rsplit("/", 1)[0]) if "/" in prefix else None
        from remote_store.backends._memory_tree import FileEntry

        if isinstance(node, FileEntry):
            if self.mode == "invalid":
                raise InvalidPath(f"Not a directory: {prefix}", path=prefix)
            raise PermissionDenied(f"denied: {prefix}", path=prefix)
        return super().list_page(prefix, delimiter=delimiter, cursor=cursor, limit=limit)


caps = CapabilitySet(set(Capability) - {Capability.LAZY_READ})
for mode in ["invalid", "denied"]:
    d = GlobDriver(caps)
    d.mode = mode
    b = DriverBackend(d)
    b.write("f.txt", b"x")
    for label, fn in [
        ("list_files('f.txt/x')", lambda: list(b.list_files("f.txt/x"))),
        ("glob('f.txt/x/*')", lambda: list(b.glob("f.txt/x/*"))),
    ]:
        try:
            print(mode, label, "->", fn())
        except Exception as e:  # noqa: BLE001
            print(mode, label, "->", type(e).__name__, e)
