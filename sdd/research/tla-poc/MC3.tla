---------------------------- MODULE MC3 ----------------------------
(* Model-checking harness for Observer.                               *)
(* Instantiates the abstract constants with a small finite model.     *)

EXTENDS Observer

CONSTANTS
    op_read, op_write, op_delete,
    read_hook, write_hook, delete_hook

MCOps         == {op_read, op_write, op_delete}
MCHookClasses == {read_hook, write_hook, delete_hook}

\* OBS-003a mapping (minimal — one op per class).
MCClassOf == [op \in MCOps |->
                  IF op = op_read   THEN read_hook
                  ELSE IF op = op_write  THEN write_hook
                  ELSE (* op = op_delete *) delete_hook]

MCMaxCalls == 3
=============================================================================
