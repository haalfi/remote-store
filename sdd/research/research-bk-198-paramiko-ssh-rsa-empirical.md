# Research: paramiko `ssh-rsa` host-key compatibility — empirical findings (BK-198)

**Date:** 2026-05-12
**Status:** Complete; corrected the BK-198 framing in [PR 613](https://github.com/haalfi/remote-store/pull/613).
**Scope:** Verify the empirical premise of `SFTPUtils.enable_ssh_rsa_compat()` against a Dockerized legacy SFTP server across four paramiko versions, before locking in the docstring / guide / hint-message wording.
**Related:** [BK-198](../BACKLOG-DONE.md), [trace](../traces/BK-198-ssh-rsa-compat.yml), [PR 613](https://github.com/haalfi/remote-store/pull/613).

**Context.** The first cut of BK-198 was reasoned out from one data point (paramiko 4.0.0 import surface) and shipped a helper whose docstring claimed "Paramiko 3.x+ removed `ssh-rsa` from defaults at four levels." A PR reviewer challenged that premise. This note is the proper empirical test that should have happened first: a four-version client matrix probing a server that mirrors the failure shape the user originally reported, with every claim in the PR re-derived from the observed behavior.

---

## 1. Test rig

Two Docker images, both forcing the legacy-server shape:

| Image | Forcing | Port |
|---|---|---|
| `legacy-sftp:test` | Only `ssh-rsa` host-key + pubkey algorithms; modern KEX defaults | 2222 |
| `legacy-sftp:kex` | Same as above PLUS `KexAlgorithms diffie-hellman-group14-sha1,diffie-hellman-group1-sha1` | 2223 |

Image 2 mirrors the user's originally-reported `IncompatiblePeer: no acceptable kex algorithm` shape more faithfully than image 1.

Client matrix: four isolated `uv` venvs, all on Python 3.11, all sharing `cryptography==48.0.0`, varying only paramiko:

- `paramiko==2.12.0` (last 2.x release)
- `paramiko==3.0.0` (claimed cut-off in the original PR docstring)
- `paramiko==3.5.0` (mid-3.x sanity check)
- `paramiko==4.0.0` (current `[sftp]` floor)

Probe script (`tmp/paramiko-test/probe.py`, see appendix) snapshots paramiko's class-level state and runs four scenarios in sequence per venv:

| ID | Scenario | What it tests |
|---|---|---|
| S1 | Bare connect on paramiko defaults | Does the legacy server connect out of the box? |
| S2 | Connect after `enable_ssh_rsa_compat()` on defaults | Is the helper a no-op when defaults already contain `ssh-rsa`? |
| S3 | Strip `ssh-rsa` from all four sites, then connect | Reproduces the cleared-defaults state |
| S4 | Run helper after S3, then connect | Does the helper actually recover? |

---

## 2. Findings

### 2.1 Default `_preferred_keys` and `RSAKey.HASHES` across versions

All four paramiko versions ship `ssh-rsa` at every site the helper touches:

| Site | 2.12.0 | 3.0.0 | 3.5.0 | 4.0.0 |
|---|---|---|---|---|
| `Transport._preferred_keys` | present | present | present | present |
| `Transport._preferred_pubkeys` | present | present | present | present |
| `Transport._key_info["ssh-rsa"]` | present | present | present | present |
| `RSAKey.HASHES["ssh-rsa"]` | present | present | present | present |

The only inter-version difference relevant to BK-198 is that paramiko 4.0 dropped `ssh-dss`; `ssh-rsa` itself has not been removed.

### 2.2 Connection outcomes per scenario

Identical across all four paramiko versions against both server images:

| Scenario | Outcome |
|---|---|
| S1 (bare) | ✅ Connect + open SFTP subsystem succeed |
| S2 (helper on defaults) | ✅ Succeeds; helper guards all short-circuit (no-op) |
| S3 (cleared, then bare) | ❌ `paramiko.ssh_exception.IncompatiblePeer: Incompatible ssh peer (no acceptable host key)` |
| S4 (cleared, then helper, then connect) | ✅ Helper re-adds `ssh-rsa`; connection succeeds |

The S3 error string is byte-identical across paramiko 2.12 and 4.0 — same handler in `Transport._parse_kex_init`.

---

## 3. What this falsifies in the original PR

1. **"Paramiko 3.x+ removed `ssh-rsa` from defaults at four levels."** False on every tested version. `ssh-rsa` is *deprecated* (slated for future removal) but still ships in all four defaults.
2. **"`SFTPUtils.enable_ssh_rsa_compat()` is required for legacy SFTP servers."** False as stated. Paramiko's defaults already negotiate against an `ssh-rsa`-only server. The helper is required only when `ssh-rsa` has been cleared from the four sites — which is not the case for a freshly-imported paramiko.
3. **The IncompatiblePeer hint always pointing at the helper.** `IncompatiblePeer` wraps any of `no acceptable {host key, kex algorithm, cipher, MAC}` failures. The helper only addresses the first. A blanket hint misleads users hitting the other three.

## 4. What this confirms

1. **The helper is mechanically correct.** When `ssh-rsa` IS missing from the four sites (S3 setup), it cleanly restores all four entries and the connection works (S4).
2. **The "recovery + forward-compatibility" framing** in the corrected docstring matches reality: helper is a no-op on a clean process, only changes behavior when defaults have been mutated or removed.
3. **The user's empirical fix was real but not for the reason the original PR claimed.** Their environment must have had upstream code (legacy `aha_utils.sftp` or similar) that cleared `ssh-rsa` from paramiko's class attrs at import time. The helper recovered that state. Without that prior mutation the helper does nothing on paramiko ≥2.12.

---

## 5. Changes derived from this verification

Tracked in PR 613 commit `43be100e3` ("BK-198: empirical verification + scoped IncompatiblePeer hint"):

1. `_map_exception` IncompatiblePeer branch: hint gated on `"host key"` substring; KEX / cipher / MAC variants pass through as plain `BackendUnavailable`.
2. `enable_ssh_rsa_compat` docstring: dropped the "removed from defaults" framing; lists the paramiko versions verified; redirects KEX/cipher/MAC failures at `connect_kwargs.disabled_algorithms`.
3. `docs-src/guides/backends/sftp.md` Legacy Servers section: matches the docstring framing; inline KEX-failure pointer added.
4. `sdd/BACKLOG-DONE.md` BK-198 entry + `sdd/traces/BK-198-ssh-rsa-compat.yml` trigger: corrected to the empirical framing.
5. New test `test_incompatible_peer_no_hint_for_kex` locks the conditional hint.

---

## 6. Open questions / follow-ups

- **Real-world utility unknown.** The helper now exists for a recovery scenario whose origin we haven't identified. We never reproduced the cleared-defaults state from any in-tree code path. The user's case suggests some libraries DO clear `ssh-rsa` at import time (legacy `aha_utils.sftp` is a candidate), but we have no enumeration. Worth filing as a follow-up: a brief enumeration of which Python libraries are known to mutate paramiko's `ssh-rsa` defaults on import.
- **No assertion of a specific paramiko removal date.** The docstring and guide say "future major release" without committing to a specific paramiko version. If paramiko 5 announces concrete removal, the wording should be updated.

---

## Appendix: probe script

The probe lives at `tmp/paramiko-test/probe.py` (not committed — Docker rig is regenerated as needed; see `tests/e2e/test_sftp_legacy_recovery.py` for the durable integration test).

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
