"""Execute tutorial notebooks as smoke tests.

Reads each .ipynb file, extracts code cells, and runs them sequentially
in a single namespace — the same approach as running cells top-to-bottom
in Jupyter.  No Jupyter/nbclient dependency required.

Skips ``benchmark_analysis.ipynb`` which needs pre-generated benchmark
data and matplotlib.

Usage::

    python examples/notebooks/run_notebooks.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SKIP = {"benchmark_analysis.ipynb"}

NOTEBOOK_DIR = Path(__file__).resolve().parent


def _run_notebook(path: Path) -> None:
    """Execute all code cells in *path* sequentially."""
    with open(path) as f:
        nb = json.load(f)

    namespace: dict[str, object] = {"__name__": "__main__"}
    for idx, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell["source"])
        if not source.strip():
            continue
        try:
            code = compile(source, f"{path.name}[cell {idx}]", "exec")
            exec(code, namespace)  # noqa: S102
        except Exception as exc:
            print(f"  FAIL cell {idx}: {exc}")
            raise


def main() -> int:
    notebooks = sorted(p for p in NOTEBOOK_DIR.glob("*.ipynb") if p.name not in SKIP)
    if not notebooks:
        print("No notebooks found.", file=sys.stderr)
        return 1

    failed = 0
    for nb_path in notebooks:
        print(f"  {nb_path.name} ...", end=" ", flush=True)
        try:
            _run_notebook(nb_path)
            print("OK")
        except Exception:
            failed += 1

    if failed:
        print(f"\n{failed}/{len(notebooks)} notebook(s) failed.")
        return 1

    print(f"\nAll {len(notebooks)} notebook(s) passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
