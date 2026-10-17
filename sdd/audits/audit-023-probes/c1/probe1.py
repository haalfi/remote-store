"""Audit probes c1: kernel behaviour under misbehaving / mis-declared drivers.

Run from repo root: hatch run python <this file>
"""

from __future__ import annotations

import sys
import traceback

sys.path.insert(0, ".")

from remote_store._errors import BackendUnavailable, NotFound, RemoteStoreError  # noqa: E402
from remote_store._kernel._model import Entry, Page  # noqa: E402
from tests._kernel._fake import FakeStore, make_kernel  # noqa: E402


def show(label, fn):
    try:
        out = fn()
        print(f"[{label}] -> returned {out!r}")
    except BaseException as e:  # noqa: BLE001
        print(f"[{label}] -> raised {type(e).__module__}.{type(e).__name__}: {e}")


for rt in ("sync", "async"):
    print(f"===== runtime {rt} =====")

    # P1: namespace typo accepted at construction?
    def p1():
        st = FakeStore(parents="none")
        try:
            r = make_kernel(rt, st, namespace="Flat")
        except Exception as e:  # noqa: BLE001
            return f"construction refused: {type(e).__name__}: {e}"
        st.namespace = "flat"  # the wire IS flat; only the declaration is misspelt
        st.add("k")
        r.write("k/a.txt", b"x")
        return f"constructed; write below item k succeeded; files={sorted(st.files)}"

    show("P1 namespace='Flat' typo", p1)

    def p1b():
        st = FakeStore(parents="none")
        try:
            make_kernel(rt, st, namespace="object")
        except Exception as e:  # noqa: BLE001
            return f"construction refused: {type(e).__name__}: {e}"
        return "constructed with namespace='object'"

    show("P1b namespace='object'", p1b)

    def p1c():
        st = FakeStore(parents="none")
        st.parents = "None"  # typo of "none"
        try:
            make_kernel(rt, st, namespace="hierarchical")
        except Exception as e:  # noqa: BLE001
            return f"construction refused: {type(e).__name__}: {e}"
        return "constructed with parents='None'"

    show("P1c parents='None' typo (with remove_folder present)", p1c)

    # P2: stat returns a non-Entry
    def p2():
        r = make_kernel(rt, FakeStore())
        if rt == "sync":
            r.driver.__class__.stat = lambda self, key, *, follow_links=True: "not-an-entry"
        else:

            async def bad(self, key, *, follow_links=True):
                return "not-an-entry"

            r.driver.__class__.stat = bad
        return r.exists("a")

    show("P2 stat returns str -> exists", p2)

    # P3: stat returns an Entry for another key
    def p3():
        st = FakeStore().add("a")
        r = make_kernel(rt, st)
        if rt == "sync":
            r.driver.__class__.stat = lambda self, key, *, follow_links=True: Entry("zzz/other", "file", 1)
        else:

            async def bad(self, key, *, follow_links=True):
                return Entry("zzz/other", "file", 1)

            r.driver.__class__.stat = bad
        info = r.get_file_info("a")
        return f"FileInfo.path={info.path!s} name={info.name}"

    show("P3 stat returns Entry(key='zzz/other') -> get_file_info('a')", p3)

    # P4: list_page yields a key outside the listed prefix
    def p4():
        st = FakeStore()
        st.add("d/f", "e/g")
        r = make_kernel(rt, st)
        orig = st.list_page

        def lp(prefix, **kw):
            page = orig(prefix, **kw)
            return Page(entries=(*page.entries, Entry("e/g", "file", 1)), prefixes=page.prefixes, cursor=page.cursor)

        st.list_page = lp
        return [str(i.path) for i in r.list_files("d")]

    show("P4 list_page adds 'e/g' to listing of 'd' -> list_files('d')", p4)

    def p4b():
        st = FakeStore()
        st.add("d/f")
        r = make_kernel(rt, st)
        orig = st.list_page

        def lp(prefix, **kw):
            page = orig(prefix, **kw)
            return Page(entries=page.entries, prefixes=(*page.prefixes, "x/y"), cursor=page.cursor)

        st.list_page = lp
        return [str(i.path) for i in r.list_folders("d")]

    show("P4b list_page adds prefix 'x/y' (outside 'd') -> list_folders('d')", p4b)

    # P5: put returns a non-PutResult
    def p5():
        st = FakeStore(parents="implicit")
        r = make_kernel(rt, st)
        if rt == "sync":
            r.driver.__class__.put = lambda self, key, content, *, overwrite, metadata: None
        else:

            async def bad(self, key, content, *, overwrite, metadata):
                return None

            r.driver.__class__.put = bad
        return r.write("a", b"x")

    show("P5 put returns None -> write", p5)

    # P6: driver raises a TYPED error for an absent container (no classify path)
    def p6():
        st = FakeStore()
        r = make_kernel(rt, st)
        st.fault("delete", BackendUnavailable("container gone"))
        r.driver.container_absent = lambda exc, *, op: True  # recognises everything
        r.delete("a", missing_ok=True)
        return "returned cleanly"

    show("P6 typed BackendUnavailable from delete, container_absent says True -> delete(missing_ok=True)", p6)

    def p6b():
        from tests._kernel._fake import FakeContainerGone

        st = FakeStore()
        r = make_kernel(rt, st)
        st.fault("delete", FakeContainerGone("container gone"))
        r.delete("a", missing_ok=True)
        return "returned cleanly"

    show("P6b untyped FakeContainerGone from delete -> delete(missing_ok=True)", p6b)

    # P7: unwrap of an unsupported type
    def p7():
        r = make_kernel(rt, FakeStore())
        return r.unwrap(int)

    show("P7 unwrap(int) on fake driver", p7)

    # P8: native_path raising in the driver
    def p8():
        r = make_kernel(rt, FakeStore())

        def bad(self, key):
            raise KeyError(key)

        r.driver.__class__.native_path = bad
        return r.native_path("a")

    show("P8 driver native_path raises KeyError -> kernel native_path", p8)

    # P9: folder_stats returns a bad shape
    def p9():
        st = FakeStore().add("d/f")
        r = make_kernel(rt, st)
        if rt == "sync":
            r.driver.__class__.folder_stats = lambda self, prefix: (1, 2)
        else:

            async def bad(self, prefix):
                return (1, 2)

            r.driver.__class__.folder_stats = bad
        return r.get_folder_info("d")

    show("P9 folder_stats returns 2-tuple -> get_folder_info", p9)

    def p9b():
        st = FakeStore().add("d/f")
        r = make_kernel(rt, st)
        if rt == "sync":
            r.driver.__class__.folder_stats = lambda self, prefix: (-5, -1, None)
        else:

            async def bad(self, prefix):
                return (-5, -1, None)

            r.driver.__class__.folder_stats = bad
        return r.get_folder_info("d")

    show("P9b folder_stats returns negative counts -> get_folder_info", p9b)

    # P10: list_page returns a non-Page
    def p10():
        st = FakeStore().add("d/f")
        r = make_kernel(rt, st)
        st.list_page = lambda prefix, **kw: None
        return r.list_files("d")

    show("P10 list_page returns None -> list_files", p10)

    # P11: lazy vs eager errors on listings (closed terminal, refused key)
    def p11():
        r = make_kernel(rt, FakeStore(), close_is_terminal=True)
        r.close()
        gen = r.kernel.list_files("../x")
        return f"call returned {type(gen).__name__} without raising"

    show("P11 closed terminal: list_files('../x') at call time", p11)

    # P12: classify returns None
    def p12():
        from tests._kernel._fake import FakeOdd

        st = FakeStore().add("a")
        r = make_kernel(rt, st)
        r.driver.classify = lambda exc, *, op, key: None
        st.fault("get", FakeOdd("odd"))
        return r.read_bytes("a")

    show("P12 classify returns None for get failure -> read_bytes", p12)

    # P13: entry.kind invalid value
    def p13():
        st = FakeStore()
        r = make_kernel(rt, st)
        if rt == "sync":
            r.driver.__class__.stat = lambda self, key, *, follow_links=True: Entry(key, "dir", 0)
        else:

            async def bad(self, key, *, follow_links=True):
                return Entry(key, "dir", 0)

            r.driver.__class__.stat = bad
        return (r.exists("a"), r.is_file("a"), r.is_folder("a"))

    show("P13 stat returns kind='dir' -> (exists,is_file,is_folder)", p13)
