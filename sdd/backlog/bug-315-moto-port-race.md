# BUG-315 — The moto fixture picks a port and binds it later, so two servers can share it or a failed bind hangs the session
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and advisory
prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

## Evidence, 2026-10-10

Read from `tests/conftest.py` and the installed `moto` in the default hatch env
(`hatch run python -c "import inspect, moto.moto_server.threaded_moto_server as t; print(inspect.getsource(t.ThreadedMotoServer))"`).
Found during BK-419 by a read-only contention analysis outside the repo; not
reproduced.

1. `_free_port()` (`tests/conftest.py`) binds port 0, reads the port and closes
   the socket. The port is free only at that instant.
2. The `moto_server` session fixture then constructs
   `ThreadedMotoServer(port=port, verbose=False)`. It passes no `ip_address`,
   so the server takes the default `"0.0.0.0"` (every interface). Each xdist
   worker runs this session fixture, so one run starts one server per worker.
3. werkzeug's `BaseWSGIServer` sets `allow_reuse_address = True`, so the bind
   uses `SO_REUSEADDR`. **Inferred, not reproduced:** on Windows that option
   lets a second socket bind a port another socket is using. Two servers that
   pick the same port then share it, and S3 state can cross between workers or
   between overlapping runs.
4. **Confirmed by reading the source:** `ThreadedMotoServer.start()` calls
   `self._server_ready_event.wait()` with no timeout, and `_server_entry` sets
   the event only after `make_server(...)` returns, inside the server thread.
   Any failure to bind ends that thread before the event is set, so `start()`,
   and with it the fixture and the xdist worker, waits forever.

Step 4 matches the "workers idle near 97%" stall in the
[BK-419 dossier](bk-419-local-gate-unbounded-wait.md). It is a candidate cause,
not a proven one. Since BK-419, a local run through `scripts/run_tests.py` ends
such a hang at its per-test timeout (fixture setup counts toward it). CI runs
pytest inline with no timeout, so a CI run would still hang.

## Reproduced, 2026-10-10

Both inferred steps above now hold by measurement; step 4's hang also has a
real trigger on Windows. Probes ran moto 5.2.3's `ThreadedMotoServer`, with
`start()` in a thread joined after 5 s.

- **Windows 11, Python 3.13.11.** A second `ThreadedMotoServer` on a port that a
  running one holds, both on `0.0.0.0`, starts and shares it (step 3), as does
  one on a port held by a plain `127.0.0.1` listener. `start()` hangs on a port
  held with `SO_EXCLUSIVEADDRUSE` (WinError 10013), on an unassignable address
  (WinError 10049), and on port 49800 (10013), which
  `netsh interface ipv4 show excludedportrange protocol=tcp` lists as excluded.
  That command listed 17 ranges, 15 of them inside the dynamic range
  `netsh interface ipv4 show dynamicport tcp` reports (start 49152, 16384
  ports).
  A range reserved between `_free_port()` returning and moto binding is a
  failed bind, and so a hang.
- **Linux (`python:3.13-slim` in Docker, Python 3.13.13).** The collision does
  not share: werkzeug prints `Address already in use`, and the second server's
  `start()` hangs. On CI the race therefore ends as a hang, and `ci.yml` passes
  pytest no timeout.

Also measured: werkzeug's `BaseWSGIServer.__init__` answers a failed bind by
printing the `OSError` and calling `sys.exit(1)`, so a bind in the caller's
thread surfaces as `SystemExit` whose `__context__` is the `OSError`. And
moto's S3 state is per process: two servers in one process share buckets, so
the isolation a distinct port buys is between xdist workers.

## Advisory fix

Bind once and read the port back: construct
`ThreadedMotoServer(ip_address="127.0.0.1", port=0)`, call `start()`, then take
the real port from `get_host_and_port()` (present in the installed version).
That removes the gap between choosing and binding, and stops listening on every
interface. Per the bug-fix protocol, the failing test comes first: for example,
a test that a port already held by another socket cannot be handed to the
fixture.

**Shipped differently, 2026-10-10.** `port=0` through `ThreadedMotoServer`
closes the race but keeps the unbounded wait for any bind that still fails.
`infra/_moto.py`'s `start_moto_server` instead binds with werkzeug's
`make_server("127.0.0.1", 0, ...)` in the caller's thread and converts the
`SystemExit` above back to `OSError`; the failing test is a bind to an
unassignable address, which hung before and raises now. Review of PR #1107
found the same pattern in `benchmarks/conftest.py`'s `moto_url`, which now uses
the same helper.

**Left unchanged, 2026-10-10.** `rg 'ThreadedMotoServer\(' sdd -g '*.py'` finds
the pattern at 5 sites in 3 measurement scripts:
`sdd/research/research-s3-error-mapping-fidelity.py` (1),
`sdd/research/research-id-211-flat-ns-file-ancestor-precheck.py` (1) and
`sdd/rfcs/rfc-0017-delete-folder-measure.py` (3). They stay as written because
they are records of what they measured. A new probe should start its server
with `infra._moto.start_moto_server` rather than copy one of them, including
the one `sdd/traces/id-200-s3-error-mapping-fidelity.yml` calls the probe
harness template.
