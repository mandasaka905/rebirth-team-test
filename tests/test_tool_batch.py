from copy import deepcopy
import tempfile
from pathlib import Path
import unittest
from test_core import ledger
from rebirth.domain import ValidationError
from rebirth.tool_batch import expand
from rebirth.engine import Engine
from rebirth.store import Store
from rebirth.providers import RuleProvider


class BatchTests(unittest.TestCase):
    def test_invalid_batches_rejected_before_any_execution(self):
        for args in ({'calls':[]},{'calls':[{'name':'read_tools','arguments':{}}]},
                     {'calls':[{'name':'http://example.com','arguments':{}}]},
                     {'calls':[{'name':'inventory_analyze','arguments':{}}]*9}):
            with self.assertRaises(ValidationError):expand('read_tools',args)

    def test_investigation_keeps_individual_evidence_and_two_cloud_steps(self):
        class Batch(RuleProvider):
            def __init__(self):self.seen=[]
            def step(self,c):
                self.seen.append(deepcopy(c))
                if not c['observations']:
                    return {'action':'tool','name':'read_tools','arguments':{'calls':[
                        {'name':'inventory_analyze','arguments':{}},{'name':'data_readiness','arguments':{}}]}}
                from rebirth.collaboration_protocol import rule_contract
                return {'action':'final','result':rule_contract(c,{})}
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'business.sqlite3');l=ledger();store.put_ledger(l)
            run,_=store.new_run(l['merchant_id'],'rules');p=Batch();e=Engine(store,p);e.strict_collaboration=True
            result=e.call(l['merchant_id'],run,l,'inventory','investigate')
            self.assertEqual(len(p.seen),2)
            observations=p.seen[-1]['observations']
            self.assertEqual({o['tool'] for o in observations},{'inventory_analyze','data_readiness'})
            self.assertEqual(len({o['evidence_id'] for o in observations}),2)
            self.assertIn('assessment',result)
            events=store.events(l['merchant_id'],run)
            self.assertEqual(sum(x['kind']=='tool_result' for x in events),2)


if __name__=='__main__':unittest.main()
