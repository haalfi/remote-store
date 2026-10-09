"""Fetch the top-level review findings on prose files for the long-loop PRs, as input to classification.

A finding is a top-level review comment (no ``replyTo``) on a path that is
not code (``rounds.CODE``, Markdown always counts as prose). Each review
submission that carries one is a round, in submission order. The key of a
finding is ``<PR>-<round>-<index>``; ``results/prose_labels.json`` uses it.

Writes ``--data/prose_findings.json`` with the comment bodies. Bodies are
public on GitHub but stay out of the repo: the labels are the result.
"""

from __future__ import annotations

import json
import subprocess

import _common as c
from rounds import CODE

# The 13 PRs with the longest review loops among those carrying a derived review: block.
LONG = [1027, 1045, 1047, 1048, 1052, 1053, 1056, 1061, 1066, 1073, 1041, 1050, 1051]
Q = (
    "query($owner:String!,$name:String!,$n:Int!){repository(owner:$owner,name:$name){pullRequest(number:$n){title "
    "reviews(first:100){nodes{submittedAt comments(first:100){nodes{path line originalLine body replyTo{id}}}}}}}}"
)


def main(argv=None) -> int:
    ap = c.parser(__doc__, results=False)
    ap.add_argument("--repo", default="haalfi/remote-store", help="GitHub owner/name")
    ap.add_argument("--pr", type=int, action="append", help="PR to fetch (repeatable; default the 13 long loops)")
    args = c.resolve(ap.parse_args(argv))
    owner, name = args.repo.split("/")
    out = []
    for n in args.pr or LONG:
        r = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={Q}", "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"n={n}"],
            capture_output=True, text=True, encoding="utf-8", check=True,
        )  # fmt: skip
        pr = json.loads(r.stdout)["data"]["repository"]["pullRequest"]
        revs = [x for x in pr["reviews"]["nodes"] if x["submittedAt"]]
        revs = sorted(
            (x for x in revs if any(not k.get("replyTo") for k in x["comments"]["nodes"])),
            key=lambda x: x["submittedAt"],
        )
        for i, rv in enumerate(revs, 1):
            for k in rv["comments"]["nodes"]:
                path = k["path"] or ""
                if k.get("replyTo") or (CODE.search(path) and not path.endswith(".md")):
                    continue
                out.append(
                    {
                        "key": f"{n}-{i}-{len(out)}",
                        "pr": n,
                        "round": i,
                        "rounds_total": len(revs),
                        "path": path,
                        "body": k["body"],
                    }
                )
    args.data.mkdir(parents=True, exist_ok=True)
    (args.data / "prose_findings.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(len(out), "prose findings written to", args.data / "prose_findings.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
