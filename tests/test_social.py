import json
import tempfile
import unittest
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

from rebirth.store import Store
from rebirth.domain import ValidationError

ROOT = Path(__file__).resolve().parent.parent
TODAY = date.today().isoformat()
BASE = (date.today() - timedelta(days=31)).isoformat()


class SocialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'social.sqlite3'
        self.s = Store(self.path)
        self.ledger = json.loads((ROOT/'examples/planning.synthetic.json').read_text(encoding='utf-8'))
        self.m = self.ledger['merchant_id']
        self.s.put_ledger(self.ledger)
        self.s.put_ledger({**deepcopy(self.ledger), 'merchant_id': 'neighbor'})

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, merchant=None, **kw):
        raw = dict(category='digital', problem='不会整理库存表', goal='独立完成一次盘点', availability='下午空闲时', requested_on=BASE, next_on=TODAY, local_consent=True, aggregate_consent=True)
        raw.update(kw)
        return self.s.support_request(merchant or self.m, raw)

    def event(self, request, action, **kw):
        case = next(c for c in self.s.social_home(self.m)['cases'] if c['id'] == request['id'])
        raw = dict(request_id=request['id'], expected_id=case['last_id'], action=action, occurred_on=TODAY, notes='全部合成：核对操作记录', confirmed=True)
        raw.update(kw)
        return self.s.support_event(self.m, raw)

    def closed(self, outcome='solved', **kw):
        r = self.request()
        self.event(r, 'plan', helper_alias='合成协助者', step='先学会导出一张盘点表', planned_minutes=20, next_on=TODAY, **kw)
        self.event(r, 'visit', actual_minutes=20, extra_spend='0', blockers='仍需练习', next_on=TODAY)
        self.event(r, 'review', outcome=outcome, merchant_voice='可以独立试一次', next_choice='下周再核对')
        return r

    def share(self, request, **kw):
        raw = dict(request_id=request['id'], title='先盘清一种商品', industry='retail', problem='商品记录不清', steps=['只选一种商品盘点', '保留数量与来源'], fits='有可核对的原单和库存', stop_when='数量来源不明时先停下', lesson='没有立刻改善，先把缺口记清', share_consent=True, anonymous_checked=True)
        raw.update(kw)
        return self.s.experience_share(self.m, raw)

    def adopt(self, card, **kw):
        raw = dict(share_id=card['id'], step_index=0, planned_on=TODAY, next_on=TODAY, minutes_cap=15, spend_cap='0', fit_note='本店也有同类盘点困难', adapted_step='只盘一种已有商品', stop_when='原单找不到就暂停', confirmed=True)
        raw.update(kw)
        return self.s.experience_adopt('neighbor', raw)

    def test_support_enforces_order_and_preserves_ledger(self):
        r = self.request()
        with self.assertRaises(ValidationError): self.event(r, 'review', outcome='solved')
        with self.assertRaises(ValidationError): self.event(r, 'visit', actual_minutes=2, extra_spend='0', next_on=TODAY)
        self.event(r, 'plan', helper_alias='自己', step='核对一张表', planned_minutes=10, next_on=TODAY)
        self.event(r, 'pause', next_on=TODAY)
        self.event(r, 'resume', next_on=TODAY)
        self.event(r, 'visit', actual_minutes=8, extra_spend='0', blockers='没有额外障碍', next_on=TODAY)
        self.event(r, 'review', outcome='partial', merchant_voice='还有部分没学会', next_choice='继续整理')
        c = Store(self.path).social_home(self.m)['cases'][0]
        self.assertEqual(c['status'], 'closed')
        self.assertEqual(len(c['history']), 5)
        self.assertEqual(self.s.ledger(self.m), self.ledger)
        self.event(r, 'resume', next_on=TODAY)
        self.assertEqual(self.s.social_home(self.m)['cases'][0]['status'], 'following')

    def test_confirmations_dates_and_versions(self):
        with self.assertRaises(ValidationError): self.s.support_request(self.m, {'local_consent': False})
        r = self.request()
        with self.assertRaises(ValidationError): self.event(r, 'plan', expected_id='wrong')
        with self.assertRaises(ValidationError): self.event(r, 'pause', confirmed=False)
        with self.assertRaises(ValidationError): self.event(r, 'pause', next_on='2000-01-01')
        with self.assertRaises(ValidationError): self.s.support_event('neighbor', dict(request_id=r['id'], expected_id=r['id'], action='withdraw', occurred_on=TODAY, notes='不得操作别店', confirmed=True))
        self.event(r, 'withdraw')
        self.assertEqual(self.s.social_home(self.m)['reminders'], [])

    def test_share_requires_review_and_allows_unsuccessful_lessons(self):
        r = self.request()
        with self.assertRaises(ValidationError): self.share(r)
        r = self.closed('unresolved')
        card = self.share(r)
        self.assertEqual(card['data']['outcome'], 'unresolved')
        with self.assertRaises(ValidationError): self.share(r)
        with self.assertRaises(ValidationError): self.share(self.closed(), share_consent=False)

    def test_neighbor_only_gets_allowlisted_abstract(self):
        r = self.closed()
        card = self.share(r)
        neighbor = self.s.social_home('neighbor')['cards'][0]
        serialized = json.dumps(neighbor, ensure_ascii=False)
        for key in ['request_id', 'review_id', 'helper_alias', 'merchant_voice', 'source_note', 'cash_balance', 'owner_merchant']:
            self.assertNotIn(key, serialized)
        self.assertEqual(neighbor['id'], card['id'])
        with self.assertRaises(ValidationError): self.share(self.closed(), lesson='请联系13812345678')
        with self.assertRaises(ValidationError): self.share(self.closed(), steps=['找 x@example.com'])

    def test_reopened_source_is_unavailable_for_new_adoptions(self):
        r = self.closed(); card = self.share(r)
        self.event(r, 'resume', next_on=TODAY)
        self.assertEqual(self.s.social_home('neighbor')['cards'], [])
        with self.assertRaises(ValidationError): self.adopt(card)
        self.assertTrue(self.s.social_home(self.m)['cards'][0]['source_changed'])

    def test_withdrawal_stops_new_use_but_preserves_prior_feedback(self):
        card = self.share(self.closed()); a = self.adopt(card)
        with self.assertRaises(ValidationError): self.adopt(card)
        with self.assertRaises(ValidationError): self.s.experience_withdraw('neighbor', {'share_id':card['id'],'confirmed':True,'reason':'不是本店'})
        self.s.experience_withdraw(self.m, {'share_id':card['id'],'confirmed':True,'reason':'合成撤回'})
        self.assertTrue(self.s.social_home('neighbor')['adoptions'][0]['source_unavailable'])
        with self.assertRaises(ValidationError): self.adopt(card)
        raw = dict(adoption_id=a['id'], expected_id=None, observed_on=TODAY, result='unsuitable', actual_minutes=20, extra_spend='2', actual='不适合，已停止', source_note='原单缺失，无真实经营', next_step='先补原单', confirmed=True)
        result = self.s.experience_result('neighbor', raw)
        with self.assertRaises(ValidationError): self.s.experience_result('neighbor', raw)
        self.s.experience_result('neighbor', {**raw,'expected_id':result['id'],'actual':'更正：仅试做，没有执行经营'})
        self.assertEqual(len(self.s.social_home('neighbor')['adoptions'][0]['history']), 2)

    def test_real_synthetic_separation_and_future_dates(self):
        self.share(self.closed())
        real = {**deepcopy(self.ledger), 'merchant_id':'real', 'synthetic':False}
        self.s.put_ledger(real)
        self.assertEqual(self.s.social_home('real')['cards'], [])
        self.assertEqual(self.s.social_home('real')['summary']['participating_shops'], 0)
        with self.assertRaises(ValidationError): self.request('real', requested_on='2099-01-01')

    def test_summary_deduplicates_and_keeps_units_and_observation_window(self):
        baseline = self.s.impact_start(self.m, dict(confirmed=True, metric='checking_time', scope='同一盘点步骤', goal='学会整理', baseline_date=BASE, baseline_value='30', source_note='合成计时'))
        c = self.closed(impact_case_id=baseline['id']); self.closed('unresolved', impact_case_id=baseline['id'])
        raw = dict(case_id=baseline['id'], observed_on=TODAY, value='20', source_note='合成计时', actions='合成练习', external_factors='可能熟练度变化', extra_spend='0', extra_minutes=20, status='observed', previous_id=None, same_scope_confirmed=True)
        self.s.impact_observe(self.m, raw)
        report = self.s.social_home(self.m)['summary']
        self.assertEqual(report['participating_shops'],1)
        self.assertEqual(report['reviewed_cases'],2)
        self.assertEqual(report['reviewed_shops'],1)
        self.assertEqual(report['unresolved_cases'],1)
        self.assertEqual(report['observed_30day_shops'],1)
        self.assertEqual(report['metrics'][0]['cases'],1)
        self.assertEqual(report['metrics'][0]['lower'],1)
        for key in ['merchant', 'cash_balance', 'name', 'problem']:
            self.assertNotIn('"'+key+'"', json.dumps(report))
        self.assertTrue(any(x['kind']=='support_request' for x in self.s.export_bundle(self.m)['workbench_history']))

    def test_opt_out_requests_never_enter_community_summary(self):
        raw = dict(category='records', problem='不会用表', goal='学习一次', availability='周末', requested_on=TODAY, next_on=TODAY, local_consent=True, aggregate_consent=False)
        self.s.support_request(self.m,raw)
        self.assertEqual(self.s.social_home(self.m)['summary']['requested_cases'],0)

    def test_aggregate_consent_can_be_withdrawn_without_losing_case(self):
        r = self.closed()
        raw = dict(request_id=r['id'], expected_id=None, aggregate_consent=False, confirmed=True)
        saved = self.s.support_consent(self.m, raw)
        self.assertEqual(self.s.social_home(self.m)['summary']['participating_shops'], 0)
        self.assertEqual(self.s.social_home(self.m)['cases'][0]['status'], 'closed')
        with self.assertRaises(ValidationError): self.s.support_consent(self.m, raw)
        self.s.support_consent(self.m, {**raw,'expected_id':saved['id'],'aggregate_consent':True})
        self.assertEqual(self.s.social_home(self.m)['summary']['participating_shops'], 1)

    def test_thirty_day_counter_excludes_short_and_paused_observations(self):
        base = (date.today()-timedelta(days=10)).isoformat()
        c = self.s.impact_start(self.m,dict(confirmed=True,metric='stock_value',scope='同批货',goal='核对',baseline_date=base,baseline_value='100',source_note='合成'))
        self.closed(impact_case_id=c['id'])
        self.s.impact_observe(self.m,dict(case_id=c['id'],observed_on=TODAY,value='80',source_note='合成',actions='合成',external_factors='季节',extra_spend='0',extra_minutes=10,status='observed',previous_id=None,same_scope_confirmed=True))
        self.assertEqual(self.s.social_home(self.m)['summary']['observed_30day_shops'],0)

    def test_concurrent_followups_accept_only_one_same_version(self):
        from concurrent.futures import ThreadPoolExecutor
        r = self.request()
        raw = dict(request_id=r['id'],expected_id=r['id'],action='pause',occurred_on=TODAY,next_on=TODAY,notes='合成并发暂停',confirmed=True)
        def save():
            try:
                Store(self.path).support_event(self.m,raw)
                return True
            except ValidationError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(lambda _:save(),range(2))),[False,True])

    def test_adoption_requires_other_store_and_existing_step(self):
        card = self.share(self.closed())
        with self.assertRaises(ValidationError): self.adopt(card, step_index=2)
        with self.assertRaises(ValidationError): self.adopt(card, minutes_cap=0)
        with self.assertRaises(ValidationError): self.s.experience_adopt(self.m,dict(confirmed=True,share_id=card['id']))

    def test_learning_only_shop_can_opt_in_and_withdraw_its_own_aggregate(self):
        card = self.share(self.closed())
        a = self.adopt(card, aggregate_consent=True)
        summary = self.s.social_home('neighbor')['summary']
        self.assertEqual(summary['participating_shops'],2)
        self.assertEqual(summary['learning_shops'],1)
        with self.assertRaises(ValidationError): self.s.experience_consent(self.m,dict(adoption_id=a['id'],confirmed=True,aggregate_consent=False))
        raw = dict(adoption_id=a['id'],expected_id=None,confirmed=True,aggregate_consent=False)
        self.s.experience_consent('neighbor',raw)
        self.assertEqual(self.s.social_home('neighbor')['summary']['learning_shops'],0)
        self.assertEqual(len(self.s.social_home('neighbor')['adoptions']),1)
        with self.assertRaises(ValidationError): self.s.experience_consent('neighbor',raw)


if __name__ == '__main__': unittest.main()
