import json
import tempfile
import unittest
from pathlib import Path
from rebirth.store import Store

class RecoveryTests(unittest.TestCase):
    def test_restart_preserves_partial_events_and_finished_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'data.sqlite3')
            ledger=json.loads((Path(__file__).parents[1]/'examples/acceptance.synthetic.json').read_text(encoding='utf-8'))
            store.put_ledger(ledger)
            merchant=ledger['merchant_id']
            run,_=store.new_run(merchant,'agentarts')
            store.event(merchant,run,'inventory','agent_result',{'phase':'investigate','result':{}})
            finished,_=store.new_run(merchant,'rules')
            store.finish(merchant,finished,{'status':'needs_data','proposals':[]})
            self.assertEqual(store.interrupt_orphaned_runs(),1)
            self.assertEqual(store.check(merchant,run)['status'],'interrupted')
            self.assertEqual(store.check(merchant,finished)['status'],'needs_data')
            self.assertEqual(store.events(merchant,run)[0]['kind'],'agent_result')
            self.assertEqual(store.interrupt_orphaned_runs(),0)

if __name__=='__main__':unittest.main()

