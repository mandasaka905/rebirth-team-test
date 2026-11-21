import tempfile
from pathlib import Path
import unittest
from test_core import ledger
from rebirth.engine import Engine
from rebirth.providers import ProviderError
from rebirth.store import Store


class PhaseResumeTests(unittest.TestCase):
    def test_same_input_reuses_real_phase_evidence_without_another_tool_call(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'test.sqlite3')
            l=ledger();store.put_ledger(l)
            run,_=store.new_run(l['merchant_id'],'test')
            class Interrupted:
                mode='test'
                def step(self,c):
                    if not c['observations']:return {'action':'tool','name':'cash_baseline','arguments':{}}
                    raise ProviderError('synthetic interruption')
            with self.assertRaises(ProviderError):Engine(store,Interrupted()).call(l['merchant_id'],run,l,'coordinator','coordinate')
            class Continued:
                mode='test'
                def step(inner,c):
                    self.assertEqual(len(c['observations']),1)
                    self.assertEqual(c['observations'][0]['tool'],'cash_baseline')
                    self.assertTrue(c['observations'][0]['evidence_id'].startswith('e'))
                    return {'action':'final','result':{'revise_roles':[]}}
            engine=Engine(store,Continued());engine.resuming=True
            engine.call(l['merchant_id'],run,l,'coordinator','coordinate')
            events=store.events(l['merchant_id'],run)
            self.assertEqual(sum(e['kind']=='tool_result' for e in events),1)
            self.assertTrue(any(e['kind']=='phase_evidence_resumed' for e in events))

    def test_different_input_does_not_reuse_previous_phase_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'test.sqlite3');l=ledger();store.put_ledger(l)
            run,_=store.new_run(l['merchant_id'],'test')
            store.event(l['merchant_id'],run,'coordinator','phase_started',{'phase':'coordinate','input_digest':'different'})
            store.event(l['merchant_id'],run,'coordinator','tool_result',{'phase':'coordinate','tool':'cash_baseline','arguments':{},'value':{}})
            class Continued:
                mode='test'
                def step(inner,c):
                    self.assertEqual(c['observations'],[])
                    return {'action':'final','result':{'revise_roles':[]}}
            engine=Engine(store,Continued());engine.resuming=True
            engine.call(l['merchant_id'],run,l,'coordinator','coordinate')


if __name__=='__main__':unittest.main()
