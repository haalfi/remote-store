# Dependency and version policy

What `remote-store` commits to about the packages it pulls into your
environment, and about the compatibility of its own API across releases.

Each rule states an obligation, the reason it exists, and what it costs or buys
you. Where a rule is not backed by a mechanism, it says so.

## Installation

<a id="rule-1"></a>
### Rule 1. The core package declares no runtime dependencies

**Why:** a storage abstraction should not decide your dependency tree.

**For you:** `pip install remote-store` adds one package. Anything else in your
environment, you asked for.

<a id="rule-2"></a>
### Rule 2. Installing one extra never installs another's dependencies

**Why:** the alternative is shipping an SSH client to someone who wanted S3.

**For you:** the failure is deferred to runtime rather than caught at install.
What it looks like depends on where the missing package is reached: an
extension names the extra to install, a storage backend reports the missing
module itself, and a backend whose import is swallowed at registration
surfaces later as an unknown backend type. The
[troubleshooting guide](../guides/troubleshooting.md#importerror-for-optional-dependencies)
maps each symptom to the extra that fixes it, and the
[extensions guide](../guides/extensions.md) covers the extension case.

<a id="rule-3"></a>
### Rule 3. Conda carries the same constraints, in the only form it has

**Why:** conda has no equivalent of extras, so the recipe restates each
constraint as a plain bound.

**For you:** `conda install` brings the core package only, and a backend's
dependencies are yours to name alongside it. The recipe's constraints bound
what you install; they pull in nothing. A feedstock also trails its upstream
release, so the channel can sit a release behind PyPI with constraints that
predate the ranges here. What the channel serves is compared weekly against what
this project published for the version the channel is on, and a difference is
reported rather than corrected — the recipe lives in a repository this project
does not own, so the comparison is a watch on that copy, not a guarantee about
it. The
[README's installation section](https://github.com/haalfi/remote-store#installation)
has the practical form.

## Version ranges

<a id="rule-4"></a>
### Rule 4. Every extra declares a floor

**Why:** a range with no lower bound lets a resolver pick a version that cannot
work.

**For you:** a resolver refuses rather than installing a version we know fails.

<a id="rule-5"></a>
### Rule 5. A ceiling is added only against a published, known break

**Why:** a speculative ceiling is invisible when it is right and unfixable when
it is wrong. It silently excludes `remote-store` from your resolution the
moment an upstream ships a major that would have worked, and you cannot
override it without forking. A missing ceiling fails loudly and locally.

**For you:** an upstream major can break you before we cap it. You can pin that
package yourself; you could not un-pin ours.

<a id="rule-6"></a>
### Rule 6. An upstream break we can absorb is absorbed, not capped

**Why:** a cap charges every user for a problem only some of them have.

**For you:** the SFTP backend is the worked example. A major release changed
which host-key algorithms are enabled by default; rather than pin the library
for everyone, the backend ships an opt-in compatibility helper and a diagnostic
that reports what a given server accepts. Users on modern servers pay nothing.

<a id="rule-7"></a>
### Rule 7. The authoritative ranges are in `pyproject.toml`, not on this page

**Why:** a list kept by hand goes stale the moment a bound is added or lifted.

**For you:** the ranges are published on
[Tested versions](../reference/tested-versions.md), rendered from
`pyproject.toml` by a generator a gate keeps in step — so that page cannot go
stale the way a hand-kept one would, and this rule is about hand-keeping rather
than about publishing. Read
[`pyproject.toml`](https://github.com/haalfi/remote-store/blob/master/pyproject.toml)
itself when you want the *reasoning*: each range carries the measurement behind
it in a comment. Development and documentation build extras sit outside this
convention and may pin tooling directly; they never reach your environment.

## Support windows

<a id="rule-8"></a>
### Rule 8. A Python version is supported for as long as it gets security fixes

**Why:** the line worth drawing is the one upstream already draws. CPython
publishes source-only security releases for five years after a version's first
release, and a version still receiving them is one you can reasonably still be
running. [SPEC 0](https://scientific-python.org/specs/spec-0000/), the
Scientific Python ecosystem's time-based support policy, sets a shorter floor of
three years; we name it because it is the schedule your *other* dependencies
drop on, so you can see where ours sits relative to theirs. Ours is the longer
of the two.

**For you:** the chart is the rule. Each bar runs from a version's first release
to the end of its security support, SPEC 0's three-year minimum is marked inside
it, and the vertical line is today.

```mermaid
--8<-- "docs-src/_data/python-support-window.mmd"
```

Which versions are supported *right now* is the `Programming Language :: Python`
classifiers in
[`pyproject.toml`](https://github.com/haalfi/remote-store/blob/master/pyproject.toml),
the same hand-off [Rule 7](#rule-7) makes for dependency ranges. The chart is
drawn from those classifiers, so it cannot disagree with them. That makes the
earliest a version can be dropped computable in advance rather than something
you read out of our release notes, and the window is
[watched weekly](#how-the-ranges-are-watched) so the date is reported rather
than noticed. We may support a version past the end of its security support; we
will not support one for less.

<a id="rule-9"></a>
### Rule 9. A supported dependency version stays supported at least 2 years

**Why:** the same SPEC 0 cadence, applied to the packages behind the extras.
The window runs from that dependency's own initial release, not from ours.

**For you:** a floor may be raised in any release, including a patch, as long
as every version it newly excludes is itself at least 2 years past its own
release. Excluding a version younger than that is a breaking change and takes
the path in [Rule 11](#rule-11).

A check at release time derives that test rather than leaving it to be
remembered. It compares every extra's floors against the previous release's,
and for each floor that moved it names the newest version the raise newly
excludes and how old that version's own release is, so the answer is a
measurement rather than a recollection.

<a id="rule-10"></a>
### Rule 10. Security fixes go to the latest release only

**Why:** one maintained line is one that actually gets fixed.

**For you:** staying current is the security posture. See
[SECURITY.md](https://github.com/haalfi/remote-store/blob/master/SECURITY.md).

<a id="stability-tiers"></a>
## API compatibility

The public API is everything exported from `remote_store` itself, meaning
`__all__` on the top-level package. Anything reachable only through a private
module is internal and may change in any release.

| Label | Meaning |
|-------|---------|
| **Alpha** (pre-0.11) | API may change freely between releases |
| **Beta** (0.11+) | Core API (`Store`, `Registry`, `Backend`, models, errors) is stable. Breaking changes are documented in the changelog and avoid gratuitous churn. Extensions (`ext.*`) may evolve more freely. |
| **Stable** (1.0+) | Full [Semantic Versioning](https://semver.org/): breaking changes require a major bump |

<a id="rule-11"></a>
### Rule 11. A breaking change ships its upgrade path in the same change

**Why:** an upgrade path assembled at release time is written by someone who
has forgotten the details.

**For you:** every break carries a changelog entry marked breaking and a
section in the [migration guide](../reference/migration.md), both present by
the time you can install it. A gate enforces the link between the two.

<a id="rule-12"></a>
### Rule 12. Below 1.0, a breaking change arrives in a minor bump

**Why:** Semantic Versioning leaves pre-1.0 minors free to break, and the table
above says which tier a version falls in.

**For you:** read our minor bumps the way you would read majors elsewhere.

## What this policy does not promise

<a id="rule-13"></a>
### Rule 13. Not a reproducible resolution

We publish ranges, not pins. Two installs a month apart can differ. If you need
them not to, lock on your side.

<a id="rule-14"></a>
### Rule 14. Not a verified floor, on every interpreter

A floor is installed and exercised weekly, on one interpreter, as far as that
extra's smoke reaches. That is narrower than "the floor works", and the gap is
where the known failures have lived.

Scheduled CI installs each extra at the floor of every range it declares and
runs that extra's smoke against it, on the oldest Python we support. Findings
are advisory: they open a maintainer's issue, they do not block a release, and
a floor can be published while a finding against it is open. What that lane
does **not** see: a floor that breaks only on a *newer* interpreter — two of
the five floor corrections we have made were exactly that shape, and all five
are in the [migration guide](../reference/migration.md) — and anything past
the depth of the smoke, which the
[Tested versions](../reference/tested-versions.md) page states per extra.

Floors themselves are still established by hand, by installing a candidate
release and running the code against it, and a regression test then guards the
boundary. Sweeps have found floors naming a release that installs cleanly and
then fails, including some wrong for a long time; the corrections appear in the
[migration guide](../reference/migration.md).

**If you pin near the bottom of a range, prefer a version comfortably above the
floor.** The top of the range is where every environment we run resolves to,
and the bottom is checked once a week on one interpreter rather than
continuously on all of them.

<a id="rule-15"></a>
### Rule 15. Not that every version in a range has been tried

A range is bounded by what we measured at each end. Between the ends is
inference.

## How the ranges are watched

Scheduled CI watches both ends of every range it covers, weekly. It re-resolves
each extra against the latest available versions, pre-releases included, and
diffs the result against a committed record; and it installs each extra at the
floor of every range it declares. At both ends the extra is installed **alone**
and its own declared packages are imported before anything else joins the
environment — which is the only thing that would notice an extra failing to
declare something another extra happens to supply. The extra's smoke then runs,
alongside the test tooling it needs. Findings land on a rolling issue. The recorded versions and the declared ranges are both
published on [Tested versions](../reference/tested-versions.md), which answers
"what was CI last green against, and what is it held to?" and not "what will
work".

**The conda channel's copy of these constraints is watched on the same schedule,
for a third reason.** The recipe conda-forge builds from lives in a repository
this project does not own, so a copy that was right when it was taken can go on
being served long after the ranges here have moved. The same weekly job fetches
it and compares it against what this project published for the version the
channel is on — not against the current ranges, which the channel is not meant to
have yet ([Rule 3](#rule-3)).

**The interpreter windows are watched on the same schedule, for a different
reason.** A dependency range goes stale when an upstream publishes, which a
re-resolution can detect. A support window closes when a date passes, and no
diff can carry that. So the same weekly job reports, per supported version,
when its security support ends and how far away that is. The verdict is
advisory in the same way the rest of the guard is: a closed window means we
*may* drop a version, never that we must.

**How fast the tested zone moves is something you can read rather than guess.**
The guard runs weekly, and each extra on that page carries the date its record
was captured, so the gap between that date and today is how far your install
may have drifted from anything we have exercised. No upgrade cadence is stated
here, because none has been measured; [Rule 10](#rule-10) is the one timing
obligation this policy places on you, and it says only that security fixes
reach the latest release.

These limits bound that, and they are why [Rule 14](#rule-14) and
[Rule 15](#rule-15) read as they do:

- **It does not cover every extra you can install.** An extra whose resolution
  depends on the running interpreter is excluded, so it has no committed record
  and no row on the Tested versions page. That page
  [names which ones](../reference/tested-versions.md), so an absent row is
  readable rather than ambiguous. Being excluded is not a claim that nothing
  watches it, only that this guard does not.
- **The smoke can be shallower than the extra.** Where the target is an import,
  a drift breaking anything past module load passes. The Tested versions page
  states the depth per extra, so how much a given row is worth is readable.
  Widening that reach is tracked work.
- **The floor check is one interpreter wide.** It runs on the oldest Python we
  support, and leaves transitive packages at their newest — so it tests the
  floors we declare rather than a whole old environment. A floor that installs
  and breaks only on a newer interpreter is outside it; so is a floor that
  cannot be installed at all on a newer one, which announces itself to you at
  install time rather than silently.
- **That check is stricter than your runtime, on purpose.** Our tests treat
  warnings as errors, so a floor that still works but has started emitting
  deprecation warnings fails it. You would see nothing at those versions yet;
  we would rather find out a release early than a release late. It means a
  floor being flagged is not the same as a floor being broken for you.
- **It is early warning, not remediation**, and each end resolves on one
  platform and one Python version — the newest end on the version we develop
  against, the floor end on the oldest we support. The job never edits a range
  or opens a pin-update pull request; a maintainer reads the finding and
  decides.

## See also

- [Tested versions](../reference/tested-versions.md) — the resolutions CI was last green against
- [Migration guide](../reference/migration.md) — what changed, release by release, and how to move
- [Extensions](../guides/extensions.md) — how optional dependencies are gated at import
- [Security model](security-model.md) — credentials, trust boundaries, and vulnerability reporting
- [`CONTRIBUTING.md` § Versioning](../../CONTRIBUTING.md#versioning) — which change earns which bump
