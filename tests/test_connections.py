import json
import tempfile
import unittest
from pathlib import Path
from copy import deepcopy
from rebirth.store import Store
from rebirth.domain import ValidationError, validate_proposal, validate_ledger
from rebirth.providers import RuleProvider, SimulationProvider
from rebirth.engine import Engine
from rebirth.linkage import resolve
from rebirth.experiment_drafts import validate_draft
from rebirth.research import evaluate_design, validate_design
from rebirth.cohorts import analyze_cohorts
from rebirth.server import make_handler
import test_core
from test_workbench import model

ROOT=Path(__file__).resolve().parent.parent


def cohort(i="a", start="2026-09-01", end="2026-09-30", retained=60):
    return {"id":i,"cohort_id":"fixed_aug","label":"合成八月固定客群","definition":"八月购买过的固定去重客群；不收集个人ID",
            "baseline_start":"2026-08-01","baseline_end":"2026-08-31","base_size":100,"start":start,"end":end,
            "retained":retained,"membership_confirmed":True,"observation_complete":True,"source_note":"合成汇总"}


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"db.sqlite3")
        self.ledger=json.loads((ROOT/"examples/planning.synthetic.json").read_text(encoding="utf-8"))
        self.m=self.ledger["merchant_id"];self.store.put_ledger(self.ledger)
    def tearDown(self):self.tmp.cleanup()

    def run_local(self,provider=None):
        return Engine(self.store,provider or RuleProvider()).execute(self.m)

    def trial(self,report=None):
        r=report or self.run_local();p=r["result"]["proposals"][0]["proposal"]
        return self.store.save_experiment(self.m,{"run_id":r["run_id"],"proposal_id":p["id"],"proposal_version":p["version"],"hypothesis":"合成假设","success_metric":"同口径","end_date":"2026-11-01","stop_budget":"500.00","status":"planned","source_note":"合成","acknowledged":True})

    def design(self):
        t=self.trial();d=self.store.design_template(self.m,t["id"])
        d.update(scope_confirmed=True,target_value="50.00",source_note="合成预注册",min_days=2,min_visits=2)
        return t,d

    def measure(self,d,**updates):
        return {"end":"2026-11-01","revenue":"800.00","goods_cost":"500.00","expenses":"100.00","visits":20,"buyers":5,
                "trial_spend":"100.00","closing_cash":"5000.00","source_note":"合成","scope_id":d["scope_id"],"count_basis":d["count_basis"],**updates}

    def test_models_version_on_change_and_stale_write_rejected(self):
        before=self.store.ledger(self.m)["business_models"]
        changed=deepcopy(before);changed[0]["channel"]="合成渠道修订"
        self.store.save_section(self.m,"business_models",changed,"合成")
        after=self.store.ledger(self.m)["business_models"]
        self.assertEqual(after[0]["version"],2);self.assertEqual(after[1]["version"],1)
        with self.assertRaises(ValidationError):self.store.save_section(self.m,"business_models",changed,"过期页面")
        self.store.save_section(self.m,"business_models",after,"无字段变化核对")
        self.assertEqual(self.store.ledger(self.m)["business_models"][0]["version"],2)

    def test_put_ledger_also_versions_models(self):
        l=self.store.ledger(self.m);l["business_models"][0]["value_proposition"]="新价值假设"
        saved=self.store.put_ledger(l)
        self.assertEqual(saved["business_models"][0]["version"],2)

    def test_period_comparison_rejects_different_scope_or_count_basis(self):
        from rebirth.business import diagnostics
        baseline=deepcopy(self.ledger)
        self.assertTrue(diagnostics(baseline)["findings"])
        for field,value in (("scope_id","sku_only"),("count_basis","unique_people")):
            ledger=deepcopy(baseline);ledger["operating_periods"][-1][field]=value
            report=diagnostics(ledger)
            self.assertEqual(report["comparison_status"],"scope_mismatch")
            self.assertEqual(report["findings"],[])
            self.assertEqual(len(report["periods"]),len(ledger["operating_periods"]))
            self.assertIn("不输出升降比较",report["note"])

    def test_lineage_exposes_drafts_under_their_exact_trial(self):
        r=self.run_local();t=self.trial(r)
        link=next(l for l in self.store.workbench(self.m)["lineage"] if l["run_id"]==t["run_id"] and l["proposal_id"]==t["proposal_id"])
        trial=next(x for x in link["trials"] if x["id"]==t["id"])
        expected=[d["id"] for d in r["result"]["experiment_drafts"] if d["proposal_id"]==t["proposal_id"] and d["proposal_version"]==t["proposal_version"]]
        self.assertTrue(expected);self.assertEqual(trial["draft_ids"],expected)

    def test_stopped_trial_accepts_final_observation_and_correction_without_reactivation(self):
        t,d=self.design();saved=self.store.save_design(self.m,d)
        self.store.save_experiment(self.m,{**t,"status":"active","acknowledged":True})
        self.store.save_experiment(self.m,{**t,"status":"stopped","source_note":"人工停止新增投入","acknowledged":True})
        m={**self.measure(d),"design_id":saved["id"],"change_reason":"停止后补齐实际记录","supersedes_id":None}
        first=self.store.save_measurement(self.m,m)
        correction=self.store.save_measurement(self.m,{**m,"revenue":"900.00","supersedes_id":first["id"],"change_reason":"原单核对更正"})
        self.assertNotEqual(first["id"],correction["id"])
        self.assertEqual(len(self.store.records(self.m,"measurement")),2)
        self.assertEqual(self.store.experiments(self.m)[0]["status"],"stopped")

    def test_rules_bind_modes_and_trials_freeze_actual_model_snapshot(self):
        r=self.run_local();p=r["result"]["proposals"][0]["proposal"]
        self.assertTrue(p["model_refs"])
        t=self.trial(r);self.assertEqual(t["model_refs"],p["model_refs"])
        self.assertEqual(t["model_snapshots"][0]["version"],1)
        l=self.store.ledger(self.m);models=l["business_models"];models[0]["channel"]="后来修改"
        self.store.save_section(self.m,"business_models",models,"合成")
        frozen=self.store.experiments(self.m)[0]["model_snapshots"][0]
        self.assertNotEqual(frozen["channel"],"后来修改")
        self.assertEqual(self.store.lineage(self.m)[0]["model_snapshots"][0]["version"],1)

    def test_missing_wrong_or_duplicate_model_refs_rejected(self):
        p=self.run_local()["result"]["proposals"][0]["proposal"];l=self.store.ledger(self.m)
        for refs in ([],[{"id":"other","version":1}],[{"id":p["model_refs"][0]["id"],"version":99}],p["model_refs"]*2):
            with self.assertRaises(ValidationError):resolve(l,{**p,"model_refs":refs})

    def test_manual_model_binding_and_positive_version_required(self):
        r=self.run_local();p=deepcopy(r["result"]["proposals"][0]["proposal"]);p["version"]+=1
        p["model_refs"]=[]
        with self.assertRaises(ValidationError):Engine(self.store,RuleProvider()).execute(self.m,draft=p,parent_run=r["run_id"])
        for version in (0,True,-1):
            with self.assertRaises(ValidationError):validate_proposal({**p,"version":version})

    def test_rule_draft_preview_uses_same_contract_and_requires_human_confirmation(self):
        r=self.run_local();self.assertTrue(r["result"]["experiment_drafts"])
        t=self.trial(r);draft=next(d for d in r["result"]["experiment_drafts"] if d["proposal_id"]==t["proposal_id"])
        preview=self.store.draft_preview(self.m,t["id"],draft["id"])
        self.assertFalse(preview["design"]["scope_confirmed"])
        self.assertEqual(self.store.records(self.m,"design"),[])
        with self.assertRaises(ValidationError):self.store.save_design(self.m,preview["design"])
        d=preview["design"];d.update(scope_confirmed=True,source_note="商户核对合成草案",target_value="1200.00")
        saved=self.store.save_design(self.m,d)
        self.assertEqual(saved["data"]["draft_original"]["id"],draft["id"])
        self.assertIn("target_value",saved["data"]["draft_changes"])
        self.assertEqual(saved["data"]["draft_source_mode"],"rules")

    def test_simulation_draft_is_labeled_non_ai_and_actual_version_only(self):
        r=self.run_local(SimulationProvider("normal"))
        self.assertEqual(r["mode"],"simulation")
        self.assertTrue(r["result"]["experiment_drafts"])
        self.assertTrue(all(any(p["proposal"]["id"]==d["proposal_id"] and p["proposal"]["version"]==d["proposal_version"] for p in r["result"]["proposals"]) for d in r["result"]["experiment_drafts"]))

    def test_invalid_draft_cannot_invent_baseline_or_cross_owner(self):
        r=self.run_local();d=deepcopy(r["result"]["experiment_drafts"][0]);p=next(x["proposal"] for x in r["result"]["proposals"] if x["proposal"]["id"]==d["proposal_id"])
        for modify in ({"baseline_period_id":"made_up"},{"proposal_version":99},{"owner":"cash"}):
            with self.assertRaises(ValidationError):validate_draft({**d,**modify},p,r["ledger_snapshot"])
        d["design"]["baseline"]["revenue"]="999999.00"
        normalized=validate_draft(d,p,r["ledger_snapshot"])
        original=next(x for x in r["ledger_snapshot"]["operating_periods"] if x["id"]==d["baseline_period_id"])
        self.assertEqual(normalized["design"]["baseline"]["revenue"],original["revenue"])

    def test_engine_validates_draft_tool_evidence(self):
        class Forged(RuleProvider):
            def step(self,c):
                action=super().step(c)
                if action.get("action")=="final":
                    for d in action["result"].get("experiment_drafts",[]):d["evidence_ids"]=["fabricated"]
                return action
        with self.assertRaises(ValidationError):self.run_local(Forged())

    def test_draft_cannot_relabel_whole_shop_baseline_as_sku_scope(self):
        r=self.run_local();d=deepcopy(r["result"]["experiment_drafts"][0]);p=next(x["proposal"] for x in r["result"]["proposals"] if x["proposal"]["id"]==d["proposal_id"])
        d["design"]["scope_id"]="sku_only"
        with self.assertRaises(ValidationError):validate_draft(d,p,r["ledger_snapshot"])

    def test_put_ledger_cannot_bypass_fixed_cohort_denominator(self):
        l=self.store.ledger(self.m);l["customer_cohorts"][0]["base_size"]=120;l["customer_cohorts"][1]["base_size"]=120
        with self.assertRaises(ValidationError):self.store.put_ledger(l)

    def test_target_met_but_worse_is_not_improvement(self):
        t,d=self.design();p={**t,"spend_date":d["observe_start"]}
        r=evaluate_design(d,self.measure(d),p,self.store.ledger(self.m))
        self.assertEqual(r["status"],"target_only");self.assertTrue(r["target_met"]);self.assertEqual(r["baseline_relation"],"worse")
        d["target_value"]="1100.00"
        r=evaluate_design(d,self.measure(d,revenue="8800.00"),p,self.store.ledger(self.m))
        self.assertEqual(r["status"],"target_met");self.assertEqual(r["baseline_relation"],"improved")

    def test_improved_but_target_not_met_and_unchanged_baseline(self):
        t,d=self.design();p={**t,"spend_date":d["observe_start"]};d["target_value"]="1200.00"
        r=evaluate_design(d,self.measure(d,revenue="8800.00"),p,self.store.ledger(self.m))
        self.assertEqual(r["status"],"revise");self.assertEqual(r["baseline_relation"],"improved")
        d["target_value"]="50.00"
        r=evaluate_design(d,self.measure(d,revenue="8400.00"),p,self.store.ledger(self.m))
        self.assertEqual(r["status"],"target_only");self.assertEqual(r["baseline_relation"],"unchanged")

    def test_scope_or_count_mismatch_and_unconfirmed_design_rejected(self):
        t,d=self.design();p={**t,"spend_date":d["observe_start"]}
        for m in (self.measure(d,scope_id="sku_group"),self.measure(d,count_basis="unique_people")):
            with self.assertRaises(ValidationError):evaluate_design(d,m,p,self.store.ledger(self.m))
        with self.assertRaises(ValidationError):validate_design({**d,"scope_confirmed":False},p,self.store.ledger(self.m))
        d["baseline"]["scope_id"]="other"
        with self.assertRaises(ValidationError):validate_design(d,p,self.store.ledger(self.m))

    def test_negative_contribution_target_supports_loss_reduction(self):
        t,d=self.design();d.update(metric="contribution_per_day",target_value="-25.00")
        p={**t,"spend_date":d["observe_start"]};l=self.store.ledger(self.m)
        validate_design(d,p,l)
        r=evaluate_design(d,self.measure(d,revenue="100.00",goods_cost="200.00",expenses="20.00"),p,l)
        self.assertEqual(r["status"],"target_met") # -15/day versus baseline -50/day, target -25
        d["metric"]="revenue_per_day"
        with self.assertRaises(ValidationError):validate_design(d,p,l)

    def test_structured_exit_and_hard_budget_cannot_be_relaxed(self):
        t,d=self.design();p={**t,"spend_date":d["observe_start"]};l=self.store.ledger(self.m)
        d["exit_rules"]=[{"id":"profit_floor","metric":"contribution_per_day","op":"lte","value":"30.00","description":"同口径贡献低于阈值退出"}]
        validate_design(d,p,l)
        r=evaluate_design(d,self.measure(d),p,l)
        self.assertEqual(r["status"],"stop");self.assertEqual(r["rule_hits"][0]["id"],"profit_floor")
        r=evaluate_design(d,self.measure(d,trial_spend="500.00"),p,l)
        self.assertEqual(r["status"],"stop")
        d["exit_rules"][0]["op"]="python"
        with self.assertRaises(ValidationError):validate_design(d,p,l)

    def test_legacy_scope_is_readable_but_no_improvement_claim(self):
        t,d=self.design();d.pop("scope_id")
        r=evaluate_design(d,self.measure({**d,"scope_id":"shop_all"}),{**t,"spend_date":d["observe_start"]},self.store.ledger(self.m))
        self.assertEqual(r["status"],"incomparable");self.assertEqual(r["baseline_relation"],"unknown")

    def test_fixed_cohort_rate_and_unpurchased_counts(self):
        rows=[cohort(),cohort("b","2026-10-01","2026-10-30",40)]
        l={**self.ledger,"as_of":"2026-10-30","customer_cohorts":rows}
        validate_ledger(l);r=analyze_cohorts(l)
        self.assertEqual(r["windows"][0]["retention"],"0.6000")
        self.assertEqual(r["windows"][1]["not_repeated"],60)
        self.assertEqual(r["findings"][0]["kind"],"decline")

    def test_unknown_cohort_not_zero_and_different_window_not_compared(self):
        a=cohort();a.update(observation_complete=False,retained=None)
        l={**self.ledger,"customer_cohorts":[a,cohort("b","2026-10-01","2026-10-20",40)]}
        validate_ledger(l);r=analyze_cohorts(l)
        self.assertIsNone(r["windows"][0]["not_repeated_rate"])
        self.assertEqual(r["findings"][0]["kind"],"incomparable")

    def test_cohort_denominator_definition_future_overlap_and_bounds_rejected(self):
        a=cohort()
        for b in ({**cohort("b","2026-10-01","2026-10-20",40),"base_size":120},
                  cohort("b","2026-09-20","2026-10-20",40),
                  cohort("b","2026-10-01","2026-11-01",40),
                  cohort("b","2026-10-01","2026-10-20",101)):
            with self.assertRaises(ValidationError):validate_ledger({**self.ledger,"customer_cohorts":[a,b]})
        self.store.save_section(self.m,"customer_cohorts",[a],"合成")
        with self.assertRaises(ValidationError):self.store.save_section(self.m,"customer_cohorts",[{**a,"base_size":120}],"不能改原分母")

    def test_cohorts_flow_into_customer_investigation_and_old_snapshot_unchanged(self):
        l=self.store.ledger(self.m);l["as_of"]="2026-10-30"
        l["customer_cohorts"]=[cohort(),cohort("b","2026-10-01","2026-10-30",40)]
        self.store.put_ledger(l);r=self.run_local()
        findings=r["result"]["investigations"]["customer"]["findings"]
        self.assertTrue(any("固定客群" in f["statement"] for f in findings))
        rows=deepcopy(l["customer_cohorts"]);rows[1]["retained"]=50
        self.store.save_section(self.m,"customer_cohorts",rows,"合成更正")
        old=self.store.result(self.m,r["run_id"])
        self.assertTrue(old["ledger_changed"])
        self.assertEqual(old["ledger_snapshot"]["customer_cohorts"][1]["retained"],40)


class ConnectionApiTests(unittest.TestCase):
    request=test_core.ApiTests.request
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"api.sqlite3")
        self.handler=make_handler(self.store,"missing.json")
        self.request("/api/ledgers",test_core.ledger())
    def tearDown(self):self.tmp.cleanup()
    def test_asset_and_cohort_route(self):
        self.assertTrue(self.request("/connections.js",raw=True)[1])
        result=self.request("/api/merchants/sample_clothing/cohorts",{"cohorts":[cohort()],"source_note":"合成"})
        self.assertEqual(result["cohorts"]["windows"][0]["retention"],"0.6000")
        self.assertFalse(self.request("/api/preflight")["can_request_cloud"])


if __name__=="__main__":unittest.main()

