// RootPath.dfy. Verified properties of BE-029's root predicate.
//
// BK-388: `AddressesRoot` lives upstream in BackendContract.dfy §5c, because
// the trait's write-shaped postconditions name it.  This module proves what
// the predicate accepts and rejects without adding to the trait, in the
// shape of DepthCounting.dfy:
//   1. Every slash-and-dot spelling of the root addresses it: the six BE-029
//      names, and (RootSpellingCharacterisation) exactly the keys whose
//      every '/'-segment is "" or ".", stated character by character.
//   2. The Root sentinel addresses it.
//   3. On the trait's domain (WellFormedPath) it holds for Root alone, so
//      the trait's root clauses fire on exactly the one well-formed root.
//   4. A backslash key does not address the root (BE-029's stated bound).

include "BackendContract.dfy"

// ---------------------------------------------------------------------------
// §1  The root spellings
// ---------------------------------------------------------------------------

// Property 1: BE-029 § "Every spelling that addresses it" lists "", ".",
// "./", ".//", "./." and "/"; each has no addressable segment.
lemma RootSpellingsAddressRoot()
  // @spec BE-029
  ensures AddressesRoot("")
  ensures AddressesRoot(".")
  ensures AddressesRoot("./")
  ensures AddressesRoot(".//")
  ensures AddressesRoot("./.")
  ensures AddressesRoot("/")
{
  // Each unfolds one character at a time down to "".
  assert AddressesRoot("");
  assert "/"[1..] == "";
  assert AddressesRoot("/");
  assert "//"[1..] == "/";
  assert AddressesRoot("//");
  assert "./"[1..] == "/";
  assert AddressesRoot("./");
  assert ".//"[1..] == "//";
  assert AddressesRoot(".//");
  assert "."[1..] == "";
  assert AddressesRoot(".");
  assert "/."[1..] == ".";
  assert AddressesRoot("/.");
  assert "./."[1..] == "/.";
  assert AddressesRoot("./.");
}

// A key made only of "" and "." segments, stated per character: every
// character is '/' or '.', and a '.' ends the key or is followed by '/'.
// (A '.' followed by '.' would start a ".." or longer segment, which
// addresses something.)
ghost predicate RootSpelling(s: string)
{
  forall i | 0 <= i < |s| ::
    (s[i] == '/' || s[i] == '.') && (s[i] == '.' ==> i + 1 == |s| || s[i + 1] == '/')
}

// Property 1, universally: AddressesRoot accepts exactly the root spellings,
// so the six above are instances, not the whole of what is proved.
// Induction on |s|, following AddressesRoot's own recursion.
lemma {:induction false} RootSpellingCharacterisation(s: string)
  // @spec BE-029
  ensures AddressesRoot(s) <==> RootSpelling(s)
  decreases |s|
{
  if |s| == 0 {
    assert RootSpelling(s);
  } else {
    RootSpellingCharacterisation(s[1..]);
    // RootSpelling(s) is RootSpelling(s[1..]) plus the condition at index 0.
    assert forall i | 1 <= i < |s| :: s[i] == s[1..][i - 1];
    if s[0] == '/' || (s[0] == '.' && (|s| == 1 || s[1] == '/')) {
      assert AddressesRoot(s) == AddressesRoot(s[1..]);
      assert RootSpelling(s) <==> RootSpelling(s[1..]);
    } else {
      assert !AddressesRoot(s);
      assert !RootSpelling(s);
    }
  }
}

// Property 2: the sentinel the Python adapter maps "" onto is the root.
lemma RootSentinelAddressesRoot()
  // @spec BE-029
  ensures AddressesRoot(Root)
{
  assert Root == ".";
  assert "."[1..] == "";
  assert AddressesRoot("");
}

// ---------------------------------------------------------------------------
// §2  The predicate on the trait's domain
// ---------------------------------------------------------------------------

// Property 3: a well-formed path other than Root never addresses the root.
//
// Proof outline: a well-formed non-root path is non-empty and has no
// leading '/', so AddressesRoot can only accept it through a leading '.'
// followed by the end or by '/'.  The end makes it ".", which is Root; a
// '/' makes "." a leading segment, which PATH-006 (no "." segment) rules
// out.
lemma WellFormedNonRootIsNotRoot(s: string)
  requires WellFormedPath(s)
  requires s != Root
  // @spec BE-029
  ensures !AddressesRoot(s)
{
  assert |s| > 0;
  assert s[0] != '/';
  if AddressesRoot(s) {
    assert s[0] == '.' && (|s| == 1 || s[1] == '/');
    if |s| == 1 {
      assert s == ".";
      assert s == Root;
      assert false;
    } else {
      assert s[..2] == "./";
      assert HasSegment(s, ".");
      assert false;
    }
  }
}

// ---------------------------------------------------------------------------
// §3  The stated bound
// ---------------------------------------------------------------------------

// Property 4: BE-029 § "The rule stops at the slash-and-dot spellings": a
// backslash-only key is not refused, because folding '\' would move the
// addressing the same predicate decides.
lemma BackslashIsNotRoot()
  // @spec BE-029
  ensures !AddressesRoot("\\")
{
  assert "\\"[0] == '\\';
  assert "\\"[0] != '/' && "\\"[0] != '.';
}
