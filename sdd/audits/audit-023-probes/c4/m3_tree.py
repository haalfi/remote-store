"""Measure Memory listings and tree answers against spec 051 / BE-032 claims."""

import asyncio
import fnmatch
import ntpath
import unicodedata

from remote_store import Store
from remote_store.aio import AsyncStore
from remote_store.aio.backends import AsyncMemoryBackend
from remote_store.backends import MemoryBackend
from remote_store.ext.glob import glob_files


def t(label, fn):
    try:
        r = fn()
        if hasattr(r, "__iter__") and not isinstance(r, (str, bytes, bool)):
            r = [str(getattr(x, "path", x)) for x in r]
        print(f"{label:55} -> {r!r}")
    except Exception as e:  # noqa: BLE001
        print(f"{label:55} -> {type(e).__name__}: {e}")


s = Store(backend=MemoryBackend())
for k in [
    "f.txt",
    "d/a.csv",
    "d/e/c.csv",
    "A.csv",
    "a.csv",
    unicodedata.normalize("NFC", "é.csv"),
    unicodedata.normalize("NFD", "é.csv"),
    "nl\n.csv",
    ".",
    "d/.x",
]:
    t(f"write {k!r}", lambda k=k: s.write(k, b"x") and None)

t("list_files root", lambda: s.list_files(""))
t("list_files root recursive", lambda: s.list_files("", recursive=True))
t("list_files item f.txt", lambda: s.list_files("f.txt"))
t("list_files through item f.txt/x", lambda: s.list_files("f.txt/x"))
t("list_folders item f.txt", lambda: s.list_folders("f.txt"))
t("iter_children item", lambda: s.iter_children("f.txt"))
t("get_folder_info item", lambda: s.get_folder_info("f.txt"))
t("get_folder_info absent", lambda: s.get_folder_info("nope"))
t("list_files absent", lambda: s.list_files("nope"))
t("write below item f.txt/x (A.4)", lambda: s.write("f.txt/x", b"x"))
t("write item over folder d (A.4)", lambda: s.write("d", b"x"))
t("move onto folder d", lambda: s.move("f.txt", "d"))
t("copy below item", lambda: s.copy("a.csv", "f.txt/y"))
t("exists A.csv / a.csv distinct", lambda: (s.read_bytes("A.csv"), s.exists("a.csv")))
nfc, nfd = unicodedata.normalize("NFC", "é.csv"), unicodedata.normalize("NFD", "é.csv")
t(
    "NFC vs NFD both listed (exact equality)",
    lambda: [ascii(str(x.path)) for x in s.list_files("") if "csv" in str(x.path)],
)
t("is_folder root '' / exists ''", lambda: (s.is_folder(""), s.exists("")))
t("list_files max_depth=0 root", lambda: s.list_files("", max_depth=0))
t("list_files max_depth=1 root", lambda: s.list_files("", max_depth=1))
t("list_folders max_depth=1", lambda: s.list_folders("", max_depth=1))
t("delete d/e/c.csv then is_folder d/e (A.6)", lambda: (s.delete("d/e/c.csv"), s.is_folder("d/e"))[1])
t("glob_files '**' after empty folder", lambda: glob_files(s, "**"))
t("list_folders d (empty folder e present)", lambda: s.list_folders("d"))

# Tier 1 case rule: fnmatch.fnmatch uses os.path.normcase; simulate Windows
t("tier1 '*.CSV' posix", lambda: s.list_files("", pattern="*.CSV"))
orig = fnmatch.os.path
try:
    fnmatch.os.path = ntpath
    t("tier1 '*.CSV' with ntpath normcase (Windows sim)", lambda: list(s.list_files("", pattern="*.CSV")))
finally:
    fnmatch.os.path = orig
t("tier3 '*.CSV' (regex, exact)", lambda: glob_files(s, "*.CSV"))


async def amain():
    a = AsyncStore(backend=AsyncMemoryBackend())
    await a.write("d/a.csv", b"x")
    try:
        r = [str(i.path) async for i in a.glob("d/*.csv")]
        print("async glob ->", r)
    except Exception as e:  # noqa: BLE001
        print("async glob ->", type(e).__name__, e)


asyncio.run(amain())
