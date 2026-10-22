import KeyConcept

/-!
# Key model, store layer (BK-484)

Proves the store-layer lemmas K7 to K12 of `sdd/research/research-key-model.md`
(§ 3.6, § 3.7, § 4) against spec 051's own definitions in `StoreAxioms.lean`: `seqOf`
(the names along an entity's chain), `Key` (TREE-009) and the L6 trie
construction `ofTrie`. A position is a sequence of names; an entity's position
is `seqOf`, and its Key is the `/`-join of it.
-/

namespace KeyConcept
open StoreAxioms

set_option linter.unusedSectionVars false

variable {α : Type} [DecidableEq α]

/-- `/`-only splitting: the segments of a key string (§ 4). -/
def slashSep (sl : α) (c : α) : Bool := decide (c = sl)

theorem take_append_length {β : Type} : ∀ (a b : List β), (a ++ b).take a.length = a
  | [], _ => rfl
  | x :: a, b => by simp [take_append_length a b]

/-- The largest index ≤ n satisfying P, when P 0 holds. -/
theorem exists_max (P : Nat → Prop) (h0 : P 0) :
    ∀ n, ∃ j, j ≤ n ∧ P j ∧ ∀ i, j < i → i ≤ n → ¬ P i
  | 0 => ⟨0, Nat.le_refl _, h0, fun i hi hin => absurd hin (by omega)⟩
  | n + 1 => by
    by_cases hp : P (n + 1)
    · exact ⟨n + 1, Nat.le_refl _, hp, fun i hi hin => absurd hin (by omega)⟩
    · obtain ⟨j, hj, hpj, hmax⟩ := exists_max P h0 n
      refine ⟨j, by omega, hpj, fun i hi hin => ?_⟩
      by_cases hin' : i ≤ n
      · exact hmax i hi hin'
      · have : i = n + 1 := by omega
        rw [this]; exact hp

section Model

variable {U : Type} {sl : α} {S : Structure α U} (h : Axioms sl S)
include h

/-! ## § 4 the operations on key strings agree with spec 051 -/

/-- segments(Key(x)) = the names along the chain of x (TREE-009), x ≠ r. -/
theorem segments_key (x : U) (hx : x ≠ S.r) : splitBy (slashSep sl) (Key h x) = seqOf h x := by
  have hne : seqOf h x ≠ [] := fun hs => hx (eq_root_of_depth h (by
    rw [← length_seqOf, hs]; rfl))
  refine splitBy_join _ sl (by simp [slashSep]) _ hne (fun w hw c hc => ?_)
  have := (seqOf_InN h x w hw).2
  simp only [slashSep, decide_eq_false_iff_not]
  exact fun e => this (e ▸ hc)

/-- last(Key(x)) = name(x), the root included (TREE-007, TREE-009). -/
theorem name_eq_last (x : U) : (seqOf h x).getLast?.getD [] = S.name x := by
  by_cases hx : x = S.r
  · rw [hx, seqOf_root h, h.ax7_root]; rfl
  · obtain ⟨p, hpx, _⟩ := D1 h x hx
    rw [seqOf_step h hpx]; simp

/-- parent(Key(x)) = Key(container of x) (TREE-004, TREE-006). -/
theorem parent_eq_dropLast {p x : U} (hpx : S.C p x) : (seqOf h x).dropLast = seqOf h p := by
  rw [seqOf_step h hpx]; simp

/-! ## § 3.7 resolution -/

/-- Some entity has the position s. -/
def Occupied (s : List (List α)) : Prop := ∃ x, seqOf h x = s

/-- Occupied prefixes are closed downward (TREE-012). -/
theorem occupied_take {k : List (List α)} {i i' : Nat} (hi' : i' ≤ i)
    (hk : Occupied h (k.take i)) : Occupied h (k.take i') := by
  obtain ⟨x, hx⟩ := hk
  have e : k.take i' = (k.take i).take i' := by rw [List.take_take, Nat.min_eq_left hi']
  rw [e, ← hx]
  by_cases hd : i' ≤ depth h x
  · refine ⟨chain h x i', ?_⟩
    rw [seqOf_chain h (chain_spec h x) hd, seqOf, take_seqAlong S _ _ _ hd]
  · refine ⟨x, ?_⟩
    rw [List.take_of_length_le (by rw [length_seqOf]; omega)]

/-- Nothing is below an item (TREE-003): its position has no occupied
extension. -/
theorem item_has_no_extension {e : U} (he : S.I e) (w : List α) :
    ¬ Occupied h (seqOf h e ++ [w]) := by
  rintro ⟨x, hx⟩
  have hxr : x ≠ S.r := by
    intro hr; rw [hr, seqOf_root h] at hx; simp at hx
  obtain ⟨p, hpx, _⟩ := D1 h x hxr
  rw [seqOf_step h hpx] at hx
  have hpe : seqOf h p = seqOf h e := (List.append_inj' hx rfl).1
  have hp : p = e := seqOf_inj h _ p e rfl hpe
  exact h.ax1_disjoint e ⟨hp ▸ h.ax3 p x hpx, he⟩

/-- § 3.7's table: with j the largest i ≤ n whose prefix kᵢ is occupied and e
its entity, the prefixes up to j are all occupied, none beyond it is, j = n
exactly when k is occupied, and one of Found, BlockedByItem, Absent,
AbsentAncestor holds. The four are disjoint: j = n against j < n, I against F
(TREE-001), j + 1 = n against j + 1 < n. -/
theorem resolution (k : List (List α)) :
    ∃ j e, j ≤ k.length ∧ seqOf h e = k.take j ∧
      (∀ i, i ≤ j → Occupied h (k.take i)) ∧
      (∀ i, j < i → i ≤ k.length → ¬ Occupied h (k.take i)) ∧
      (j = k.length ↔ Occupied h k) ∧
      (j = k.length ∨ (j < k.length ∧ S.I e) ∨
        (j + 1 = k.length ∧ S.F e) ∨ (j + 1 < k.length ∧ S.F e)) := by
  obtain ⟨j, hj, ⟨e, he⟩, hmax⟩ := exists_max (fun i => Occupied h (k.take i))
    ⟨S.r, by rw [seqOf_root h]; rfl⟩ k.length
  have hall := List.take_length (l := k)
  refine ⟨j, e, hj, he, fun i hi => occupied_take h hi ⟨e, he⟩, hmax,
    ⟨fun hn => ⟨e, by rw [he, hn, hall]⟩, fun hk => ?_⟩, ?_⟩
  · by_cases hn : j = k.length
    · exact hn
    · exact absurd (by rw [hall]; exact hk) (hmax k.length (by omega) (Nat.le_refl _))
  · rcases h.ax1_covering e with hF | hI
    · by_cases hn : j = k.length
      · exact Or.inl hn
      · by_cases h1 : j + 1 = k.length
        · exact Or.inr (Or.inr (Or.inl ⟨h1, hF⟩))
        · exact Or.inr (Or.inr (Or.inr ⟨by omega, hF⟩))
    · by_cases hn : j = k.length
      · exact Or.inl hn
      · exact Or.inr (Or.inl ⟨by omega, hI⟩)

/-- The root resolves to Found(r, folder): ε is r's position (TREE-002). -/
theorem root_found : seqOf h S.r = [] ∧ S.F S.r := ⟨seqOf_root h, h.ax2⟩

/-! ## § 3.6 the child store at a folder -/

/-- The child at e, as L6's pair: positions relative to e, and the items. -/
def childTrie (e : U) : Trie α :=
  ⟨fun t => Occupied h (seqOf h e ++ t), fun t => ∃ x, seqOf h x = seqOf h e ++ t ∧ S.I x⟩

theorem childTrie_WF {e : U} (heF : S.F e) : (childTrie h e).WF sl where
  names t := fun ⟨x, hx⟩ w hw => seqOf_InN h x w (hx ▸ List.mem_append_right _ hw)
  nil := ⟨e, (List.append_nil _).symm⟩
  closed s t := fun hst => by
    have hst' : Occupied h ((seqOf h e ++ s) ++ t) := by rwa [List.append_assoc]
    have := occupied_take h (k := (seqOf h e ++ s) ++ t) (i := ((seqOf h e ++ s) ++ t).length)
      (i' := (seqOf h e ++ s).length) (by simp) (by rwa [List.take_length])
    rwa [take_append_length] at this
  K_L _ := fun ⟨x, hx, _⟩ => ⟨x, hx⟩
  K_ne t := fun ⟨x, hx, hI⟩ ht => by
    subst ht
    rw [List.append_nil] at hx
    have hxe : x = e := seqOf_inj h _ x e rfl hx
    exact h.ax1_disjoint e ⟨heF, hxe ▸ hI⟩
  K_leaf s t := fun ⟨x, hx, hI⟩ hst => by
    cases t with
    | nil => rfl
    | cons w t' =>
      exfalso
      have hst0 : Occupied h (seqOf h e ++ (s ++ w :: t')) := hst
      have hst' : Occupied h ((seqOf h e ++ s ++ [w]) ++ t') := by
        simpa [List.append_assoc] using hst0
      have := occupied_take h (k := (seqOf h e ++ s ++ [w]) ++ t')
        (i := ((seqOf h e ++ s ++ [w]) ++ t').length)
        (i' := (seqOf h e ++ s ++ [w]).length) (by simp) (by rwa [List.take_length])
      rw [take_append_length, ← hx] at this
      exact item_has_no_extension h hI w this

/-- § 3.6: the child at a folder e is a store per spec 051, and each of its
entities t is the parent's entity at e's position followed by t's, with the
same kind: keys compose by join. -/
theorem child_view {e : U} (heF : S.F e) :
    ∃ hA : Axioms sl (ofTrie (childTrie_WF h heF)),
      ∀ t : {s // (childTrie h e).L s}, ∃ x, seqOf h x = seqOf h e ++ seqOf hA t ∧
        (S.I x ↔ (ofTrie (childTrie_WF h heF)).I t) := by
  refine ⟨ofTrie_axioms _, fun t => ?_⟩
  obtain ⟨x, hx⟩ := t.property
  refine ⟨x, by rw [seqOf_ofTrie]; exact hx, ⟨fun hI => ⟨x, hx, hI⟩, fun ⟨x', hx', hI'⟩ => ?_⟩⟩
  have hxx : x' = x := seqOf_inj h _ x' x rfl (hx'.trans hx.symm)
  exact hxx ▸ hI'

end Model

/-! ## § 4 Lemma C: every key string is a Key in some store -/

/-- The prefixes of one sequence of names; `item` makes the last one an item. -/
def chainTrie (ws : List (List α)) (item : Bool) : Trie α :=
  ⟨fun s => ∃ t, s ++ t = ws, fun s => item = true ∧ s = ws⟩

theorem chainTrie_WF {sl : α} {ws : List (List α)} (item : Bool) (hws : ∀ w ∈ ws, InN sl w)
    (hne : item = true → ws ≠ []) : (chainTrie ws item).WF sl where
  names s := fun ⟨t, ht⟩ w hw => hws w (ht ▸ List.mem_append_left t hw)
  nil := ⟨ws, rfl⟩
  closed s t := fun ⟨u, hu⟩ => ⟨t ++ u, by rw [← List.append_assoc]; exact hu⟩
  K_L s := fun ⟨_, hs⟩ => ⟨[], by rw [hs, List.append_nil]⟩
  K_ne s := fun ⟨hi, hs⟩ => hs ▸ hne hi
  K_leaf s t := fun ⟨_, hs⟩ ⟨u, hu⟩ => by
    rw [hs] at hu
    have hl := congrArg List.length hu
    simp only [List.length_append] at hl
    exact List.eq_nil_of_length_eq_zero (by omega)

/-- Lemma C: for every sequence of names, in folder form and (when non-empty)
in item form, there is a store with an entity of that kind whose Key is its
`/`-join. -/
theorem lemma_C {sl : α} (ws : List (List α)) (hws : ∀ w ∈ ws, InN sl w) (item : Bool)
    (hne : item = true → ws ≠ []) :
    ∃ (U : Type) (S : Structure α U) (h : Axioms sl S) (x : U),
      Key h x = join sl ws ∧ (S.I x ↔ item = true) := by
  refine ⟨_, ofTrie (chainTrie_WF item hws hne), ofTrie_axioms (chainTrie_WF item hws hne),
    ⟨ws, ⟨[], List.append_nil _⟩⟩, by rw [Key, seqOf_ofTrie], ?_⟩
  exact ⟨fun ⟨hi, _⟩ => hi, fun hi => ⟨hi, rfl⟩⟩

/-! ## What the claims rest on -/

/-- info: 'KeyConcept.segments_key' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in #print axioms segments_key
/-- info: 'KeyConcept.name_eq_last' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in #print axioms name_eq_last
/-- info: 'KeyConcept.parent_eq_dropLast' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in #print axioms parent_eq_dropLast
/-- info: 'KeyConcept.item_has_no_extension' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in #print axioms item_has_no_extension
/-- info: 'KeyConcept.occupied_take' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in #print axioms occupied_take
/-- info: 'KeyConcept.resolution' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in #print axioms resolution
/-- info: 'KeyConcept.child_view' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in #print axioms child_view
/-- info: 'KeyConcept.lemma_C' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in #print axioms lemma_C

end KeyConcept
