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

**For you:** an import fails at runtime when its extra is absent. The error
names the extra to install; see the
[extensions guide](../guides/extensions.md).

<a id="rule-3"></a>
### Rule 3. Conda carries the same constraints, in the only form it has

**Why:** conda has no equivalent of extras, so the recipe restates each
constraint as a plain bound.

**For you:** `conda install` brings the core package only, and a backend's
dependencies are yours to name alongside it. The recipe's constraints bound
what you install; they pull in nothing. A feedstock also trails its upstream
release, so the channel can sit a release behind PyPI with constraints that
predate the ranges here. The
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

**For you:** read the current set from
[`pyproject.toml`](https://github.com/haalfi/remote-store/blob/master/pyproject.toml),
where each range carries its reasoning. Development and documentation build
extras sit outside this convention and may pin tooling directly; they never
reach your environment.

## Support windows

<a id="rule-8"></a>
### Rule 8. A Python version is supported at least 3 years after its release

**Why:** [SPEC 0](https://scientific-python.org/specs/spec-0000/), the
Scientific Python ecosystem's time-based support policy. A shared schedule
means your other dependencies drop versions on the same cadence we do.

**For you:** the end of support for a version is computable in advance, from
[SPEC 0's drop schedule](https://scientific-python.org/specs/spec-0000/) rather
than from our release notes. We may support a version longer than the minimum;
we will not support one for less.

<a id="rule-9"></a>
### Rule 9. A supported dependency version stays supported at least 2 years

**Why:** the same SPEC 0 cadence, applied to the packages behind the extras.
The window runs from that dependency's own initial release, not from ours.

**For you:** raising a floor past that window is a breaking change and takes
the path in [Rule 11](#rule-11). Within it, a floor can still rise in any
release.

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
### Rule 14. Not a continuously verified floor

Floors are established by hand, by installing a candidate release and running
the code against it, and a regression test then guards that boundary. Nothing
re-derives them, so a floor that upstream invalidates stays as written until
someone measures it again. Sweeps have found floors naming a release that
installs cleanly and then fails, including some wrong for a long time; the
corrections appear in the [migration guide](../reference/migration.md). Closing
that gap is open, tracked work.

**If you pin near the bottom of a range, prefer a version comfortably above the
floor.** The top of the range is where every environment we run resolves to.

<a id="rule-15"></a>
### Rule 15. Not that every version in a range has been tried

A range is bounded by what we measured at each end. Between the ends is
inference.

## How the ranges are watched

Scheduled CI re-resolves the extras it covers weekly against the latest
available versions, pre-releases included, diffs the result against a committed
record, and runs a smoke target for any extra that moved. Findings land on a
rolling issue. The recorded versions are published on
[Tested versions](../reference/tested-versions.md), which answers "what was CI
last green against?" and not "what will work".

Four limits bound that, and they are why [Rule 14](#rule-14) and
[Rule 15](#rule-15) read as they do:

- **It does not cover every extra you can install.** An extra whose resolution
  depends on the running interpreter is excluded, so it has no committed record
  and no row on the Tested versions page. Being excluded is not a claim that
  nothing watches it, only that this guard does not.
- **The smoke can be shallower than the extra.** Where the target is an import,
  a drift breaking anything past module load passes. Widening that reach is
  tracked work.
- **It watches the top of the range only**, because it resolves to the newest
  compatible release, as does every environment that builds this project.
- **It is early warning, not remediation**, and it resolves on one platform and
  one Python version. The job never edits a range or opens a pin-update pull
  request; a maintainer reads the finding and decides.

## See also

- [Tested versions](../reference/tested-versions.md) — the resolutions CI was last green against
- [Migration guide](../reference/migration.md) — what changed, release by release, and how to move
- [Extensions](../guides/extensions.md) — how optional dependencies are gated at import
- [Security model](security-model.md) — credentials, trust boundaries, and vulnerability reporting
- [`CONTRIBUTING.md` § Versioning](../../CONTRIBUTING.md#versioning) — which change earns which bump
