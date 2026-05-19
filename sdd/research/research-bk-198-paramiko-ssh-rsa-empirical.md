# Research: paramiko `ssh-rsa` host-key compatibility — empirical findings (BK-198)

**Date:** 2026-05-12
**Status:** Complete; matrix extended to paramiko 5.0 and the BK-198 framing finalised in [PR 613](https://github.com/haalfi/remote-store/pull/613).
**Scope:** Verify the empirical premise of `SFTPUtils.enable_ssh_rsa_compat()` against a Dockerized legacy SFTP server across the full paramiko 2.x / 3.x / 4.x / 5.x range, before locking in the docstring / guide / hint-message wording.
**Related:** [BK-198](../BACKLOG-DONE.md), [trace](../traces/BK-198-ssh-rsa-compat.yml), [PR 613](https://github.com/haalfi/remote-store/pull/613).

**Context.** The first cut of BK-198 was reasoned out from one data point (paramiko 4.0.0 import surface) and shipped a helper whose docstring claimed "Paramiko 3.x+ removed `ssh-rsa` from defaults at four levels." That claim turned out to be version-shifted by two majors: paramiko 2.x / 3.x / 4.x all ship `ssh-rsa` in defaults; paramiko **5.0** is where the removal happened. A first corrective sweep over-corrected (claimed the helper was a no-op on every shipping paramiko); this note records the final empirical state after a 5.0 probe re-confirmed that the helper is in fact required against modern paramiko + legacy SFTP servers.

---

## 1. Test rig

Two Docker images, both forcing the legacy-server shape:

| Image | Forcing | Port |
|---|---|---|
| `legacy-sftp` (durable) | Only `ssh-rsa` host-key + pubkey algorithms; modern KEX defaults; `infra/legacy-sftp/Dockerfile` | 2223 |
| `legacy-sftp:kex` (research-only) | Same as above PLUS `KexAlgorithms diffie-hellman-group14-sha1,diffie-hellman-group1-sha1` | 2224 |

The second image is kept only for research-time reproductions of the user's originally-reported `IncompatiblePeer: no acceptable kex algorithm` shape; the durable e2e test (`tests/e2e/test_sftp_legacy_recovery.py`) drives the first.

Client matrix: five isolated `uv` venvs, all on Python 3.11/3.13, all sharing a recent `cryptography`, varying only paramiko:

- `paramiko==2.12.0` (last 2.x release)
- `paramiko==3.0.0` (claimed cut-off in the original PR docstring)
- `paramiko==3.5.0` (mid-3.x sanity check)
- `paramiko==4.0.0` (previous `[sftp]` floor)
- `paramiko==5.0.0` (first major to actually clear `ssh-rsa`)

Probe runs four scenarios per venv:

| ID | Scenario | What it tests |
|---|---|---|
| S1 | Bare connect on paramiko defaults | Does the legacy server connect out of the box? |
| S2 | Connect after `enable_ssh_rsa_compat()` on defaults | Is the helper a no-op when defaults already contain `ssh-rsa`? |
| S3 | Strip `ssh-rsa` from all four sites, then connect | Reproduces the cleared-defaults state |
| S4 | Run helper after S3, then connect | Does the helper actually recover? |

---

## 2. Findings

### 2.1 Default `_preferred_keys` and `RSAKey.HASHES` across versions

| Site | 2.12.0 | 3.0.0 | 3.5.0 | 4.0.0 | 5.0.0 |
|---|---|---|---|---|---|
| `Transport._preferred_keys` | present | present | present | present | **absent** |
| `Transport._preferred_pubkeys` | present | present | present | present | **absent** |
| `Transport._key_info["ssh-rsa"]` | present | present | present | present | **absent** |
| `RSAKey.HASHES["ssh-rsa"]` | present | present | present | present | **absent** |

Paramiko 5.0 is the version where the removal lands. The 2.x → 4.x range still ships `ssh-rsa` at every site (deprecated, but present). The only other relevant inter-version difference is that paramiko 4.0 dropped `ssh-dss`.

Defaults on paramiko 5.0 (post-removal): `ssh-ed25519`, `ecdsa-sha2-nistp256`, `ecdsa-sha2-nistp384`, `ecdsa-sha2-nistp521`, `rsa-sha2-512`, `rsa-sha2-256`.

### 2.2 Connection outcomes per scenario

Outcomes split cleanly along the 4.x / 5.x divide:

| Scenario | paramiko 2.x–4.x | paramiko 5.x |
|---|---|---|
| S1 (bare) | ✅ connect + open SFTP subsystem | ❌ `IncompatiblePeer: Incompatible ssh peer (no acceptable host key)` |
| S2 (helper on defaults) | ✅ succeeds; helper guards short-circuit (no-op) | ✅ succeeds; helper re-adds `ssh-rsa` and connection works |
| S3 (cleared, then bare) | ❌ same `IncompatiblePeer` as 5.x S1 | ❌ identical (defaults are already cleared) |
| S4 (cleared, then helper, then connect) | ✅ helper re-adds `ssh-rsa`; connection succeeds | ✅ same |

The S1-5.x and S3-2.x–4.x failures share a byte-identical error string — same handler in `Transport._parse_kex_init`.

---

## 3. Conclusions

1. **Paramiko 5.0 cleared `ssh-rsa` from all four sites.** This is the version this PR addresses; the 2.x → 4.x range is unaffected by the BK-198 failure mode.
2. **The helper is required on paramiko ≥ 5.0 to connect to an `ssh-rsa`-only server.** Without it, bare connect fails immediately during KEX in `_parse_kex_init` before authentication is attempted.
3. **The helper is a no-op on paramiko < 5.0.** All four guard clauses short-circuit because `ssh-rsa` is already present. Calling it eagerly is harmless and forward-compatible.
4. **The `IncompatiblePeer` hint is correctly scoped.** `IncompatiblePeer` also wraps `no acceptable {kex algorithm, cipher, MAC}` failures, which the helper does not address. Gating the hint on `"host key" in str(exc)` keeps it accurate.

---

## 4. Changes derived from this verification

Tracked across PR 613:

1. `enable_ssh_rsa_compat` docstring: names paramiko 5.0 explicitly as the version that cleared `ssh-rsa`; describes the helper as required-on-5.0+, no-op-below.
2. `docs-src/guides/backends/sftp.md` Legacy Servers section: version-split framing (`< 5` vs `>= 5`); new "Diagnose first" subsection introduces `scan_host_algorithms` as the triage step; the "Alternative: pin" tradeoff names `paramiko<5` (the `<3` alternative previously listed was version-shifted and also conflicted with the `>=3.0` floor).
3. `_map_exception` IncompatiblePeer branch: host-key variant carries the `enable_ssh_rsa_compat` hint (gated on `"host key"` substring); KEX / cipher / MAC variants carry a hint pointing at `scan_host_algorithms` + `connect_kwargs={"disabled_algorithms": ...}` (BK-200).
4. `SFTPUtils.scan_host_algorithms(host, port)` (BK-200): new raw-socket SSH KEXINIT probe; companion to `scan_host_keys`. Returns the server's full algorithm advertisement (kex / host-key / cipher / MAC / compression name-lists) so users can identify which negotiation list the server narrowed before reaching for a remedy. E2E-tested against the legacy-sftp Docker fixture (asserts `server_host_key_algorithms == ["ssh-rsa"]`).
5. `tests/e2e/test_sftp_legacy_recovery.py::test_S1_bare_connect_*` parametrised on `paramiko.__version__`: expects success on `< 5`, `IncompatiblePeer` on `>= 5`.
6. `sdd/BACKLOG-DONE.md` BK-198 entry + `sdd/traces/BK-198-ssh-rsa-compat.yml` trigger: corrected to the version-conditional framing.

---

## 5. Decision: no library-side `paramiko<5` cap

PR 613 deliberately keeps the `[sftp]` extra at `paramiko>=3.0` with **no
upper bound**, after weighing the alternatives.

| Option | Pro | Con |
|---|---|---|
| Add `<5` cap to `[sftp]` extra | Fresh installs do not hit the legacy-server failure on day one | Locks every consumer out of paramiko 5+ (security fixes, protocol improvements, the eventual paramiko 6 floor) regardless of whether they ever touch a legacy server. Cap becomes load-bearing and decays. |
| Opt-in `BackendConfig` flag (`allow_legacy_ssh_rsa: bool`) | Expresses intent in config | Adds public API surface that only matters to a narrow audience; still process-global underneath (mutates paramiko class attrs); per-backend solution would need a Transport subclass (the T40 follow-up). |
| **No cap; helper + diagnostic + scoped hint (chosen)** | Library evolves with paramiko; consumers who never touch legacy servers pay nothing; `scan_host_algorithms` + `enable_ssh_rsa_compat` + the `IncompatiblePeer` hint make the failure self-explanatory when it does occur | First-time hit on a legacy server is a runtime failure, not an install-time guard |

The chosen option keeps the cost on the population that hits the
failure (a runtime `IncompatiblePeer` with a hint pointing at the
diagnostic) rather than on the population that doesn't (every other
consumer of `[sftp]`). A consumer-side pin (`paramiko>=3.0,<5` in
`requirements.txt`) remains available for environments where calling
the helper at startup is not an option — documented in the SFTP
backend guide's "Alternative: pin `paramiko<5`" subsection.

The decision is recorded here rather than as an ADR because there is
no architecture-level commitment beyond this single dependency line;
the relevant context is the empirical evidence in §§ 1–4 above. If
the policy changes (e.g. paramiko 6 forces a re-evaluation), update
this section together with the `pyproject.toml` line.

---

## 6. Open questions / follow-ups

- **Dependency policy.** The `[sftp]` extra currently pins `paramiko>=3.0` with no upper bound, so fresh installs resolve to paramiko 5.x and need the helper. Whether to add a `<5` ceiling, an opt-in `BackendConfig` flag, or rely on the documented helper + hint is a separate decision tracked in PR 613 review.
- **Per-backend opt-in.** The helper mutates paramiko's class attributes process-wide. For multi-backend processes that talk to a mix of modern and legacy SFTP servers, a per-Transport-subclass opt-in would scope the SHA-1 acceptance to one backend. Tracked as a non-blocking follow-up in the BK-198 trace's `discovery_followups`.
- **CI drift guard.** The 4.x → 5.x ssh-rsa removal is the second transitive-bump incident the PR addresses (BUG-204 = the 2.x → 3.x `channel_timeout=` API surface). A scheduled CI job that re-resolves `[<extra>]` against `pip install --upgrade --pre` and runs the legacy-sftp e2e against each delta would catch the next one before users do. Tracked as a non-blocking follow-up in the BK-198 trace's `discovery_followups`.

---

## Appendix: probe script

The probe lives at `tmp/paramiko5-probe/probe.py` (not committed — Docker rig is regenerated as needed; see `tests/e2e/test_sftp_legacy_recovery.py` for the durable integration test).

Probe sketch:

```python
def snapshot() -> dict:
    t = paramiko.Transport
    return {
        "paramiko": paramiko.__version__,
        "_preferred_keys": list(t._preferred_keys),
        # ... and three more sites
    }

def clear_ssh_rsa() -> None:
    t = paramiko.Transport
    t._preferred_keys = tuple(k for k in t._preferred_keys if k != "ssh-rsa")
    # ... and three more sites

def main() -> int:
    print(snapshot())
    print(try_connect("S1_bare"))
    enable_ssh_rsa_compat()
    print(try_connect("S2_helper_on_defaults"))
    clear_ssh_rsa()
    print(try_connect("S3_after_clear"))      # fails: no acceptable host key
    enable_ssh_rsa_compat()
    print(try_connect("S4_recovery"))         # succeeds
```

Per-venv run: `tmp/paramiko-test/v<ver>/Scripts/python.exe tmp/paramiko-test/probe.py`.
