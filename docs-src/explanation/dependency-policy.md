# Dependency and version policy

What `remote-store` promises about the packages it pulls into your
environment, and about the compatibility of its own API across releases.
Two promises, one page, because they fail together: a library that widens
your dependency tree without warning breaks you as surely as one that
renames a method.

## The core pulls in nothing

`pip install remote-store` adds one package to your environment. Every
backend and every integration lives behind an extra, so the dependency tree
you end up with is the one you asked for: installing the S3 backend does not
also bring in an SSH client, a database driver, or a telemetry SDK.

This is a deliberate trade. It means an import can fail at runtime when the
matching extra is absent, and the library spends code on making that failure
say which extra to install rather than assuming everything is present. The
[extensions guide](../guides/extensions.md) covers what that looks like when
you hit it.

The backends themselves are thin. Where a mature library already does the
work — the Azure SDK, an S3 filesystem layer, an SSH implementation —
the backend adapts it rather than reimplementing it, so the code handling
your bytes is code that a much larger community already exercises.

### Installing from conda works differently

Conda has no equivalent of extras. `conda install` brings in the core package
alone, and a backend's dependencies are yours to name alongside it; the
recipe's constraints do not pull anything in, they only bound the version of
whatever you do install. The promise is the same one stated below, expressed
in the only form the packaging format allows.

One consequence is worth knowing before you rely on it: a feedstock trails
its upstream release, so the conda channel can be a release behind PyPI, and
its constraints can predate the ranges described here. The
[README's installation section](https://github.com/haalfi/remote-store#installation)
carries the practical version of this caveat.

## How version ranges are chosen

Every extra declares a **floor**. A **ceiling is the exception**, added only
when a known-incompatible major release already exists and would break the
import. We do not cap dependencies speculatively.

That asymmetry is the whole policy, and it is chosen against your interests
in one direction on purpose. A speculative ceiling is invisible when it is
right and expensive when it is wrong: it silently excludes `remote-store`
from your resolution the moment an upstream project ships a major that would
have worked fine, and you cannot override it without forking. A missing
ceiling, by contrast, fails loudly and locally, and you can pin the package
yourself.

So when an upstream major changes behaviour we rely on, the first question
is whether we can absorb it rather than cap it. Two live cases show both
answers:

- **The SSH library is deliberately uncapped**, even though a major release
  changed which host-key algorithms are enabled by default. Rather than
  constrain the library for every consumer, the SFTP backend ships an opt-in
  compatibility helper and a diagnostic that reports what a given server
  will accept. Users on modern servers are unaffected; users on legacy
  servers get a switch.
- **The HTTP client carries the one runtime ceiling.** Its next major line
  is a wholesale client-API rewrite that removes the types the Graph and
  HTTP backends are built on, so an unbounded range would break the import
  outright rather than degrade. Porting to it is tracked work; the cap lifts
  when the port lands.

Development and documentation build extras sit outside this convention and
may pin tooling directly. They never reach your environment.

The authoritative ranges, with the reasoning for each, are the comments on
`[project.optional-dependencies]` in
[`pyproject.toml`](https://github.com/haalfi/remote-store/blob/master/pyproject.toml).

## What the drift guard gives you

Declaring a floor with no ceiling means transitive versions move underneath
us between releases. Scheduled CI re-resolves every extra weekly against the
latest available versions, pre-releases included, and diffs the result against
a committed record of the last known-good resolution. Any extra that moved then
has the real test suite run against the freshly resolved package set: the
backend conformance suite where there is one, the extension's own tests
otherwise. Findings land on a rolling issue in the repository.

The versions those records hold, per extra, are published on
[Tested versions](../reference/tested-versions.md). That page answers "what
was CI last green against?" — not "what will work".

Four limits worth being explicit about:

- **It watches the top of the range only.** The guard resolves to the newest
  compatible release, as does every other environment that builds this
  project. So the upper end of every range is exercised continuously and the
  *floor* is exercised by nothing. See the next section for what that has
  cost.
- **It is early warning, not remediation.** The job never edits version
  ranges and never opens a pin-update pull request. A maintainer reads the
  finding and decides.
- **It does not pin your install.** The committed resolutions are CI's
  record. Nothing in the published package constrains your transitive tree
  to them, and a reproducible deployment still needs your own lock file.
- **It resolves on one platform and one Python version.** A resolution that
  only occurs on another OS or interpreter is outside what the guard sees.

## What a floor is worth

A floor is a claim that the named version works. Until recently nothing
tested that claim, and it turned out to be wrong more often than anyone
expected: a sweep across the declared minimums found **five floors naming a
release that installs cleanly and then fails** — at import, or at the first
call. Two of them had been wrong for over a year. The corrections shipped in
0.32.0 and are listed in the
[migration guide](../reference/migration.md).

Two things follow, and the second is the one to act on.

The floors are now measured rather than assumed. Each one was established by
installing that release into a clean environment and running the code against
it, on the oldest and newest supported Python, and a regression test guards
the boundaries that sweep found.

But **nothing re-derives them**, and the class of failure is not closed: a
future floor can go stale the same way, because the mechanism that would
catch it — resolving each extra at its minimums and running that extra's
tests — does not exist yet. It is an open, tracked gap rather than a solved
problem.

So if you pin near the bottom of a declared range, treat the floor as our
best measurement rather than a tested guarantee, and prefer a version
comfortably above it. Pinning near the top is the well-trodden path: that is
where every environment we run resolves to.

## Stability tiers

The public API surface is everything exported from `remote_store` itself —
`__all__` on the top-level package. Anything reachable only through a
private module is internal and may change in any release.

| Label | Meaning |
|-------|---------|
| **Alpha** (pre-0.11) | API may change freely between releases |
| **Beta** (0.11+) | Core API (`Store`, `Registry`, `Backend`, models, errors) is stable. Breaking changes are documented in the changelog and avoid gratuitous churn. Extensions (`ext.*`) may evolve more freely. |
| **Stable** (1.0+) | Full Semantic Versioning: breaking changes require a major bump |

The version you installed places you in one of those rows. Below 1.0, the
practical consequence is that a breaking change reaches you through a
*minor* bump rather than a major one, because
[Semantic Versioning](https://semver.org/) leaves pre-1.0 minors free to
break: read minor bumps as you would read majors elsewhere. In exchange,
every such change arrives with a changelog entry marked as breaking and a
section in the [migration guide](../reference/migration.md) showing the
before and after, written in the same change that makes the break rather
than assembled at release time.

Extensions under `ext.*` are held to a looser promise than the core on
purpose: they are where new ideas are tried, and freezing them early would
buy stability in the part of the library least in need of it.

For which kind of change earns which bump, see
[`CONTRIBUTING.md` § Versioning](../../CONTRIBUTING.md#versioning).

## What this policy does not promise

- **Reproducible resolution.** We publish ranges, not pins. Two installs a
  month apart can differ. If you need them not to, lock on your side.
- **Support for older releases.** Security fixes go to the latest release
  only. See
  [SECURITY.md](https://github.com/haalfi/remote-store/blob/master/SECURITY.md).
- **A continuously verified floor.** The declared minimums were measured once
  and are guarded against regression, but nothing re-derives them as upstreams
  release. See [What a floor is worth](#what-a-floor-is-worth).
- **That every version in a range has been tried.** A range is a statement of
  what we believe works, bounded by what we measured at each end. The newest
  releases are exercised continuously; everything between the ends is
  inference.

## See also

- [Tested versions](../reference/tested-versions.md) — the resolutions CI was last green against
- [Migration guide](../reference/migration.md) — what changed, release by release, and how to move
- [Extensions](../guides/extensions.md) — how optional dependencies are gated at import
- [Security model](security-model.md) — credentials, trust boundaries, and vulnerability reporting
- [`CONTRIBUTING.md` § Versioning](../../CONTRIBUTING.md#versioning) — bump rules and the release checklist
