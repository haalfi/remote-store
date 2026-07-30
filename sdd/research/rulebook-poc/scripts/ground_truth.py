"""Dump trigger + recorded gates for the four replay items."""

from __future__ import annotations

import yaml

ITEMS = {
    "BK-167a": "sdd/traces/bk-167a-documentation-framework-tooling.yml",
    "BK-171": "sdd/traces/bk-171-link-validation.yml",
    "BK-167": "sdd/traces/bk-167-documentation-framework-defined.yml",
    "BUG-199": "sdd/traces/bug-199-azure-folder-info-hns-dir-count.yml",
}

for tid, path in ITEMS.items():
    with open(path) as fh:
        t = yaml.safe_load(fh)
    print("=" * 70)
    print(f"{tid}: {t['title']}")
    print(f"TRIGGER: {t['trigger']}")
    print(f"audience: {t.get('audience')}")
    print("GATES:")
    for ph in t.get("phases", []):
        for s in ph.get("steps", []):
            if s.get("read_type") == "gate":
                print(f"  [{ph['id']:10s}] {s['file']} :: {s['section']}")
    print()
