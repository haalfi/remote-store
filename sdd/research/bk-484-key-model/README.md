# BK-484 key model: spike and Lean proofs

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
| `probes/probe_paths.py` | Sends raw keys to a storage service or a local implementation and records what is stored, for `../research-backend-path-authorities.md` § 5 |
| `probes/results-2026-10-22.json` | That probe's output, with account, resource, region and zone names and exception message text left out; its `sftp` entry is the 2026-10-23 re-run |
| `probes/test_probe_paths.py`, `probes/pytest.ini` | Tests of the probe's above-root key and of what its output may contain; the ini anchors pytest's rootdir here |
| `probes/check_quotes.py` | Checks every double-quoted passage in `../research-backend-path-authorities.md` § 3 against the sources its subsection lists, as a substring after the normalisation its docstring lists |

No folder here is collected, built or run by any gate: `spike/` and `probes/`
are outside `testpaths` and `hatch run lint`'s ruff paths (the pre-commit ruff
hook still lints a changed file), and no CI job runs Lean (BK-462).

## Running the spike

From the repo root:

```
hatch run python -m pytest sdd/research/bk-484-key-model/spike -q -p no:cacheprovider -p no:randomly
```

Expected: `45 passed` (2026-10-21, a few minutes: up to 2000 examples per
property).

## Building the proofs

```
bash sdd/research/bk-484-key-model/lean/build.sh
```

It builds the Docker image `remote-store-lean:4.34.1` from
`scripts/lean.Dockerfile` on its first run. The version is pinned here, in
`build.sh` and `lean/lean-toolchain`, and is not on `scripts/lean_check.sh`'s
bump list, so a repo-wide Lean bump leaves this build alone. The proofs were
last checked on 2026-10-23 against `sdd/formal/lean` as of `45132599a`, the
last commit to touch it. A later change there can break this build, and no
gate runs it (BK-462): to reproduce the evidence, check out a commit where
`git log -1 -- sdd/formal/lean` names `45132599a`. The script mounts the
repo read-only, copies `sdd/formal/lean` and this project into the container
with their relative layout, and runs `lake build`; warnings fail the build,
and `#guard_msgs` pins the axioms of every theorem in the document's § 10
table, so a `sorry` fails it too. Expected: `Build completed successfully`.

## Running the probe

The local stack (`docker compose -f infra/docker-compose.yml up -d --wait
minio azurite sftp`) needs no account:

```
hatch run python sdd/research/bk-484-key-model/probes/probe_paths.py --target minio,azurite,sftp --out tmp/probe-local.json
```

Its tests need no service:

```
hatch run python -m pytest sdd/research/bk-484-key-model/probes -q -p no:cacheprovider -p no:randomly
```

Expected: `12 passed` (2026-10-23).

The quote check fetches each source once into a cache outside the tracked
tree:

```
hatch run python sdd/research/bk-484-key-model/probes/check_quotes.py --cache tmp/quote-cache
```

Expected: `92 of 92 quotes found in their section's sources` (2026-10-23).

`--target s3,s3express,azure` reaches the accounts in `.env`. Each run
creates and deletes a temporary bucket or container and costs a few dozen
requests. The script's docstring lists the targets.
