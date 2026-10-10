"""Unit tests for scripts/run_tests.py (BK-277, BK-419, BK-421).

Pins the resource-bounded worker formula, its free-memory cap, and the explicit-``-n`` passthrough so
a future edit cannot silently restore ``-n auto`` behaviour or break the
``RS_TEST_WORKERS`` override; and the suite lock and per-test timeout, the lock
against real separate processes, because what it guards against is another
process.
"""

from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_tests.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_tests", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("run_tests", module)
    spec.loader.exec_module(module)
    return module


_REAL_RUN = subprocess.run
_mod = _load_module()
compute_workers = _mod.compute_workers
_has_explicit_n = _mod._has_explicit_n
main = _mod.main


@pytest.mark.parametrize(
    ("cpus", "expected"),
    [
        (1, 1),  # max(1, floor(0.75) - 1) = max(1, -1)
        (2, 1),  # floor(1.5) - 1 = 0 -> clamped to 1
        (4, 2),  # floor(3.0) - 1
        (8, 5),  # floor(6.0) - 1
        (16, 11),  # floor(12.0) - 1
        (32, 23),  # floor(24.0) - 1
        (None, 1),  # unknown CPU count -> single worker
    ],
)
def test_default_formula_leaves_headroom(cpus: int | None, expected: int) -> None:
    assert compute_workers(cpus, None) == expected


def test_default_formula_never_exceeds_cpus() -> None:
    for cpus in range(1, 65):
        assert 1 <= compute_workers(cpus, None) <= cpus


@pytest.mark.parametrize("override", ["auto", "AUTO", " auto "])
def test_override_auto_uses_all_cpus(override: str) -> None:
    assert compute_workers(8, override) == 8
    assert compute_workers(1, override) == 1


@pytest.mark.parametrize(
    ("override", "expected"),
    [("4", 4), (" 3 ", 3), ("1", 1), ("16", 16)],  # explicit count may exceed cpus
)
def test_override_integer_is_respected(override: str, expected: int) -> None:
    assert compute_workers(8, override) == expected


def test_empty_override_falls_back_to_formula() -> None:
    assert compute_workers(8, "") == 5
    assert compute_workers(8, "   ") == 5


@pytest.mark.parametrize("override", ["abc", "0", "-2", "2.5"])
def test_invalid_override_raises(override: str) -> None:
    with pytest.raises(ValueError, match="RS_TEST_WORKERS"):
        compute_workers(8, override)


# -- Free-memory cap (BK-421) ----------------------------------------------

_GIB = 2**30


@pytest.mark.parametrize(
    ("free_gib", "expected"),
    [
        (7.9, 3),  # the 2026-10-04 crash: (7.9 - 2) // 1.5, where 14 workers died
        (3.5, 1),  # exactly one worker's budget above the reserve
        (2.0, 1),  # nothing above the reserve: still one worker, never zero
        (0.5, 1),  # below the reserve
        (100.0, 14),  # plenty of memory: the CPU formula binds
    ],
)
def test_free_memory_caps_the_default(free_gib: float, expected: int) -> None:
    assert compute_workers(20, None, int(free_gib * _GIB)) == expected


def test_unknown_free_memory_leaves_the_cpu_formula() -> None:
    assert compute_workers(20, None, None) == 14


@pytest.mark.parametrize("override", ["8", "auto"])
def test_override_ignores_the_memory_cap(override: str) -> None:
    """An explicit RS_TEST_WORKERS is the caller's decision, memory or not."""
    assert compute_workers(20, override, 1 * _GIB) == (8 if override == "8" else 20)


def test_main_reports_when_memory_caps_workers(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured = _stub_run(monkeypatch, cpu_count=20, free_bytes=int(7.9 * _GIB))
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py"])
    main()
    assert captured["argv"][3:5] == ["-n", "3"]
    err = capsys.readouterr().err
    assert "3 workers" in err
    assert "14" in err  # what the CPU formula would have used
    assert "RS_TEST_WORKERS" in err  # how to override


def test_main_is_silent_when_memory_does_not_bind(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured = _stub_run(monkeypatch, cpu_count=20, free_bytes=100 * _GIB)
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py"])
    main()
    assert captured["argv"][3:5] == ["-n", "14"]
    assert "workers" not in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "env_workers", "expected_n"),
    [
        (["run_tests.py", "-n", "0"], None, None),  # the caller's -n runs, so no claim about workers
        (["run_tests.py"], "8", "8"),  # the override runs, so nothing was capped
    ],
)
def test_main_is_silent_when_the_caller_chose_the_count(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    env_workers: str | None,
    expected_n: str | None,
) -> None:
    captured = _stub_run(monkeypatch, cpu_count=20, free_bytes=int(7.9 * _GIB))
    if env_workers is not None:
        monkeypatch.setenv("RS_TEST_WORKERS", env_workers)
    monkeypatch.setattr(_mod.sys, "argv", argv)
    main()
    run = captured["argv"]
    if expected_n is None:
        assert run.count("-n") == 1
        assert run[run.index("-n") + 1] == "0"  # the caller's, not an injected 3
    else:
        assert run[3:5] == ["-n", expected_n]
    assert "workers" not in capsys.readouterr().err


def test_memory_is_probed_after_the_lock(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """A run that waited for the lock sizes itself by the memory left once the holder is gone.

    While another suite holds the lock its workers hold their memory, so a probe
    taken before the wait would under-provision this run.
    """
    captured = _stub_run(monkeypatch, cpu_count=20)
    state = {"locked": False}

    class _Lock:
        def release(self) -> None:
            pass

    def _fake_acquire(path, wait_seconds):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN202
        state["locked"] = True
        return _Lock()

    monkeypatch.setattr(_mod, "acquire_suite_lock", _fake_acquire)
    # Before the lock: the holder's workers leave 7.9 GiB; after: 100 GiB.
    monkeypatch.setattr(_mod, "free_commit_bytes", lambda: 100 * _GIB if state["locked"] else int(7.9 * _GIB))
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py"])
    main()
    assert captured["argv"][3:5] == ["-n", "14"]
    assert "workers" not in capsys.readouterr().err


def _independent_free_bytes() -> int:
    """Free memory read through a second route, for checking the probe's field and scale.

    Windows: ``GetPerformanceInfo``'s commit limit minus commit charge, in pages,
    the same quantity as ``ullAvailPageFile`` from another API. Linux: this
    test's own parse of ``MemAvailable``.
    """
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class _PerfInfo(ctypes.Structure):
            _fields_ = [  # noqa: RUF012 - ctypes reads it from the class
                ("cb", wintypes.DWORD),
                ("CommitTotal", ctypes.c_size_t),
                ("CommitLimit", ctypes.c_size_t),
                ("CommitPeak", ctypes.c_size_t),
                ("PhysicalTotal", ctypes.c_size_t),
                ("PhysicalAvailable", ctypes.c_size_t),
                ("SystemCache", ctypes.c_size_t),
                ("KernelTotal", ctypes.c_size_t),
                ("KernelPaged", ctypes.c_size_t),
                ("KernelNonpaged", ctypes.c_size_t),
                ("PageSize", ctypes.c_size_t),
                ("HandleCount", wintypes.DWORD),
                ("ProcessCount", wintypes.DWORD),
                ("ThreadCount", wintypes.DWORD),
            ]

        info = _PerfInfo()
        info.cb = ctypes.sizeof(info)
        assert ctypes.windll.kernel32.K32GetPerformanceInfo(ctypes.byref(info), info.cb)
        return (info.CommitLimit - info.CommitTotal) * info.PageSize
    fields = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines())
    kib, unit = fields["MemAvailable"].split()
    assert unit == "kB"
    return int(kib) * 1024


def test_free_commit_bytes_reads_this_machine() -> None:
    """The real probe reads free memory, not another field, at the right scale.

    Checked against a second route to the same quantity within 1 GiB, the
    allowance for memory moving between the two reads. On the machine this was
    written on the wrong Windows fields sit 13 GiB or more away (free 44.4 GiB;
    available RAM 14.4, total RAM 31.3, commit limit 71.3), and kB read as bytes
    is off by a factor of 1024.
    """
    if sys.platform not in ("win32", "linux"):
        pytest.skip("no free-memory probe on this platform; the cap stays off")
    free = _mod.free_commit_bytes()
    assert free is not None
    assert abs(free - _independent_free_bytes()) < _GIB


@pytest.mark.parametrize(
    ("meminfo", "expected"),
    [
        ("MemTotal:       16000000 kB\nMemFree:  100 kB\nMemAvailable:    8000000 kB\n", 8000000 * 1024),
        ("MemTotal:       16000000 kB\nMemFree:  100 kB\n", None),  # kernel older than 3.14
        ("", None),
    ],
)
def test_meminfo_available_parsing(meminfo: str, expected: int | None) -> None:
    assert _mod._meminfo_available(meminfo) == expected


@pytest.mark.parametrize(
    "args",
    [["-n", "4"], ["-n0"], ["--numprocesses=2"], ["--numprocesses", "auto"], ["-p", "x", "-n", "2"]],
)
def test_explicit_n_detected(args: list[str]) -> None:
    assert _has_explicit_n(args) is True


@pytest.mark.parametrize("args", [[], ["-p", "no:benchmark"], ["tests/aio"], ["--cov=remote_store"]])
def test_no_explicit_n(args: list[str]) -> None:
    assert _has_explicit_n(args) is False


@pytest.fixture(autouse=True)
def lock_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every test at its own lock file, never the machine-wide one.

    The suite running these tests holds the real lock, and exports
    ``RS_TEST_LOCK_HELD`` to its workers; both are removed here so ``main()``
    exercises the locking path against a file no other test shares.
    """
    lock = tmp_path / "suite.lock"
    monkeypatch.setenv("RS_TEST_LOCK_FILE", str(lock))
    monkeypatch.delenv("RS_TEST_LOCK_HELD", raising=False)
    monkeypatch.delenv("RS_TEST_LOCK_WAIT", raising=False)
    monkeypatch.delenv("RS_TEST_TIMEOUT", raising=False)
    return lock


def _stub_run(monkeypatch: pytest.MonkeyPatch, cpu_count: int = 8, free_bytes: int | None = None) -> dict:
    """Stub subprocess.run / os.cpu_count / free memory / RS_TEST_WORKERS; capture the argv.

    *free_bytes* ``None`` (the default) means free memory is unknown, so only the
    CPU formula applies and the result does not depend on the machine running it.
    """
    captured: dict = {}

    class _Result:
        returncode = 7

    def _fake_run(argv, check, env=None):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN202
        captured["argv"] = argv
        captured["check"] = check
        captured["env"] = env
        return _Result()

    monkeypatch.setattr(_mod.subprocess, "run", _fake_run)
    monkeypatch.setattr(_mod.os, "cpu_count", lambda: cpu_count)
    monkeypatch.setattr(_mod, "free_commit_bytes", lambda: free_bytes)
    monkeypatch.delenv("RS_TEST_WORKERS", raising=False)
    return captured


def test_main_injects_bounded_workers_and_forwards(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() injects the computed -n and forwards the rest, propagating exit code."""
    captured = _stub_run(monkeypatch, cpu_count=8)
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py", "-p", "no:benchmark", "tests/x"])
    rc = main()
    assert rc == 7  # subprocess returncode propagated
    argv = captured["argv"]
    assert argv[:3] == [_mod.sys.executable, "-m", "pytest"]
    assert argv[3:5] == ["-n", "5"]  # floor(8*0.75) - 1
    assert argv[5] == "--timeout=300"  # local per-test default
    assert argv[6:] == ["-p", "no:benchmark", "tests/x"]
    assert captured["check"] is False


def test_main_respects_explicit_n(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() does not inject -n when the caller already passed one."""
    captured = _stub_run(monkeypatch, cpu_count=8)
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py", "-n", "2", "tests/x"])
    main()
    argv = captured["argv"]
    assert argv == [_mod.sys.executable, "-m", "pytest", "--timeout=300", "-n", "2", "tests/x"]
    assert argv.count("-n") == 1  # no second -n injected


def test_main_invalid_override_returns_2(monkeypatch: pytest.MonkeyPatch) -> None:
    """An invalid RS_TEST_WORKERS makes main() exit 2 without invoking pytest."""
    captured = _stub_run(monkeypatch)
    monkeypatch.setenv("RS_TEST_WORKERS", "nope")
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py"])
    assert main() == 2
    assert "argv" not in captured  # subprocess.run never called


# -- Per-test timeout (BK-419) ---------------------------------------------


@pytest.mark.parametrize("args", [["--timeout=60"], ["--timeout", "60"], ["-p", "x", "--timeout=0"]])
def test_main_respects_explicit_timeout(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    """A caller's own --timeout wins; the launcher adds no second one."""
    captured = _stub_run(monkeypatch)
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py", *args])
    main()
    timeouts = [a for a in captured["argv"] if a.startswith("--timeout")]
    assert timeouts == [a for a in args if a.startswith("--timeout")]


@pytest.mark.parametrize(("raw", "expected"), [("45", "--timeout=45"), (" 120 ", "--timeout=120")])
def test_timeout_env_override(monkeypatch: pytest.MonkeyPatch, raw: str, expected: str) -> None:
    captured = _stub_run(monkeypatch)
    monkeypatch.setenv("RS_TEST_TIMEOUT", raw)
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py"])
    main()
    assert [a for a in captured["argv"] if a.startswith("--timeout")] == [expected]


def test_timeout_env_zero_disables(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _stub_run(monkeypatch)
    monkeypatch.setenv("RS_TEST_TIMEOUT", "0")
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py"])
    main()
    assert not any(a.startswith("--timeout") for a in captured["argv"])


@pytest.mark.parametrize("name", ["RS_TEST_TIMEOUT", "RS_TEST_LOCK_WAIT"])
@pytest.mark.parametrize("raw", ["abc", "-1", "1.5x"])
def test_invalid_seconds_env_returns_2(monkeypatch: pytest.MonkeyPatch, name: str, raw: str) -> None:
    captured = _stub_run(monkeypatch)
    monkeypatch.setenv(name, raw)
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py"])
    assert main() == 2
    assert "argv" not in captured


@pytest.mark.os_sensitive
def test_timeout_reaches_a_hung_test(tmp_path: Path) -> None:
    """End to end: the injected timeout ends a hung test and names it.

    Runs the real launcher on a one-test file that sleeps past a 2 s timeout,
    serially, so the outcome does not depend on xdist's crash reporting.
    """
    test_file = tmp_path / "test_hang.py"
    test_file.write_text("import time\n\n\ndef test_hangs_forever():\n    time.sleep(60)\n", encoding="utf-8")
    env = {**os.environ, "RS_TEST_TIMEOUT": "2", "RS_TEST_LOCK_FILE": str(tmp_path / "e2e.lock")}
    env.pop("RS_TEST_LOCK_HELD", None)
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "-n", "0", "-p", "no:cacheprovider", str(test_file)],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=50,
        check=False,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "Timeout" in out
    assert "test_hangs_forever" in out


# -- Machine-wide suite lock (BK-419) --------------------------------------

_HOLDER = """
import importlib.util, sys, time
spec = importlib.util.spec_from_file_location("run_tests", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
lock = mod.acquire_suite_lock(mod.Path(sys.argv[2]), wait_seconds=0)
print(f"LOCKED {mod.os.getpid()}" if lock else "BUSY", flush=True)
time.sleep(float(sys.argv[3]))
"""

_PROBE = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location("run_tests", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print("FREE" if mod.acquire_suite_lock(mod.Path(sys.argv[2]), wait_seconds=0) else "BUSY")
"""


class _Holder:
    """A separate process holding the lock. ``pid`` is the interpreter's own pid.

    ``proc.pid`` is not used: on Windows a venv's ``python.exe`` is a launcher
    that runs the interpreter as a child, so the two pids differ.
    """

    def __init__(self, proc: subprocess.Popen[str], pid: int) -> None:
        self.proc = proc
        self.pid = pid


def _start_holder(lock: Path, hold_seconds: float) -> _Holder:
    """Start a separate process that takes *lock* and holds it for *hold_seconds*."""
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(_SCRIPT), str(lock), str(hold_seconds)],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    first = proc.stdout.readline().split()
    if first[:1] != ["LOCKED"]:
        _stop(proc)
        pytest.fail(f"lock holder did not take the lock: {first!r}")
    return _Holder(proc, int(first[1]))


def _stop(target: subprocess.Popen[str] | _Holder) -> None:
    proc = target.proc if isinstance(target, _Holder) else target
    proc.kill()
    proc.wait()
    if proc.stdout is not None:
        proc.stdout.close()


def _probe(lock: Path) -> bool:
    """True if a fresh process can take *lock* right now.

    Calls ``_REAL_RUN``: the tests that probe have patched ``subprocess.run``.
    """
    out = _REAL_RUN(
        [sys.executable, "-c", _PROBE, str(_SCRIPT), str(lock)], capture_output=True, text=True, timeout=30, check=True
    )
    return out.stdout.strip() == "FREE"


@pytest.mark.os_sensitive
def test_second_run_waits_then_gives_up_naming_the_holder(lock_file: Path) -> None:
    holder = _start_holder(lock_file, hold_seconds=30)
    try:
        out = io.StringIO()
        lock = _mod.acquire_suite_lock(lock_file, wait_seconds=1.5, poll=0.1, report_every=0.5, out=out)
        assert lock is None
        text = out.getvalue()
        assert f"pid {holder.pid}" in text  # the holder is named
        assert "waiting" in text
        assert "gave up" in text
    finally:
        _stop(holder)


@pytest.mark.os_sensitive
def test_second_run_proceeds_once_the_holder_exits(lock_file: Path) -> None:
    holder = _start_holder(lock_file, hold_seconds=1.0)
    try:
        out = io.StringIO()
        start = time.monotonic()
        lock = _mod.acquire_suite_lock(lock_file, wait_seconds=30, poll=0.1, out=out)
        assert lock is not None
        assert time.monotonic() - start < 25  # took over when the holder left, not at the bound
        assert "waiting" in out.getvalue()
        lock.release()
    finally:
        _stop(holder)


@pytest.mark.os_sensitive
def test_main_returns_lock_timeout_code_without_running_pytest(
    monkeypatch: pytest.MonkeyPatch, lock_file: Path
) -> None:
    holder = _start_holder(lock_file, hold_seconds=30)
    try:
        captured = _stub_run(monkeypatch)
        monkeypatch.setenv("RS_TEST_LOCK_WAIT", "0")
        monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py"])
        assert main() == _mod.EXIT_LOCK_TIMEOUT
        assert "argv" not in captured  # pytest never started
    finally:
        _stop(holder)


@pytest.mark.os_sensitive
def test_lock_of_a_killed_holder_does_not_block(lock_file: Path) -> None:
    """A holder that dies without cleanup leaves its files behind, not its lock."""
    holder = _start_holder(lock_file, hold_seconds=60)
    _stop(holder)
    assert lock_file.exists()  # the dead holder's files are still there
    assert lock_file.with_name(lock_file.name + ".info").exists()
    # A short wait, not zero: on Windows the venv launcher's child interpreter,
    # which holds the lock, exits a moment after the launcher is killed.
    lock = _mod.acquire_suite_lock(lock_file, wait_seconds=10, poll=0.1, out=io.StringIO())
    assert lock is not None
    lock.release()


@pytest.mark.os_sensitive
def test_main_holds_lock_during_run_and_exports_marker(monkeypatch: pytest.MonkeyPatch, lock_file: Path) -> None:
    seen: dict = {}

    class _Result:
        returncode = 0

    def _fake_run(argv, check, env=None):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN202
        seen["free_during_run"] = _probe(lock_file)
        seen["env"] = env
        return _Result()

    monkeypatch.setattr(_mod.subprocess, "run", _fake_run)
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py"])
    assert main() == 0
    assert seen["free_during_run"] is False
    assert seen["env"]["RS_TEST_LOCK_HELD"] == str(os.getpid())
    assert _probe(lock_file) is True  # released after a normal exit


@pytest.mark.os_sensitive
@pytest.mark.parametrize("exc", [KeyboardInterrupt, FileNotFoundError])
def test_main_releases_lock_when_the_run_raises(
    monkeypatch: pytest.MonkeyPatch, lock_file: Path, exc: type[BaseException]
) -> None:
    def _boom(argv, check, env=None):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN202
        raise exc

    monkeypatch.setattr(_mod.subprocess, "run", _boom)
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py"])
    with pytest.raises(exc):
        main()
    assert _probe(lock_file) is True


@pytest.mark.os_sensitive
def test_nested_run_skips_the_lock(monkeypatch: pytest.MonkeyPatch, lock_file: Path) -> None:
    """A run started inside a locked suite must not wait on its own parent."""
    holder = _start_holder(lock_file, hold_seconds=30)
    try:
        captured = _stub_run(monkeypatch)
        monkeypatch.setenv("RS_TEST_LOCK_HELD", str(holder.pid))
        monkeypatch.setenv("RS_TEST_LOCK_WAIT", "0")
        monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py"])
        assert main() == 7
        assert "argv" in captured
    finally:
        _stop(holder)


def test_default_lock_wait_fits_inside_the_session_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default wait leaves room for a run under both session bounds.

    A foreground tool call is cut off at 600 s, and CLAUDE.md gives a background
    wait 15 minutes. A wait of 300 s leaves a gate run about 300 s inside the
    tighter bound, so a waiter either takes the lock with time to run or gives
    up with exit 75 before any cut-off.
    """
    _stub_run(monkeypatch)
    seen: dict = {}

    def _fake_acquire(path, wait_seconds):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN202
        seen["wait"] = wait_seconds

    monkeypatch.setattr(_mod, "acquire_suite_lock", _fake_acquire)
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py"])
    assert main() == _mod.EXIT_LOCK_TIMEOUT  # the fake never grants the lock
    assert seen["wait"] == 300


def test_default_lock_path_is_outside_the_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every worktree and clone must resolve the same file, so it cannot live in one."""
    monkeypatch.delenv("RS_TEST_LOCK_FILE", raising=False)
    path = _mod.suite_lock_path()
    assert path.is_relative_to(Path.home())
    assert not path.is_relative_to(_SCRIPT.parents[1])
