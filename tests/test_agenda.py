import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from rebirth.store import Store
from rebirth.engine import Engine
from rebirth.providers import RuleProvider
from rebirth.domain import ValidationError
ROOT=Path(__file__).resolve().parent.parent
class AgendaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'agenda.db';self.store=Store(self.path)
        self.ledger=json.loads((ROOT/'examples/planning.synthetic.json').read_text(encoding='utf-8'));self.m=self.ledger['merchant_id'];self.store.put_ledger(self.ledger)
        self.report=Engine(self.store,RuleProvider()).execute(self.m)
        self.request={'run_id':self.report['run_id'],'start_date':self.ledger['as_of'],'days':7,'daily_minutes':30}
    def tearDown(self):self.tmp.cleanup()
    def preview(self,**changes):return self.store.agenda_preview(self.m,{**self.request,**changes})
    def save(self,preview=None,current=None):
        p=preview or self.preview();return self.store.save_agenda(self.m,{**p['request'],'fingerprint':p['fingerprint'],'confirmed':True,'expected_current_id':current})
    def progress(self,a,tid,status='done',note='合成验收：对照原单据核对，未发生真实经营动作'):
        return self.store.agenda_progress(self.m,{'agenda_id':a['id'],'task_id':tid,'status':status,'note':note,'expected_revision':a['revision']})
    def test_paused_count_survives_refresh_without_completing_task(self):
        agenda=self.save()['agendas'][0]
        tid=agenda['days'][0]['tasks'][0]['id']
        self.progress(agenda,tid,status='skipped',note='模拟：凭证待核对，暂停本项')
        fresh=Store(self.path).agendas(self.m)['agendas'][0]
        self.assertEqual(fresh['completed_count'],0)
        self.assertEqual(fresh['paused_count'],1)
        self.assertEqual(fresh['pending_count'],fresh['task_count']-1)
        task=next(t for day in fresh['days'] for t in day['tasks'] if t['id']==tid)
        self.assertIn('凭证待核对',task['note'])

    def test_client_refresh_after_save_does_not_trigger_second_error_reply(self):
        from types import SimpleNamespace
        from rebirth.server import make_handler
        class ClosedWriter:
            def write(self,value):raise ConnectionAbortedError('client refreshed')
        handler=SimpleNamespace(send_response=lambda *args:None,send_header=lambda *args:None,end_headers=lambda:None,wfile=ClosedWriter())
        make_handler(self.store,ROOT/'config/local.example.json').reply(handler,200,{'saved':True})
    def test_no_selection_is_zero_spend_with_real_source(self):
        p=self.preview();self.assertEqual(p['plan_spend_cap'],'0.00');self.assertTrue(p['summary']['gates']);self.assertEqual(p['source_run'],self.report['run_id']);self.assertEqual(len(p['days']),7)
        self.assertTrue(all(t['kind']!='execution' for d in p['days'] for t in d['tasks']));self.assertTrue(any(t['id']=='due_0' for d in p['days'] for t in d['tasks']));self.assertEqual(next(t['date'] for d in p['days'] for t in d['tasks'] if t['id']=='due_0'),self.ledger['obligations'][0]['date'])
    def test_action_basis_and_specific_expenses_stay_preparation_when_unverified(self):
        fixture=json.loads((ROOT/'testing/explainable-case/case-and-evidence.json').read_text(encoding='utf-8'))
        l=fixture['ledger'];l['candidate_for_review']=fixture['after'];l['candidate_for_review']['version']=1
        self.store.put_ledger(l);report=Engine(self.store,RuleProvider(),max_rounds=0).execute(l['merchant_id'])
        p=self.store.agenda_preview(l['merchant_id'],{'run_id':report['run_id'],'start_date':l['as_of'],'days':14,'daily_minutes':180,'proposal_id':fixture['after']['id'],'proposal_version':1})
        all_tasks=[t for d in p['days'] for t in d['tasks']]+p['backlog']
        cost=next(t for t in all_tasks if t['id']=='check_costs')
        self.assertIn('20 × ¥2.00 = ¥40.00',' '.join(cost['steps']))
        self.assertEqual(cost['basis']['proposal_version'],1);self.assertTrue(cost['basis']['evidence_ids'])
        self.assertEqual(p['plan_spend_cap'],'0.00');self.assertFalse(any(t['kind']=='execution' for t in all_tasks))
    def test_caps_and_backlog_do_not_shift_dates(self):
        l=deepcopy(self.ledger);l['weekly_available_hours']=1;l['obligations'].append({**l['obligations'][0],'id':'rent_second'});self.store.put_ledger(l);self.report=Engine(self.store,RuleProvider()).execute(self.m);self.request['run_id']=self.report['run_id']
        p=self.preview(daily_minutes=10);self.assertLessEqual(p['total_minutes'],60);self.assertTrue(p['backlog']);self.assertTrue(all(d['minutes']<=10 for d in p['days']))
    def test_stale_source_rejected(self):
        p=self.preview();l=self.store.ledger(self.m);l['cash_balance']='11999.00';self.store.put_ledger(l)
        with self.assertRaises(ValidationError):self.save(p)
    def test_client_cannot_change_generated_tasks(self):
        p=self.preview();request={**p['request'],'daily_minutes':45,'fingerprint':p['fingerprint'],'confirmed':True,'expected_current_id':None}
        with self.assertRaises(ValidationError):self.store.save_agenda(self.m,request)
    def test_exact_version_and_past_spend_are_guarded(self):
        p=self.report['result']['proposals'][0]['proposal']
        with self.assertRaises(ValidationError):self.preview(proposal_id=p['id'],proposal_version=999)
        draft=self.preview(proposal_id=p['id'],proposal_version=p['version'],start_date='2026-10-29')
        self.assertTrue(any('日期已早于' in g for g in draft['summary']['gates']));self.assertEqual(draft['plan_spend_cap'],'0.00')
    def test_save_and_progress_survive_restart_without_changing_ledger(self):
        original=self.store.ledger(self.m);a=self.save()['agendas'][0];updated=self.progress(a,'check_cash')['agendas'][0]
        self.assertEqual(updated['completed_count'],1);self.assertEqual(Store(self.path).agendas(self.m)['agendas'][0]['completed_count'],1);self.assertEqual(self.store.ledger(self.m),original)
        self.assertTrue(any(r['kind']=='agenda_progress' for r in self.store.export_bundle(self.m)['workbench_history']))
    def test_dependencies_and_concurrent_revision(self):
        a=self.save()['agendas'][0]
        with self.assertRaises(ValidationError):self.progress(a,'check_stock')
        b=self.progress(a,'check_cash')['agendas'][0]
        with self.assertRaises(ValidationError):self.progress(a,'check_cash')
        b=self.progress(b,'check_stock')['agendas'][0]
        with self.assertRaises(ValidationError):self.progress(b,'check_cash','pending')
    def test_new_agenda_preserves_read_only_history(self):
        a=self.save()['agendas'][0]
        with self.assertRaises(ValidationError):self.save()
        listing=self.save(current=a['id']);self.assertEqual(len(listing['agendas']),2);self.assertFalse(listing['agendas'][1]['current'])
        with self.assertRaises(ValidationError):self.progress(a,'check_cash')
    def test_invalid_time_types_and_cross_merchant(self):
        for change in ({'days':7.0},{'daily_minutes':True},{'daily_minutes':0},{'days':30},{'start_date':'invalid'}):
            with self.assertRaises(ValidationError):self.preview(**change)
        l=deepcopy(self.ledger);l['merchant_id']='other_shop';self.store.put_ledger(l)
        with self.assertRaises(ValidationError):self.store.agenda_preview('other_shop',self.request)
    def test_expense_task_cannot_be_marked_without_trial_and_design(self):
        from datetime import date,timedelta
        p=deepcopy(self.report['result']['proposals'][0]['proposal']);p.update(version=p['version']+1,costs_confirmed=True,upfront_cost='10.00',other_cost='0.00',weekly_hours=1,spend_date=(date.fromisoformat(self.ledger['as_of'])+timedelta(days=3)).isoformat(),procurements=[])
        for item in p['items']:item.update(quantity=1,variable_cash_cost='0.00',sale_date=(date.fromisoformat(self.ledger['as_of'])+timedelta(days=4)).isoformat(),receipt_date=(date.fromisoformat(self.ledger['as_of'])+timedelta(days=5)).isoformat())
        provider=RuleProvider();provider.mode='manual';self.report=Engine(self.store,provider,max_rounds=0).execute(self.m,draft=p,parent_run=self.report['run_id']);self.request['run_id']=self.report['run_id']
        draft=self.preview(proposal_id=p['id'],proposal_version=p['version'],daily_minutes=180)
        self.assertFalse(draft['summary']['gates'],draft['summary']['gates']);a=self.save(draft)['agendas'][0]
        for tid in ('check_cash','check_stock','check_demand','register_trial'):a=self.progress(a,tid)['agendas'][0]
        execution=next(t for d in a['days'] for t in d['tasks'] if t['kind']=='execution')
        with self.assertRaises(ValidationError):self.progress(a,execution['id'])
if __name__=='__main__':unittest.main()
