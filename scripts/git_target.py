"""Print the working tree of each ``git <subcommand>`` a Bash hook payload runs.

Run by ``.claude/hooks/gate-commit.sh`` and ``gate-push.sh``, which are wired
without ``if:`` (its prefix match misses ``git -C <path> commit``, BK-486) and
so see every Bash call. Usage: ``git_target.py SUBCOMMAND`` with the PreToolUse
payload on stdin. Prints one absolute directory per invocation, in order, and
nothing when the command runs no such subcommand.

An invocation counts only with ``git`` in command position: at the start, after
``;``, ``&&``, ``||``, ``|``, ``&``, ``(`` or a newline, past ``VAR=value``
assignments, shell keywords and the wrappers in ``_WRAPPERS``. So quoted text
(``gh pr create --body "... git commit ..."``) and arguments
(``git log --grep commit``, ``git cat-file commit HEAD``) do not count. The tree
starts at the cwd, follows each earlier ``cd <dir>`` and the invocation's own
``-C`` and ``--work-tree``, with ``$VAR`` and ``~`` expanded (``$PWD`` as the
cwd).

Bounds: a git run inside backticks, ``bash -c '...'`` or an alias is not seen,
so its gate does not act, as before BK-486; a ``cd`` inside ``( ... )`` is taken
to persist past it, ``cd -`` or a bare ``cd`` is ignored, and a backslashed
Windows path loses its backslashes, so its gate finds no branch. A command shlex cannot
split (an unbalanced quote) falls back to a whole-word match, printing the cwd,
so the gate still acts there. Stdlib only and no construct newer than the
oldest host ``python``, for the reason ``record_decision.py`` gives.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

_SEPARATORS = frozenset({";", "&&", "||", "|", "&", "(", ")", "|&", ";;"})
_KEYWORDS = frozenset({"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}", "time"})
# Wrappers that run their argument as the command; leading options and, for
# timeout, the duration are skipped.
_WRAPPERS = frozenset({"command", "exec", "env", "nohup", "nice", "timeout", "xargs", "sudo"})
# git's global options that take a separate value (`-C dir`, not `-Cdir`).
_VALUED = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--exec-path"})
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def _expand(path: str, cwd: str) -> str:
    os.environ["PWD"] = cwd
    return os.path.normpath(os.path.join(cwd, os.path.expanduser(os.path.expandvars(path))))


def _tokens(command: str) -> list[str]:
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def _invocation(tokens: list[str], start: int, subcommand: str, cwd: str) -> tuple[str | None, int]:
    """The tree of the git run starting at *start*, or None; and the index after its options."""
    tree, i = cwd, start + 1
    while i < len(tokens) and tokens[i].startswith("-") and tokens[i] not in _SEPARATORS:
        option, _, value = tokens[i].partition("=")
        if option in _VALUED and not value:
            i += 1
            value = tokens[i] if i < len(tokens) else ""
        if option in ("-C", "--work-tree") and value:
            tree = _expand(value, tree)
        i += 1
    return (tree if i < len(tokens) and tokens[i] == subcommand else None), i


def targets(command: str, subcommand: str, cwd: str) -> list[str]:
    """The working tree of each ``git <subcommand>`` *command* runs, in order."""
    try:
        tokens = _tokens(command)
    except ValueError:
        whole_words = rf"(^|\W)git(\W.*)?\W{re.escape(subcommand)}(\W|$)"
        return [cwd] if re.search(whole_words, command.replace("\n", " ")) else []
    found, at_command, i = [], True, 0
    while i < len(tokens):
        token = tokens[i]
        if token in _SEPARATORS:
            at_command = True
        elif not at_command or token in _KEYWORDS or _ASSIGNMENT.match(token):
            pass
        elif token in _WRAPPERS:
            while i + 1 < len(tokens) and (
                tokens[i + 1].startswith("-") or (token == "timeout" and tokens[i + 1][:1].isdigit())
            ):
                i += 1
        elif token == "cd":
            if i + 1 < len(tokens) and tokens[i + 1] not in _SEPARATORS and tokens[i + 1] != "-":
                i += 1
                cwd = _expand(tokens[i], cwd)
            at_command = False
        elif token == "git":
            tree, i = _invocation(tokens, i, subcommand, cwd)
            if tree is not None:
                found.append(tree)
            at_command = False
            continue
        else:
            at_command = False
        i += 1
    return found


def main(argv: list[str] | None = None) -> int:
    """Print the trees for ``argv[0]``; a payload without a readable command prints the cwd.

    That fallback keeps the gate acting, as ``command_mentions`` did.
    """
    args = sys.argv[1:] if argv is None else argv
    cwd = os.getcwd()
    try:
        command = json.loads(sys.stdin.read()).get("tool_input", {}).get("command")
    except (ValueError, AttributeError):
        command = None
    if not isinstance(command, str) or not command:
        print(cwd)
        return 0
    for tree in targets(command, args[0] if args else "", cwd):
        print(tree)
    return 0


if __name__ == "__main__":
    sys.exit(main())
