"""Bounded local evidence preparation; no conclusions or external requests."""
from copy import deepcopy
PRIMARY={'inventory':'inventory_analyze','customer':'customer_evidence','cash':'cash_baseline'}
def plan(role,phase,proposals=()):
    if role not in PRIMARY or phase not in ('investigate','propose','review','revise'):return []
    calls=[(PRIMARY[role],{})]
    if phase=='investigate':calls.append(('data_readiness',{}))
    if phase in ('review','revise'):calls.extend(('proposal_evaluate',{'proposal':deepcopy(p)}) for p in proposals)
    return calls[:8]
