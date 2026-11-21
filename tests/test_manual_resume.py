from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from test_core import ledger,proposal
from rebirth.store import Store
from rebirth.engine import Engine
from rebirth.providers import RuleProvider,ProviderError


class ManualResumeTests(unittest.TestCase):
    def test_resume_preserves_manual_input_and_validated_reviews(self):
        class FailAtCoordination(RuleProvider):
            def step(self,c):
                if c['phase']=='coordinate':raise ProviderError('constructed interruption')
                return super().step(c)
        class Count(RuleProvider):
            def __init__(self):self.phases=[]
            def step(self,c):self.phases.append(c['phase']);return super().step(c)
        with tempfile.TemporaryDirectory() as folder:
            s=Store(Path(folder)/'manual.sqlite3');l=ledger();s.put_ledger(l)
            parent=Engine(s,RuleProvider(),max_rounds=0).execute(l['merchant_id'])
            p=deepcopy(parent['result']['proposals'][0]['proposal']);p.update(id='manual_new_candidate',version=1,new_candidate=True)
            engine=Engine(s,FailAtCoordination(),max_rounds=0)
            with self.assertRaises(ProviderError):engine.execute(l['merchant_id'],draft=p,parent_run=parent['run_id'])
            old=s.result(l['merchant_id'],engine.run_id)
            original=next(e['data']['after'] for e in old['events'] if e['kind']=='proposal_revision' and e['actor']=='merchant')
            provider=Count();r=Engine(s,provider,max_rounds=0).execute(l['merchant_id'],resume_run=engine.run_id)
            manual=[e for e in r['events'] if e['kind']=='proposal_revision' and e['actor']=='merchant']
            self.assertEqual(len(manual),1);self.assertEqual(manual[0]['data']['after'],original)
            self.assertNotIn('propose',provider.phases);self.assertNotIn('review',provider.phases)
            self.assertEqual([x['proposal']['id'] for x in r['result']['proposals']],['manual_new_candidate'])
