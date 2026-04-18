---------------------------- MODULE MC2 ----------------------------
(* Model-checking harness for WR018ProxyForwarding.                   *)

EXTENDS WR018ProxyForwarding

CONSTANTS p1, p2

MCPaths     == {p1, p2}
MCDataSizes == 1..2
MCMaxClock  == 3
=============================================================================
