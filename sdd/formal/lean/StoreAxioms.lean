/-!
# The store model's axioms, and the lemmas of § 7, for every universe

Source of truth: `sdd/specs/051-store-tree.md` (TREE-001 to TREE-012). The
§ numbers below are those of its rationale,
`sdd/research/research-store-model-axioms.md` (BK-435). This
file restates § 3 clause by clause, and § 2 as noted below, and proves § 4's D1 and § 7's L1 to
L6 from them; it adds no claim of its own. Where this file and spec 051
disagree, a statement here that misrestates the spec is fixed here; a spec
claim that a faithful restatement disproves is fixed in the spec.

Nothing here assumes finiteness: the universe `U` is an arbitrary type, and
no lemma takes a `Fintype` or a bound. That is the difference from the Alloy
model `sdd/formal/alloy/StoreAxioms.als`, which checks L1 to L5 up to a
bounded scope and cannot state L6. Two claims no bounded scope reaches are
proved at the end: that the axioms have an infinite model (§ 3, no finiteness
axiom), which also shows the axioms consistent, so no lemma here holds merely
because nothing satisfies them; and § 9.7's infinite upward chain.

The alphabet is any type with a chosen separator. The lemmas do not need a
symbol besides `/`; only the infinite model takes one, as § 2 provides.

Lean core only, no Mathlib. The lakefile turns warnings into errors, so a
`sorry` fails the build, and the `#guard_msgs` lines at the end pin the
axioms each headline result depends on (D1, L1 to L6, L6_empty_folder,
infinite_model, infinite_upward_chain); a new result is pinned only once a
line is added for it.
-/

namespace StoreAxioms

variable {α : Type}

/-! ## § 2 Notation and parameters

`α` is the alphabet Σ and `sl` its separator `/`; a word is a `List α`, ε is
`[]`, and words are compared as lists, exactly. -/

/-- N: the non-empty words in which `/` does not occur. -/
def InN (sl : α) (w : List α) : Prop := w ≠ [] ∧ sl ∉ w

/-- A structure (U, F, I, r, C, name) of § 2, before any axiom. `C p x` reads
"p contains x". -/
structure Structure (α U : Type) where
  F : U → Prop
  I : U → Prop
  r : U
  C : U → U → Prop
  name : U → List α

/-- AX-6's chain: x₀, …, xₙ with x₀ = r, xₙ = x and (xᵢ, xᵢ₊₁) ∈ C for every
i < n, given as a function on the indices (values past n are unused). -/
def IsChain {U : Type} (S : Structure α U) (x : U) (n : Nat) (c : Nat → U) : Prop :=
  c 0 = S.r ∧ c n = x ∧ ∀ i, i < n → S.C (c i) (c (i + 1))

/-! ## § 3 The axioms -/

/-- AX-1 to AX-8, one field per clause. -/
structure Axioms {U : Type} (sl : α) (S : Structure α U) : Prop where
  /-- AX-1, disjoint: F ∩ I = ∅. -/
  ax1_disjoint : ∀ x, ¬ (S.F x ∧ S.I x)
  /-- AX-1, covering: U = F ∪ I. -/
  ax1_covering : ∀ x, S.F x ∨ S.I x
  /-- AX-2: r ∈ F. -/
  ax2 : S.F S.r
  /-- AX-3: C ⊆ F × U. -/
  ax3 : ∀ p x, S.C p x → S.F p
  /-- AX-4: at most one container. -/
  ax4 : ∀ x p q, S.C p x → S.C q x → p = q
  /-- AX-5: the root has no container. -/
  ax5 : ∀ p, ¬ S.C p S.r
  /-- AX-6: every entity has a chain from the root. -/
  ax6 : ∀ x, ∃ n c, IsChain S x n c
  /-- AX-7, name(r) = ε. -/
  ax7_root : S.name S.r = []
  /-- AX-7, non-empty: name(x) ≠ ε for x ≠ r. -/
  ax7_nonempty : ∀ x, x ≠ S.r → S.name x ≠ []
  /-- AX-7, no `/`: `/` does not occur in name(x) for x ≠ r. -/
  ax7_noslash : ∀ x, x ≠ S.r → sl ∉ S.name x
  /-- AX-8: two children of one container never share a name. -/
  ax8 : ∀ p x y, S.C p x → S.C p y → S.name x = S.name y → x = y

/-! ## Words: the `/`-join of a sequence of names -/

/-- s₁ / s₂ / … / sₙ, and ε for the empty sequence. -/
def join (sl : α) : List (List α) → List α
  | [] => []
  | [w] => w
  | w :: v :: ws => w ++ sl :: join sl (v :: ws)

/-- The first `/` of `w ++ / ++ J`, when `w` has none, is the one after `w`:
any other split `a ++ / ++ rest` of the same word either is that one or lies
inside `J`. -/
theorem split_first (sl : α) : ∀ (w a rest J : List α), sl ∉ w →
    a ++ sl :: rest = w ++ sl :: J →
    (a = w ∧ rest = J) ∨ ∃ a', a = w ++ sl :: a' ∧ a' ++ sl :: rest = J
  | [], a, rest, J, _, heq => by
    cases a with
    | nil =>
      left
      simp only [List.nil_append, List.cons.injEq] at heq
      exact ⟨rfl, heq.2⟩
    | cons b a' =>
      right
      simp only [List.cons_append, List.nil_append, List.cons.injEq] at heq
      exact ⟨a', by simp [heq.1], heq.2⟩
  | c :: w', a, rest, J, hw, heq => by
    cases a with
    | nil =>
      simp only [List.nil_append, List.cons_append, List.cons.injEq] at heq
      exact absurd (heq.1 ▸ List.mem_cons_self) hw
    | cons b a' =>
      simp only [List.cons_append, List.cons.injEq] at heq
      have hw' : sl ∉ w' := fun hm => hw (List.mem_cons_of_mem _ hm)
      rcases split_first sl w' a' rest J hw' heq.2 with ⟨h1, h2⟩ | ⟨a'', h1, h2⟩
      · exact Or.inl ⟨by rw [heq.1, h1], h2⟩
      · exact Or.inr ⟨a'', by rw [heq.1, h1]; rfl, h2⟩

theorem mem_of_eq_append_cons {sl : α} {w a b : List α} (h : w = a ++ sl :: b) : sl ∈ w := by
  rw [h]; exact List.mem_append_right _ List.mem_cons_self

theorem join_eq_nil {sl : α} {ws : List (List α)} (hN : ∀ w ∈ ws, InN sl w)
    (h : join sl ws = []) : ws = [] := by
  match ws, hN, h with
  | [], _, _ => rfl
  | [w], hN, h => exact absurd h (hN w List.mem_cons_self).1
  | w :: v :: ws, hN, h =>
    simp only [join, List.append_eq_nil_iff] at h
    exact absurd h.1 (hN w List.mem_cons_self).1

/-- The auxiliary lemma of § 10 step 2, as injectivity: the `/`-join of a
sequence of names from N determines the sequence. -/
theorem join_inj {sl : α} : ∀ (ws vs : List (List α)), (∀ w ∈ ws, InN sl w) →
    (∀ v ∈ vs, InN sl v) → join sl ws = join sl vs → ws = vs
  | [], vs, _, hv, h => (join_eq_nil hv h.symm).symm
  | ws@(_ :: _), [], hw, _, h => join_eq_nil hw h
  | [w], [v], _, _, h => by simp only [join] at h; rw [h]
  | [w], v :: v' :: vs, hw, hv, h => by
    simp only [join] at h
    exact absurd (mem_of_eq_append_cons h) (hw w List.mem_cons_self).2
  | w :: w' :: ws, [v], hw, hv, h => by
    simp only [join] at h
    exact absurd (mem_of_eq_append_cons h.symm) (hv v List.mem_cons_self).2
  | w :: w' :: ws, v :: v' :: vs, hw, hv, h => by
    simp only [join] at h
    have hwN := (hw w List.mem_cons_self).2
    have hvN := (hv v List.mem_cons_self).2
    rcases split_first sl w v _ _ hwN h.symm with ⟨h1, h2⟩ | ⟨a', h1, _⟩
    · have := join_inj (w' :: ws) (v' :: vs)
        (fun x hx => hw x (List.mem_cons_of_mem _ hx))
        (fun x hx => hv x (List.mem_cons_of_mem _ hx)) h2.symm
      rw [h1, this]
    · exact absurd (mem_of_eq_append_cons h1) hvN

/-- L4's shape clauses: no leading, trailing or doubled `/`. -/
def GoodShape (sl : α) (k : List α) : Prop :=
  (∀ b, k ≠ sl :: b) ∧ (∀ a, k ≠ a ++ [sl]) ∧ (∀ a b, k ≠ a ++ sl :: sl :: b)

theorem join_shape {sl : α} : ∀ (ws : List (List α)), ws ≠ [] → (∀ w ∈ ws, InN sl w) →
    join sl ws ≠ [] ∧ GoodShape sl (join sl ws)
  | [], hne, _ => absurd rfl hne
  | [w], _, hN => by
    have ⟨hne, hsl⟩ := hN w List.mem_cons_self
    refine ⟨hne, fun b h => ?_, fun a h => ?_, fun a b h => ?_⟩
    · exact hsl (by simp only [join] at h; rw [h]; exact List.mem_cons_self)
    · exact hsl (mem_of_eq_append_cons h)
    · exact hsl (mem_of_eq_append_cons h)
  | w :: v :: ws, _, hN => by
    have ⟨hne, hsl⟩ := hN w List.mem_cons_self
    have ⟨hJne, hJlead, hJtrail, hJdouble⟩ :=
      join_shape (v :: ws) (List.cons_ne_nil _ _) (fun x hx => hN x (List.mem_cons_of_mem _ hx))
    simp only [join]
    refine ⟨List.append_ne_nil_of_left_ne_nil hne _, fun b h => ?_, fun a h => ?_, fun a b h => ?_⟩
    · rcases split_first sl w [] b _ hsl (by rw [List.nil_append]; exact h.symm) with
        ⟨h1, _⟩ | ⟨a', h1, _⟩
      · exact hne h1.symm
      · simp at h1
    · rcases split_first sl w a [] _ hsl h.symm with ⟨_, h2⟩ | ⟨a', _, h2⟩
      · exact hJne h2.symm
      · exact hJtrail a' h2.symm
    · rcases split_first sl w a (sl :: b) _ hsl h.symm with ⟨_, h2⟩ | ⟨a', _, h2⟩
      · exact hJlead b h2.symm
      · exact hJdouble a' b h2.symm

/-! ## § 4 Derived definitions and two consequences -/

/-- name(c₁), …, name(cₙ): the names along a chain, the root's excluded. -/
def seqAlong {U : Type} (S : Structure α U) (c : Nat → U) : Nat → List (List α)
  | 0 => []
  | n + 1 => seqAlong S c n ++ [S.name (c (n + 1))]

theorem length_seqAlong {U : Type} (S : Structure α U) (c : Nat → U) :
    ∀ n, (seqAlong S c n).length = n
  | 0 => rfl
  | n + 1 => by simp [seqAlong, length_seqAlong S c n]

theorem seqAlong_congr {U : Type} (S : Structure α U) {c d : Nat → U} :
    ∀ n, (∀ i, i ≤ n → c i = d i) → seqAlong S c n = seqAlong S d n
  | 0, _ => rfl
  | n + 1, h => by
    simp only [seqAlong]
    rw [seqAlong_congr S n (fun i hi => h i (Nat.le_succ_of_le hi)), h (n + 1) (Nat.le_refl _)]

theorem take_seqAlong {U : Type} (S : Structure α U) (c : Nat → U) :
    ∀ n i, i ≤ n → (seqAlong S c n).take i = seqAlong S c i
  | 0, i, hi => by rw [Nat.le_zero.mp hi]; rfl
  | n + 1, i, hi => by
    rcases Nat.lt_or_eq_of_le hi with hlt | heq
    · simp only [seqAlong]
      rw [List.take_append_of_le_length (by rw [length_seqAlong]; omega)]
      exact take_seqAlong S c n i (by omega)
    · have hl := List.take_length (l := seqAlong S c (n + 1))
      rw [length_seqAlong] at hl
      rw [heq, hl]

/-- A proper ancestor: a chain of one or more C-steps from a to x. -/
def ProperAncestor {U : Type} (S : Structure α U) (a x : U) : Prop :=
  ∃ k, 1 ≤ k ∧ ∃ y : Nat → U, y 0 = a ∧ y k = x ∧ ∀ j, j < k → S.C (y j) (y (j + 1))

section Model

variable {U : Type} {sl : α} {S : Structure α U} (h : Axioms sl S)
include h

/-- Chain uniqueness, the core of L1: two chains to one entity have the same
length and the same entries. -/
theorem chain_unique : ∀ (n : Nat) (x : U) (c : Nat → U) (m : Nat) (d : Nat → U),
    IsChain S x n c → IsChain S x m d → m = n ∧ ∀ i, i ≤ n → d i = c i := by
  intro n
  induction n with
  | zero =>
    intro x c m d ⟨hc0, hcn, _⟩ ⟨hd0, hdm, hdC⟩
    have hx : x = S.r := hcn.symm.trans hc0
    cases m with
    | zero =>
      refine ⟨rfl, fun i hi => ?_⟩
      rw [Nat.le_zero.mp hi, hd0, hc0]
    | succ k =>
      have hC := hdC k (Nat.lt_succ_self k)
      rw [hdm, hx] at hC
      exact absurd hC (h.ax5 _)
  | succ k ih =>
    intro x c m d ⟨hc0, hcn, hcC⟩ ⟨hd0, hdm, hdC⟩
    have hcx : S.C (c k) x := by rw [← hcn]; exact hcC k (Nat.lt_succ_self k)
    cases m with
    | zero =>
      have hx : x = S.r := hdm.symm.trans hd0
      rw [hx] at hcx
      exact absurd hcx (h.ax5 _)
    | succ j =>
      have hdx : S.C (d j) x := by rw [← hdm]; exact hdC j (Nat.lt_succ_self j)
      have hp : d j = c k := h.ax4 x _ _ hdx hcx
      have ⟨hjk, hi⟩ := ih (c k) c j d
        ⟨hc0, rfl, fun i hi => hcC i (Nat.lt_succ_of_lt hi)⟩
        ⟨hd0, hp, fun i hi => hdC i (Nat.lt_succ_of_lt hi)⟩
      refine ⟨by rw [hjk], fun i hi' => ?_⟩
      rcases Nat.lt_or_eq_of_le hi' with hlt | heq
      · exact hi i (Nat.le_of_lt_succ hlt)
      · rw [heq, ← hjk, hdm, hjk, hcn]

/-- The depth n of x: the length of its chain. -/
noncomputable def depth (x : U) : Nat := Classical.choose (h.ax6 x)

/-- The chain of x. L1 makes it the only one. -/
noncomputable def chain (x : U) : Nat → U :=
  Classical.choose (Classical.choose_spec (h.ax6 x))

theorem chain_spec (x : U) : IsChain S x (depth h x) (chain h x) :=
  Classical.choose_spec (Classical.choose_spec (h.ax6 x))

/-- Any chain to x is the chain of x. -/
theorem chain_eq {x : U} {n : Nat} {c : Nat → U} (hc : IsChain S x n c) :
    n = depth h x ∧ ∀ i, i ≤ depth h x → c i = chain h x i :=
  chain_unique h _ x (chain h x) n c (chain_spec h x) hc

omit h in
/-- A chain's prefix is a chain to its last entry. -/
theorem chain_prefix {x : U} {n : Nat} {c : Nat → U} (hc : IsChain S x n c) {i : Nat}
    (hi : i ≤ n) : IsChain S (c i) i c :=
  ⟨hc.1, rfl, fun j hj => hc.2.2 j (by omega)⟩

theorem depth_root : depth h S.r = 0 :=
  (chain_eq h (x := S.r) (c := fun _ => S.r) ⟨rfl, rfl, fun _ hi => absurd hi (by omega)⟩).1.symm

theorem eq_root_of_depth {x : U} (hx : depth h x = 0) : x = S.r := by
  have ⟨h0, hn, _⟩ := chain_spec h x
  rw [hx] at hn
  exact hn.symm.trans h0

theorem chain_ne_root {x : U} {n : Nat} {c : Nat → U} (hc : IsChain S x n c) {i : Nat}
    (hi : 1 ≤ i) (hin : i ≤ n) : c i ≠ S.r := by
  intro heq
  have hC := hc.2.2 (i - 1) (by omega)
  rw [Nat.sub_add_cancel hi, heq] at hC
  exact h.ax5 _ hC

/-- Extending the chain of p by x gives the chain of x. -/
theorem chain_step {p x : U} (hpx : S.C p x) :
    depth h x = depth h p + 1 ∧ (∀ i, i ≤ depth h p → chain h x i = chain h p i) ∧
      chain h x (depth h p + 1) = x := by
  let c : Nat → U := fun i => if i ≤ depth h p then chain h p i else x
  have ⟨hp0, hpn, hpC⟩ := chain_spec h p
  have hlast : ¬ (depth h p + 1 ≤ depth h p) := by omega
  have hc : IsChain S x (depth h p + 1) c := by
    refine ⟨by simp [c, hp0], by simp [c, hlast], fun i hi => ?_⟩
    have hil : i ≤ depth h p := by omega
    by_cases hi1 : i + 1 ≤ depth h p
    · simp only [c, hil, hi1, ite_true]; exact hpC i (by omega)
    · have hip : i = depth h p := by omega
      simp only [c, hil, hi1, ite_true, ite_false]
      rw [hip, hpn]; exact hpx
  have ⟨hd, hcx⟩ := chain_eq h hc
  refine ⟨hd.symm, fun i hi => ?_, ?_⟩
  · rw [← hcx i (by omega)]; simp [c, hi]
  · rw [← hcx _ (by omega)]; simp [c, hlast]

/-- D1: every non-root has exactly one container. -/
theorem D1 (x : U) (hx : x ≠ S.r) : ∃ p, S.C p x ∧ ∀ q, S.C q x → q = p := by
  have ⟨_, hn, hC⟩ := chain_spec h x
  cases hd : depth h x with
  | zero => exact absurd (eq_root_of_depth h hd) hx
  | succ k =>
    rw [hd] at hn hC
    have hpx := hC k (Nat.lt_succ_self k)
    rw [hn] at hpx
    exact ⟨chain h x k, hpx, fun q hq => h.ax4 x q _ hq hpx⟩

/-- The sequence of names along the chain of x. -/
noncomputable def seqOf (x : U) : List (List α) := seqAlong S (chain h x) (depth h x)

/-- Key(x) = name(x₁) / … / name(xₙ), and Key(r) = ε. -/
noncomputable def Key (x : U) : List α := join sl (seqOf h x)

theorem length_seqOf (x : U) : (seqOf h x).length = depth h x := length_seqAlong _ _ _

theorem seqOf_root : seqOf h S.r = [] := by
  simp only [seqOf, depth_root h]; rfl

theorem seqOf_step {p x : U} (hpx : S.C p x) : seqOf h x = seqOf h p ++ [S.name x] := by
  have ⟨hd, hpre, hlast⟩ := chain_step h hpx
  simp only [seqOf, hd, seqAlong, hlast]
  rw [seqAlong_congr S _ hpre]

/-- The names along any chain to x are seqOf x, and those along a prefix of
it are the prefix's seqOf. -/
theorem seqOf_chain {x : U} {n : Nat} {c : Nat → U} (hc : IsChain S x n c) {i : Nat}
    (hi : i ≤ n) : seqOf h (c i) = seqAlong S c i := by
  have ⟨hd, hcc⟩ := chain_eq h (chain_prefix hc hi)
  simp only [seqOf, ← hd]
  exact (seqAlong_congr S i (fun j hj => hcc j (by omega))).symm

theorem seqAlong_InN {c : Nat → U} : ∀ n, (∀ i, i < n → S.C (c i) (c (i + 1))) →
    ∀ w ∈ seqAlong S c n, InN sl w
  | 0, _, w, hw => absurd hw List.not_mem_nil
  | n + 1, hC, w, hw => by
    simp only [seqAlong, List.mem_append, List.mem_singleton] at hw
    rcases hw with hw | hw
    · exact seqAlong_InN n (fun i hi => hC i (by omega)) w hw
    · have hne : c (n + 1) ≠ S.r := fun heq => h.ax5 (c n) (heq ▸ hC n (by omega))
      rw [hw]
      exact ⟨h.ax7_nonempty _ hne, h.ax7_noslash _ hne⟩

theorem seqOf_InN (x : U) : ∀ w ∈ seqOf h x, InN sl w :=
  seqAlong_InN h _ (chain_spec h x).2.2

theorem seqOf_inj : ∀ (n : Nat) (x y : U), depth h x = n → seqOf h x = seqOf h y → x = y := by
  intro n
  induction n with
  | zero =>
    intro x y hx hxy
    have hy : depth h y = 0 := by rw [← length_seqOf, ← hxy, length_seqOf, hx]
    rw [eq_root_of_depth h hx, eq_root_of_depth h hy]
  | succ k ih =>
    intro x y hx hxy
    have hy : depth h y = k + 1 := by rw [← length_seqOf, ← hxy, length_seqOf, hx]
    have hxr : x ≠ S.r := fun he => by rw [he, depth_root h] at hx; omega
    have hyr : y ≠ S.r := fun he => by rw [he, depth_root h] at hy; omega
    have ⟨p, hpx, _⟩ := D1 h x hxr
    have ⟨q, hqy, _⟩ := D1 h y hyr
    rw [seqOf_step h hpx, seqOf_step h hqy] at hxy
    have ⟨hpq, hn⟩ := List.append_inj' hxy rfl
    have hp : depth h p = k := by have := (chain_step h hpx).1; omega
    have hpq' : p = q := ih p q hp hpq
    rw [← hpq'] at hqy
    exact h.ax8 p x y hpx hqy (List.singleton_inj.mp hn)

/-! ## § 7 Lemmas -/

/-- L1, chain uniqueness: every x has exactly one chain. -/
theorem L1 (x : U) : ∃ n c, IsChain S x n c ∧
    ∀ m d, IsChain S x m d → m = n ∧ ∀ i, i ≤ n → d i = c i :=
  ⟨depth h x, chain h x, chain_spec h x,
    fun m d hd => chain_unique h _ x _ m d (chain_spec h x) hd⟩

/-- L2, acyclicity: no y₀, …, yₖ with k ≥ 1, (yᵢ, yᵢ₊₁) ∈ C and yₖ = y₀. -/
theorem L2 (k : Nat) (y : Nat → U) (hk : 1 ≤ k)
    (hy : ∀ i, i < k → S.C (y i) (y (i + 1))) : y k ≠ y 0 := by
  have hd : ∀ i, i ≤ k → depth h (y i) = depth h (y 0) + i := by
    intro i
    induction i with
    | zero => intro _; rfl
    | succ i ih =>
      intro hi
      rw [(chain_step h (hy i (by omega))).1, ih (by omega)]
      omega
  intro heq
  have := hd k (Nat.le_refl k)
  rw [heq] at this
  omega

/-- L3, Key injectivity. -/
theorem L3 (x y : U) (hxy : Key h x = Key h y) : x = y :=
  seqOf_inj h _ x y rfl (join_inj _ _ (seqOf_InN h x) (seqOf_InN h y) hxy)

/-- L4, Key shape: Key(x) = ε iff x = r; otherwise Key(x) has no leading,
trailing or doubled `/`. -/
theorem L4 :
    (∀ x, Key h x = [] ↔ x = S.r) ∧
    ∀ x, x ≠ S.r → (∀ b, Key h x ≠ sl :: b) ∧ (∀ a, Key h x ≠ a ++ [sl]) ∧
      (∀ a b, Key h x ≠ a ++ sl :: sl :: b) := by
  refine ⟨fun x => ⟨fun hk => ?_, fun hx => ?_⟩, fun x hx => ?_⟩
  · have hs := join_eq_nil (seqOf_InN h x) hk
    exact eq_root_of_depth h (by rw [← length_seqOf, hs]; rfl)
  · rw [hx, Key, seqOf_root]; rfl
  · have hne : seqOf h x ≠ [] := fun hs => hx (eq_root_of_depth h (by
      rw [← length_seqOf, hs]; rfl))
    exact (join_shape _ hne (seqOf_InN h x)).2

/-- L5, prefix closure: if Key(x) = s₁/…/sₙ then for each 0 < i < n the
string s₁/…/sᵢ is the Key of a folder that is a proper ancestor of x; and an
item occurs only at the final index of any chain. -/
theorem L5 :
    (∀ (x : U) (ss : List (List α)), (∀ s ∈ ss, InN sl s) → Key h x = join sl ss →
      ∀ i, 0 < i → i < ss.length →
        ∃ a, S.F a ∧ ProperAncestor S a x ∧ Key h a = join sl (ss.take i)) ∧
    (∀ (x : U) (n : Nat) (c : Nat → U), IsChain S x n c → ∀ i, i < n → ¬ S.I (c i)) := by
  refine ⟨fun x ss hss hk i _ hi => ?_, fun x n c hc i hi hI => ?_⟩
  · have hs : seqOf h x = ss := join_inj _ _ (seqOf_InN h x) hss hk
    have hid : i < depth h x := by rw [← length_seqOf, hs]; exact hi
    have ⟨_, hxn, hC⟩ := chain_spec h x
    refine ⟨chain h x i, h.ax3 _ _ (hC i hid), ?_, ?_⟩
    · refine ⟨depth h x - i, by omega, fun j => chain h x (i + j), rfl, ?_, fun j hj => ?_⟩
      · show chain h x (i + (depth h x - i)) = x
        rw [Nat.add_sub_cancel' (by omega)]; exact hxn
      · show S.C (chain h x (i + j)) (chain h x (i + (j + 1)))
        rw [← Nat.add_assoc]; exact hC (i + j) (by omega)
    · rw [Key, seqOf_chain h (chain_spec h x) (Nat.le_of_lt hid), ← hs, seqOf,
        take_seqAlong S _ _ _ (Nat.le_of_lt hid)]
  · exact h.ax1_disjoint _ ⟨h.ax3 _ _ (hc.2.2 i hi), hI⟩

end Model

/-! ## § 7, L6: the trie correspondence -/

/-- A pair (L, K) of § 7's L6: a set of sequences of names and the items. -/
structure Trie (α : Type) where
  L : List (List α) → Prop
  K : List (List α) → Prop

theorem Trie.ext' {T T' : Trie α} (hL : ∀ s, T.L s ↔ T'.L s) (hK : ∀ s, T.K s ↔ T'.K s) :
    T = T' := by
  cases T; cases T'
  simp only [Trie.mk.injEq]
  exact ⟨funext fun s => propext (hL s), funext fun s => propext (hK s)⟩

/-- L6's conditions on (L, K): L is a set of finite sequences of names from N,
closed under taking prefixes and containing the empty sequence; K is a set of
non-empty sequences in L that have no proper extension in L. -/
structure Trie.WF (sl : α) (T : Trie α) : Prop where
  names : ∀ s, T.L s → ∀ w ∈ s, InN sl w
  nil : T.L []
  closed : ∀ s t, T.L (s ++ t) → T.L s
  K_L : ∀ s, T.K s → T.L s
  K_ne : ∀ s, T.K s → s ≠ []
  K_leaf : ∀ s t, T.K s → T.L (s ++ t) → t = []

/-- The structure a pair (L, K) describes: the entities are the sequences in
L, the items those in K and the folders the rest, the root is the empty
sequence, p contains p ++ [w], and a sequence's name is its last name. -/
def ofTrie {sl : α} {T : Trie α} (hT : T.WF sl) : Structure α {s // T.L s} where
  F s := ¬ T.K s.val
  I s := T.K s.val
  r := ⟨[], hT.nil⟩
  C p x := ∃ w, x.val = p.val ++ [w]
  name s := s.val.getLast?.getD []

/-- An isomorphism of structures: a bijection that preserves F, I, r, C and
name. -/
structure Iso {U V : Type} (S : Structure α U) (S' : Structure α V) where
  f : U → V
  g : V → U
  gf : ∀ x, g (f x) = x
  fg : ∀ y, f (g y) = y
  F : ∀ x, S.F x ↔ S'.F (f x)
  I : ∀ x, S.I x ↔ S'.I (f x)
  r : f S.r = S'.r
  C : ∀ p x, S.C p x ↔ S'.C (f p) (f x)
  name : ∀ x, S'.name (f x) = S.name x

def Iso.refl {U : Type} (S : Structure α U) : Iso S S :=
  ⟨id, id, fun _ => rfl, fun _ => rfl, fun _ => Iff.rfl, fun _ => Iff.rfl, rfl,
    fun _ _ => Iff.rfl, fun _ => rfl⟩

def Iso.symm {U V : Type} {S : Structure α U} {S' : Structure α V} (e : Iso S S') :
    Iso S' S where
  f := e.g
  g := e.f
  gf := e.fg
  fg := e.gf
  F y := by have := e.F (e.g y); rw [e.fg] at this; exact this.symm
  I y := by have := e.I (e.g y); rw [e.fg] at this; exact this.symm
  r := by rw [← e.r, e.gf]
  C p x := by have := e.C (e.g p) (e.g x); rw [e.fg, e.fg] at this; exact this.symm
  name y := by have := e.name (e.g y); rw [e.fg] at this; exact this.symm

def Iso.trans {U V W : Type} {S : Structure α U} {S' : Structure α V} {S'' : Structure α W}
    (e : Iso S S') (e' : Iso S' S'') : Iso S S'' where
  f := e'.f ∘ e.f
  g := e.g ∘ e'.g
  gf x := by simp [Function.comp, e'.gf, e.gf]
  fg y := by simp [Function.comp, e.fg, e'.fg]
  F x := (e.F x).trans (e'.F _)
  I x := (e.I x).trans (e'.I _)
  r := by simp [Function.comp, e.r, e'.r]
  C p x := (e.C p x).trans (e'.C _ _)
  name x := (e'.name _).trans (e.name x)

def Iso.ofEq {sl : α} {T T' : Trie α} (hT : T.WF sl) (hT' : T'.WF sl) (he : T = T') :
    Iso (ofTrie hT) (ofTrie hT') := by
  subst he; exact Iso.refl _

section Trie

variable {sl : α}

theorem getLastD_concat (s : List (List α)) (w : List α) :
    (s ++ [w]).getLast?.getD [] = w := by
  simp

theorem ofTrie_axioms {T : Trie α} (hT : T.WF sl) : Axioms sl (ofTrie hT) where
  ax1_disjoint _ hx := hx.1 hx.2
  ax1_covering x := (Classical.em (T.K x.val)).symm
  ax2 := fun hK => hT.K_ne _ hK rfl
  ax3 p x := fun ⟨w, hw⟩ hK => by
    have := hT.K_leaf p.val [w] hK (hw ▸ x.property)
    exact List.cons_ne_nil _ _ this
  ax4 x p q := fun ⟨w, hw⟩ ⟨w', hw'⟩ =>
    Subtype.ext (List.append_inj' (hw.symm.trans hw') rfl).1
  ax5 p := fun ⟨w, hw⟩ => by
    have : ([] : List (List α)) = p.val ++ [w] := hw
    simp at this
  ax6 x := by
    refine ⟨x.val.length,
      fun i => ⟨x.val.take i, hT.closed _ (x.val.drop i) (by rw [List.take_append_drop]; exact x.property)⟩,
      Subtype.ext (by simp; rfl), Subtype.ext (by simp), fun i hi => ⟨x.val[i], ?_⟩⟩
    simp only
    rw [List.take_add_one, List.getElem?_eq_getElem hi]
    rfl
  ax7_root := rfl
  ax7_nonempty x hx := by
    have ⟨hne, _⟩ := ax7_names hT x hx
    exact hne
  ax7_noslash x hx := (ax7_names hT x hx).2
  ax8 p x y := fun ⟨w, hw⟩ ⟨w', hw'⟩ hn => by
    simp only [ofTrie, hw, hw', getLastD_concat] at hn
    exact Subtype.ext (by rw [hw, hw', hn])
where
  ax7_names (hT : T.WF sl) (x : {s // T.L s}) (hx : x ≠ (ofTrie hT).r) :
      InN sl ((ofTrie hT).name x) := by
    have hne : x.val ≠ [] := fun he => hx (Subtype.ext he)
    have hlast := List.getLast_mem hne
    simp only [ofTrie, List.getLast?_eq_some_getLast hne, Option.getD_some]
    exact hT.names _ x.property _ hlast

/-- In the structure of (L, K), the sequence of names of the entity s is s. -/
theorem seqOf_ofTrie {T : Trie α} (hT : T.WF sl) (x : {s // T.L s}) :
    seqOf (ofTrie_axioms hT) x = x.val := by
  let c : Nat → {s // T.L s} := fun i =>
    ⟨x.val.take i, hT.closed _ (x.val.drop i) (by rw [List.take_append_drop]; exact x.property)⟩
  have hc : IsChain (ofTrie hT) x x.val.length c :=
    (ofTrie_axioms hT).ax6 x |>.elim fun _ _ => by
      refine ⟨Subtype.ext (by simp [c]; rfl), Subtype.ext (by simp [c]), fun i hi => ⟨x.val[i], ?_⟩⟩
      simp only [c]
      rw [List.take_add_one, List.getElem?_eq_getElem hi]
      rfl
  have hs : ∀ n, n ≤ x.val.length → seqAlong (ofTrie hT) c n = x.val.take n := by
    intro n
    induction n with
    | zero => intro _; rfl
    | succ n ih =>
      intro hn
      simp only [seqAlong]
      rw [ih (by omega)]
      show List.take n x.val ++ [(List.take (n + 1) x.val).getLast?.getD []] = _
      have ht : List.take (n + 1) x.val = List.take n x.val ++ [x.val[n]] := by
        rw [List.take_add_one, List.getElem?_eq_getElem (by omega)]; rfl
      rw [ht, getLastD_concat]
  have := seqOf_chain (ofTrie_axioms hT) hc (Nat.le_refl _)
  have hcl : c x.val.length = x := Subtype.ext (by simp [c])
  rw [hcl] at this
  rw [this, hs _ (Nat.le_refl _), List.take_length]

end Trie

section ToTrie

variable {U : Type} {sl : α} {S : Structure α U} (h : Axioms sl S)
include h

/-- The pair (L, K) of a model: the sequences of names of its entities, and
those of its items. -/
def toTrie : Trie α where
  L s := ∃ x, seqOf h x = s
  K s := ∃ x, S.I x ∧ seqOf h x = s

theorem not_I_root : ¬ S.I S.r := fun hI => h.ax1_disjoint _ ⟨h.ax2, hI⟩

theorem seqOf_ne_nil {x : U} (hx : x ≠ S.r) : seqOf h x ≠ [] := fun hs =>
  hx (eq_root_of_depth h (by rw [← length_seqOf, hs]; rfl))

/-- The prefix of length i of seqOf x is seqOf of the i-th entry of x's chain. -/
theorem seqOf_take {x : U} {i : Nat} (hi : i ≤ depth h x) :
    seqOf h (chain h x i) = (seqOf h x).take i := by
  rw [seqOf_chain h (chain_spec h x) hi, seqOf, take_seqAlong S _ _ _ hi]

theorem toTrie_wf : (toTrie h).WF sl where
  names _ := fun ⟨x, hx⟩ => hx ▸ seqOf_InN h x
  nil := ⟨S.r, seqOf_root h⟩
  closed s t := fun ⟨x, hx⟩ => by
    have hle : s.length ≤ depth h x := by
      rw [← length_seqOf, hx, List.length_append]; omega
    exact ⟨chain h x s.length, by rw [seqOf_take h hle, hx, List.take_left]⟩
  K_L _ := fun ⟨x, _, hx⟩ => ⟨x, hx⟩
  K_ne _ := fun ⟨x, hI, hx⟩ => by
    have hxr : x ≠ S.r := fun he => not_I_root h (he ▸ hI)
    exact hx ▸ seqOf_ne_nil h hxr
  K_leaf s t := fun ⟨x, hI, hx⟩ ⟨y, hy⟩ => by
    cases t with
    | nil => rfl
    | cons a t =>
      exfalso
      have hlt : s.length < depth h y := by
        rw [← length_seqOf, hy, List.length_append, List.length_cons]; omega
      have hpre : seqOf h (chain h y s.length) = seqOf h x := by
        rw [seqOf_take h (Nat.le_of_lt hlt), hy, List.take_left, hx]
      have hxe := seqOf_inj h _ _ x rfl hpre
      have hF := h.ax3 _ _ ((chain_spec h y).2.2 s.length hlt)
      rw [hxe] at hF
      exact h.ax1_disjoint x ⟨hF, hI⟩

/-- The entity whose sequence of names is s. -/
noncomputable def ofSeq (s : {s // (toTrie h).L s}) : U := Classical.choose s.property

theorem seqOf_ofSeq (s : {s // (toTrie h).L s}) : seqOf h (ofSeq h s) = s.val :=
  Classical.choose_spec s.property

/-- A model is isomorphic to the structure of its (L, K). -/
noncomputable def isoToTrie : Iso S (ofTrie (toTrie_wf h)) where
  f x := ⟨seqOf h x, x, rfl⟩
  g := ofSeq h
  gf x := seqOf_inj h _ _ _ rfl (seqOf_ofSeq h ⟨seqOf h x, x, rfl⟩)
  fg s := Subtype.ext (seqOf_ofSeq h s)
  F x := by
    show S.F x ↔ ¬ ∃ y, S.I y ∧ seqOf h y = seqOf h x
    constructor
    · exact fun hF ⟨y, hI, hy⟩ => h.ax1_disjoint x ⟨hF, seqOf_inj h _ _ _ rfl hy ▸ hI⟩
    · exact fun hn => (h.ax1_covering x).resolve_right fun hI => hn ⟨x, hI, rfl⟩
  I x := by
    show S.I x ↔ ∃ y, S.I y ∧ seqOf h y = seqOf h x
    exact ⟨fun hI => ⟨x, hI, rfl⟩, fun ⟨y, hI, hy⟩ => seqOf_inj h _ _ _ rfl hy ▸ hI⟩
  r := Subtype.ext (seqOf_root h)
  C p x := by
    show S.C p x ↔ ∃ w, seqOf h x = seqOf h p ++ [w]
    constructor
    · exact fun hpx => ⟨S.name x, seqOf_step h hpx⟩
    · intro ⟨w, hw⟩
      have hxr : x ≠ S.r := fun he => by rw [he, seqOf_root h] at hw; simp at hw
      have ⟨q, hqx, _⟩ := D1 h x hxr
      rw [seqOf_step h hqx] at hw
      have hqp := seqOf_inj h _ _ _ rfl (List.append_inj' hw rfl).1
      exact hqp ▸ hqx
  name x := by
    show (seqOf h x).getLast?.getD [] = S.name x
    by_cases hxr : x = S.r
    · rw [hxr, seqOf_root h, h.ax7_root]; rfl
    · have ⟨p, hpx, _⟩ := D1 h x hxr
      rw [seqOf_step h hpx, getLastD_concat]

/-- An isomorphism preserves the sequence of names. -/
theorem seqOf_iso {V : Type} {S' : Structure α V} (h' : Axioms sl S') (e : Iso S S') :
    ∀ n x, depth h x = n → seqOf h' (e.f x) = seqOf h x := by
  intro n
  induction n with
  | zero =>
    intro x hx
    rw [eq_root_of_depth h hx, e.r, seqOf_root h, seqOf_root h']
  | succ k ih =>
    intro x hx
    have hxr : x ≠ S.r := fun he => by rw [he, depth_root h] at hx; omega
    have ⟨p, hpx, _⟩ := D1 h x hxr
    have hp : depth h p = k := by have := (chain_step h hpx).1; omega
    rw [seqOf_step h' ((e.C p x).mp hpx), ih p hp, e.name, seqOf_step h hpx]

/-- Isomorphic models give the same (L, K). -/
theorem toTrie_eq_of_iso {V : Type} {S' : Structure α V} (h' : Axioms sl S') (e : Iso S S') :
    toTrie h = toTrie h' := by
  have hs : ∀ x, seqOf h' (e.f x) = seqOf h x := fun x => seqOf_iso h h' e _ x rfl
  have hs' : ∀ y, seqOf h (e.g y) = seqOf h' y := fun y => by rw [← hs, e.fg]
  apply Trie.ext'
  · intro s
    exact ⟨fun ⟨x, hx⟩ => ⟨e.f x, (hs x).trans hx⟩, fun ⟨y, hy⟩ => ⟨e.g y, (hs' y).trans hy⟩⟩
  · intro s
    exact ⟨fun ⟨x, hI, hx⟩ => ⟨e.f x, (e.I x).mp hI, (hs x).trans hx⟩,
      fun ⟨y, hI, hy⟩ => ⟨e.g y, (e.I (e.g y)).mpr (by rw [e.fg]; exact hI), (hs' y).trans hy⟩⟩

/-- Models that give the same (L, K) are isomorphic. -/
noncomputable def isoOfToTrieEq {V : Type} {S' : Structure α V} (h' : Axioms sl S')
    (he : toTrie h = toTrie h') : Iso S S' :=
  ((isoToTrie h).trans (Iso.ofEq _ _ he)).trans (isoToTrie h').symm

end ToTrie

/-- (L, K) → model → (L, K) is the identity. -/
theorem toTrie_ofTrie {sl : α} {T : Trie α} (hT : T.WF sl) :
    toTrie (ofTrie_axioms hT) = T := by
  apply Trie.ext'
  · intro s
    refine ⟨fun ⟨x, hx⟩ => ?_, fun hs => ⟨⟨s, hs⟩, seqOf_ofTrie hT _⟩⟩
    rw [← hx, seqOf_ofTrie hT x]; exact x.property
  · intro s
    refine ⟨fun ⟨x, hK, hx⟩ => ?_, fun hK => ⟨⟨s, hT.K_L s hK⟩, hK, seqOf_ofTrie hT _⟩⟩
    rw [← hx, seqOf_ofTrie hT x]; exact hK

/-- L6, the trie correspondence: models of AX-1 to AX-8 correspond, up to
isomorphism, to pairs (L, K) satisfying `Trie.WF`. Each model gives such a
pair; each pair gives a model; pair → model → pair is the identity; model →
pair → model is the identity up to isomorphism; and two models are
isomorphic exactly when they give the same pair. -/
theorem L6 (sl : α) :
    (∀ {U : Type} {S : Structure α U} (h : Axioms sl S), (toTrie h).WF sl) ∧
    (∀ (T : Trie α) (hT : T.WF sl), Axioms sl (ofTrie hT)) ∧
    (∀ (T : Trie α) (hT : T.WF sl), toTrie (ofTrie_axioms hT) = T) ∧
    (∀ {U : Type} {S : Structure α U} (h : Axioms sl S),
      Nonempty (Iso S (ofTrie (toTrie_wf h)))) ∧
    (∀ {U V : Type} {S : Structure α U} {S' : Structure α V}
      (h : Axioms sl S) (h' : Axioms sl S'),
      Nonempty (Iso S S') ↔ toTrie h = toTrie h') :=
  ⟨fun h => toTrie_wf h, fun _ hT => ofTrie_axioms hT, fun _ hT => toTrie_ofTrie hT,
    fun h => ⟨isoToTrie h⟩,
    fun h h' => ⟨fun ⟨e⟩ => toTrie_eq_of_iso h h' e, fun he => ⟨isoOfToTrieEq h h' he⟩⟩⟩

/-- L6, last sentence: a leaf of L outside K is an empty folder. -/
theorem L6_empty_folder {sl : α} {T : Trie α} (hT : T.WF sl) (s : {s // T.L s})
    (hK : ¬ T.K s.val) (hleaf : ∀ t, T.L (s.val ++ t) → t = []) :
    (ofTrie hT).F s ∧ ∀ x, ¬ (ofTrie hT).C s x :=
  ⟨hK, fun x ⟨w, hw⟩ => List.cons_ne_nil _ _ (hleaf [w] (hw ▸ x.property))⟩

/-! ## § 3: no finiteness axiom

The axioms admit an infinite model: one infinite downward branch, every name
the one-letter word `a`. -/

theorem infinite_model (sl a : α) (ha : a ≠ sl) :
    ∃ (U : Type) (S : Structure α U), Axioms sl S ∧
      ∃ f : Nat → U, ∀ m n, f m = f n → m = n := by
  let T : Trie α := ⟨fun s => ∀ w ∈ s, w = [a], fun _ => False⟩
  have hT : T.WF sl := {
    names := fun s hs w hw => by
      rw [hs w hw]
      exact ⟨List.cons_ne_nil _ _, by simp; exact fun he => ha he.symm⟩
    nil := fun _ hw => absurd hw List.not_mem_nil
    closed := fun _ _ hst w hw => hst w (List.mem_append_left _ hw)
    K_L := fun _ hK => hK.elim
    K_ne := fun _ hK => hK.elim
    K_leaf := fun _ _ hK => hK.elim }
  refine ⟨_, ofTrie hT, ofTrie_axioms hT,
    fun n => ⟨List.replicate n [a], fun w hw => List.eq_of_mem_replicate hw⟩, fun m n he => ?_⟩
  have := congrArg (fun s => s.val.length) he
  simpa using this

/-! ## § 9.7: without AX-6, acyclicity does not give reachability

An infinite upward chain … → x₂ → x₁ → x₀ with the root elsewhere: every
non-root has a container, the root has none, nothing is its own ancestor, and
AX-6 fails. -/

/-- `some n` is xₙ, contained by xₙ₊₁; `none` is the root. -/
def upChain : Structure α (Option Nat) where
  F _ := True
  I _ := False
  r := none
  C p x := ∃ n, p = some (n + 1) ∧ x = some n
  name _ := []

theorem upChain_index {y : Nat → Option Nat} {k : Nat} (hk : 1 ≤ k)
    (hy : ∀ i, i < k → (upChain (α := α)).C (y i) (y (i + 1))) :
    ∀ i, i ≤ k → ∃ m, y i = some m ∧ y 0 = some (m + i) := by
  intro i
  induction i with
  | zero =>
    intro _
    have ⟨n, h0, _⟩ := hy 0 (by omega)
    exact ⟨n + 1, h0, h0⟩
  | succ i ih =>
    intro hi
    have ⟨m, hyi, hy0⟩ := ih (by omega)
    have ⟨n, hp, hx⟩ := hy i (by omega)
    rw [hyi, Option.some.injEq] at hp
    refine ⟨n, hx, ?_⟩
    rw [hy0, hp]
    congr 1
    omega

theorem infinite_upward_chain :
    (∀ x, x ≠ (upChain (α := α)).r → ∃ p, (upChain (α := α)).C p x) ∧
    (∀ p, ¬ (upChain (α := α)).C p (upChain (α := α)).r) ∧
    (∀ k (y : Nat → Option Nat), 1 ≤ k →
      (∀ i, i < k → (upChain (α := α)).C (y i) (y (i + 1))) → y k ≠ y 0) ∧
    ¬ ∀ x, ∃ n c, IsChain (upChain (α := α)) x n c := by
  refine ⟨fun x hx => ?_, fun p ⟨n, _, hn⟩ => ?_, fun k y hk hy he => ?_, fun hreach => ?_⟩
  · cases x with
    | none => exact absurd rfl hx
    | some n => exact ⟨some (n + 1), n, rfl, rfl⟩
  · cases hn
  · have ⟨m, hyk, hy0⟩ := upChain_index hk hy k (Nat.le_refl k)
    rw [he, hy0, Option.some.injEq] at hyk
    omega
  · have ⟨n, c, h0, hn, hC⟩ := hreach (some 0)
    cases n with
    | zero =>
      rw [h0] at hn
      cases hn
    | succ j =>
      have ⟨m, hc0, _⟩ := hC 0 (by omega)
      rw [h0] at hc0
      cases hc0

/-! ## What the results rest on

Each result depends only on Lean's standard axioms (some of `propext`,
`Classical.choice`, `Quot.sound`), never on `sorryAx`. A
change that adds an axiom, or proves a result by `sorry`, changes this
output and fails the build. -/

/-- info: 'StoreAxioms.D1' depends on axioms: [Classical.choice] -/
#guard_msgs in #print axioms D1
/-- info: 'StoreAxioms.L1' depends on axioms: [Classical.choice] -/
#guard_msgs in #print axioms L1
/-- info: 'StoreAxioms.L2' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in #print axioms L2
/-- info: 'StoreAxioms.L3' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in #print axioms L3
/-- info: 'StoreAxioms.L4' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in #print axioms L4
/-- info: 'StoreAxioms.L5' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in #print axioms L5
/-- info: 'StoreAxioms.L6' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in #print axioms L6
/-- info: 'StoreAxioms.L6_empty_folder' does not depend on any axioms -/
#guard_msgs in #print axioms L6_empty_folder
/-- info: 'StoreAxioms.infinite_model' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in #print axioms infinite_model
/-- info: 'StoreAxioms.infinite_upward_chain' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms infinite_upward_chain

end StoreAxioms
