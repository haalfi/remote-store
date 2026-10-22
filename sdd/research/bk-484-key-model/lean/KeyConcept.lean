import StoreAxioms

/-!
# Key model, input layer (BK-484)

Restates `sdd/research/research-key-model.md` § 3.3 (separators, the walk) and § 3.5 (ν, steps
0 to 2) and proves the input-layer claims the Hypothesis spike tested, for
every input, over any alphabet with distinct `/`, `\` and NUL. Reuses spec
051's `join` (TREE-009) and its shape lemma `join_shape` (TREE-011) from
`StoreAxioms.lean`. Evidence for that document; no gate builds it (BK-462).

Positions are lists of names; the walk keeps its stack reversed (head = last
name). A Reject is `none`.
-/

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
abbrev bad (y : Sym α) (cfg : Cfg α) (raw : List α) : Prop :=
  y.nul ∈ raw ∨ (cfg.bsSep = false ∧ y.bs ∈ raw)

/-- Steps 0 and 1: the walk's end stack (reversed position), or Reject. -/
def walkRaw (y : Sym α) (cfg : Cfg α) (raw : List α) : Option (List (List α)) :=
  if bad y cfg raw then none else walkFrom y [] (splitBy (isSep y cfg) raw)

/-- Step 2, on the composed position root ⊕ pos. -/
def finish (y : Sym α) (cfg : Cfg α) (root : List (List α)) :
    Option (List (List α)) → Option (List α)
  | none => none
  | some st => if cfg.tier (root ++ st.reverse) then some (join y.sl st.reverse) else none

/-- ν, for a store whose root is `root` (ε, or a child's root, § 3.6); the
result is the child-relative key string. -/
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

theorem nu_fixed_point (y : Sym α) (cfg : Cfg α) (root : List (List α)) {pos : List (List α)}
    (h : ∀ w ∈ pos, ApiName y w) (ht : cfg.tier (root ++ pos) = true) :
    nu y cfg root (join y.sl pos) = some (join y.sl pos) := by
  have hw : walkRaw y cfg (join y.sl pos) = some pos.reverse := by
    unfold walkRaw; rw [ite_eq_right (not_bad_join y cfg h)]; exact walk_key y cfg pos h
  unfold nu; rw [hw]; simp [finish, ht]

/-! ## K3: ν decides ≈ on accepted values (§ 3.5) -/

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
