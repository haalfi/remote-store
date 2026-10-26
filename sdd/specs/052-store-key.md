# 052: Store Key Specification

## Overview

A caller's input is reduced, by the string and the store's configuration
alone, to one key string in [spec 051](051-store-tree.md)'s Key shape, or
refused; resolution then answers one of four outcomes for that key string
against the store's state. Reduction walks the input from the store's root, so `.` and `..`
navigate and an escape above the root is refused; it accepts only where the
walk ends, against a language the backend can hold unchanged.

Scope: the reduction ν, the equivalence it decides, the languages it accepts
against, and resolution Ω. Every section is a function: of the input and the
configuration for ν, of the Key and one state for Ω; what the spec relies on
from a backend is in its assumptions. Out of scope, each with its owner:

- Which operations accept the root, and which error or result an outcome
  becomes: each operation's own spec.
- How a caller sets and reads the separator set, the acceptance choice and
  P_b, how a P_b smaller than L_shared is announced, and the type that carries
  a key: the API's spec.
- What a listing yields for a stored name outside L_api, and a write that
  would put two names equal under a backend's coarser name equality side by
  side: the listing and write operations' specs, under spec 051 § Name
  equality.
- What a store rooted at a key c reports for an outcome's kⱼ that lies above
  c: the spec of the operation that makes such a store.
- Each backend's L_b and P_b: the
  [profile table](profiles/052-store-key.md) beside this spec, by measurement
  or a cited authority.
- How a key is displayed, the root included: the API's spec. `glob`
  patterns: the `glob` operation's spec.

**Supersedes** [spec 004](004-path-model.md) PATH-002 to PATH-008.

## Terms

Spec 051's terms are used unchanged: Σ\*, ε, N, the store tuple S =
(U, F, I, r, C, name), Key (TREE-009) and kind, with F and I the folders and
items. Names compare exactly (spec 051 § Name equality).

| Term | Meaning |
| --- | --- |
| Σ | The Unicode scalar values: every code point except the surrogates U+D800 to U+DFFF. |
| Input | A string of code points passed as a key; it may hold a surrogate. |
| Quoted input | Read literally, except that `␀` stands for U+0000 and `\ud800` for that surrogate; every other `\` is a backslash. |
| Key string | ε, or one or more names of N joined by `/`: TREE-011's Key shape. L_core is the set of them. |
| Segments | Of a key string k = s₁/…/sₙ, the names (s₁, …, sₙ); ε has none. kᵢ = s₁/…/sᵢ is its prefix of length i, k₀ = ε. |
| Sep | The store's separator set: {`/`, `\`} or {`/`} (KEY-009). |
| Navigation segment | A segment of an input split on Sep that is empty or equals `.` or `..`. A segment merely containing dots, such as `a..b`, `...` or `.hidden`, is a name. |
| Position | A finite sequence of names; the empty sequence is the root. |
| Base c | The key string a reduction starts from: ε for the store itself, or the key string c of a store rooted at c. |
| L_floor | The key strings none of whose segments holds U+0000 or `\`, or equals `.` or `..`. |
| L_b | The store's backend language: a prefix-closed subset of L_core declared for the store's backend b at the store's location. A whole-key limit of b counts the location's own share, so L_b gets what the location leaves of it. That b honours it is KEY-A-02. |
| L_shared | The portable language: ε, and the key strings `PORTABLE_KEY` below fully matches. It is a library policy and names no backend. |
| P_b | The store's portable set: a prefix-closed subset of L_shared declared explicitly for the store's backend at the store's location, never inferred. P_b = L_shared is the normal value; a smaller P_b is a declared deviation. That b honours it is KEY-A-03. |
| L_api | The store's acceptance language (KEY-008). |
| c · k | The key string whose segments are c's followed by k's; ε · k = k · ε = k. |
| K(S) | The Keys of S: { Key(x) │ x ∈ U }. |
| ν_c(p) | The reduction of input p from base c: a key string, or refused (KEY-001). |
| p ≈ q | p and q are equivalent: neither is refused by KEY-002, neither walk escapes, and both end at the same position. |
| Ω_S(k) | The resolution of key string k against store S (KEY-013). |
| Store rooted at c | For c ∈ L_api of a store S: the store that reduces inputs by ν_c and resolves its key string k as Ω_S(c · k), with S's Sep and L_api. At c = ε it is S. |

`PORTABLE_KEY`, in Python `re` syntax, is the definition of L_shared; a name in
it is a portable name.

```text
PORTABLE_NAME = (?!(?i:CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:[./]|\Z))[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9_-])?
PORTABLE_KEY  = (?=[ -~]{1,255}\Z)PORTABLE_NAME(?:/PORTABLE_NAME)*
```

---

## Reduction

### KEY-002: Input Refusal

**Invariant:** ν_c(p) is refused when p holds U+0000, a surrogate, or, when
`\` ∉ Sep, a `\`, wherever it stands in p, a segment the walk would drop
included.

### KEY-003: The Walk

**Invariant:** An input not refused by KEY-002 is split on Sep and read from the
empty position, one segment at a time:

| Segment | Step |
| --- | --- |
| a name | append it |
| `..` | drop the last name; at the empty position the walk escapes |
| `.` or empty | stay |

### KEY-004: Escape Refusal

**Invariant:** ν_c(p) is refused when the walk of p escapes, from every base c;
an escape is never clamped to the root.

### KEY-005: Acceptance at the End

**Invariant:** For a walk of p that ends at position (s₁, …, sₙ), ν_c(p) is
s₁/…/sₙ (ε when n = 0) if c · s₁/…/sₙ is in L_api, and refused otherwise; a
name the walk drops is never judged.

---

## Acceptance

### KEY-008: Acceptance Language

**Invariant:** L_api is L_floor ∩ L_b, unless the store opts into portability,
when it is P_b; a store opts in only where its P_b is declared, and the choice
is part of the store's configuration.

### KEY-009: Separator Set

**Invariant:** Sep is {`/`, `\`} by default and on every backend whose profile
treats `\` as a separator; on any other backend a store may opt out to {`/`}.

---

## Derived

### KEY-001: Totality

**Invariant:** For every input p and base c ∈ L_api, ν_c(p) is exactly one key
string or refused, and is a function of p, c, Sep and L_api alone, never of the
store's state.

### KEY-010: Canonical Fixed Point

**Invariant:** ν_c(k) = k for every key string k with c · k ∈ L_api, ε
included: every key ν returns reduces to itself when passed back.

### KEY-011: Equivalence

**Invariant:** For inputs p, q that ν_c accepts, p ≈ q exactly when
ν_c(p) = ν_c(q).

### KEY-012: Composition

**Invariant:** A key a store rooted at c accepts is the key its parent store
accepts for the composed input: if ν_c(p) = k then ν_ε(c/p) = c · k.

---

## Resolution

### KEY-013: Resolution Outcomes

**Invariant:** For k ∈ L_api with n segments and a store S, let j be the
largest i ≤ n with kᵢ ∈ K(S) and e the entity whose Key is kⱼ; Ω_S(k) is
exactly one of:

| Case | Ω_S(k) |
| --- | --- |
| j = n | Found(e, kind(e)) |
| j < n, e ∈ I | BlockedByItem(kⱼ) |
| j = n − 1, e ∈ F | Absent |
| j < n − 1, e ∈ F | AbsentAncestor(kⱼ) |

---

## Assumptions

| ID | Assumption |
| --- | --- |
| KEY-A-02 | The store's backend holds every key string of L_b, and stores each of its names unchanged, judged for each name as the last segment of the prefix that ends in it. |
| KEY-A-03 | The store's backend holds every key string of its declared P_b, and stores each of its names unchanged. |

## Notes

Not normative. The model, its decisions and the counterexample behind each
rule are [`research-key-model.md`](../research/research-key-model.md) §§ 3 to
6; the proofs below are in [`KeyModel.lean`](../formal/lean/KeyModel.lean),
which imports spec 051's own definitions from `StoreAxioms.lean`. Its inputs
range over Σ, so KEY-002's surrogate arm is checked by the reference model
alone.

- **Axioms and lemmas.** KEY-002 to KEY-005, KEY-008 and KEY-009 define ν,
  and KEY-013 defines Ω; KEY-001 and KEY-010 to KEY-012 follow. KEY-006,
  KEY-007 and KEY-A-01 are unassigned. KEY-001 holds by construction, ν being
  a total function of those parameters (`nu`). KEY-010 is K2 (`nu_fixed_point`), KEY-011 is K3
  (`nu_decides_equiv`), KEY-012 is K6 (`child_compose`) with K4
  (`join_continuation`), and KEY-013's cases are exhaustive by K10
  (`resolution`, `occupied_take`); their disjointness follows from arithmetic
  and TREE-001. Every key ν returns has TREE-011's shape and lies in L_floor
  (K1, `nu_output`, `nu_key_shape`).
- **Why the input refusals read the raw input.** Checked on the end position
  instead, `a\a/..` would mean ε by default and `a` after an opt-out, and
  `x␀/..` would denote the root. An opt-out therefore only refuses more: what
  ν accepts with Sep = {`/`} it accepts with the same result under {`/`, `\`}
  (K5, `opt_out_only_rejects_more`).
- **`\` is never a name character.** Where it is not a separator it is
  refused, so one input never means two keys in two stores of one backend.
  A stored name holding `\`, U+0000, a surrogate, or equal to `.` or `..`, or
  outside L_b, can exist in a backend and is not addressable through ν.
- **The root.** ε is a key string and ν_c(p) = ε for every input that walks
  back to the base; Ω_S(ε) is Found(r, folder) in every store (TREE-002,
  TREE-009). Whether an operation accepts the root is that operation's own
  clause.
- **Resolution's outcomes.** BlockedByItem is apart from Absent because no
  write below an item can succeed: no Key extends an item's Key (K11,
  `item_has_no_extension`). Absent tells "create in place" from
  AbsentAncestor's "create with the missing folders".
- **A store rooted at c.** It is defined by composition (Terms), so it never
  disagrees with S about one entity. At a folder c it is a store per spec 051
  of its own, the subtree below c (K12, `child_view`); at an absent or item c
  it has none, and every key below its root resolves as AbsentAncestor or
  BlockedByItem. Acceptance runs on c · k (KEY-005), so a whole-key limit can
  refuse under c a k it accepts alone. A join k ⊕ p = ν_ε(k/p) continues the
  walk: (k ⊕ p) ⊕ q = k ⊕ (p/q) whenever k ⊕ p is accepted (K4).
- **Examples.** The examples behind each section, such as `x␀/..` refused
  rather than ε, `../b` refused from base `a` although ν_ε(`a/../b`) = `b`,
  and ν_ε(`CON/../a`) = `a` where `CON` is outside L_b, are cases of the
  reference model's tests, each marked with its section.
- **No Unicode normalisation or case folding.** Every name of ν_c(p) is a
  segment of p, code point for code point. A backend with a coarser name
  equality (case-insensitive, normalising) still holds both `A` and `a`; that
  they conflict as siblings is spec 051 § Name equality's, a constraint on the
  state rather than on a key string.
- **L_shared.** A policy that `PORTABLE_KEY` defines, not a derivation from
  any set of backends, and no backend is promised to hold it. Each rule has
  its own reason. A portable name is ASCII letters, digits, `.`, `_` and `-`:
  beyond ASCII, stores differ in whether a composed and a decomposed spelling
  are one name or two, in how case-insensitive comparison folds a letter, and
  in whether a length counts bytes or UTF-16 units, while an ASCII character
  has one spelling, one fold, and is one byte and one unit. Σ stays the
  Unicode scalar values: by default a store accepts every name of L_floor its
  backend's L_b holds, `café` included (KEY-008), and only the opt-in
  narrows to ASCII. A name
  starts with a letter or digit, so no tool reads it as hidden or as an
  option; it ends in neither `.` nor a space, the endings a store that strips
  them would alias; it is no reserved device name (`CON`, `PRN`, `AUX`,
  `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9` after Microsoft's "Naming Files, Paths,
  and Namespaces", widened by the digit 0 to `COM0` and `LPT0`, alone or
  before a `.`); and a key is at most 255 characters. Every portable name is
  a name of L_floor, and every key in L_shared is its own reduction.
  `sdd/research/bk-468-key-probe/check_portable_regex.py` checks the patterns
  against that gloss.
- **P_b.** Under the opt-in a store accepts its backend's portable set: the
  whole of L_shared where the backend holds it, otherwise the subset declared
  for it, so a key the backend could not hold is refused by ν, not at the
  backend. A smaller P_b is a declared deviation from the normal value
  L_shared, never a silent one; a portable store therefore refuses on one
  backend a key it accepts on another only where a declaration says so.
- **Backend languages as a profile table.** Each backend's L_b is recorded
  per axis beside this spec, every cell citing its source
  ([RFC-0024](../rfcs/rfc-0024-spec-first-reset.md) D6). `SPEC-DESIGN.md`
  Rule 5 asks for a capability or a driver flag instead; how a store shows
  its language to a caller is the API's spec.

## Tested against

A reference model of ν, Ω and the profile table's columns, with its property
tests, in `tests/test_store_key_model.py`; run with
`python scripts/run_tests.py tests/test_store_key_model.py`. `KeyModel.lean`
restates the sections and informs review; no bridge makes it govern. Build it
with `bash scripts/lean_check.sh`.
