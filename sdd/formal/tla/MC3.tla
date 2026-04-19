---------------------------- MODULE MC3 ----------------------------
(* Model-checking harness for Observer.                               *)
(* Instantiates the abstract constants with a small finite model.     *)

EXTENDS Observer

CONSTANTS
    op_read, op_write, op_delete,
    read_hook, write_hook, delete_hook

MCOps         == {op_read, op_write, op_delete}
MCHookClasses == {read_hook, write_hook, delete_hook}

\* OBS-003a mapping (minimal — one op per class). The final branch is
\* guarded with Assert so that widening MCOps without extending this
\* function trips TLC immediately rather than silently bucketing the
\* new op into delete_hook.
MCClassOf == [op \in MCOps |->
                  IF op = op_read   THEN read_hook
                  ELSE IF op = op_write  THEN write_hook
                  ELSE IF op = op_delete THEN delete_hook
                  ELSE Assert(FALSE, "MCClassOf: unmapped op — extend MCClassOf when widening MCOps")]

MCOutcomes == {"success", "error"}

MCMaxCalls == 3
=============================================================================
