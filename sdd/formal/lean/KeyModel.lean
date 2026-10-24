import StoreAxioms

/-!
# Spec 054's store key: reduction, acceptance, resolution

Restates `sdd/specs/054-store-key.md` and proves its derived sections for
every input, over any alphabet with distinct `/`, `\` and NUL, against spec
051's own definitions in `StoreAxioms.lean` (`join`, `join_shape`, `seqOf`,
`Key`, and L6's `ofTrie`). The research behind it is
`sdd/research/research-key-model.md`; K1 to K12 below are its lemma names.

Positions are lists of names; the walk keeps its stack reversed (head = last
name). A refusal is `none`. Inputs are lists over the alphabet α, so a
surrogate (KEY-002), which is outside Σ, is not an input here; that arm is the
reference model's (`tests/test_store_key_model.py`). The acceptance language
is a parameter (`Cfg.tier`), so KEY-006 to KEY-008's bounds on it are stated
by the spec and checked by the reference model, not here.
-/

-- @restates sdd/specs/054-store-key.md

namespace KeyConcept
open StoreAxioms

-- Some lemmas need no decidable equality; the spike keeps one variable block.
set_option linter.unusedSectionVars false

variable {α : Type} [DecidableEq α]

/-- The distinguished symbols: `/`, `\`, NUL and `.`. -/
structure Sym (α : Type) where
  sl : α
  bs : α
  nul : α
  dot : α
  sl_ne_bs : sl ≠ bs
  sl_ne_nul : sl ≠ nul

/-- A store's configuration: whether `\` ∈ Sep_S (§ 3.3), and its acceptance
language as a predicate on the composed position (§ 3.2 tiers, § 3.6). -/
-- @spec KEY-006
-- @spec KEY-007
-- @spec KEY-008
-- @spec KEY-009
-- @spec KEY-A-01
structure Cfg (α : Type) where
  bsSep : Bool
  tier : List (List α) → Bool

/-! ## Splitting raw input on Sep_S -/

def isSep (y : Sym α) (cfg : Cfg α) (c : α) : Bool :=
  decide (c = y.sl) || (cfg.bsSep && decide (c = y.bs))

def consHead (c : α) : List (List α) → List (List α)
  | [] => [[c]]
  | w :: ws => (c :: w) :: ws

/-- Split on every separator, keeping empty segments. -/
def splitBy (p : α → Bool) : List α → List (List α)
  | [] => [[]]
  | c :: cs => if p c then [] :: splitBy p cs else consHead c (splitBy p cs)

theorem splitBy_ne_nil (p : α → Bool) : ∀ l, splitBy p l ≠ []
  | [] => by simp [splitBy]
  | c :: cs => by
    cases hc : p c
    · simp only [splitBy, hc, Bool.false_eq_true, ite_false]
      cases h : splitBy p cs with
      | nil => exact absurd h (splitBy_ne_nil p cs)
      | cons w ws => simp [consHead]
    · simp [splitBy, hc]

theorem consHead_append (c : α) : ∀ (xs ys : List (List α)), xs ≠ [] →
    consHead c (xs ++ ys) = consHead c xs ++ ys
  | [], _, h => absurd rfl h
  | _ :: _, _, _ => rfl

theorem splitBy_append_sep (p : α → Bool) {s : α} (hs : p s = true) :
    ∀ (a b : List α), splitBy p (a ++ s :: b) = splitBy p a ++ splitBy p b
  | [], b => by simp [splitBy, hs]
  | c :: a, b => by
    cases hc : p c
    · simp only [List.cons_append, splitBy, hc, Bool.false_eq_true, ite_false]
      rw [splitBy_append_sep p hs a b, consHead_append c _ _ (splitBy_ne_nil p a)]
    · simp [splitBy, hc, splitBy_append_sep p hs a b]

theorem splitBy_noSep (p : α → Bool) : ∀ (w : List α), (∀ c ∈ w, p c = false) →
    splitBy p w = [w]
  | [], _ => rfl
  | c :: w, h => by
    have hc := h c List.mem_cons_self
    have ih := splitBy_noSep p w (fun x hx => h x (List.mem_cons_of_mem _ hx))
    simp [splitBy, hc, ih, consHead]

/-- Splitting a `/`-join of separator-free names gives the names back. -/
theorem splitBy_join (p : α → Bool) (sl : α) (hsl : p sl = true) :
    ∀ (ws : List (List α)), ws ≠ [] → (∀ w ∈ ws, ∀ c ∈ w, p c = false) →
      splitBy p (join sl ws) = ws
  | [], h, _ => absurd rfl h
  | [w], _, h => by simp only [join]; exact splitBy_noSep p w (h w List.mem_cons_self)
  | w :: v :: ws, _, h => by
    simp only [join]
    rw [splitBy_append_sep p hsl, splitBy_noSep p w (h w List.mem_cons_self),
      splitBy_join p sl hsl (v :: ws) (List.cons_ne_nil _ _)
        (fun x hx => h x (List.mem_cons_of_mem _ hx))]
    rfl

theorem splitBy_congr (p q : α → Bool) : ∀ (l : List α), (∀ c ∈ l, p c = q c) →
    splitBy p l = splitBy q l
  | [], _ => rfl
  | c :: l, h => by
    have hc := h c List.mem_cons_self
    have ih := splitBy_congr p q l (fun x hx => h x (List.mem_cons_of_mem _ hx))
    simp only [splitBy, hc, ih]

theorem mem_consHead {c : α} {w : List α} : ∀ {xs : List (List α)}, w ∈ consHead c xs →
    w = [c] ∨ (∃ w0, w = c :: w0 ∧ w0 ∈ xs) ∨ w ∈ xs
  | [], h => by simp [consHead] at h; exact Or.inl h
  | w0 :: _, h => by
    simp only [consHead, List.mem_cons] at h
    rcases h with h | h
    · exact Or.inr (Or.inl ⟨w0, h, List.mem_cons_self⟩)
    · exact Or.inr (Or.inr (List.mem_cons_of_mem _ h))

/-- Every symbol of a segment comes from the input and is not a separator. -/
theorem mem_splitBy (p : α → Bool) : ∀ {l w : List α} {c : α},
    w ∈ splitBy p l → c ∈ w → c ∈ l ∧ p c = false
  | [], w, c, hw, hc => by simp [splitBy] at hw; subst hw; simp at hc
  | d :: l, w, c, hw, hc => by
    cases hpd : p d
    · simp only [splitBy, hpd, Bool.false_eq_true, ite_false] at hw
      rcases mem_consHead hw with h | ⟨w0, h, h0⟩ | h
      · subst h
        rw [List.mem_singleton] at hc
        subst hc
        exact ⟨List.mem_cons_self, hpd⟩
      · subst h
        rcases List.mem_cons.mp hc with e | hc0
        · subst e; exact ⟨List.mem_cons_self, hpd⟩
        · have := mem_splitBy p h0 hc0
          exact ⟨List.mem_cons_of_mem _ this.1, this.2⟩
      · have := mem_splitBy p h hc
        exact ⟨List.mem_cons_of_mem _ this.1, this.2⟩
    · simp only [splitBy, hpd, ite_true, List.mem_cons] at hw
      rcases hw with h | h
      · subst h; simp at hc
      · have := mem_splitBy p h hc
        exact ⟨List.mem_cons_of_mem _ this.1, this.2⟩

/-! ## § 3.3 the walk -/

/-- One segment: skip empty and `.`, pop on `..` (none at the root: an
escape), push any other. -/
-- @spec KEY-003
-- @spec KEY-004
def step (y : Sym α) (st : List (List α)) (s : List α) : Option (List (List α)) :=
  if s = [] ∨ s = [y.dot] then some st
  else if s = [y.dot, y.dot] then st.tail?
  else some (s :: st)

def walkFrom (y : Sym α) : List (List α) → List (List α) → Option (List (List α))
  | st, [] => some st
  | st, s :: ss => (step y st s).bind (fun st' => walkFrom y st' ss)

theorem walkFrom_append (y : Sym α) : ∀ (st a b : List (List α)),
    walkFrom y st (a ++ b) = (walkFrom y st a).bind (fun st' => walkFrom y st' b)
  | _, [], _ => rfl
  | st, s :: a, b => by
    simp only [List.cons_append, walkFrom]
    cases h : step y st s with
    | none => rfl
    | some st' => exact walkFrom_append y st' a b

/-- A segment the walk pushes: not empty, `.` or `..`. -/
def NotNav (y : Sym α) (w : List α) : Prop := w ≠ [] ∧ w ≠ [y.dot] ∧ w ≠ [y.dot, y.dot]

theorem step_push (y : Sym α) (st : List (List α)) {w : List α} (h : NotNav y w) :
    step y st w = some (w :: st) := by
  obtain ⟨h1, h2, h3⟩ := h
  simp [step, h1, h2, h3]

theorem walkFrom_names (y : Sym α) : ∀ (st ws : List (List α)), (∀ w ∈ ws, NotNav y w) →
    walkFrom y st ws = some (ws.reverse ++ st)
  | _, [], _ => rfl
  | st, w :: ws, h => by
    have hs := step_push y st (h w List.mem_cons_self)
    have ih := walkFrom_names y (w :: st) ws (fun x hx => h x (List.mem_cons_of_mem _ hx))
    simp [walkFrom, hs, ih]

theorem step_base (y : Sym α) {st st' : List (List α)} {s : List α} (base : List (List α))
    (h : step y st s = some st') : step y (st ++ base) s = some (st' ++ base) := by
  unfold step at h ⊢
  by_cases h1 : s = [] ∨ s = [y.dot]
  · rw [ite_eq_left h1] at h ⊢; injection h with h; rw [h]
  · rw [ite_eq_right h1] at h ⊢
    by_cases h2 : s = [y.dot, y.dot]
    · rw [ite_eq_left h2] at h ⊢
      cases st with
      | nil => simp at h
      | cons x t => simp at h; simp [h]
    · rw [ite_eq_right h2] at h ⊢; injection h with h; rw [← h]; rfl

/-- A walk that does not escape from the empty stack runs the same on top of
any base: the base of a child store (§ 3.6). -/
theorem walkFrom_base (y : Sym α) (base : List (List α)) : ∀ (st ss r : List (List α)),
    walkFrom y st ss = some r → walkFrom y (st ++ base) ss = some (r ++ base)
  | st, [], r, h => by simp only [walkFrom] at h ⊢; injection h with h; rw [h]
  | st, s :: ss, r, h => by
    simp only [walkFrom] at h ⊢
    cases hs : step y st s with
    | none => rw [hs] at h; simp at h
    | some st' =>
      rw [hs] at h
      rw [step_base y base hs]
      exact walkFrom_base y base st' ss r h

theorem walkFrom_inv (y : Sym α) (P : List α → Prop) : ∀ (st ss r : List (List α)),
    walkFrom y st ss = some r → (∀ w ∈ st, P w) → (∀ s ∈ ss, NotNav y s → P s) →
      ∀ w ∈ r, P w
  | st, [], r, h, hst, _ => by
    simp only [walkFrom] at h; injection h with h; subst h; exact hst
  | st, s :: ss, r, h, hst, hss => by
    simp only [walkFrom] at h
    cases hs : step y st s with
    | none => rw [hs] at h; simp at h
    | some st' =>
      rw [hs] at h
      refine walkFrom_inv y P st' ss r h ?_ (fun x hx => hss x (List.mem_cons_of_mem _ hx))
      unfold step at hs
      by_cases h1 : s = [] ∨ s = [y.dot]
      · rw [ite_eq_left h1] at hs; injection hs with hs; subst hs; exact hst
      · rw [ite_eq_right h1] at hs
        by_cases h2 : s = [y.dot, y.dot]
        · rw [ite_eq_left h2] at hs
          cases st with
          | nil => simp at hs
          | cons x t =>
            simp at hs; subst hs
            exact fun w hw => hst w (List.mem_cons_of_mem _ hw)
        · rw [ite_eq_right h2] at hs; injection hs with hs; subst hs
          intro w hw
          rcases List.mem_cons.mp hw with hw | hw
          · subst hw
            exact hss _ List.mem_cons_self ⟨fun e => h1 (Or.inl e), fun e => h1 (Or.inr e), h2⟩
          · exact hst w hw

/-! ## § 3.5 ν -/

/-- Step 0: NUL anywhere, or `\` when `\` ∉ Sep_S. -/
-- @spec KEY-002
abbrev bad (y : Sym α) (cfg : Cfg α) (raw : List α) : Prop :=
  y.nul ∈ raw ∨ (cfg.bsSep = false ∧ y.bs ∈ raw)

/-- Steps 0 and 1: the walk's end stack (reversed position), or Reject. -/
def walkRaw (y : Sym α) (cfg : Cfg α) (raw : List α) : Option (List (List α)) :=
  if bad y cfg raw then none else walkFrom y [] (splitBy (isSep y cfg) raw)

/-- Step 2, on the composed position root ⊕ pos. -/
-- @spec KEY-005
def finish (y : Sym α) (cfg : Cfg α) (root : List (List α)) :
    Option (List (List α)) → Option (List α)
  | none => none
  | some st => if cfg.tier (root ++ st.reverse) then some (join y.sl st.reverse) else none

/-- ν, for a store whose root is `root` (ε, or a child's root, § 3.6); the
result is the child-relative key string. -/
-- @spec KEY-001
def nu (y : Sym α) (cfg : Cfg α) (root : List (List α)) (raw : List α) : Option (List α) :=
  finish y cfg root (walkRaw y cfg raw)

/-- A name in L_api's floor (§ 3.2): not navigation, no `/`, `\` or NUL. -/
def ApiName (y : Sym α) (w : List α) : Prop :=
  NotNav y w ∧ y.sl ∉ w ∧ y.bs ∉ w ∧ y.nul ∉ w

theorem inN_of_apiName {y : Sym α} {w : List α} (h : ApiName y w) : InN y.sl w :=
  ⟨h.1.1, h.2.1⟩

theorem nu_eq_some {y : Sym α} {cfg : Cfg α} {root : List (List α)} {raw k : List α}
    (h : nu y cfg root raw = some k) :
    ∃ st, walkRaw y cfg raw = some st ∧ cfg.tier (root ++ st.reverse) = true ∧
      k = join y.sl st.reverse := by
  unfold nu at h
  cases hw : walkRaw y cfg raw with
  | none => rw [hw] at h; simp [finish] at h
  | some st =>
    rw [hw] at h
    simp only [finish] at h
    by_cases ht : cfg.tier (root ++ st.reverse) = true
    · rw [ite_eq_left ht] at h; injection h with h; exact ⟨st, rfl, ht, h.symm⟩
    · rw [ite_eq_right ht] at h; cases h

theorem walkRaw_eq_some {y : Sym α} {cfg : Cfg α} {raw : List α} {st : List (List α)}
    (h : walkRaw y cfg raw = some st) :
    ¬ bad y cfg raw ∧ walkFrom y [] (splitBy (isSep y cfg) raw) = some st := by
  unfold walkRaw at h
  by_cases hb : bad y cfg raw
  · rw [ite_eq_left hb] at h; cases h
  · rw [ite_eq_right hb] at h; exact ⟨hb, h⟩

theorem apiName_of_segment (y : Sym α) (cfg : Cfg α) {raw : List α} (hb : ¬ bad y cfg raw)
    {s : List α} (hs : s ∈ splitBy (isSep y cfg) raw) (hn : NotNav y s) : ApiName y s := by
  refine ⟨hn, fun h => ?_, fun h => ?_, fun h => ?_⟩
  · have := (mem_splitBy _ hs h).2; simp [isSep] at this
  · have ⟨hr, hp⟩ := mem_splitBy _ hs h
    cases hc : cfg.bsSep
    · exact hb (Or.inr ⟨hc, hr⟩)
    · simp [isSep, hc] at hp
  · exact hb (Or.inl (mem_splitBy _ hs h).1)

theorem walkRaw_names (y : Sym α) (cfg : Cfg α) {raw : List α} {st : List (List α)}
    (h : walkRaw y cfg raw = some st) : ∀ w ∈ st, ApiName y w := by
  obtain ⟨hb, hwalk⟩ := walkRaw_eq_some h
  exact walkFrom_inv y (ApiName y) [] _ st hwalk (by simp)
    (fun s hs hn => apiName_of_segment y cfg hb hs hn)

/-! ## K1: the output is a navigation-free key string of TREE-011's shape -/

theorem nu_output (y : Sym α) (cfg : Cfg α) (root : List (List α)) {raw k : List α}
    (h : nu y cfg root raw = some k) :
    ∃ pos, k = join y.sl pos ∧ (∀ w ∈ pos, ApiName y w) ∧ cfg.tier (root ++ pos) = true := by
  obtain ⟨st, hw, ht, hk⟩ := nu_eq_some h
  exact ⟨st.reverse, hk, fun w hw' => walkRaw_names y cfg hw w (List.mem_reverse.mp hw'), ht⟩

theorem nu_key_shape (y : Sym α) (cfg : Cfg α) (root : List (List α)) {raw k : List α}
    (h : nu y cfg root raw = some k) : k = [] ∨ GoodShape y.sl k := by
  obtain ⟨pos, hk, hn, _⟩ := nu_output y cfg root h
  cases pos with
  | nil => left; rw [hk]; rfl
  | cons w ws =>
    right; rw [hk]
    exact (join_shape (w :: ws) (List.cons_ne_nil _ _) (fun x hx => inN_of_apiName (hn x hx))).2

/-! ## K2: canonical fixed point, ν(k) = k on L_api (the round trip) -/

theorem mem_join {sl c : α} : ∀ {ws : List (List α)}, c ∈ join sl ws → c = sl ∨ ∃ w ∈ ws, c ∈ w
  | [], h => by simp [join] at h
  | [w], h => Or.inr ⟨w, List.mem_cons_self, by simpa [join] using h⟩
  | w :: v :: ws, h => by
    simp only [join, List.mem_append, List.mem_cons] at h
    rcases h with h | h | h
    · exact Or.inr ⟨w, List.mem_cons_self, h⟩
    · exact Or.inl h
    · rcases mem_join h with h | ⟨x, hx, hc⟩
      · exact Or.inl h
      · exact Or.inr ⟨x, List.mem_cons_of_mem _ hx, hc⟩

theorem not_bad_join (y : Sym α) (cfg : Cfg α) {pos : List (List α)}
    (h : ∀ w ∈ pos, ApiName y w) : ¬ bad y cfg (join y.sl pos) := by
  rintro (hn | ⟨_, hb⟩)
  · rcases mem_join hn with e | ⟨w, hw, hc⟩
    · exact y.sl_ne_nul e.symm
    · exact (h w hw).2.2.2 hc
  · rcases mem_join hb with e | ⟨w, hw, hc⟩
    · exact y.sl_ne_bs e.symm
    · exact (h w hw).2.2.1 hc

theorem noSep_of_apiName (y : Sym α) (cfg : Cfg α) {w : List α} (h : ApiName y w) :
    ∀ c ∈ w, isSep y cfg c = false := by
  intro c hc
  have h1 : c ≠ y.sl := fun e => h.2.1 (e ▸ hc)
  have h2 : c ≠ y.bs := fun e => h.2.2.1 (e ▸ hc)
  simp [isSep, h1, h2]

theorem walk_key (y : Sym α) (cfg : Cfg α) : ∀ (pos : List (List α)), (∀ w ∈ pos, ApiName y w) →
    walkFrom y [] (splitBy (isSep y cfg) (join y.sl pos)) = some pos.reverse
  | [], _ => by simp [join, splitBy, walkFrom, step]
  | w :: ws, h => by
    rw [splitBy_join _ y.sl (by simp [isSep]) (w :: ws) (List.cons_ne_nil _ _)
      (fun x hx => noSep_of_apiName y cfg (h x hx)),
      walkFrom_names y [] (w :: ws) (fun x hx => (h x hx).1)]
    simp

-- @spec KEY-010
theorem nu_fixed_point (y : Sym α) (cfg : Cfg α) (root : List (List α)) {pos : List (List α)}
    (h : ∀ w ∈ pos, ApiName y w) (ht : cfg.tier (root ++ pos) = true) :
    nu y cfg root (join y.sl pos) = some (join y.sl pos) := by
  have hw : walkRaw y cfg (join y.sl pos) = some pos.reverse := by
    unfold walkRaw; rw [ite_eq_right (not_bad_join y cfg h)]; exact walk_key y cfg pos h
  unfold nu; rw [hw]; simp [finish, ht]

/-! ## K3: ν decides ≈ on accepted values (§ 3.5) -/

-- @spec KEY-011
theorem nu_decides_equiv (y : Sym α) (cfg : Cfg α) (root : List (List α)) {p q kp kq : List α}
    (hp : nu y cfg root p = some kp) (hq : nu y cfg root q = some kq) :
    walkRaw y cfg p = walkRaw y cfg q ↔ kp = kq := by
  obtain ⟨sp, hwp, _, hkp⟩ := nu_eq_some hp
  obtain ⟨sq, hwq, _, hkq⟩ := nu_eq_some hq
  rw [hwp, hwq]
  constructor
  · intro e; injection e with e; rw [hkp, hkq, e]
  · intro e
    rw [hkp, hkq] at e
    have hnp := walkRaw_names y cfg hwp
    have hnq := walkRaw_names y cfg hwq
    have := join_inj sp.reverse sq.reverse
      (fun w hw => inN_of_apiName (hnp w (List.mem_reverse.mp hw)))
      (fun w hw => inN_of_apiName (hnq w (List.mem_reverse.mp hw))) e
    rw [List.reverse_inj.mp this]

/-! ## K4: join is walk continuation (§ 3.5) -/

theorem bad_sep_append (y : Sym α) (cfg : Cfg α) (a b : List α) :
    bad y cfg (a ++ y.sl :: b) ↔ bad y cfg a ∨ bad y cfg b := by
  have hn : y.nul ≠ y.sl := fun e => y.sl_ne_nul e.symm
  have hb : y.bs ≠ y.sl := fun e => y.sl_ne_bs e.symm
  simp only [bad, List.mem_append, List.mem_cons, hn, hb, false_or]
  constructor
  · rintro ((h | h) | ⟨e, h | h⟩)
    · exact Or.inl (Or.inl h)
    · exact Or.inr (Or.inl h)
    · exact Or.inl (Or.inr ⟨e, h⟩)
    · exact Or.inr (Or.inr ⟨e, h⟩)
  · rintro ((h | ⟨e, h⟩) | (h | ⟨e, h⟩))
    · exact Or.inl (Or.inl h)
    · exact Or.inr ⟨e, Or.inl h⟩
    · exact Or.inl (Or.inr h)
    · exact Or.inr ⟨e, Or.inr h⟩

theorem isSep_sl (y : Sym α) (cfg : Cfg α) : isSep y cfg y.sl = true := by simp [isSep]

/-- (k ⊕ p) ⊕ q = k ⊕ (p/q) whenever k ⊕ p is accepted, for any k. -/
theorem join_continuation (y : Sym α) (cfg : Cfg α) (root : List (List α)) (k p q : List α)
    {m : List α} (hm : nu y cfg root (k ++ y.sl :: p) = some m) :
    nu y cfg root (m ++ y.sl :: q) = nu y cfg root (k ++ y.sl :: (p ++ y.sl :: q)) := by
  obtain ⟨st, hw, _, hmk⟩ := nu_eq_some hm
  obtain ⟨hb, hwalk⟩ := walkRaw_eq_some hw
  have hmnames : ∀ w ∈ st.reverse, ApiName y w :=
    fun w h => walkRaw_names y cfg hw w (List.mem_reverse.mp h)
  have hL : walkRaw y cfg (m ++ y.sl :: q) =
      if bad y cfg q then none else walkFrom y st (splitBy (isSep y cfg) q) := by
    unfold walkRaw
    by_cases hq : bad y cfg q
    · rw [ite_eq_left ((bad_sep_append y cfg _ _).mpr (Or.inr hq)), ite_eq_left hq]
    · have hmb : ¬ bad y cfg m := by rw [hmk]; exact not_bad_join y cfg hmnames
      rw [ite_eq_right (fun e => ((bad_sep_append y cfg _ _).mp e).elim hmb hq), ite_eq_right hq,
        splitBy_append_sep _ (isSep_sl y cfg), walkFrom_append, hmk,
        walk_key y cfg _ hmnames, List.reverse_reverse]
      rfl
  have hR : walkRaw y cfg (k ++ y.sl :: (p ++ y.sl :: q)) =
      if bad y cfg q then none else walkFrom y st (splitBy (isSep y cfg) q) := by
    unfold walkRaw
    have e : k ++ y.sl :: (p ++ y.sl :: q) = (k ++ y.sl :: p) ++ y.sl :: q := by simp
    rw [e]
    by_cases hq : bad y cfg q
    · rw [ite_eq_left ((bad_sep_append y cfg _ _).mpr (Or.inr hq)), ite_eq_left hq]
    · rw [ite_eq_right (fun e => ((bad_sep_append y cfg _ _).mp e).elim hb hq), ite_eq_right hq,
        splitBy_append_sep _ (isSep_sl y cfg), walkFrom_append, hwalk]
      rfl
  unfold nu; rw [hL, hR]

/-! ## K5: opting out of `\` only rejects more (§ 3.3) -/

theorem opt_out_only_rejects_more (y : Sym α) (t : List (List α) → Bool)
    (root : List (List α)) {raw k : List α} (h : nu y ⟨false, t⟩ root raw = some k) :
    nu y ⟨true, t⟩ root raw = some k := by
  obtain ⟨st, hw, ht, hk⟩ := nu_eq_some h
  obtain ⟨hb, hwalk⟩ := walkRaw_eq_some hw
  have hbs : y.bs ∉ raw := fun m => hb (Or.inr ⟨rfl, m⟩)
  have hnul : y.nul ∉ raw := fun m => hb (Or.inl m)
  have hsplit : splitBy (isSep y ⟨true, t⟩) raw = splitBy (isSep y ⟨false, t⟩) raw := by
    apply splitBy_congr
    intro c hc
    have : c ≠ y.bs := fun e => hbs (e ▸ hc)
    simp [isSep, this]
  have hnb : ¬ bad y ⟨true, t⟩ raw := by
    rintro (m | ⟨e, _⟩)
    · exact hnul m
    · simp at e
  have hw' : walkRaw y ⟨true, t⟩ raw = some st := by
    unfold walkRaw; rw [ite_eq_right hnb, hsplit]; exact hwalk
  unfold nu; rw [hw', hk]
  simp only [finish] at ht ⊢
  simp [ht]

/-! ## K6: child keys compose with the parent's (§ 3.6, CHILD-005) -/

-- @spec KEY-012
theorem child_compose (y : Sym α) (cfg : Cfg α) {cpos : List (List α)}
    (hc : ∀ w ∈ cpos, ApiName y w) (hne : cpos ≠ []) {raw k : List α}
    (h : nu y cfg cpos raw = some k) :
    ∃ kpos, k = join y.sl kpos ∧
      nu y cfg [] (join y.sl cpos ++ y.sl :: raw) = some (join y.sl (cpos ++ kpos)) := by
  obtain ⟨st, hw, ht, hk⟩ := nu_eq_some h
  obtain ⟨hb, hwalk⟩ := walkRaw_eq_some hw
  refine ⟨st.reverse, hk, ?_⟩
  have hw' : walkRaw y cfg (join y.sl cpos ++ y.sl :: raw) = some (st ++ cpos.reverse) := by
    unfold walkRaw
    rw [ite_eq_right (fun e => ((bad_sep_append y cfg _ _).mp e).elim (not_bad_join y cfg hc) hb),
      splitBy_append_sep _ (isSep_sl y cfg),
      splitBy_join _ y.sl (isSep_sl y cfg) cpos hne (fun x hx => noSep_of_apiName y cfg (hc x hx)),
      walkFrom_append, walkFrom_names y [] cpos (fun x hx => (hc x hx).1)]
    have := walkFrom_base y cpos.reverse [] _ st hwalk
    simpa using this
  unfold nu; rw [hw']
  simp [finish, ht]

/-! ## Examples over `Char`, including the spike's counterexample -/

def symC : Sym Char := ⟨'/', '\\', '\x00', '.', by decide, by decide⟩
def cfgDefault : Cfg Char := ⟨true, fun _ => true⟩
def cfgOptOut : Cfg Char := ⟨false, fun _ => true⟩

-- `a\a/..`: Reject after the opt-out (step 0), `a` by default.
example : nu symC cfgOptOut [] ['a', '\\', 'a', '/', '.', '.'] = none := by decide
example : nu symC cfgDefault [] ['a', '\\', 'a', '/', '.', '.'] = some ['a'] := by decide
-- `x\0/..`: NUL is rejected even in a popped name.
example : nu symC cfgDefault [] ['x', '\x00', '/', '.', '.'] = none := by decide
-- `..` escapes.
example : nu symC cfgDefault [] ['.', '.'] = none := by decide
-- `a/c/../b` gives `a/b`; the empty input gives ε.
example : nu symC cfgDefault [] ['a', '/', 'c', '/', '.', '.', '/', 'b'] = some ['a', '/', 'b'] := by
  decide
example : nu symC cfgDefault [] [] = some [] := by decide

/-! ## What the claims rest on: Lean's standard axioms only, never `sorryAx` -/

/-- info: 'KeyConcept.nu_output' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms nu_output
/-- info: 'KeyConcept.nu_key_shape' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms nu_key_shape
/-- info: 'KeyConcept.nu_fixed_point' depends on axioms: [propext] -/
#guard_msgs in #print axioms nu_fixed_point
/-- info: 'KeyConcept.nu_decides_equiv' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms nu_decides_equiv
/-- info: 'KeyConcept.join_continuation' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms join_continuation
/-- info: 'KeyConcept.opt_out_only_rejects_more' depends on axioms: [propext] -/
#guard_msgs in #print axioms opt_out_only_rejects_more
/-- info: 'KeyConcept.child_compose' depends on axioms: [propext] -/
#guard_msgs in #print axioms child_compose

end KeyConcept

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
-- @spec KEY-013
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
