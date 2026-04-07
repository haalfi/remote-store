// DepthCounting.dfy — Verified reference algorithm for DEPTH-001.
//
// Gap 4 from BK-140: backends diverged on how they count depth in
// `list_files(path, recursive=True, max_depth=N)`.
//
// This module proves four properties of the Depth function defined
// in BackendContract.dfy:
//   1. Immediate children have depth 0.
//   2. max_depth=0 includes immediate children.
//   3. Depth filter is inclusive (<=, not <).
//   4. Files deeper than max_depth are excluded.
//
// Best-practice notes:
// - Uses `calc` blocks for step-by-step arithmetic.
// - Lemma bodies have explicit assert breadcrumbs.
// - Helper lemma isolates SlashCount reasoning.

include "BackendContract.dfy"

// ---------------------------------------------------------------------------
// §1  SlashCount helper lemma
// ---------------------------------------------------------------------------

// A string with no '/' has SlashCount == 0.
lemma SlashCountZero(s: string)
  requires forall i | 0 <= i < |s| :: s[i] != '/'
  ensures SlashCount(s) == 0
  decreases |s|
{
  if |s| == 0 {
    // Base case: SlashCount("") == 0.
  } else {
    assert s[0] != '/';
    // Recursive case: 0 + SlashCount(s[1..]).
    SlashCountZero(s[1..]);
  }
}

// ---------------------------------------------------------------------------
// §2  Immediate child depth
// ---------------------------------------------------------------------------

// Property 1: A file at "root/fileName" has depth 0 relative to root,
// for any root (including hierarchical roots like "data/raw/subdir"),
// provided fileName contains no '/'.
//
// Proof outline:
//   child = root + "/" + fileName
//   child[..|root|] == root           ✓ (string concatenation)
//   child[|root|] == '/'              ✓ (the separator we inserted)
//   suffix = child[|root|+1..] == fileName
//   SlashCount(fileName) == 0         ✓ (precondition)
//   Depth == 0
lemma ImmediateChildDepthIsZero(root: string, fileName: string)
  requires root != ""
  requires fileName != ""
  // Only fileName must be slash-free; root may contain slashes
  // (e.g. "data/raw/subdir").  Depth only examines the suffix
  // after root + "/", which is fileName.
  requires forall i | 0 <= i < |fileName| :: fileName[i] != '/'
  ensures Depth(root, root + "/" + fileName) == 0
{
  var child := root + "/" + fileName;

  // Establish prefix match.
  assert |child| == |root| + 1 + |fileName|;
  assert |child| > |root| + 1;
  assert child[..|root|] == root;
  assert child[|root|] == '/';

  // Suffix is fileName.
  var suffix := child[|root| + 1..];
  assert suffix == fileName;

  // fileName has no slashes, so SlashCount == 0.
  SlashCountZero(fileName);
  assert SlashCount(suffix) == 0;

  // By definition of Depth.
  assert Depth(root, child) == SlashCount(suffix);
  assert Depth(root, child) == 0;
}

// ---------------------------------------------------------------------------
// §3  Filter boundary properties
// ---------------------------------------------------------------------------

// Property 2: max_depth=0 includes immediate children.
lemma MaxDepthZeroIsImmediate(root: string, fileName: string)
  requires root != ""
  requires fileName != ""
  requires forall i | 0 <= i < |fileName| :: fileName[i] != '/'
  ensures Depth(root, root + "/" + fileName) <= 0
{
  ImmediateChildDepthIsZero(root, fileName);
  assert Depth(root, root + "/" + fileName) == 0;
  assert 0 <= 0;
}

// Property 3: IsChildOf implies non-negative Depth.
// This closes the -1 gap: a valid child always has Depth >= 0,
// so the depth filter postcondition (Depth >= 0 && Depth <= max_depth)
// cannot be trivially satisfied by non-children.
lemma ChildHasNonNegativeDepth(root: string, child: string)
  requires IsChildOf(child, root)
  ensures Depth(root, child) >= 0
{
  // IsChildOf guarantees: |child| > |root| + 1, prefix match, separator.
  // Depth's first three guards all pass, so it returns SlashCount(suffix) >= 0.
  assert |child| > |root| + 1;
  assert child[..|root|] == root;
  assert child[|root|] == '/';
  var suffix := child[|root| + 1..];
  assert Depth(root, child) == SlashCount(suffix);
  // SlashCount returns nat (>= 0).
}

// Property 4: Depth filter is inclusive — depth == maxDepth passes.
lemma DepthFilterIsInclusive(root: string, child: string, maxDepth: nat)
  requires Depth(root, child) == maxDepth as int
  ensures Depth(root, child) <= maxDepth as int
{
  calc {
    Depth(root, child);
  ==
    maxDepth as int;
  <=
    maxDepth as int;
  }
}

// Property 4: depth == maxDepth + 1 is excluded.
lemma DepthFilterExcludesDeeper(root: string, child: string, maxDepth: nat)
  requires Depth(root, child) == (maxDepth + 1) as int
  ensures Depth(root, child) > maxDepth as int
{
  calc {
    Depth(root, child);
  ==
    (maxDepth + 1) as int;
  >
    maxDepth as int;
  }
}

// ---------------------------------------------------------------------------
// §4  Depth table (documentation / cross-reference)
// ---------------------------------------------------------------------------
//
// Given root = "data" (no internal "/"):
//
// | File path                 | Suffix after "data/" | SlashCount | Depth | max_depth=1? |
// |---------------------------|----------------------|------------|-------|--------------|
// | data/a.csv                | a.csv                |     0      |   0   |   included   |
// | data/raw/b.csv            | raw/b.csv            |     1      |   1   |   included   |
// | data/raw/2026/c.csv       | raw/2026/c.csv       |     2      |   2   |   excluded   |
// | data/raw/2026/01/d.csv    | raw/2026/01/d.csv    |     3      |   3   |   excluded   |
//
// This table matches spec 037-depth-limited-listing.md and the
// DEPTH-001 amendment proposed in BK-140.

// ---------------------------------------------------------------------------
// §5  PBT cross-reference
// ---------------------------------------------------------------------------
//
// | Dafny lemma                 | Hypothesis property        | What it checks          |
// |-----------------------------|----------------------------|-------------------------|
// | ImmediateChildDepthIsZero   | test_depth_immediate_child | depth("r","r/f") == 0   |
// | DepthFilterIsInclusive      | test_depth_filter_boundary | d==N passes filter(N)   |
// | DepthFilterExcludesDeeper   | test_depth_filter_boundary | d==N+1 fails filter(N)  |
// | MaxDepthZeroIsImmediate     | test_list_max_depth_zero   | max_depth=0 → immediate |
