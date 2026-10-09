"""Fetch every merged PR's size and review activity from GitHub into ``--data/prs.json``.

Uses ``gh api graphql``, paged 40 at a time. ``--repo`` names the GitHub
repository (default: the one ``gh`` resolves for ``--repo-root``). The file
is public data; it stays in ``--data`` because it is an input, not a result.
"""

from __future__ import annotations

import json
import subprocess

import _common as c

Q = (
    "query($owner:String!,$name:String!,$cursor:String){repository(owner:$owner,name:$name){"
    "pullRequests(states:MERGED,first:40,after:$cursor,orderBy:{field:CREATED_AT,direction:ASC}){"
    "pageInfo{hasNextPage endCursor}nodes{number title headRefName createdAt mergedAt additions deletions "
    "changedFiles commits{totalCount} reviews{totalCount} reviewThreads{totalCount} comments{totalCount}}}}}"
)


def gh_repo(repo_root) -> str:
    out = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True, text=True, encoding="utf-8", cwd=repo_root, check=True,
    )  # fmt: skip
    return out.stdout.strip()


def main(argv=None) -> int:
    ap = c.parser(__doc__, results=False)
    ap.add_argument("--repo", default=None, help="owner/name (default: gh's view of --repo-root)")
    args = c.resolve(ap.parse_args(argv))
    owner, name = (args.repo or gh_repo(args.repo_root)).split("/")
    rows, cursor = [], None
    while True:
        cmd = ["gh", "api", "graphql", "-f", f"query={Q}", "-F", f"owner={owner}", "-F", f"name={name}"]
        if cursor:
            cmd += ["-f", f"cursor={cursor}"]
        data = json.loads(subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True).stdout)
        page = data["data"]["repository"]["pullRequests"]
        for n in page["nodes"]:
            rows.append(
                {
                    "number": n["number"],
                    "title": n["title"],
                    "branch": n["headRefName"],
                    "created": n["createdAt"],
                    "merged": n["mergedAt"],
                    "add": n["additions"],
                    "del": n["deletions"],
                    "files": n["changedFiles"],
                    "commits": n["commits"]["totalCount"],
                    "reviews": n["reviews"]["totalCount"],
                    "threads": n["reviewThreads"]["totalCount"],
                    "comments": n["comments"]["totalCount"],
                }
            )
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    args.data.mkdir(parents=True, exist_ok=True)
    (args.data / "prs.json").write_text(json.dumps(rows), encoding="utf-8")
    print(len(rows), "merged PRs written to", args.data / "prs.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
