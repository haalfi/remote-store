# Research: Example Testing Across Language Ecosystems

**Date:** 2026-03-06
**Context:** Evaluating how other ecosystems test examples/tutorials to inform
our approach for `examples/*.py` scripts in remote-store.

---

## 1. Python Ecosystem

### Python doctest (stdlib)

Code in docstrings prefixed with `>>>` is extracted and run by `doctest`.
Expected output follows on the next line. Integrated into pytest via
`--doctest-modules` or `pytest.ini` addopts.

- **Pros:** Zero dependencies, stdlib, appears in `help()` and Sphinx docs.
- **Cons:** Fragile string comparison, whitespace/repr sensitivity, poor error
  messages, doesn't scale to complex examples.

### pytest-examples (Pydantic)

Extracts Python code blocks from markdown files or `#>` output markers in `.py`
files. Runs them and compares output. `--update-examples` auto-syncs markers.

```python
content = store.read_bytes("hello.txt")
print(content)
#> b'Hello, world!'
```

- **Pros:** Output validated, auto-update keeps examples current.
- **Cons:** Extra dependency, `#>` syntax visible to readers.

### xdoctest

Drop-in replacement for `doctest` with better parsing (AST-based), clearer
error messages, and support for multi-line statements without `...` prefixes.

### Sybil

Evaluates code blocks in Sphinx/markdown docs. Supports multiple languages and
custom parsers. Used by projects needing to test documentation examples.

### subprocess smoke tests (what we do now)

Run `python examples/foo.py` and check exit code. Simple, reliable, but only
verifies "no crash," not correctness.

---

## 2. Rust — `rustdoc` Doc-Tests

Code blocks inside `///` doc comments are compiled and run by `rustdoc`.
`cargo test` includes doc-tests automatically.

- Lines prefixed with `#` are compiled but hidden from rendered docs.
- Annotations: `ignore` (skip), `no_run` (compile only), `should_panic`.
- 2024 edition: doc-tests compiled into a single binary for speed.

**Key insight:** The `#`-hiding mechanism lets examples look clean while being
complete programs. Because they run in CI, examples are guaranteed correct.

**Used by:** The standard library, serde, regex, tokio — essentially every
published crate.

---

## 3. Go — `Example` Test Functions

Functions named `ExampleFoo` in `_test.go` files are compiled and run by
`go test`. A trailing `// Output:` comment is compared against stdout.

```go
func ExampleReverse() {
    fmt.Println(stringutil.Reverse("hello"))
    // Output: olleh
}
```

- `// Unordered output:` matches lines in any order.
- Examples without `// Output:` are compiled but not executed.
- Examples appear in `godoc` automatically.

**Key insight:** The naming convention IS the mechanism — no annotations, no
special syntax. The `// Output:` comment is both assertion and documentation.
Arguably the most elegant design of any language.

**Tradeoff:** Only tests stdout.

---

## 4. Elixir — ExUnit Doctests

`iex>` lines in `@doc` strings are parsed by `ExUnit.DocTest`. Expected output
follows on the next line. `doctest MyModule` in test files enables them.

- Blank lines between `iex>` blocks create separate test cases.
- Exception testing via `** (ExceptionName)` prefix.
- `doctest_file "README.md"` runs doctests from markdown files.

**Key insight:** Explicitly positioned as "documentation that happens to be
tested," not "tests that happen to be documentation."

---

## 5. Haskell — `doctest` Package

`>>>` lines in Haddock comments run via GHCi. Output on following lines is
compared. Examples within a comment share scope.

- **Pros:** Pure REPL transcript approach.
- **Cons:** Slow (GHCi reload per group). `doctest-parallel` and
  `cabal-docspec` exist to address performance.

---

## 6. JavaScript/TypeScript

**No built-in mechanism.** Ad-hoc tools exist:

- **markdown-doctest:** Extracts JS blocks from markdown, checks no-throw only.
- **doctest-ts:** `// =>` assertions in TS source translated to test files.
- **davidchambers/doctest:** `// >` expressions in JS source evaluated.

Major JS projects (Express, axios) generally don't test README examples. Prisma
maintains a separate `prisma-examples` repo with full runnable projects.

**Key insight:** The lack of a standard mechanism means JS examples drift.

---

## 7. Java/Kotlin

**JEP 413 `@snippet` tag (JDK 18+):** JavaDoc references external `.java` files
that are part of the test suite. Tested code IS documented code.

**evitaDB pattern:** JUnit 5 `DynamicContainer` extracts code blocks from
markdown, compiles via JShell, runs as parameterized tests.

**Key insight:** Java's `@snippet` is architecturally sound — reference by path,
no extraction needed.

---

## 8. Language-Agnostic Tools

### LLVM `lit`

`RUN:` lines in comments specify shell commands. `FileCheck` matches patterns
against stdout (`CHECK:`, `CHECK-NEXT:`, `CHECK-NOT:`, `CHECK-DAG:`).
Concurrent execution. `XFAIL` marks known-broken tests.

### Cram Tests

`.t` files with shell transcripts: `  $ ` for commands, indented lines for
expected output. `(re)` suffix for regex, `(glob)` for glob patterns.

**Killer feature:** `cram -i` accepts actual output interactively. Adopted by
OCaml's Dune as `dune promote`.

### mdBook

`mdbook test` passes Rust code blocks to `rustdoc --test`. Reuses rustdoc
infrastructure for free.

---

## Summary Table

| Approach | Mechanism | Strength | Weakness |
|---|---|---|---|
| **Rust rustdoc** | Doc comment code compiled+run | Example IS test | Slow per-example compilation |
| **Go Examples** | Naming convention + `// Output:` | Elegant, zero config | Stdout-only |
| **Elixir doctest** | `iex>` in `@doc` strings | First-class in ExUnit | No sandbox isolation |
| **Haskell doctest** | `>>>` in Haddock, GHCi | Pure REPL transcript | Slow |
| **JS markdown-doctest** | Extract from .md | Better than nothing | No-crash only |
| **Java `@snippet`** | JavaDoc refs tested files | Clean architecture | JDK 18+ |
| **Cram** | Shell transcripts in `.t` | Interactive accept workflow | CLI-only |
| **pytest-examples** | `#>` markers in .py | Auto-update output | Extra dependency |

## Cross-Cutting Insights

1. **The best systems make the documentation the test** (Rust, Go, Elixir)
   rather than maintaining separate example files.
2. **Hiding boilerplate** is critical — Rust's `#` lines, Go's implicit main,
   Elixir's shared module context.
3. **Output-based testing** (`// Output:`, Cram) is the simplest assertion
   mechanism but limits what you can test.
4. **The "accept actual output" workflow** (Cram `-i`, Dune `promote`,
   pytest-examples `--update-examples`) dramatically reduces maintenance
   friction.
5. **Java's `@snippet`** (reference external tested files) is the cleanest
   for compiled languages where inline evaluation is impractical.

## Recommendations for remote-store

**Option A: Inline assertions (simplest, recommended now)**
Add `assert` statements to existing `examples/*.py` scripts. Zero dependencies,
examples stay runnable standalone, immediate value.

**Option B: Go-style output markers + pytest-examples**
Adopt `#>` markers, use `--update-examples` to auto-sync. Good if we want
output validation.

**Option C: Doctest in docstrings (longer-term)**
Small examples in API docstrings, run with `pytest --doctest-modules`. Closest
to the Rust/Go/Elixir ideal for core methods. Keep standalone examples as
tutorials with inline assertions (Option A).

**Suggested path:** A now, C later as the API stabilizes.
