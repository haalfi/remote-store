// RootPath.dfy. Verified properties of BE-029's root predicate.
//
// BK-388: `AddressesRoot` lives upstream in BackendContract.dfy §5c, because
// the trait's write-shaped postconditions name it.  This module proves what
// the predicate accepts and rejects without adding to the trait, in the
// shape of DepthCounting.dfy:
//   1. Every slash-and-dot spelling of the root addresses it.
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
