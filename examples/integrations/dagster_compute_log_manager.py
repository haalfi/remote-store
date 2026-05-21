"""Dagster Compute Log Manager — Persist op/step stdout & stderr to any Store.

Demonstrates:
- RemoteStoreComputeLogManager: a Dagster *instance* component (configured in
  dagster.yaml), not a resource
- Capturing a job's stdout / stderr and persisting it to a remote-store backend
- Reading the captured logs back through the manager

Unlike the IO manager, the compute log manager has no Python construction API —
Dagster instantiates it from a dagster.yaml config dict. This demo wires the
equivalent config programmatically through DagsterInstance overrides.

---
see_also:
  - label: Dagster
    url: ../../guides/dagster.md
    note: Dagster integration guide
"""

from __future__ import annotations

import sys
import tempfile
from typing import Any

from dagster import DagsterInstance, job, op
from dagster._core.storage.compute_log_manager import ComputeIOType

from remote_store.ext.dagster import RemoteStoreComputeLogManager


@op
def chatty() -> None:
    """An op that writes to both stdout and stderr."""
    print("processed 3 records")
    print("warning: record 2 had a null field", file=sys.stderr)


@job
def chatty_job() -> None:
    chatty()


def demo() -> dict[str, Any]:
    """Dagster compute log manager demo. Returns results for test verification."""
    results: dict[str, Any] = {}

    with tempfile.TemporaryDirectory() as workdir:
        # The dagster.yaml equivalent, wired programmatically: Dagster builds
        # the RemoteStoreComputeLogManager from this config dict by string.
        print("=== RemoteStoreComputeLogManager (memory backend) ===")
        instance = DagsterInstance.local_temp(
            workdir,
            overrides={
                "compute_logs": {
                    "module": "remote_store.ext.dagster",
                    "class": "RemoteStoreComputeLogManager",
                    "config": {
                        "backend_type": "memory",
                        "local_dir": f"{workdir}/compute-logs",
                    },
                }
            },
        )
        try:
            manager = instance.compute_log_manager
            results["manager_is_remote_store"] = isinstance(manager, RemoteStoreComputeLogManager)
            print(f"  Configured: {type(manager).__name__}")
            print()

            # Run a job — Dagster captures its stdout / stderr, and the manager
            # uploads each stream to the Store on step completion.
            print("=== Run a job ===")
            run = chatty_job.execute_in_process(instance=instance)
            print(f"  Job succeeded: {run.success}")
            results["job_succeeded"] = run.success
            print()

            # Read the captured logs back out of the Store.
            print("=== Read compute logs back from the Store ===")
            log_key = list(
                manager.get_log_keys_for_log_key_prefix([run.run_id, "compute_logs"], ComputeIOType.STDOUT)[0]
            )
            stdout, _ = manager.get_log_data_for_type(log_key, ComputeIOType.STDOUT, offset=0, max_bytes=None)
            stderr, _ = manager.get_log_data_for_type(log_key, ComputeIOType.STDERR, offset=0, max_bytes=None)
            print(f"  stdout: {stdout!r}")
            print(f"  stderr: {stderr!r}")
            results["stdout_captured"] = stdout is not None and b"processed 3 records" in stdout
            results["stderr_captured"] = stderr is not None and b"null field" in stderr
        finally:
            instance.dispose()

    return results


if __name__ == "__main__":
    demo()
    print("\nDone!")
