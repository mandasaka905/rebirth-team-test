from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rebirth.domain import ValidationError, money
from rebirth.engine import Engine
from rebirth.feedback import validate_feedback, summarize_feedback
from rebirth.providers import RuleProvider
from rebirth.readiness import questions
from rebirth.store import Store


ROOT = Path(__file__).resolve().parent.parent


def ledger():
    return json.loads((ROOT / "examples" / "merchant.synthetic.json").read_text(encoding="utf-8"))


class LocalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "test.sqlite3")
        self.store.put_ledger(ledger())

    def tearDown(self):
        self.tmp.cleanup()

    def run_local(self):
        # A local regression must fail immediately if any network call is attempted.
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network prohibited")):
            return Engine(self.store, RuleProvider()).execute("sample_clothing")

    def missing(self):
        l = ledger()
        l["products"][1]["unit_cost"] = None
        l["products"][1]["size_complete"] = None
        l["customer_signals"] = []
        l["completeness"]["obligations_complete"] = False
        self.store.put_ledger(l)
        return l

    def record(self, report, *, fixed="100.00", id="outcome1"):
        proposal = report["result"]["proposals"][0]["proposal"]
        raw = {"id": id, "run_id": report["run_id"], "proposal_id": proposal["id"],
               "proposal_version": proposal["version"], "period_start": "2026-10-24", "period_end": "2026-10-31",
               "synthetic": True, "source_note": "合成收支数据，仅用于本地回归测试", "fixed_spend": fixed,
               "hours_spent": 3, "costs_confirmed": True,
               "items": [{"sku": p["sku"], "units_sold": 2, "units_returned": 0,
                          "cash_received": str(money(p["price"])*2), "refund_paid": "0.00", "variable_spend": "10.00"}
                         for p in proposal["items"]], "observations": ["测试记录：部分受邀顾客时间不合适，尚不能判断原因。"]}
        return raw, proposal

    def test_normal_rules_do_not_manufacture_conflict(self):
        report = self.run_local()
        self.assertEqual(report["result"]["revision_rounds"], 0)
        self.assertEqual(len(report["result"]["proposals"]), 2)
        self.assertTrue(all(not p["evaluation"]["checks"] for p in report["result"]["proposals"]))
        self.assertFalse(any(e["kind"] == "proposal_revision" for e in report["events"]))

    def test_low_cash_does_not_produce_fictional_funded_plan(self):
        l = ledger()
        l["cash_balance"] = "1000.00"
        self.store.put_ledger(l)
        report = self.run_local()
        self.assertEqual(report["result"]["proposals"], [])

    def test_missing_demand_does_not_trigger_default_appointment_plan(self):
        l = ledger()
        l["customer_signals"] = []
        self.store.put_ledger(l)
        report = self.run_local()
        self.assertFalse(any(p["proposal"]["owner"] == "customer" for p in report["result"]["proposals"]))
        self.assertTrue(any(q["id"] == "customer_observation" for q in report["result"]["readiness"]["questions"]))

    def test_missing_evidence_questions_are_role_specific(self):
        l = self.missing()
        pending = {q["id"]: q for q in questions(l)["questions"]}
        self.assertEqual(pending["unit_cost_COAT_02"]["owner"], "inventory")
        self.assertEqual(pending["obligations_complete"]["owner"], "cash")
        self.assertEqual(pending["customer_observation"]["owner"], "customer")

    def test_answers_are_typed_sourced_and_leave_prior_snapshot_unchanged(self):
        self.missing()
        run, _ = self.store.new_run("sample_clothing", "rules")
        answer = self.store.answer("sample_clothing", [{"question_id": "unit_cost_COAT_02", "value": "81.50", "source_note": "商户核对采购单"}])
        self.assertEqual(self.store.ledger("sample_clothing")["products"][1]["unit_cost"], "81.50")
        self.assertNotIn("unit_cost_COAT_02", {q["id"] for q in answer["readiness"]["questions"]})
        snapshot = json.loads(self.store.check("sample_clothing", run)["snapshot"])
        self.assertIsNone(snapshot["products"][1]["unit_cost"])
        self.assertIn("products/COAT_02/unit_cost", self.store.ledger("sample_clothing")["field_sources"])

    def test_invalid_answer_batch_is_atomic(self):
        self.missing()
        with self.assertRaises(ValidationError):
            self.store.answer("sample_clothing", [
                {"question_id": "unit_cost_COAT_02", "value": "81.50", "source_note": "采购单"},
                {"question_id": "size_COAT_02", "value": "false", "source_note": "库存核对"}])
        self.assertIsNone(self.store.ledger("sample_clothing")["products"][1]["unit_cost"])

    def test_answers_cannot_demote_synthetic_flag_or_reanswer_stale_question(self):
        with self.assertRaises(ValidationError):
            self.store.answer("sample_clothing", [{"question_id": "synthetic", "value": False, "source_note": "fake"}])
        entry = {"question_id": "merchant_confirmation", "value": True, "source_note": "仅核对合成示例结构"}
        self.store.answer("sample_clothing", [entry])
        self.assertTrue(self.store.ledger("sample_clothing")["synthetic"])
        with self.assertRaises(ValidationError):
            self.store.answer("sample_clothing", [entry])

    def test_customer_observation_gets_own_source(self):
        self.missing()
        self.store.answer("sample_clothing", [{"question_id": "customer_observation", "value": "顾客询问下班后预约", "source_note": "店主访谈"}])
        l = self.store.ledger("sample_clothing")
        signal = l["customer_signals"][0]
        self.assertEqual(l["sources"][signal["source_id"]], "店主访谈")

    def test_feedback_cash_and_margin_are_separate(self):
        report = self.run_local()
        raw, p = self.record(report)
        summary = self.store.record_feedback("sample_clothing", raw)
        self.assertEqual(summary["net_cash_received"], "278.00")
        self.assertEqual(summary["trial_net_cash"], "168.00")
        self.assertEqual(summary["trial_margin_contribution"], "8.00")
        self.assertTrue(summary["synthetic"])
        self.assertTrue(any("合成反馈" in x for x in summary["unknowns"]))
        self.assertIn("不证明", summary["interpretation"])

    def test_feedback_does_not_rewrite_ledger(self):
        before = self.store.ledger("sample_clothing")
        report = self.run_local()
        raw, _ = self.record(report)
        self.store.record_feedback("sample_clothing", raw)
        self.assertEqual(before, self.store.ledger("sample_clothing"))

    def test_feedback_duplicate_cannot_double_count(self):
        report = self.run_local()
        raw, _ = self.record(report)
        self.store.record_feedback("sample_clothing", raw)
        for duplicate in (raw, {**raw, "id": "new_id"}):
            with self.subTest(duplicate=duplicate["id"]), self.assertRaises(ValidationError):
                self.store.record_feedback("sample_clothing", duplicate)
        self.assertEqual(len(self.store.feedback_history("sample_clothing")), 1)

    def test_feedback_rejects_old_version_and_cross_merchant(self):
        report = self.run_local()
        raw, _ = self.record(report)
        with self.assertRaises(ValidationError):
            self.store.record_feedback("sample_clothing", {**raw, "proposal_version": 99})
        with self.assertRaises(ValidationError):
            self.store.record_feedback("another_merchant", raw)

    def test_feedback_cannot_turn_synthetic_into_real(self):
        report = self.run_local()
        raw, _ = self.record(report)
        with self.assertRaises(ValidationError):
            self.store.record_feedback("sample_clothing", {**raw, "synthetic": False})

    def test_feedback_missing_row_is_not_zero_sales(self):
        report = self.run_local()
        raw, _ = self.record(report)
        raw["items"] = []
        with self.assertRaises(ValidationError):
            self.store.record_feedback("sample_clothing", raw)

    def test_feedback_refund_and_return_constraints(self):
        report = self.run_local()
        raw, _ = self.record(report)
        raw["items"][0]["units_returned"] = 3
        with self.assertRaises(ValidationError):
            self.store.record_feedback("sample_clothing", raw)
        raw["items"][0]["units_returned"] = 0
        raw["items"][0]["refund_paid"] = "9999.00"
        with self.assertRaises(ValidationError):
            self.store.record_feedback("sample_clothing", raw)

    def test_feedback_uses_original_snapshot_cost(self):
        report = self.run_local()
        raw, _ = self.record(report)
        l = ledger()
        l["products"][1]["unit_cost"] = "1000.00"
        self.store.put_ledger(l)
        summary = self.store.record_feedback("sample_clothing", raw)
        self.assertEqual(summary["trial_margin_contribution"], "8.00")

    def test_future_feedback_is_not_available_in_earlier_analysis(self):
        report = self.run_local()
        raw, _ = self.record(report)
        self.store.record_feedback("sample_clothing", raw)
        again = self.run_local()
        history_events = [e for e in again["events"] if e["kind"] == "history_snapshot"]
        self.assertEqual(history_events[0]["data"]["outcomes"], [])
        self.assertEqual(self.store.feedback_history("another_merchant"), [])

    def test_valid_history_informs_followup_without_automatic_learning(self):
        report = self.run_local()
        raw, p = self.record(report, fixed="1000.00")
        self.store.record_feedback("sample_clothing", raw)
        l = ledger()
        l["as_of"] = "2026-11-01"
        self.store.put_ledger(l)
        again = self.run_local()
        self.assertFalse(any(x["proposal"]["owner"] == p["owner"] for x in again["result"]["proposals"]))
        self.assertTrue(again["result"]["investigations"]["cash"]["historical_followups"])
        ev = next(e for e in again["events"] if e["kind"] == "history_snapshot")
        self.assertEqual(len(ev["data"]["outcomes"]), 1)

    def test_history_synthetic_filter(self):
        report = self.run_local()
        raw, _ = self.record(report)
        self.store.record_feedback("sample_clothing", raw)
        self.assertEqual(self.store.feedback_history("sample_clothing", synthetic=False), [])

    def test_returns_require_resellable_condition_and_keep_damage_cost(self):
        report = self.run_local()
        raw, p = self.record(report)
        item = raw["items"][0]
        item["units_returned"] = 1
        item["refund_paid"] = "139.00"
        with self.assertRaises(ValidationError):
            self.store.record_feedback("sample_clothing", raw)
        item["units_returned_resellable"] = 0
        summary = self.store.record_feedback("sample_clothing", raw)
        self.assertEqual(summary["trial_margin_contribution"], "-131.00")

    def test_partial_period_cannot_hide_upfront_spend(self):
        report = self.run_local()
        raw, _ = self.record(report)
        raw["period_start"] = "2026-10-25"
        with self.assertRaises(ValidationError):
            self.store.record_feedback("sample_clothing", raw)


if __name__ == "__main__":
    unittest.main()
