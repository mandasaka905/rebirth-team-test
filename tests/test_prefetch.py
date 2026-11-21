from pathlib import Path
import tempfile,unittest
from copy import deepcopy
from test_core import ledger,proposal
from rebirth.engine import Engine
from rebirth.store import Store
from rebirth.providers import RuleProvider
from rebirth.prefetch import plan
class PrefetchTests(unittest.TestCase):
 def test_only_registered_readonly_tools_and_bounded_exact_proposal_versions(self):
  from rebirth.tools import TOOL_ARGS
  p=proposal();calls=plan('cash','review',[p]*20);self.assertEqual(len(calls),8)
  self.assertTrue(all(n in TOOL_ARGS for n,a in calls));self.assertEqual(calls[1][1]['proposal']['version'],p['version']);calls[1][1]['proposal']['version']=99;self.assertNotEqual(p['version'],99)
  self.assertEqual(plan('coordinator','coordinate',[]),[])
 def test_first_model_step_already_has_real_role_scoped_evidence(self):
  class Capture(RuleProvider):
   prefetch_readonly_evidence=True
   def __init__(self):self.seen=[]
   def step(self,c):self.seen.append(deepcopy(c));return super().step(c)
  with tempfile.TemporaryDirectory() as d:
   store=Store(Path(d)/'db.sqlite3');l=ledger();store.put_ledger(l);provider=Capture();r=Engine(store,provider,max_rounds=0).execute(l['merchant_id'])
   for role in ('inventory','customer','cash'):
    c=next(c for c in provider.seen if c['role']==role and c['phase']=='investigate');self.assertGreaterEqual(len(c['observations']),2)
    for o in c['observations']:
     e=next(e for e in r['events'] if e['id']==o['evidence_id']);self.assertEqual(e['actor'],role);self.assertEqual(e['data']['source'],'host_prefetch');self.assertEqual(e['data']['phase'],'investigate')
   self.assertEqual(r['status'],'rehearsal_only')
