import json
import tempfile
import unittest
from pathlib import Path
from copy import deepcopy
from datetime import date
from unittest.mock import patch
import urllib.error
from rebirth.store import Store
from rebirth.engine import Engine
from rebirth.providers import RuleProvider
from rebirth.domain import ValidationError, validate_ledger
from rebirth.planning import assess_models, optimize
from rebirth.accounting import reconcile, parse_csv
from rebirth.tools import cash_baseline, evaluate
from rebirth.research import evaluate_design
from rebirth.server import make_handler
import test_core

ROOT = Path(__file__).resolve().parent.parent


def model():
    return {"id":"m1","name":"预约经营假设","status":"candidate","customer_segment":"下班后的社区居民","customer_problem":"营业时间不匹配","value_proposition":"可预约试穿","channel":"已有自愿咨询","fulfilment":"到店核验","revenue_method":"按件销售","key_resources":"现有商品","required_skills":"接待\n库存核对","available_skills":"接待","demand_evidence":"合成询问，尚待验证","source_note":"全部合成","period_days":30,"unit_revenue":"100.00","unit_cost":"60.00","fixed_cost":"800.00","investment":"100.00","assumed_orders":30,"weekly_hours":4,"costs_confirmed":True}


def accounts():
    return {"opening":{"date":"2026-10-01","balance":"12500.00","source_note":"合成"},
            "purchases":[{"id":"po1","date":"2026-10-20","sku":"COAT_02","quantity":5,"unit_cost":"100.00","other_cost":"0.00","supplier":"合成供应方","due_date":"2026-10-25","external_ref":"invoice1","obligation_id":"","source_note":"合成"}],
            "cash_entries":[{"id":"pay1","date":"2026-10-21","direction":"out","category":"purchase","amount":"500.00","purchase_id":"po1","external_ref":"bank1","source_note":"合成"}]}


def candidate(key, cost="50.00", quantity=2, hours=2):
    return {"key":key,"requires":[],"exclusive_group":"","objections":[],
            "proposal":{"id":key,"version":1,"owner":"inventory","title":key,"spend_date":"2026-10-25","upfront_cost":cost,"other_cost":"0.00","weekly_hours":hours,"sales_assumption":"merchant_estimate","costs_confirmed":True,"items":[{"sku":"COAT_02","quantity":quantity,"price":"139.00","variable_cash_cost":"0.00","receipt_date":"2026-10-30"}],"rationale":"合成假设","evidence_ids":["e1"],"assumptions":["合成"],"stop_conditions":["预算线"]}}


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/"wb.sqlite3")
        self.ledger=json.loads((ROOT/"examples/acceptance.synthetic.json").read_text(encoding="utf-8"))
        self.m=self.ledger["merchant_id"]
        self.store.put_ledger(self.ledger)

    def tearDown(self):
        self.tmp.cleanup()

    def trial(self):
        report=Engine(self.store,RuleProvider()).execute(self.m)
        p=report["result"]["proposals"][0]["proposal"]
        t={"run_id":report["run_id"],"proposal_id":p["id"],"proposal_version":p["version"],"hypothesis":"合成试验","success_metric":"先登记后测量","end_date":"2026-10-30","stop_budget":"500.00","status":"planned","source_note":"合成","acknowledged":True}
        return self.store.save_experiment(self.m,t)

    def study(self):
        trial=self.trial()
        d=self.store.design_template(self.m,trial["id"])
        d.update(scope_confirmed=True,target_value="50.00",source_note="合成预先设计",min_days=2,min_visits=5)
        saved=self.store.save_design(self.m,d)
        self.store.save_experiment(self.m,{**trial,"status":"active","acknowledged":True})
        return trial,saved

    def measurement(self,design):
        return {"design_id":design["id"],"end":"2026-10-30","revenue":"500.00","goods_cost":"300.00","expenses":"20.00","visits":10,"buyers":2,"trial_spend":"100.00","closing_cash":"5000.00","source_note":"合成观察","change_reason":"首次合成","supersedes_id":None,"scope_id":"shop_all","count_basis":"person_visits"}

    def test_model_unit_economics_and_skill_gap(self):
        self.store.save_section(self.m,"business_models",[model()],"合成")
        r=assess_models(self.store.ledger(self.m))["models"][0]
        self.assertEqual(r["unit_contribution"],"40.00")
        self.assertEqual(r["break_even_orders"],20)
        self.assertEqual(r["assumed_period_contribution"],"400.00")
        self.assertIn("库存核对",r["missing_skills"])
        self.assertEqual(len(self.store.records(self.m,"section_change")),1)

    def test_unknown_model_cost_is_not_zero(self):
        m=model();m.update(unit_cost=None,fixed_cost=None,investment=None)
        ledger=validate_ledger({**self.ledger,"business_models":[m]})
        r=assess_models(ledger)["models"][0]
        self.assertIsNone(r["unit_contribution"])
        self.assertIsNone(r["break_even_orders"])
        self.assertIsNone(r["assumed_period_contribution"])
        self.assertTrue(any("未知" in i for i in r["issues"]))

    def test_model_missing_orders_and_nonpositive_unit_margin(self):
        m=model();m.update(assumed_orders=None,unit_cost="110.00")
        ledger={**self.ledger,"business_models":[m]}
        validate_ledger(ledger)
        r=assess_models(ledger)["models"][0]
        self.assertIsNone(r["break_even_orders"])
        self.assertIsNone(r["assumed_period_contribution"])
        self.assertIsNone(r["investment_payback_periods"])

    def test_invalid_models_atomic_and_old_task_immutable(self):
        report=Engine(self.store,RuleProvider()).execute(self.m)
        bad=model();bad["unit_cost"]=1.5
        with self.assertRaises(ValidationError):self.store.save_section(self.m,"business_models",[bad],"合成")
        self.assertNotIn("business_models",self.store.ledger(self.m))
        self.store.save_section(self.m,"business_models",[model()],"合成")
        old=self.store.result(self.m,report["run_id"])
        self.assertTrue(old["ledger_changed"]);self.assertNotIn("business_models",old["ledger_snapshot"])

    def test_accounts_reconcile_without_posting_twice(self):
        self.store.save_section(self.m,"accounts",accounts(),"合成")
        l=self.store.ledger(self.m);r=reconcile(l)
        self.assertEqual(r["closing"],"12000.00");self.assertEqual(r["balance_difference"],"0.00")
        self.assertEqual(r["purchases"][0]["unpaid"],"0.00")
        self.assertEqual(l["products"],self.ledger["products"])
        self.assertEqual(l["cash_balance"],self.ledger["cash_balance"])
        self.assertTrue(cash_baseline(l,{})["complete"])

    def test_unmatched_purchase_blocks_unsafe_plan(self):
        a=accounts();a["cash_entries"]=[]
        l=validate_ledger({**self.ledger,"accounts":a})
        self.assertFalse(cash_baseline(l,{})["complete"])
        r=evaluate(l,{"proposal":candidate("p")["proposal"]})
        self.assertIn("UNRECONCILED_ACCOUNTS",[c["code"] for c in r["checks"]])

    def test_accounts_overpayment_direction_dates_and_unknown_sku(self):
        for mutate in (lambda a:a["cash_entries"][0].update(amount="501.00"),
                       lambda a:a["cash_entries"][0].update(direction="in"),
                       lambda a:a["purchases"][0].update(sku="not_here"),
                       lambda a:a["cash_entries"][0].update(date="2026-10-26")):
            a=accounts();mutate(a)
            with self.assertRaises(ValidationError):validate_ledger({**self.ledger,"accounts":a})

    def test_cash_csv_preview_commit_and_duplicates_are_atomic(self):
        text="id,date,direction,category,amount,external_ref,purchase_id,source_note\nc1,2026-10-20,in,sale,100.00,bank1,,合成"
        raw={"kind":"cash_entries","csv":text,"source_note":"合成批次","confirmed":True}
        self.assertFalse(self.store.import_accounts(self.m,raw)["committed"])
        self.assertNotIn("accounts",self.store.ledger(self.m))
        self.store.import_accounts(self.m,raw,commit=True)
        with self.assertRaises(ValidationError):self.store.import_accounts(self.m,raw,commit=True)
        self.assertEqual(len(self.store.ledger(self.m)["accounts"]["cash_entries"]),1)

    def test_csv_bad_columns_partial_row_and_confirmation(self):
        for text in ("id,date\nx,2026-10-20","id,id\nx,x","id,date,direction,category,amount,external_ref,purchase_id,source_note\nx,2026-10-20,in"):
            with self.assertRaises(ValidationError):parse_csv(text,"cash_entries")
        text="id,date,direction,category,amount,external_ref,purchase_id,source_note\nc1,2026-10-20,in,sale,100.00,b1,,合成"
        with self.assertRaises(ValidationError):self.store.import_accounts(self.m,{"kind":"cash_entries","csv":text},commit=True)

    def test_optimizer_combines_commitments_and_selects_budget(self):
        entries=[candidate("c1","50.00"),candidate("c2","60.00")]
        r=optimize(self.ledger,entries,independent=True)
        self.assertEqual(r["checked"],3)
        self.assertEqual(r["best"]["keys"],["c1","c2"])
        self.assertEqual(r["best"]["evaluation"]["trial_cash_commitment"],"110.00")
        self.assertEqual(r["best"]["proposal"]["items"][0]["quantity"],4)
        self.assertEqual(optimize(self.ledger,entries,independent=True,budget="90.00")["best"]["keys"],["c1"])

    def test_optimizer_exclusion_dependency_and_explicit_demand_confirmation(self):
        a,b=candidate("c1"),candidate("c2")
        self.assertEqual(len(optimize(self.ledger,[a,b])["best"]["keys"]),1)
        a["exclusive_group"]=b["exclusive_group"]="same_customer"
        self.assertEqual(len(optimize(self.ledger,[a,b],independent=True)["best"]["keys"]),1)
        a["exclusive_group"]=b["exclusive_group"]=""
        a["requires"]=["c2"]
        self.assertEqual(optimize(self.ledger,[a,b],independent=True)["best"]["keys"],["c1","c2"])

    def test_optimizer_never_stacks_versions_of_same_plan(self):
        a,b=candidate("c1"),candidate("c2")
        b["proposal"]["id"]=a["proposal"]["id"]
        b["proposal"]["version"]=2
        r=optimize(self.ledger,[a,b],independent=True)
        self.assertEqual(len(r["best"]["keys"]),1)
        self.assertTrue(any("不同任务或版本" in x["reason"] for x in r["rejected"]))

    def test_optimizer_resource_limits_and_no_action(self):
        a,b=candidate("c1",quantity=15),candidate("c2",quantity=15)
        r=optimize(self.ledger,[a,b],independent=True)
        self.assertTrue(any("STOCK_EXCEEDED" in x["reason"] for x in r["rejected"]))
        a,b=candidate("c1",hours=4),candidate("c2",hours=4)
        self.assertTrue(any("WORKLOAD_EXCEEDED" in x["reason"] for x in optimize(self.ledger,[a,b],independent=True)["rejected"]))
        self.assertEqual(optimize(self.ledger,[a,b],independent=True,objective="cash_floor")["best"]["keys"],[])
        a["proposal"]["items"][0]["price"]="60.00"
        self.assertEqual(optimize(self.ledger,[a])["best"]["keys"],[])

    def test_optimizer_differing_dates_terms_unknown_cost_and_bounds(self):
        a,b=candidate("c1"),candidate("c2")
        b["proposal"]["items"][0]["price"]="138.00"
        self.assertTrue(any("同一SKU" in x["reason"] for x in optimize(self.ledger,[a,b],independent=True)["rejected"]))
        with self.assertRaises(ValidationError):optimize(self.ledger,[candidate("c"+str(i)) for i in range(11)])
        with self.assertRaises(ValidationError):optimize(self.ledger,[a],budget="2001.00")

    def test_portfolio_references_versions_reject_stale_and_exports_audit(self):
        report=Engine(self.store,RuleProvider()).execute(self.m)
        p=report["result"]["proposals"][0]["proposal"]
        ref={"key":"c1","run_id":report["run_id"],"proposal_id":p["id"],"version":p["version"]}
        raw={"candidates":[ref],"independent":False}
        self.assertIn("record_id",self.store.select_portfolio(self.m,raw))
        with self.assertRaises(ValidationError):self.store.select_portfolio(self.m,{"candidates":[ref,ref]})
        self.assertTrue(self.store.export_bundle(self.m)["workbench_history"])
        l=self.store.ledger(self.m);l["goal"]="更改目标";self.store.put_ledger(l)
        with self.assertRaises(ValidationError):self.store.select_portfolio(self.m,raw)

    def test_design_frozen_before_observation_and_cannot_rewrite(self):
        t=self.trial();d=self.store.design_template(self.m,t["id"])
        d.update(scope_confirmed=True,target_value="50.00",source_note="合成预注册")
        self.store.save_design(self.m,d)
        with self.assertRaises(ValidationError):self.store.save_design(self.m,{**d,"target_value":"1.00"})
        self.assertEqual(self.store.records(self.m,"design")[0]["data"]["target_value"],"50.00")

    def test_design_baseline_overlap_and_observation_duration_rejected(self):
        t=self.trial();d=self.store.design_template(self.m,t["id"]);d.update(scope_confirmed=True,target_value="50.00",source_note="合成")
        d["baseline"]["end"]=d["observe_start"]
        with self.assertRaises(ValidationError):self.store.save_design(self.m,d)
        d=self.store.design_template(self.m,t["id"]);d.update(scope_confirmed=True,target_value="50.00",source_note="合成",min_days=30)
        with self.assertRaises(ValidationError):self.store.save_design(self.m,d)

    def test_measurement_target_revise_stop_and_insufficient(self):
        t,d=self.study();raw=self.measurement(d)
        first=self.store.save_measurement(self.m,raw)
        self.assertEqual(first["evaluation"]["status"],"target_only")
        self.assertEqual(first["evaluation"]["baseline_relation"],"worse")
        raw.update(revenue="100.00",supersedes_id=first["id"],change_reason="合成核对更正")
        second=self.store.save_measurement(self.m,raw)
        self.assertEqual(second["evaluation"]["status"],"revise")
        raw.update(trial_spend="500.00",supersedes_id=second["id"])
        third=self.store.save_measurement(self.m,raw)
        self.assertEqual(third["evaluation"]["status"],"stop")
        self.assertEqual(len(self.store.records(self.m,"measurement")),3)
        current={**raw,"trial_spend":"100.00","visits":2,"buyers":1}
        self.assertEqual(evaluate_design(d["data"],current,d["data"]["trial_snapshot"],d["data"]["ledger_snapshot"])["status"],"insufficient")

    def test_measurement_stale_supersession_date_and_merchant_isolation(self):
        t,d=self.study();raw=self.measurement(d);saved=self.store.save_measurement(self.m,raw)
        with self.assertRaises(ValidationError):self.store.save_measurement(self.m,raw)
        raw.update(supersedes_id=saved["id"],end="2026-10-29")
        with self.assertRaises(ValidationError):self.store.save_measurement(self.m,raw)
        l=deepcopy(self.ledger);l["merchant_id"]="other";self.store.put_ledger(l)
        with self.assertRaises(ValidationError):self.store.save_measurement("other",raw)

    def test_future_measurements_not_visible_and_next_run_receives_evaluation(self):
        t,d=self.study();self.store.save_measurement(self.m,self.measurement(d))
        self.assertEqual(self.store.research_evidence(self.m,"2026-10-25"),[])
        l=self.store.ledger(self.m);l["as_of"]="2026-10-30";self.store.put_ledger(l)
        run=Engine(self.store,RuleProvider()).execute(self.m)
        ev=next(e for e in run["events"] if e["kind"]=="history_snapshot")
        self.assertEqual(ev["data"]["experiment_reviews"][0]["evaluation"]["status"],"target_only")
        self.assertTrue(any("试验评价" in json.dumps(e,ensure_ascii=False) for e in run["events"] if e["kind"]=="agent_result"))

    def test_real_future_results_rejected(self):
        t,d=self.study();l=deepcopy(d["data"]["ledger_snapshot"]);l["synthetic"]=False
        with patch("rebirth.research.date") as mocked:
            mocked.today.return_value=date(2026,10,25)
            with self.assertRaises(ValidationError):evaluate_design(d["data"],self.measurement(d),d["data"]["trial_snapshot"],l)

    def test_v04_migration_backup_and_completed_trial_design_rejected(self):
        t=self.trial();self.store.save_experiment(self.m,{**t,"status":"active","acknowledged":True})
        d=self.store.design_template(self.m,t["id"]);d.update(scope_confirmed=True,target_value="50.00",source_note="合成")
        with self.assertRaises(ValidationError):self.store.save_design(self.m,d)
        old=Path(self.tmp.name)/"old.sqlite3"
        with self.store.connect() as db:
            import sqlite3
            dest=sqlite3.connect(old);db.backup(dest);dest.close()
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(old)) as db:
            db.execute("DROP TABLE workbench_records");db.commit()
        Store(old)
        self.assertEqual(len(list((old.parent/"backups").glob("old-before-v05-*.sqlite3"))),1)


class WorkbenchApiTests(unittest.TestCase):
    request=test_core.ApiTests.request
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"api.sqlite3")
        self.handler=make_handler(self.store,"missing.json")
        self.request("/api/ledgers",test_core.ledger())
    def tearDown(self):self.tmp.cleanup()
    def test_workbench_asset_model_and_account_endpoints(self):
        self.assertTrue(self.request("/workbench.js",raw=True)[1])
        value=self.request("/api/merchants/sample_clothing/workbench")
        self.assertEqual(value["models"]["models"],[])
        self.request("/api/merchants/sample_clothing/models",{"models":[model()],"source_note":"合成"})
        self.assertEqual(len(self.request("/api/merchants/sample_clothing/workbench")["models"]["models"]),1)
        with self.assertRaises(urllib.error.HTTPError):self.request("/api/merchants/sample_clothing/accounts-import",{"kind":"cash_entries","csv":"bad"})
    def test_bad_ref_does_not_create_portfolio_or_bypass_cloud_guard(self):
        with self.assertRaises(urllib.error.HTTPError):self.request("/api/merchants/sample_clothing/portfolio",{"candidates":[{"run_id":"other","key":"c1"}]})
        self.assertEqual(self.store.records("sample_clothing","portfolio"),[])


if __name__=="__main__":unittest.main()

