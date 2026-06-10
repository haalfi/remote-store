"""Pin the dependabot auto-merge control (BK-274).

``dependabot-auto-merge.yml`` enables merge-on-approval, which makes the
approval click the only gate before ``master``. For ``github-actions`` bumps
a green check means "the workflow parsed", not "the action behaves", so that
ecosystem is deliberately excluded from auto-merge: its PRs are merged
manually after the checklist in ``sdd/CI-OPERATIONS.md``. These tests pin
the control so a future workflow refactor cannot silently restore the
rubber-stamp path.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "dependabot-auto-merge.yml"


def _job_condition() -> str:
    data = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    return data["jobs"]["dependabot"]["if"]


def test_github_actions_ecosystem_is_excluded_from_auto_merge():
    condition = _job_condition()
    # Dependabot branch names are dependabot/<ecosystem>/<dep>-<version>;
    # the trailing slash keeps a hypothetical ecosystem named
    # "github_actions_extra" out of the exclusion's blast radius.
    assert "!startsWith(github.event.pull_request.head.ref, 'dependabot/github_actions/')" in condition


def test_human_approval_gate_is_still_required():
    # The exclusion narrows the automation; it must not loosen the existing
    # guards (approved review by the maintainer, on a dependabot PR).
    condition = _job_condition()
    assert "github.event.review.state == 'approved'" in condition
    assert "github.event.pull_request.user.login == 'dependabot[bot]'" in condition
