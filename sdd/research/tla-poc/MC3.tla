---------------------------- MODULE MC3 ----------------------------
(* Model-checking harness for Observer.                               *)
(* Instantiates the abstract constants with a small finite model.     *)

EXTENDS Observer

CONSTANTS op_read, op_write, op_delete

MCOps      == {op_read, op_write, op_delete}
MCMaxCalls == 3
=============================================================================
