# BUG-263 — The migration guide promises a drive folder named `.` stays reachable as a key; no key spelling reaches it
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`docs-src/reference/migration.md` § *`GraphBackend(base_path=".")` now means
the drive root* tells a caller whose drive holds a folder literally named `.`
that it "stays reachable as an ordinary key under a `base_path` that is not
itself a root spelling". It is not reachable under any `base_path`, because
the predicate that strips `.` from `base_path` is the same one that strips it
from every key: `GraphBackend._key_segments` delegates to
`_flat_ns._addressable_segments`, and `native_path` /
`_parent_ref_path` / the write and source guards all route through it.
Measured with `base_path="reports"`:
| key | addresses |
| --- | --- |
| `./x` | `/drives/D/root:/reports/x:` |
| `.` | `/drives/D/root:/reports:` |
| `x/./y` | `/drives/D/root:/reports/x/y:` |

So the folder is unaddressable, not relocated — which is a strictly larger
break than the section describes, and the sentence sends a caller looking for
a workaround that does not exist.
**The fix is the sentence, not the code.** `_addressable_segments`' own
docstring records why the two predicates must stay identical (a draft that
widened one broke the `to_key(native_path(key)) == key` identity on 4 of 7
measured keys), so the guide should say the folder can no longer be addressed
and name what a caller does instead — rename it before upgrading.
The neighbouring claim, "Every other `base_path` value is unaffected", was
checked and **holds**: the only behavioural difference between the old `if s`
split and `if s and s != "."` is dot segments, and the preceding sentence
already covers those. Recorded so the next reader does not re-litigate it.
Found by ID-252's closing review reading outside its own diff; shipped by
BUG-261.
