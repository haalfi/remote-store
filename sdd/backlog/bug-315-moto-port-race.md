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

## Advisory fix

Bind once and read the port back: construct
`ThreadedMotoServer(ip_address="127.0.0.1", port=0)`, call `start()`, then take
the real port from `get_host_and_port()` (present in the installed version).
That removes the gap between choosing and binding, and stops listening on every
interface. Per the bug-fix protocol, the failing test comes first: for example,
a test that a port already held by another socket cannot be handed to the
fixture.
