"""Print the working tree of each ``git <subcommand>`` a Bash hook payload runs.

Run by ``.claude/hooks/gate-commit.sh`` and ``gate-push.sh``, which are wired
without ``if:`` (its prefix match misses ``git -C <path> commit``, BK-486) and
so see every Bash call. Usage: ``git_target.py SUBCOMMAND`` with the PreToolUse
payload on stdin. Prints one absolute directory per invocation, in order, and
nothing when the command runs no such subcommand.

An invocation counts only with ``git`` (or a path ending in ``/git``) in
command position: at the start, after ``;``, ``&&``, ``||``, ``|``, ``&``,
``(`` or a newline, past ``VAR=value`` assignments, shell keywords and the
wrappers in ``_WRAPPERS`` with their options. So quoted text
(``gh pr create --body "... git commit ..."``) and arguments
(``git log --grep commit``, ``git cat-file commit HEAD``) do not count. The tree
starts at the cwd, follows each earlier ``cd <dir>``, a wrapper's ``env -C`` or
``sudo -D``, and the invocation's own ``-C`` and ``--work-tree``, with ``$VAR``
and ``~`` expanded against the hook's environment (``$PWD`` as the cwd).

Bounds: a git run inside backticks, ``bash -c '...'``, an alias or behind a
wrapper not in ``_WRAPPERS`` is not seen, so its gate does not act, as before
BK-486. A tree that does not resolve (a variable set in the same command, a
``$(...)``, a backslashed Windows path) is printed as is; the gates judge the
cwd for any tree that is not a work tree. A ``cd`` inside ``( ... )`` is taken
to persist past it, ``cd -`` or a bare ``cd`` is ignored, and heredoc lines are
read as commands, which can only make a gate act. A command shlex cannot split
(an unbalanced quote) falls back to a whole-word match, printing the cwd, so the
gate still acts there. Stdlib only and no construct newer than the
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
# Wrappers that run their argument as the command, each with its options that
# take a separate value; options and timeout's duration are skipped.
_WRAPPERS = {
    "command": frozenset(),
    "exec": frozenset({"-a"}),
    "nohup": frozenset(),
    "env": frozenset({"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}),
    "nice": frozenset({"-n", "--adjustment"}),
    "timeout": frozenset({"-s", "--signal", "-k", "--kill-after"}),
    "sudo": frozenset({"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C", "-D", "--chdir"}),
    "xargs": frozenset({"-I", "-L", "-n", "-P", "-d", "-E", "-s", "-a"}),
}
# Wrapper options that run the command in another directory.
_CHDIR = frozenset({("env", "-C"), ("env", "--chdir"), ("sudo", "-D"), ("sudo", "--chdir")})
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


def _skip_wrapper(tokens: list[str], i: int, here: str) -> tuple[int, str]:
    """Step past the wrapper at *i* and its options; return the last index consumed and the directory."""
    name, valued = tokens[i], _WRAPPERS[tokens[i]]
    while i + 1 < len(tokens) and tokens[i + 1] not in _SEPARATORS:
        nxt = tokens[i + 1]
        if nxt.startswith("-"):
            option, eq, value = nxt.partition("=")
            i += 1
            if option in valued and not eq and i + 1 < len(tokens):
                i += 1
                value = tokens[i]
            if (name, option) in _CHDIR and value:
                here = _expand(value, here)
        elif name == "timeout" and nxt[:1].isdigit():
            i += 1
        else:
            break
    return i, here


def targets(command: str, subcommand: str, cwd: str) -> list[str]:
    """The working tree of each ``git <subcommand>`` *command* runs, in order."""
    try:
        tokens = _tokens(command)
    except ValueError:
        whole_words = rf"(^|\W)git(\W.*)?\W{re.escape(subcommand)}(\W|$)"
        return [cwd] if re.search(whole_words, command.replace("\n", " ")) else []
    found, at_command, i = [], True, 0
    here = cwd  # the directory of the current command; a wrapper may move it
    while i < len(tokens):
        token = tokens[i]
        if token in _SEPARATORS:
            at_command, here = True, cwd
        elif not at_command or token in _KEYWORDS or _ASSIGNMENT.match(token):
            pass
        elif token in _WRAPPERS:
            i, here = _skip_wrapper(tokens, i, here)
        elif token == "cd":
            if i + 1 < len(tokens) and tokens[i + 1] not in _SEPARATORS and tokens[i + 1] != "-":
                i += 1
                cwd = here = _expand(tokens[i], cwd)
            at_command = False
        elif os.path.basename(token) == "git":
            tree, i = _invocation(tokens, i, subcommand, here)
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
