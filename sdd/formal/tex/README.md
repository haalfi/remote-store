# Store axioms: prose proofs (TeX)
<!-- doc: repo-only -->

[`store-axioms.tex`](store-axioms.tex) gives ordinary mathematical prose
proofs of what [`StoreAxioms.lean`](../lean/StoreAxioms.lean) proves about
[spec 051](../../specs/051-store-tree.md), the store tree: D1, L1 to L6, the
infinite model and the infinite upward chain. Its last section says what the
bounded Alloy model [`StoreAxioms.als`](../alloy/StoreAxioms.als) adds.
[`store-axioms.pdf`](store-axioms.pdf) is the build output, committed so a
reader needs no TeX install.

It is an exposition for curious readers, not a source of truth. Spec 051 is
the authority for the statements, and the Lean file for the proofs. Where the
text and the Lean file disagree, the text is wrong.

## Checking

The prose proofs are **not** machine-checked. Three agent review passes
compared each statement and proof with its Lean declaration, and the Alloy
section with the `.als` file and research § 10. None found an unsound proof
step. They found 7, 8 and 2 defects in the prose and the Alloy section (one a
false claim in the abstract), all fixed; the last pass's 2 fixes were not
reviewed again. Each result
names its Lean declaration (`[Lean: …]`), and the appendix is a concordance
from results to spec IDs and declarations.

## Sources it was written from

Read from branch `store-model-axioms` at `21a0e534b`. The Lean file and spec
051 are unchanged at `bffcee464`
(`git diff 21a0e534b bffcee464 -- sdd/formal/lean sdd/specs/051-store-tree.md`
is empty).

- `sdd/specs/051-store-tree.md`: statements, TREE IDs and the abstract's
  wording.
- `sdd/formal/lean/StoreAxioms.lean`: every proof, step by step.
- `sdd/formal/alloy/StoreAxioms.als`: the Alloy section (scopes, the 30
  commands, the Key-length bound).
- [`research-store-model-axioms.md`](../../research/research-store-model-axioms.md)
  § 5 (countermodels and witnesses) and § 10 (Alloy results and mutants).

## Build

Any TeX Live with pdfLaTeX. Packages: `amsmath`, `amssymb`, `amsthm`,
`mathtools`, `booktabs`, `tabularx`, `enumerate`, `geometry`, `hyperref` and
`lmodern`. The file avoids `enumitem`, which minimal installs lack.

```
pdflatex store-axioms.tex
pdflatex store-axioms.tex   # second run resolves cross-references and the TOC
```

The auxiliary files are ignored by this directory's `.gitignore`.

## Redoing it after a source changes

1. `git diff <old>..<new> -- sdd/formal/lean/StoreAxioms.lean` shows which
   declarations changed.
2. Update the matching result. Find it by its `[Lean: …]` tag, or in the
   appendix's concordance.
3. Update the commit in `\date{…}` and under § Sources above.
4. Have an agent compare each changed statement and proof with its Lean
   declaration, then rebuild and commit the PDF with the source.

If `StoreAxioms.als` or research § 5 or § 10 change, redo the Alloy section
the same way.
