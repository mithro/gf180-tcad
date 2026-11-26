"""Shared solver options for the experiments, from the environment."""

import os

REL = float(os.environ.get("CX_REL", "1e-10"))
ABS = float(os.environ.get("CX_ABS", "1e-12"))
LIN = os.environ.get("CX_LIN", "klu2")
PFX = "Charon->Solution Control->NOX->Direction->Newton->Stratimikos Linear Solver->Stratimikos"
KLU2 = [
    f'Direct input "{PFX},Linear Solver Type,string,Amesos2"',
    f'Direct input "{PFX},Preconditioner Type,string,None"',
    f'Direct input "{PFX}->Linear Solver Types->Amesos2,Solver Type,string,KLU2"',
]
NO_RESCUE = 'Direct input "Charon->Solution Control->NOX->Direction->Newton,Rescue Bad Newton Solve,bool,false"'
if os.environ.get("CX_NORESCUE") == "1":
    KLU2 = [*KLU2, NO_RESCUE]
EXTRA = KLU2 if LIN == "klu2" else []
