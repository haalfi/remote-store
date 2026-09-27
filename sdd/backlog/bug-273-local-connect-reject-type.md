# BUG-273 — A locally-rejected SFTP connect answers the wrong type, and neither permission errno can be claimed without connect-time context
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

BUG-265 gave `_map_exception` a connect-time arm for the unreachable-host
errnos and deliberately left **both** permission errnos out of it. This is
that exclusion, recorded rather than left for the next reader to re-derive.
**`EPERM` was tried and reverted inside BUG-265, which is the sharpest
evidence this item has.** A round of review found a firewall-rejected connect
answering the base `RemoteStoreError` and argued `EPERM` was free to claim,
because `_map_exception`'s errno dispatch had no `EPERM` arm. That premise was
true of the dispatch **as it then stood** and false of the module, and the
next round measured it:
`_raise_if_dir` re-raises **both** permission errnos on purpose
(`_sftp.py`, the classification-stat guard, and its docstring says why), from
a **working** channel, inside the caller's `_errors(path)` block. Driving the
exact shape `test_raise_if_dir_permission_stat_maps_permission_denied` uses:
`EPERM` gave `RemoteStoreError` before the change and
`BackendUnavailable("[Errno 1] Permission denied")` after it, **and with a
sentinel seeded the new arm cleared the cached client** — so a healthy
connection was discarded on a server-reported denial. **The grounds matter
and were first stated too strongly:** the published v0.29.1→v0.30.0 migration
row promising `PermissionDenied` for that stat was *already* not honoured for
`EPERM` before the change and is not honoured after it, which was BUG-275, not
this item. What claiming `EPERM` did was move that path from the base class to
`BackendUnavailable` plus a client reset — worse, and enough on its own.
Reverted; `test_the_permission_errnos_stay_out_of_the_connect_arm`
now pins the exclusion so a future widening fails loudly instead of silently
changing what a live channel reports.
**BUG-275 has since shipped and made this item simpler, not harder.** The
errno dispatch now has an `EPERM` arm, so **both** permission errnos answer
`PermissionDenied`, and a locally-rejected connect is answered identically for
each — `PermissionDenied` naming the caller's key, or a bare `Permission
denied: ` from `check_health`. The two halves this item used to carry
separately are now one shape, so one fix closes both; the `EPERM` half is no
longer "the base class" as the measurement above records.
**What did not change is the exclusion from `_is_unreachable`**, and its
evidence is now per errno. `EACCES` has a live-channel producer: paramiko's
`SFTPClient._convert_status` renders `SSH_FX_PERMISSION_DENIED` as
`IOError(EACCES)` (paramiko 5.0.0). **`EPERM` has none known** — that
*renderer* has no arm producing it, and no SFTP status code maps to it; not to
be confused with `_map_exception`'s errno dispatch, which SFTP-021 now gives
an `EPERM` arm — and what keeps it out is that claiming it would take
away the `PermissionDenied` SFTP-021 now guarantees and clear the cached client
with it.
**The trigger asymmetry is what remains of the two halves**: the `EPERM` shape
is reproducible (a netfilter `REJECT` on the `OUTPUT` chain), the `EACCES` one
is not, so the `EPERM` shape is the one to build the fix against and the
`EACCES` one comes along with it.
**The answer this item must change is pinned**, so closing it fails a test
rather than silently altering a published type:
`test_a_locally_rejected_connect_is_answered_as_a_denial` asserts today's
answer for both errnos, on a keyed operation and on `check_health`. Its two
parametrizations must go red together — them being alike is the property that
lets one fix reach both.
**The lesson for whoever picks this up:** "nothing else wants this errno" is a
claim about the whole module, not about one if-chain, and `rg -n 'EPERM' src/
docs-src/` is the derivation. Both errnos are one problem, not two.
**What was measured**, by monkeypatching `socket.socket.connect` to raise a
chosen errno and driving `paramiko.SSHClient.connect` on paramiko 5.0.0:
`EACCES` is re-raised unwrapped, exactly like `ENETUNREACH` / `ENETDOWN` /
`EHOSTDOWN` (`SSHClient.connect` captures only `ECONNREFUSED` and
`EHOSTUNREACH` into `NoValidConnectionsError`; its own docstring says so). It
therefore reaches the mapping as a plain `PermissionError` and takes the
`EACCES` arm. Measured per operation, since the two answers differ:
`read_bytes("delivery.csv")` and `exists("delivery.csv")` answer
`PermissionDenied("Permission denied: delivery.csv")`, while `check_health()`
— which runs under `_errors()` with no key — answers a bare
`PermissionDenied("Permission denied: ")`. That is BUG-265's own defect shape,
a caller following the health-check guide catching the wrong type, in two
flavours: on a keyed operation the message names a path as the subject of a
failure the path had no part in, and on the probe it dangles a colon with
nothing after it — the shape
`test_a_message_less_dns_failure_does_not_trail_an_empty_colon` exists to
prevent on the sibling arm.
**What was NOT measured, and it is the item's open question:** that any real
network produces `EACCES` on `connect()`. **No trigger is known**, and the
first work here is finding one. An earlier revision of this item offered
`iptables --reject-with icmp-admin-prohibited`; that is wrong and is recorded
here so it is not tried twice. It sends ICMP type 3 code 13, which Linux's
`icmp_err_convert` maps to `EHOSTUNREACH` — an errno BUG-265 already put in
`_is_unreachable`'s tuple, so following that recipe lands on the new arm and
shows nothing. A local `OUTPUT`-chain `REJECT` yields `EPERM`, also not
`EACCES`. `EPERM` **does** have that trigger, which is what made it tempting;
it is not a reason to claim it. If no `EACCES` trigger exists, that half is a
documentation item rather than a code one.
**What it costs a caller if left, and BUG-275 changed the answer.** It used to
be nothing observable: the `EACCES` half has no producer anyone has found, and
the `EPERM` half — which a netfilter `REJECT` on the `OUTPUT` chain does
produce — answered the base class, so no caller met the wrong *type*. Since
the errno dispatch gained its `EPERM` arm, that shape answers
`PermissionDenied` naming the caller's key, or a bare `Permission denied: `
from `check_health`. So the cost is **observable today, on the half a reader
can reproduce**: someone following the health-check guide's
`except BackendUnavailable` catches nothing and lands in a permissions handler
for a request that never left the machine. **That raises the priority and
leaves the diagnosis where it was.** The item also carries a measurement worth
keeping either way: the next person to consider widening `_is_unreachable`'s
tuple finds here why that breaks a working channel, instead of rediscovering
it the way BUG-265 did across two rounds.
**The shape also pays the connect budget twice, and the fix here is what would
end that too.** Measured by patching `_connect` to raise the errno and counting
invocations, at both `2a1bbfe` and this branch's head: `read_bytes` and
`delete` cost **two** connects, `read` / `exists` / `check_health` one, and
`ECONNREFUSED` costs one everywhere. `_probe_is_futile` does not claim a
permission errno, so the caller's guard declines and `_raise_if_dir` re-enters
the lazy `_sftp` property for a second full budget. **Pre-existing and
unchanged by BUG-275** — the counts are identical on both revisions, and only
the *type* moved — but it is the same waste BUG-274 closed for unreachable
hosts, and classifying at `_connect` (the disposition below) removes it by
construction rather than needing a second widening.
**Disposition:** not widening the tuple — that was tried and measured harmful,
above. The same errnos on a live operation genuinely are a denied path
(`test_eacces_maps_to_permission_denied` and
`test_the_two_permission_errnos_answer_alike_on_every_entry_point` pin
them), and `_map_exception` dispatches on the exception alone, so it cannot
tell a connect-time one from an operation-time one. The cheap shape is for the
lazy `_sftp` property to classify what `_connect` raises **before** the
caller's `_errors(path)` block sees it, which reaches both errnos at once and
is the only place the connect-time context exists.
**Found by BUG-265's round-3 measuring member**, which reported the `EACCES`
half as a `Possible: Bug:` with its trigger flagged unreproduced; the `EPERM`
half was found, fixed and reverted across its rounds 5 and 6.
