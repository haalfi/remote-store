"""One PR's review rounds as ``/ship`` ran them, and each finding's fix classed as prose or code.

``hatch run ship-report`` and ``rounds.py`` count review *submissions*. A
``/ship`` round posts one review per reviewer or one summary review, and its
fix pass posts one reply submission per finding, so submissions overcount
rounds several times over. This script groups instead:

- **Finding:** a top-level review comment (no ``replyTo``), bots included (a
  CodeQL alert is a finding a fix pass answers).
- **Round:** the findings posted against one head commit (the comment's
  ``originalCommit``), plus a review on a commit no finding names whose body
  is not empty (an analyze-only round that posted its findings in the body).
  A bot finding on a commit no reviewer reviewed joins the latest earlier
  round. Rounds are ordered by their first submission.
- **Route:** ``--route-start SHA`` (repeatable) opens a new route at a
  re-plan. A round belongs to the last route whose start commit its head
  descends from (GitHub's compare API, so commits a rebase dropped resolve
  too); a round on a head that descends from no start is in route 1.
- **Fix commit:** the first commit a reply to the finding cites (an
  abbreviated SHA in its body) that was committed after the finding was
  posted. A finding no reply cites a later commit for is ``unfixed``.
- **Class:** ``prose`` when the fix commit changes no executable line, else
  ``code``. The diff read is the fix commit's change to the finding's file, or
  the whole commit when it leaves that file alone. A ``.py`` file changes an
  executable line when its AST, docstrings removed, differs (so comments and
  docstrings are prose); a shell, Dafny, TLA+, TOML or ``.github/`` file when a
  non-comment line differs; every other file (Markdown, traces, backlog) is
  prose. A fix pass commits once for many findings, so a code label is exact
  only when its fix commit fixed no other finding in that file:
  ``shared_fix`` marks the rest, and ``code_in_shared_fix`` counts them. It
  is where a prose fix mislabelled code is most likely, not a bound: a commit
  can also batch a prose fix to a test file with a code fix filed against a
  source file.

Commits are read from the local git object store; one a rebase dropped is
fetched from ``origin`` by its full SHA. Reviews are paged; more than 250
commits or 100 comments on one review stops the script rather than cutting the
result short, and so does a commit lookup failing for any reason but "no such
commit". The fetched review data is cached in
``--data/pr_<N>_reviews.json``. Writes ``results/pr_<N>_rounds.json``.

    python pr_rounds.py --pr 1093 --route-start cdcaa35c6
"""

from __future__ import annotations

import ast
import collections
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

import _common as c

Q = (
    "query($owner:String!,$name:String!,$n:Int!,$after:String){repository(owner:$owner,name:$name){pullRequest(number:$n){"
    "commits(first:250){totalCount nodes{commit{oid committedDate}}}"
    "reviews(first:100,after:$after){pageInfo{hasNextPage endCursor} nodes{submittedAt body author{login __typename}"
    " commit{oid} comments(first:100){totalCount nodes{id path createdAt body author{login __typename}"
    " replyTo{id} originalCommit{oid}}}}}}}}"
)
SHA = re.compile(r"\b[0-9a-f]{7,40}\b")
COMMENT = {".sh": "#", ".toml": "#", ".yml": "#", ".yaml": "#", ".ps1": "#", ".dfy": "//", ".tla": "\\*"}


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=check
    )


def fetch(pr: int, repo: str, cache: Path) -> dict:
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    owner, name = repo.split("/")
    data: dict = {"reviews": {"nodes": []}}
    after: list[str] = []
    while True:  # reviews page by cursor; a capped count is an error, never a short result
        args = ["api", "graphql", "-f", f"query={Q}", "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"n={pr}"]
        page = json.loads(gh(*args, *after))["data"]["repository"]["pullRequest"]
        data["commits"] = page["commits"]
        data["reviews"]["nodes"] += page["reviews"]["nodes"]
        if not page["reviews"]["pageInfo"]["hasNextPage"]:
            break
        after = ["-f", f"after={page['reviews']['pageInfo']['endCursor']}"]
    over = [f"commits {data['commits']['totalCount']} > 250"] if data["commits"]["totalCount"] > 250 else []
    over += [
        f"review at {r['submittedAt']}: {r['comments']['totalCount']} comments > 100"
        for r in data["reviews"]["nodes"]
        if r["comments"]["totalCount"] > len(r["comments"]["nodes"])
    ]
    if over:
        raise SystemExit(f"PR #{pr} exceeds a fetch cap: {'; '.join(over)}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


def is_bot(author: dict | None) -> bool:
    return bool(author) and (author.get("__typename") == "Bot" or author.get("login", "").endswith("[bot]"))


class Commits:
    """Resolve abbreviated SHAs, dates and ancestry; cache what the API answered."""

    def __init__(self, repo: str, root: Path, known: dict[str, str], cache: Path):
        self.repo, self.root, self.cache_path = repo, root, cache
        self.cache = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {"commit": {}, "compare": {}}
        self.date = dict(known)  # full oid -> committedDate

    def save(self) -> None:
        self.cache_path.write_text(json.dumps(self.cache), encoding="utf-8")

    def resolve(self, abbrev: str) -> str | None:
        hit = [o for o in self.date if o.startswith(abbrev)]
        if len(hit) == 1:
            return hit[0]
        if abbrev not in self.cache["commit"]:
            r = subprocess.run(
                ["gh", "api", f"repos/{self.repo}/commits/{abbrev}", "--jq", "[.sha, .commit.committer.date]"],
                capture_output=True, text=True, encoding="utf-8",
            )  # fmt: skip
            if r.returncode and not re.search(r"\(HTTP (404|422)\)", r.stderr):
                # rate limit, network, auth: fail rather than cache a real commit as "none"
                raise SystemExit(f"commit lookup {abbrev} failed: {r.stderr.strip()}")
            self.cache["commit"][abbrev] = json.loads(r.stdout) if r.returncode == 0 else None
        got = self.cache["commit"][abbrev]
        if not got:
            return None
        self.date[got[0]] = got[1]
        return got[0]

    def descends(self, oid: str, start: str) -> bool:
        key = f"{start}...{oid}"
        if key not in self.cache["compare"]:
            st = gh("api", f"repos/{self.repo}/compare/{start}...{oid}", "--jq", ".status").strip()
            self.cache["compare"][key] = st
        return self.cache["compare"][key] in ("ahead", "identical")

    def ensure(self, oid: str) -> None:
        if git(self.root, "cat-file", "-e", f"{oid}^{{commit}}", check=False).returncode:
            git(self.root, "fetch", "--quiet", "origin", oid)


def blob(root: Path, rev: str, path: str) -> str | None:
    r = git(root, "show", f"{rev}:{path}", check=False)
    return r.stdout if r.returncode == 0 else None


def executable_change(root: Path, oid: str, path: str) -> bool:
    old, new = blob(root, f"{oid}^", path), blob(root, oid, path)
    p = PurePosixPath(path)
    if p.suffix == ".py":
        return _py_shape(old) != _py_shape(new)
    mark = COMMENT.get(p.suffix)
    if p.suffix in (".yml", ".yaml") and not path.startswith(".github/"):
        mark = None
    if mark is None:
        return False
    return _code_lines(old, mark) != _code_lines(new, mark)


def _py_shape(src: str | None) -> str | None:
    if src is None:
        return None
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src  # unparsable: any text change counts as executable
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree)


def _code_lines(src: str | None, mark: str) -> list[str] | None:
    if src is None:
        return None
    return [s for line in src.splitlines() if (s := line.split(mark, 1)[0].strip())]


def classify(root: Path, oid: str, path: str | None, touched: dict[str, list[str]]) -> dict[str, object]:
    files = touched.setdefault(oid, git(root, "show", "--format=", "--name-only", oid).stdout.split())
    scope, read = ("file", [path]) if path in files else ("commit", files)
    hits = [f for f in read if executable_change(root, oid, f)]
    return {"class": "code" if hits else "prose", "scope": scope, "executable_files": hits}


def build(pr: int, repo: str, root: Path, data: Path, starts: list[str]) -> dict:
    raw = fetch(pr, repo, data / f"pr_{pr}_reviews.json")
    known = {n["commit"]["oid"]: n["commit"]["committedDate"] for n in raw["commits"]["nodes"]}
    cm = Commits(repo, root, known, data / f"pr_{pr}_commits.json")
    starts_full = [cm.resolve(s) or s for s in starts]

    replies = collections.defaultdict(list)
    findings, body_rounds = [], []
    for rv in sorted(raw["reviews"]["nodes"], key=lambda r: r["submittedAt"] or ""):
        if not rv["submittedAt"]:
            continue
        tops = []
        for x in rv["comments"]["nodes"]:
            if x.get("replyTo"):
                replies[x["replyTo"]["id"]].append(x)
            else:
                tops.append(x)
        for x in tops:
            findings.append(
                {
                    "id": x["id"],
                    "at": x["createdAt"],
                    "path": x["path"],
                    "head": (x.get("originalCommit") or rv["commit"])["oid"],
                    "bot": is_bot(x.get("author")),
                    "category": (re.match(r"\s*\**\s*([A-Za-z-]+)\s*[:,(]", x["body"] or "") or [None, "?"])[1],
                }
            )
        if not tops and (rv["body"] or "").strip() and not is_bot(rv.get("author")):
            body_rounds.append({"head": rv["commit"]["oid"], "at": rv["submittedAt"]})

    heads: dict[str, str] = {}  # head oid -> first submission time, for rounds a reviewer posted
    for f in findings:
        if not f["bot"]:
            heads[f["head"]] = min(heads.get(f["head"]) or f["at"], f["at"])
    for b in body_rounds:
        heads.setdefault(b["head"], b["at"])
    order = sorted(heads, key=lambda h: heads[h])
    for f in findings:
        if f["head"] not in heads:  # a bot finding on an unreviewed head joins the latest earlier round
            f["head"] = max((h for h in order if heads[h] <= f["at"]), key=lambda h: heads[h], default=order[0])

    touched: dict[str, list[str]] = {}
    for f in findings:
        fix = None
        for r in sorted(replies.get(f["id"], []), key=lambda r: r["createdAt"]):
            for s in SHA.findall(r["body"] or ""):
                oid = cm.resolve(s)
                if oid and cm.date.get(oid, "") > f["at"]:
                    fix = oid
                    break
            if fix:
                break
        f["fix"], f["fix_at"] = (fix[:9], cm.date[fix]) if fix else (None, "")
        if fix:
            cm.ensure(fix)
            f.update(classify(root, fix, f["path"], touched))
        else:
            f["class"], f["scope"] = "unfixed", None
    # A code label is exact only when its fix commit fixed nothing else in that file: a commit that
    # fixes a docstring and an unrelated line of one file labels both findings code.
    shared = collections.Counter((f["fix"], f["path"]) for f in findings if f["fix"])
    for f in findings:
        f["shared_fix"] = f["class"] == "code" and f["scope"] == "file" and shared[(f["fix"], f["path"])] > 1

    route_of = {}
    for h in order:
        route_of[h] = 1 + max((i + 1 for i, s in enumerate(starts_full) if cm.descends(h, s)), default=0)
    cm.save()

    rounds, per_route = [], collections.Counter()
    for h in order:
        per_route[route_of[h]] += 1
        fs = [f for f in findings if f["head"] == h]
        cls = collections.Counter(f["class"] for f in fs)
        rounds.append(
            {
                "route": route_of[h],
                "round": per_route[route_of[h]],
                "head": h[:9],
                "first_submitted": heads[h],
                "findings": len(fs),
                "prose": cls["prose"],
                "code": cls["code"],
                "unfixed": cls["unfixed"],
                "code_in_shared_fix": sum(f["shared_fix"] for f in fs),
                "fix_commits": [s for _, s in sorted({(f["fix_at"], f["fix"]) for f in fs if f["fix"]})],
                "items": [
                    {k: f[k] for k in ("path", "category", "bot", "fix", "class", "scope", "shared_fix")}
                    | ({"executable_files": f["executable_files"]} if f.get("executable_files") else {})
                    for f in sorted(fs, key=lambda f: f["at"])
                ],
            }
        )
    routes = {}
    for r in sorted(set(route_of.values())):
        rs = [x for x in rounds if x["route"] == r]
        n = sum(x["findings"] for x in rs)
        p = sum(x["prose"] for x in rs)
        routes[str(r)] = {
            "start": None if r == 1 else starts[r - 2],
            "rounds": len(rs),
            "findings_by_round": [x["findings"] for x in rs],
            "findings": n,
            "prose": p,
            "code": sum(x["code"] for x in rs),
            "unfixed": sum(x["unfixed"] for x in rs),
            "prose_pct": c.pct(p, n, 0),
            "code_in_shared_fix": sum(x["code_in_shared_fix"] for x in rs),
        }
    return {
        "pr": pr,
        "submissions": sum(1 for r in raw["reviews"]["nodes"] if r["submittedAt"]),
        "routes": routes,
        "rounds": rounds,
    }


def main(argv=None) -> int:
    ap = c.parser(__doc__)
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--route-start", action="append", default=[], help="commit that opens a new route (repeatable)")
    ap.add_argument("--repo", default="haalfi/remote-store", help="GitHub owner/name")
    args = c.resolve(ap.parse_args(argv))
    payload = build(args.pr, args.repo, args.repo_root, args.data, args.route_start)
    payload["derivation"] = f"pr_rounds.py --pr {args.pr}" + "".join(f" --route-start {s}" for s in args.route_start)
    c.write_result(
        args.results,
        f"pr_{args.pr}_rounds",
        "pr_rounds",
        {f"pr_{args.pr}_reviews.json": args.data / f"pr_{args.pr}_reviews.json"},
        payload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
