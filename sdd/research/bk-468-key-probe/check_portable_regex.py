"""Check spec 054's portable-name regex against its prose definition."""

import re

NAME = r"(?!(?i:CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:[./]|$))[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9_-])?"
KEY = re.compile(r"(?=[ -~]{1,255}\Z)" + NAME + r"(?:/" + NAME + r")*\Z")

CASES = {
    "a": True,
    "A-1_b.c": True,
    "d/e/f.txt": True,
    "con1/lpt": True,
    "n" * 255: True,
    "/".join(["seg"] * 63) + "/abc": True,
    "COM10": True,
    "a..b": True,
    "a-": True,
    "a_": True,
    "n" * 256: False,
    "a.": False,
    "a ": False,
    ".a": False,
    "_a": False,
    "-a": False,
    "CON": False,
    "con.txt": False,
    "Lpt9": False,
    "a/CON/b": False,
    "a//b": False,
    "/a": False,
    "a/": False,
    "": False,
    "a b": False,
    "é": False,
    "a.b.": False,
    "a/.": False,
    "x/./y": False,
}
bad = [k for k, v in CASES.items() if bool(KEY.match(k)) != v]
print("mismatch:", bad, "of", len(CASES))
