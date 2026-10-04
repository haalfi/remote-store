"""Derive the core-module list and related registry facts at one revision.

RFC-0019 Phase 0 deliverable "the core-module list derived"; throwaway.
Usage: python sdd/research/bk-403-phase-0/derive_lists.py <rev> [--json out]
"""

from __future__ import annotations

import json
import sys

from p0tree import Tree, facts
from selector import analysis, is_test_file


def main() -> None:
    rev = sys.argv[1]
    t = Tree(rev)
    A = analysis(t)
    src = [p for p in A.py if p.startswith("src/")]
    out = {
        "rev": rev,
        "src_modules": len(src),
        "hubs": sorted(A.hubs),
        "core": A.core,
        "eager_imported": sorted(A.eager),
        "top_effect_modules_all": A.top_effect_modules,
        "backend_reach_sizes": {b: len(r) for b, r in A.backend_reach.items()},
        "always_run": sorted(A.always_run),
        "registry_consumers": sorted(A.registry_consumers),
        "os_sensitive_files": sorted(A.os_sensitive_files),
        "os_sensitive_ids": sorted(A.os_sensitive_ids),
        "conftests_with_session_hooks": {
            p: sorted(facts(t, p).session_hooks)
            for p in A.py
            if p.endswith("conftest.py") and facts(t, p).session_hooks
        },
        "unparseable": sorted(p for p in A.py if not facts(t, p).parse_ok),
        "test_files": sum(1 for p in A.py if is_test_file(p)),
    }
    js = json.dumps(out, indent=1)
    if "--json" in sys.argv:
        with open(sys.argv[sys.argv.index("--json") + 1], "w", encoding="utf-8") as fh:
            fh.write(js)
    print(js)


if __name__ == "__main__":
    main()
