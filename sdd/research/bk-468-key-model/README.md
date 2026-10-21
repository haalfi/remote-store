# BK-468 key model: spike and Lean proofs

<!-- doc: repo-only -->

The evidence behind
[`../research-key-model.md`](../research-key-model.md) § 10: an executable
model with property tests, and Lean 4 proofs of the document's § 7 lemmas.
Section numbers (§) in these files are that document's. Per the repo's PoC
convention the folder **freezes** once the document lands: the key-model spec
and its tests are written at their own paths and do not extend this folder.

| Path | Role |
|---|---|
| `spike/keymodel.py` | The model of § 3, executable: ν, the walk, join, resolution, child stores by composition, and spec 051 stores with an axiom checker |
| `spike/test_keymodel.py` | Hypothesis property tests of § 7's claims, and § 3.5's examples |
| `spike/pytest.ini` | Anchors pytest's rootdir here, so the repo's pytest configuration does not apply |
| `lean/KeyConcept.lean` | The input layer: § 3.3 and § 3.5 restated, K1 to K6 proved |
| `lean/KeyStore.lean` | The store layer: K7 to K12 proved against `StoreAxioms.lean`'s definitions |
| `lean/lakefile.toml`, `lean/lean-toolchain` | The Lean project; it requires `sdd/formal/lean` by relative path |
| `lean/build.sh` | Builds the project in the repo's Lean image |

Neither folder is collected or built by any gate: `spike/` is outside
`testpaths` and ruff's scope, and no CI job runs Lean (BK-462).

## Running the spike

From the repo root:

```
hatch run python -m pytest sdd/research/bk-468-key-model/spike -q -p no:cacheprovider -p no:randomly
```

Expected: `44 passed` (2026-10-21, a few minutes: up to 2000 examples per
property).

## Building the proofs

```
bash sdd/research/bk-468-key-model/lean/build.sh
```

It needs the Docker image `remote-store-lean:4.34.1`, which
`bash scripts/lean_check.sh` builds on its first run. The script mounts the
repo read-only, copies `sdd/formal/lean` and this project into the container
with their relative layout, and runs `lake build`; warnings fail the build,
and `#guard_msgs` pins each headline theorem's axioms, so a `sorry` fails it
too. Expected: `Build completed successfully`.
