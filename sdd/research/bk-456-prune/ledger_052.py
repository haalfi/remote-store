"""Where each part of spec 052 went in BK-456's 052 prune, checked by ``check_prune.py``.

One entry per fragment of the spec at ``BASE``: ``(old, kind, dest, new)``.

- ``keep``: ``old`` stands, verbatim, in the new spec under section ``dest``.
- ``reword``: a load-bearing clause restated; ``new`` stands in the new spec
  under section ``dest``.
- ``move``: ``old`` stands, verbatim, in the file ``dest`` (link targets folded).
- ``homed``: already stated at ``dest``, in the words ``new``; nothing is copied.
- ``drop``: navigation, a heading or a field label with no content; ``dest``
  says why.

Whitespace is collapsed and Markdown quote and comment markers stripped before
any comparison. The fragments together must cover the whole old spec.
"""

SPEC = "sdd/specs/052-backend-lifetime.md"
BASE = "6e4c4fd"
D456 = "sdd/backlog/bk-456-split-spec-003.md"
D454 = "sdd/backlog/bk-454-refusal-timing-read-handle.md"
D455 = "sdd/backlog/bk-455-session-state-set.md"
ADR = "sdd/adrs/0049-close-and-concurrency-postures.md"
README = "sdd/formal/README.md"
BACKEND = "src/remote_store/_backend.py"
DRIVER = "src/remote_store/_kernel/_async/driver.py"
K053 = "sdd/specs/053-contract-kernel.md"

LEDGER = [
    # Title and Overview
    ("# 052: Backend Lifetime Specification", "keep", "title", None),
    ("## Overview", "keep", "Overview", None),
    (
        "What holds between a backend's calls: the states a backend, and on the contract kernel its read streams, "
        "write handles, listings and the caller's content iterator, pass through, and who owns each exit.",
        "reword",
        "Overview",
        "What holds across a backend's calls: what `close()` does to the calls after it, what one instance shared "
        "between threads guarantees, and, on the contract kernel, what each call leaves open, closed or released "
        "when it exits.",
    ),
    (
        "These are lifetime clauses ([`SPEC-DESIGN.md` Rule 2](../SPEC-DESIGN.md#kind-of-truth)): a witness of a "
        "breach is a sequence of calls on one object.",
        "keep",
        "Overview",
        None,
    ),
    (
        "Scope: every backend's close posture (BE-020) and concurrent-use posture (BE-028), and the interaction "
        "protocol of a class on the kernel (BE-033).",
        "reword",
        "Overview",
        "Scope: every backend's close posture (BE-020) and concurrent-use posture (BE-028); for a class on the "
        "kernel, a repeated close (BE-034), the cleanup on every exit (BE-033, BE-035, BE-036), a read after close "
        "(BE-037), and the driver's lifetime duties (BE-038, BE-039).",
    ),
    (
        "Out of scope: one call's outcome against the state when it runs, which is "
        "[spec 003](003-backend-adapter-contract.md)'s, and the contract kernel's single calls, which are "
        "[spec 053](053-contract-kernel.md)'s.",
        "reword",
        "Overview",
        "one call's outcome against the state when it runs: [spec 003](003-backend-adapter-contract.md), and for "
        "the kernel's single calls, its driver's single-call duties included, [spec 053](053-contract-kernel.md);",
    ),
    (
        "Lifetime clauses other specs own: a `Store`'s sharing across threads (STORE-007, "
        "[spec 001](001-store-api.md)); the async posture and the sync adapter's close (ASYNC-094, ASYNC-083 and "
        "ASYNC-088, [spec 029](029-async-store-backend-api.md)); and a stream on a condemned connection (SIO-010, "
        "[spec 006](006-streaming-io.md)).",
        "reword",
        "Overview",
        "a `Store` shared across threads (STORE-007), and when a refusal surfaces at a `Store` call: "
        "[spec 001](001-store-api.md) and, for `AsyncStore`, [spec 029](029-async-store-backend-api.md); - the "
        "async posture (ASYNC-094) and the sync adapter's close (ASYNC-083, ASYNC-088): "
        "[spec 029](029-async-store-backend-api.md); - whether a stream's close is skipped on a condemned "
        "connection (SIO-010): [spec 006](006-streaming-io.md);",
    ),
    # Terms
    ("## Terms", "keep", "Terms", None),
    (
        "- **Class on the kernel**, **driver**: as [spec 053 § Contract kernel](053-contract-kernel.md#contract-kernel) "
        "defines them.",
        "keep",
        "Terms",
        None,
    ),
    ("- **Close posture**, `close_is_terminal`: as BE-020 defines them.", "keep", "Terms", None),
    (
        "- **Concurrent-use posture**, `thread_safe`, `single_connection`: as BE-028 defines them.",
        "keep",
        "Terms",
        None,
    ),
    (
        "- **Live operation**: every member of a backend except the addressing members (`native_path`, `to_key`, "
        "`resolve`), `name`, `capabilities`, `close` and `unwrap`.",
        "keep",
        "Terms",
        None,
    ),
    (
        "- **Closed guard**: after a terminal close (BE-020), the refusal with `BackendUnavailable` of every live "
        "operation and, on the kernel, of `unwrap` too (BE-022);",
        "reword",
        "Terms",
        "- **Closed guard**: after a terminal close, the refusal with `BackendUnavailable` of every live operation "
        "and, on a class on the kernel, of `unwrap` too (BE-020).",
    ),
    (
        "on the kernel it is step 1 of [BE-030](053-contract-kernel.md#be-030-key-rule-on-the-kernel)'s pipeline.",
        "homed",
        K053,
        "1. The closed guard (BE-020), when the driver declares `close_is_terminal`.",
    ),
    (
        "- **Condemned**: a failure the driver's `connection_dead` judges a transport-level death of the "
        "connection, as BE-033's exit-owner table states.",
        "reword",
        "Terms",
        "- **Condemned**: a failure `connection_dead` judges a transport-level death of the connection.",
    ),
    (
        "- **`Session`**: the connection owner of a remote driver (RFC-0017 D5). BE-033 states its obligations and "
        "no states for it.",
        "move",
        D455,
        None,
    ),
    ("## Sections", "keep", "Sections", None),
    # BE-020
    ("### BE-020: close()", "keep", "BE-020", None),
    (
        "**Invariant:** `close()` is optional (default no-op).",
        "reword",
        "BE-020",
        "`close()` need not be overridden: the base class's does nothing.",
    ),
    ("Called for resource cleanup.", "move", D456, None),
    (
        "**Postconditions:** Whether the instance is reusable after `close()` is the backend's **close posture**, "
        "declared by the `close_is_terminal` class attribute:",
        "reword",
        "BE-020",
        "**Invariant:** a backend's close posture, its `close_is_terminal` class attribute (`False` unless the "
        "class sets it), decides what follows `close()`:",
    ),
    (
        "- `close_is_terminal = False` (the default — a backend need not restate it):",
        "reword",
        "BE-020",
        "| `close_is_terminal = False` | `close_is_terminal = True` |",
    ),
    (
        "the backend re-initialises its clients lazily and remains usable after `close()`",
        "move",
        BACKEND,
        None,
    ),
    (
        "The posture of `LocalBackend`, `MemoryBackend`, `SFTPBackend`, `ReadOnlyHttpBackend`, and the SQL backends.",
        "move",
        D456,
        None,
    ),
    (
        "- `close_is_terminal = True`: `close()` / `aclose()` is **terminal** —",
        "reword",
        "BE-020",
        "a terminal backend refuses every later live operation with `BackendUnavailable`, and a reusable one never "
        "refuses a call for being closed.",
    ),
    (
        "the flag flips at the *start* of `close()` and every lazy client accessor guards on it, so a subsequent "
        "operation raises `BackendUnavailable` rather than silently re-opening resources the caller cannot "
        "observe.",
        "move",
        BACKEND,
        None,
    ),
    (
        "The posture of `AzureBackend` (AZ-029), the three S3 backends (S3-019), and `GraphBackend` (GR-051).",
        "move",
        D456,
        None,
    ),
    (
        "The use-after-close conformance lane (`tests/backends/conformance/test_close_posture.py` and its `aio/` "
        "sibling) gates on this attribute, asserting the terminal error for terminal backends and "
        "re-initialisation for the rest.",
        "move",
        D456,
        None,
    ),
    (
        "**On the kernel:** the closed guard is the kernel's, [BE-030](053-contract-kernel.md#be-030-key-rule-on-the-kernel)'s "
        "step 1, and the posture is the driver's `close_is_terminal`. The class's own `close_is_terminal`, which "
        "the lane above reads, must match the driver's; the kernel refuses to construct over one that differs. "
        "`MemoryBackend` and `AsyncMemoryBackend` are on the kernel, and their drivers declare "
        "`close_is_terminal = False`. The states either posture passes through, and who owns each exit, are "
        "[BE-033](#be-033-interaction-protocol-on-the-kernel)'s.",
        "move",
        D456,
        None,
    ),
    (
        "**Rationale:** ",
        "drop",
        "a field label; the rationale it introduces moved to the ADR",
        None,
    ),
    (
        "A terminal close turns a use-after-close (a likely bug) into a clear typed error instead of a silent "
        "resource reopen, while leaving stateless/cheap backends freely reusable.",
        "move",
        ADR,
        None,
    ),
    ("**Formal coverage:** ", "drop", "a field label; its paragraph moved to Notes", None),
    (
        "`sdd/formal/BackendContract.dfy` models the posture as `closeIsTerminal`, `closed` and `Live()`, with a "
        "`Close()` that sets `closed` and promises nothing about the store's contents. Every operation that "
        "returns a result, except `RequireCapability`, answers `BackendUnavailable` when `!Live()`, ahead of every "
        "other clause and with `fs` unchanged. `Close()` returns nothing and stays callable after a terminal "
        "close, and `DropContainer()` models the environment rather than an operation, so neither carries the "
        "guard; every other postcondition the other formal-coverage notes in "
        "[spec 003](003-backend-adapter-contract.md) quote holds under `Live()`. `MemoryBackendMinimal` is the "
        "close-terminal witness in `MemoryBackend.dfy`.",
        "keep",
        "Notes",
        None,
    ),
    # BE-028
    ("### BE-028: Concurrent-Use Posture", "keep", "BE-028", None),
    (
        "**Invariant:** Every concrete `Backend` declares a **concurrent-use posture**, one of two values:",
        "reword",
        "BE-028",
        "**Invariant:** every backend instance has one of two concurrent-use postures, `thread_safe` unless its "
        "backend's spec declares it `single_connection` for that instance's configuration,",
    ),
    (
        "- **`thread_safe`** (the default — a backend spec need not restate it): a single instance is safe to share "
        "across threads, and each `Backend` operation is atomic with respect to other operations on the same "
        "instance.",
        "reword",
        "BE-028",
        "| `thread_safe` | raise nothing a lone call would not; writes to distinct keys all land; a read returns "
        "content a completed write left | — |",
    ),
    (
        "- **`single_connection`**: a single instance is **not** safe under concurrent use —",
        "reword",
        "BE-028",
        "| `single_connection` | no guarantee |",
    ),
    (
        "it wraps a non-thread-safe native client (e.g. one SFTP channel, or a `urllib` opener whose redirect "
        "counter is shared). Such a backend MUST document the posture in its spec **and** class docstring, and "
        "MUST state the remedy: one instance per thread, or an external serializing wrapper.",
        "move",
        D456,
        None,
    ),
    (
        "No backend provides multi-operation transactionality: atomicity is per-operation only (MEM-026), and "
        "ordering between concurrent callers is not guaranteed.",
        "reword",
        "BE-028",
        "No backend makes a sequence of calls atomic as one, and concurrent callers get no order. Whether one "
        "operation is atomic is its capability's (`ATOMIC_MOVE`, `ATOMIC_WRITE`, "
        "[spec 003](003-backend-adapter-contract.md)).",
    ),
    (
        "**Postconditions:** - `thread_safe` is the posture of `LocalBackend` (stateless; delegates to "
        "`os`/`shutil`, serialised by the operating system), `MemoryBackend` (a single `threading.Lock`, MEM-025), "
        "the cloud and SQL backends (their native clients — the boto3/s3fs client, the Azure SDK service "
        "clients, the SQLAlchemy engine/pool — are documented thread-safe for concurrent per-instance use), and "
        "`GraphBackend` on the async axis (GR-059). - `single_connection` is the posture of `SFTPBackend` "
        "(SFTP-029) and `ReadOnlyHttpBackend` on its default `urllib` transport (HTTP-CONC-001). - An "
        "**undeclared** posture is a contract violation, not a silent default: every concrete backend states its "
        "posture, or inherits the `thread_safe` default by the terms of this clause (`LocalBackend`, which has no "
        "numbered spec, is `thread_safe` by this paragraph).",
        "move",
        D456,
        None,
    ),
    (
        'STORE-007 promises a `Store` is "safe to share across threads," but a `Store` is immutable and merely '
        "delegates — the guarantee bottoms out in the backend.",
        "keep",
        "Notes",
        None,
    ),
    (
        'This clause turns "thread-safe" from an unstated assumption into an explicit per-backend obligation a '
        "caller can read from the spec without reading source. Like CAP-007's quality flags, declaring the "
        "posture gates no method; it documents a property every method has.",
        "move",
        ADR,
        None,
    ),
    (
        "The posture is the authoritative source for the machine-readable `concurrency` registry field the "
        "cross-backend concurrency conformance lane tests against.",
        "move",
        D456,
        None,
    ),
    (
        "**See also:** [001-store-api.md](001-store-api.md) (STORE-007), "
        "[013-memory-backend.md](013-memory-backend.md) (MEM-025/026), "
        "[029-async-store-backend-api.md](029-async-store-backend-api.md) (ASYNC-094);",
        "reword",
        "BE-028",
        "**See also:** [001-store-api.md](001-store-api.md) (STORE-007), "
        "[013-memory-backend.md](013-memory-backend.md) (MEM-025/026), "
        "[029-async-store-backend-api.md](029-async-store-backend-api.md) (ASYNC-094).",
    ),
    (
        "a `close` racing in-flight calls on the kernel, [BE-033](#be-033-interaction-protocol-on-the-kernel).",
        "move",
        D456,
        None,
    ),
    # BE-033
    ("### BE-033: Interaction Protocol on the Kernel", "keep", "BE-033", None),
    (
        "**Invariant:** a class on the kernel, its driver and the caller pass through the states tabled below, a "
        "call means what the transition table says in each state, and every exit, failure and cancellation "
        "included, has one owner who closes, aborts or releases what is open.",
        "reword",
        "BE-033",
        "**Invariant:** on every exit, a class on the kernel leaves no write handle open, every read stream it "
        "opened closed or, when the failure condemned the connection, released without a close, and no caller's "
        "async content iterator it took suspended, when that iterator has `aclose`.",
    ),
    (
        "Three invariants hold on every path: a terminal close absorbs every later call the closed guard covers (I1),",
        "reword",
        "BE-020",
        "a terminal backend refuses every later live operation with `BackendUnavailable`",
    ),
    (
        "every `close` reaches the driver, so a repeated one is the driver's to make idempotent (I2),",
        "reword",
        "BE-034",
        "every `close`/`aclose` reaches the driver, which makes a repeated one idempotent;",
    ),
    (
        "and on every exit the kernel observes it leaves no write handle open, no read stream open but one a "
        "condemned connection releases, and no caller iterator with `aclose` suspended (I3);",
        "reword",
        "BE-033",
        "and no caller's async content iterator it took suspended, when that iterator has `aclose`.",
    ),
    (
        "the temporary of a temp-and-rename write is the kernel's too, by the exit-owner row below, outside the model.",
        "reword",
        "Notes",
        "the temporary of a temp-and-rename write is the kernel's too, outside the model.",
    ),
    (
        "The other clauses of [spec 003](003-backend-adapter-contract.md) and [spec 053](053-contract-kernel.md) "
        "state each call; this one states the states between them.",
        "move",
        D456,
        None,
    ),
    (
        "**Scope.** The session-less classes on the kernel, such as `MemoryBackend` and `AsyncMemoryBackend`.",
        "move",
        D456,
        None,
    ),
    (
        "A `Session` (RFC-0017 D5) has an interface here and no states; its obligations below bind it.",
        "move",
        D455,
        None,
    ),
    ("**States.**", "reword", "BE-033", "The states it ranges over:"),
    ("| Party | States | Leaves a state by |", "keep", "BE-033", None),
    (
        "| backend | Open, Closed | `close`/`aclose`; nothing leaves Closed: under `close_is_terminal = False` the "
        "driver re-initialises on the next call and the backend stays Closed (BE-020) |",
        "reword",
        "BE-020",
        "**Nothing leaves Closed.** Under `close_is_terminal = False` the backend takes calls again but stays "
        "Closed; its next call re-initialises what the close released.",
    ),
    (
        "| read stream | Open, Exhausted, Failed, Closed, Released | reading to the end, a mapped stream error, "
        "`close`/`aclose`; a Failed stream whose error `connection_dead` condemns is Released, let go without a "
        "close (the model's `SReleased`) |",
        "keep",
        "BE-033",
        None,
    ),
    (
        "| write handle (`open_write`) | Open, Committed, Aborted | `commit`; `abort` on any exception |",
        "keep",
        "BE-033",
        None,
    ),
    (
        "| listing | Not started, Paging, Done, Failed | the first `next`, the last page, a refusal |",
        "move",
        D454,
        None,
    ),
    (
        "| caller's async content iterator | Unstarted, Suspended, Exhausted, Closed | each chunk the kernel takes; "
        "its end; the kernel's `aclose` |",
        "keep",
        "BE-033",
        None,
    ),
    ("| `Session` | not stated here | — |", "move", D455, None),
    (
        "A sync caller's content is a stream, not an iterator, and has no row: it stays the caller's in every "
        "state (below).",
        "reword",
        "BE-033",
        "A sync caller's content is a stream, not an iterator, and has no row: it stays the caller's in every "
        "state (BE-036).",
    ),
    (
        "**Transitions.** Per call, in the backend's state: | Call | Open | Closed, `close_is_terminal = False` | "
        "Closed, `close_is_terminal = True` | |---|---|---|---|",
        "reword",
        "BE-020",
        "| Call after `close()` | `close_is_terminal = False` | `close_is_terminal = True` | |---|---|---|",
    ),
    (
        "| a live operation (every member BE-030's pipeline runs) | its own clause | as Open, the driver "
        "re-initialising | `BackendUnavailable`, after the capability gates BE-030 orders ahead of it; no driver "
        "call |",
        "reword",
        "BE-020",
        "| a live operation | answered as before `close()` | `BackendUnavailable`, with no side effect |",
    ),
    (
        "| `unwrap` | the driver's handle, or BE-022's `CapabilityNotSupported` | as Open | `BackendUnavailable` |",
        "reword",
        "BE-020",
        "| `unwrap` | answered as before `close()` | on a class on the kernel, `BackendUnavailable`; on any other "
        "class, not refused by this clause (BE-022) |",
    ),
    (
        "| `close`/`aclose` | to Closed; forwarded | forwarded again | forwarded again |",
        "reword",
        "BE-020",
        "| `close`/`aclose` | accepted again | accepted again |",
    ),
    (
        "| `name`, `capabilities`, `native_path`, `to_key`, `resolve` | answered | answered | answered, never "
        "refused (BE-030's **Addressing stays total**) |",
        "reword",
        "BE-020",
        "| `name`, `capabilities`, the addressing members | answered | answered, never refused |",
    ),
    (
        "For a read stream: reading to the end leaves it Exhausted, and its close is the kernel's (async) or the "
        "caller's (sync, the `BinaryIO` it was handed).",
        "reword",
        "BE-033",
        "| a read stream read to its end | closed: by the kernel for an async `read` and for `read_bytes`; by the "
        "caller's close of the `BinaryIO` a sync `read` hands it, which the kernel's wrapper turns into the close "
        "or the release |",
    ),
    (
        "A mapped stream error leaves it Failed; a Failed stream is closed unless the driver's `connection_dead` "
        "condemns the error, and then it is released without a close, so no second wait falls on a dead "
        "connection (SIO-010), in both runtimes, for `read` and for `read_bytes`, which drains and closes its "
        "stream itself.",
        "reword",
        "BE-033",
        "| a read stream's mapped failure | closed, unless the driver's `connection_dead` condemns the failure, and "
        "then released without a close, in both runtimes, for `read` and for `read_bytes` |",
    ),
    (
        "Read after close: the sync stream raises `ValueError`, and an async iterator closed by its caller ends.",
        "reword",
        "BE-037",
        "**Invariant:** on a class on the kernel, a sync read stream raises `ValueError` when read after its "
        "close, and an async read iterator closed by its caller ends.",
    ),
    (
        "**Exit owners.** | Exit | Owner | What it does | |---|---|---|",
        "reword",
        "BE-033",
        "| Exit | What the kernel leaves | |---|---|",
    ),
    (
        "| a repeated `close` | the driver | is idempotent; the kernel forwards every call and short-circuits none |",
        "reword",
        "BE-034",
        "**Invariant:** on a class on the kernel, two closes leave the backend as one does, and every "
        "`close`/`aclose` reaches the driver, which makes a repeated one idempotent; the kernel short-circuits "
        "none.",
    ),
    (
        "| a read stream's close that fails after a successful read | the kernel's stream adapter | the close "
        "failure is logged, never raised, and fed to `connection_dead`; a read failure outranks a close failure |",
        "reword",
        "BE-035",
        "| a read stream's close after a successful read | nothing is raised; the close failure is logged and fed "
        "to `connection_dead`; a read failure outranks a close failure |",
    ),
    (
        "| end of data | the driver | exhaustion is the client's own end-of-data read, after any length or checksum "
        "check the client makes there,",
        "reword",
        "BE-038",
        "**Invariant:** a driver's read stream reports its end only where its client reports the end of data, "
        "after any length or checksum check the client makes there.",
    ),
    (
        "never a byte count the driver keeps |",
        "homed",
        DRIVER,
        "client's own read reports the end of data, after any length or checksum check the client makes there, "
        "never at a byte count the",
    ),
    (
        "| a write handle on any exception, cancellation included | the kernel | calls `abort`;",
        "reword",
        "BE-033",
        "| a write handle on any exception, cancellation included | aborted |",
    ),
    (
        "an `abort` that fails is logged on `remote_store._kernel` at `WARNING` with its `connection_dead` "
        "verdict, and the write's own error is raised |",
        "reword",
        "BE-035",
        "| `abort` of a write handle | the write's own error is raised; the `abort` failure is logged on "
        "`remote_store._kernel` at `WARNING` with its `connection_dead` verdict |",
    ),
    (
        "| a temporary of the temp-and-rename write | the kernel | deleted on any exception;",
        "reword",
        "BE-033",
        "| a temporary of the temp-and-rename write, on any exception | deleted |",
    ),
    (
        "a failed delete is logged as a failed `abort` is, except one that maps to `NotFound` (BE-021, a "
        "`container_absent` answer included): no temporary was left, so there is nothing to clean up |",
        "reword",
        "BE-035",
        "the failed delete is logged as a failed `abort` is, except one that maps to `NotFound` (BE-021, a "
        "`container_absent` answer included): no temporary was left, so there is nothing to clean up |",
    ),
    (
        "| `abort` after a failed `commit` | the driver | is legal and idempotent |",
        "reword",
        "BE-039",
        "**Invariant:** a driver's write handle accepts `abort` after a failed `commit`, and a repeated `abort` "
        "changes nothing a first one did not.",
    ),
    (
        "| an overwrite conflict without `overwrite` | the driver | refuses in one step on the wire where the wire "
        "has a conditional write; the conflict surfaces at `commit` for a handle, at the call for `put`; its "
        "typing as `AlreadyExists` is a driver duty |",
        "reword",
        K053,
        "An overwrite conflict without `overwrite`: the driver refuses in one step on the wire where the wire has "
        "a conditional write; the conflict surfaces at `commit` for a handle, at the call for `put`; its typing "
        "as `AlreadyExists` is a driver duty.",
    ),
    (
        "| a caller's async content iterator the kernel stops taking (a refused chunk, a driver or handle failure, "
        "a cancel, or a success whose driver returned before its end) | the kernel | calls its `aclose`, when it "
        "has one, before the call returns;",
        "reword",
        "BE-033",
        "| a caller's async content iterator the kernel stops taking (a refused chunk, a driver or handle failure, "
        "a cancel, or a success whose driver returned before its end) | its `aclose` called, when it has one, "
        "before the call returns;",
    ),
    (
        "what that raises is logged and never replaces the write's error.",
        "reword",
        "BE-035",
        "| a caller's async content iterator's `aclose` | the write's own result or error; what `aclose` raised "
        "is logged |",
    ),
    ("An exhausted one needs nothing.", "reword", "BE-033", "an exhausted one needs nothing |"),
    (
        "The kernel takes the iterator with its first chunk: a refusal before that, at the gates (closed guard, "
        "key, metadata, content shape), a write check or the driver, leaves it unstarted and the caller's to "
        "retry with |",
        "reword",
        "BE-036",
        "a refusal before it takes an async content iterator's first chunk leaves that iterator unstarted; the "
        "caller may seek or retry with either. A refusal before the first chunk is one at the gates (closed "
        "guard, key, metadata, content shape), a write check or the driver.",
    ),
    (
        "| a sync caller's content stream | the caller | the kernel never closes it, on any exit: the caller may "
        "seek it or retry with it |",
        "reword",
        "BE-036",
        "**Invariant:** a class on the kernel never closes a sync caller's content stream, on any exit,",
    ),
    (
        "| a connection a failure condemns | the `Session` | `invalidate` closes the client at once, and a stream "
        "on it fails mapped at its next read.",
        "move",
        D455,
        None,
    ),
    (
        "`connection_dead` means transport-level death, the socket or session gone, never an error the next "
        "request on the same connection survives.",
        "keep",
        "Terms",
        None,
    ),
    ("A cancel never invalidates |", "move", D455, None),
    (
        "| `unwrap` on a `Session` driver | the `Session` | goes through `run`, so after `invalidate` it reconnects |",
        "move",
        D455,
        None,
    ),
    (
        "| a `close` racing in-flight calls on a `thread_safe` class (BE-028) | the `Session` | creating and "
        "tearing down the client is atomic against the closed flag, under a lock held around the accessor alone, "
        "never over I/O, and async re-checks after its connect await; `close` waits for no in-flight call, and "
        "the teardown wakes blocked calls, which fail mapped. On a `single_connection` class concurrent `close` "
        "is already the caller's misuse |",
        "move",
        D455,
        None,
    ),
    (
        "**Refusal timing.** The rule: a pure refusal (the closed guard, a capability gate, `InvalidPath` for a "
        "malformed key) surfaces at the call; a stream's I/O refusal (`NotFound`, `InvalidPath` for a "
        "file-versus-folder mismatch) surfaces when the stream opens, through a handle (`with`/`async with "
        "store.read(...)`); a listing's I/O stays lazy, at its first page.",
        "move",
        D454,
        None,
    ),
    (
        "**Invariants**, each a lemma of `sdd/formal/KernelProtocol.dfy`:",
        "reword",
        "Notes",
        "- **The kernel's lemmas.** `sdd/formal/KernelProtocol.dfy` proves BE-020 on the kernel as I1,",
    ),
    (
        "1. **I1, terminal absorption** (`TerminalCloseAbsorbs`): from Closed under `close_is_terminal = True`, "
        "every live operation and `unwrap` answers `BackendUnavailable`, past any capability gate BE-030 ranks "
        "ahead of the guard, and the state stays Closed.",
        "reword",
        "Notes",
        "terminal absorption (`TerminalCloseAbsorbs`): from Closed under `close_is_terminal = True`, every live "
        "operation and `unwrap` answers `BackendUnavailable`, past any capability gate BE-030 ranks ahead of the "
        "guard, and the state stays Closed;",
    ),
    (
        "`close` and the addressing members are not refused (the transition table).",
        "reword",
        "BE-020",
        "| `close`/`aclose` | accepted again | accepted again |",
    ),
    (
        "A non-terminal backend is never refused for being closed (`ReusableNeverRefuses`).",
        "reword",
        "Notes",
        "and a non-terminal backend is never refused for being closed (`ReusableNeverRefuses`).",
    ),
    (
        "2. **I2, `close ∘ close = close`** (`CloseIsForwardedAndIdempotent`): two closes leave the backend as one "
        "does, and the driver sees each.",
        "reword",
        "Notes",
        "BE-034 is I2, `close ∘ close = close` (`CloseIsForwardedAndIdempotent`): two closes leave the backend as "
        "one does, and the driver sees each.",
    ),
    (
        "3. **I3, cleanup on every exit the kernel observes** (`CleanupOnEveryExit`, over `KernelExit`):",
        "reword",
        "Notes",
        "BE-033 is I3, cleanup on every exit the kernel observes (`CleanupOnEveryExit`, over `KernelExit`);",
    ),
    (
        "after any exit, no write handle is Open; every read stream is closed, except one whose failure condemned "
        "the connection, which is released without a close; and no caller iterator the kernel took is Suspended "
        "if it has `aclose`.",
        "reword",
        "BE-033",
        "**Invariant:** on every exit, a class on the kernel leaves no write handle open, every read stream it "
        "opened closed or, when the failure condemned the connection, released without a close,",
    ),
    (
        "One without `aclose` is left where the kernel stopped taking it, the caller's to finish.",
        "reword",
        "BE-033",
        "one without `aclose` is left where the kernel stopped taking it, the caller's to finish;",
    ),
    (
        "A sync read hands its stream to the caller open, so that stream's exit is the caller's close, which the "
        "kernel's wrapper turns into the close or the release.",
        "reword",
        "BE-033",
        "by the caller's close of the `BinaryIO` a sync `read` hands it, which the kernel's wrapper turns into "
        "the close or the release |",
    ),
    (
        "**Guard order.** Which capability gates run ahead of the closed guard is BE-030's **Gates around the "
        "pipeline**, and this clause keeps that order.",
        "move",
        D456,
        None,
    ),
    (
        "**The model is the oracle.** ",
        "reword",
        README,
        "**What the kernel oracle suite drives**, which bounds how far spec 052's I1 to I3 hold of the code",
    ),
    (
        "`KernelProtocol.dfy` compiles to `sdd/formal/KernelProtocol-py/`, and "
        "`tests/_kernel/test_protocol_oracle.py` drives the kernel through the exits its case builders enumerate "
        "(`_write_cases`, `_UNDRAINED_ROUTES`, `_open_atomic_cases`, `_read_cases`, `_sequences`; that file is "
        "the list), not every exit and not every state the model admits (most admitted states pair resources no "
        "single exit holds). The writes run on a hierarchical namespace with `overwrite=True` and an unnested "
        "key, and fault only the driver steps the builders name; a step reached but never faulted, and an exit "
        "never reached, is outside the suite: for example a failed `abort` or a failed delete of the temporary "
        "(both pinned in `test_protocol.py` instead), the probes after a refusal, `ensure_parents`, the metadata, "
        "content-shape and capability gates, a refused open of a read, or a flat namespace. Each cell but the "
        "read's closed guard, which asserts that no stream was opened, requires the state the kernel left to "
        "equal what the compiled `KernelExit` or `KernelStep` computes from the state at the exit, so I1 to I3 "
        "hold of the code on these exits to the extent that suite's stated mapping from the fake driver's "
        "records onto the model's states is faithful.",
        "move",
        README,
        None,
    ),
    ("**The model drawn.** ", "keep", "Notes", None),
    (
        "The diagrams below are enumerated from the same compiled model, over every value of its datatypes that "
        "`KernelExit`'s preconditions admit, and a test holds every drawn edge, label included, to one the "
        "oracle suite drives the kernel through; `hatch run gen-protocol-diagram` rewrites them after the oracle "
        "is rebuilt, and `preflight` fails while they are stale.",
        "keep",
        "Notes",
        None,
    ),
    ("GENERATED_BLOCK", "keep", "Notes", None),
    (
        "**Conformance:** `tests/_kernel/test_protocol.py`, a cell per kernel- and caller-owned row of the tables "
        "above over the fake driver, both runtimes (except the `Session` and driver rows, below, and the stream "
        "adapter's close-failure row); `tests/_kernel/test_protocol_stateful.py`, a Hypothesis state machine "
        "checking I1 to I3 under random interleavings of `write` and the wire-temporary `write_atomic` route, "
        "reads and closes, per runtime and posture; Memory's rows in `tests/backends/memory/test_kernel_cells.py`; "
        "and the repeated-close cell in both close-posture lanes (`tests/backends/conformance/test_close_posture.py` "
        "and its `aio/` sibling). The `Session` rows have no cell. The driver's rows are duties its protocols' "
        "docstrings state (`remote_store._kernel._async.driver`), and no cell checks them.",
        "move",
        D456,
        None,
    ),
    # Assumptions, Notes, Tested against
    ("## Assumptions", "keep", "Assumptions", None),
    (
        "None lifted out of the sections: BE-028 states, in its own text, what it relies on from the native clients.",
        "move",
        D456,
        None,
    ),
    ("## Notes", "keep", "Notes", None),
    (
        "The sections carry their derived claims in place: BE-033's Invariants name the `KernelProtocol.dfy` "
        "lemma behind each of I1 to I3, its diagrams are a view generated from the compiled model, and BE-028's "
        "Rationale states STORE-007's dependence on it.",
        "move",
        D456,
        None,
    ),
    ("## Tested against", "keep", "Tested against", None),
    (
        "- The Dafny models `sdd/formal/BackendContract.dfy` and `RootPath.dfy`, verified in `MemoryBackend.dfy`, "
        "and `sdd/formal/KernelProtocol.dfy` with its compiled oracle: `bash scripts/dafny_verify.sh "
        "BackendContract.dfy RootPath.dfy MemoryBackend.dfy KernelProtocol.dfy`.",
        "keep",
        "Tested against",
        None,
    ),
    (
        "- Every test file carrying a BE-020, BE-028 or BE-033 mark, both runtimes: `python scripts/run_tests.py "
        "$(rg -l 'mark\\.spec\\([^)]*\"BE-0(20|28|33)\"' tests)`.",
        "reword",
        "Tested against",
        "- Every test file carrying a mark of this spec's sections, both runtimes: `python scripts/run_tests.py "
        "$(rg -l 'mark\\.spec\\([^)]*\"BE-0(20|28|3[3-9])\"' tests)`.",
    ),
    (
        "Which test or model clause checks which section derives from the tests' spec marks and the models' "
        "`@spec` tags.",
        "keep",
        "Tested against",
        None,
    ),
]

# New sections, each with the old fragments it states (the rewording above names them).
NEW_IDS = {"BE-034", "BE-035", "BE-036", "BE-037", "BE-038", "BE-039"}
