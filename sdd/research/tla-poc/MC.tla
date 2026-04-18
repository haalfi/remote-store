---------------------------- MODULE MC ----------------------------
(* Model-checking harness for WriteHeadRoundTrip.                     *)
(* Instantiates the abstract constants with a small finite model.     *)

EXTENDS WriteHeadRoundTrip

CONSTANTS p1, p2, m1, m2

MCPaths      == {p1, p2}
MCDataSizes  == 1..2
MCMetaValues == {m1, m2}
MCMaxClock   == 4
=============================================================================
