from copy import deepcopy
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from rebirth.domain import ValidationError, day, money, validate_ledger
from rebirth.engine import Engine
from rebirth.providers import AgentArtsProvider, ProviderError, RuleProvider, decode_response
from rebirth.server import make_handler
from rebirth.store import Store
from rebirth.tools import cash_baseline, evaluate


ROOT = Path(__file__).resolve().parent.parent


def ledger():
    return json.loads((ROOT / "examples" / "merchant.synthetic.json").read_text(encoding="utf-8"))


def proposal():
    p = json.loads((ROOT / "config" / "contracts.json").read_text(encoding="utf-8"))["proposal_example"]
    p["evidence_ids"] = ["e1"]
    return p


class FinancialTests(unittest.TestCase):
    def test_budget_ceiling(self):
        self.assertEqual(cash_baseline(ledger(), {})["conservative_budget_ceiling"], "2000.00")

    def test_no_double_count_existing_stock(self):
        r = evaluate(ledger(), {"proposal": proposal()})
        self.assertEqual(r["known_stock_cost"], "400.00")
        self.assertEqual(r["gross_profit_after_declared_trial_costs"], "-205.00")
        self.assertEqual(r["incremental_cash_under_declared_sales"], "195.00")
        self.assertEqual(r["scenarios"][0]["ending_cash"], "3500.00")

    def test_expensive_trial_rejected_even_when_future_sales_look_good(self):
        p = proposal()
        p["upfront_cost"] = "3000.00"
        p["items"][0]["price"] = "99999.00"
        codes = {c["code"] for c in evaluate(ledger(), {"proposal": p})["checks"]}
        self.assertIn("BUDGET_EXCEEDED", codes)
        self.assertIn("CASH_RESERVE_BREACH_ZERO_SALES", codes)

    def test_same_day_outflows_precede_receipts(self):
        l = ledger()
        l["cash_balance"] = "1000.00"
        l["reserve_floor"] = "0.00"
        l["obligations"][0].update(date=l["as_of"], amount="2000.00")
        l["receivables"] = [{"id": "invoice", "date": l["as_of"], "amount": "5000.00", "source_id": "cash_fixture"}]
        p = proposal()
        p["upfront_cost"] = "0.00"
        r = evaluate(l, {"proposal": p})
        self.assertEqual(r["scenarios"][0]["first_reserve_breach"], l["as_of"])
        self.assertEqual(r["scenarios"][0]["minimum_cash_before_receipts"], "-1000.00")

    def test_overdue_payable_is_not_ignored(self):
        l = ledger()
        l["obligations"][0]["date"] = "2026-10-01"
        p = proposal()
        self.assertEqual(evaluate(l, {"proposal": p})["scenarios"][0]["ending_cash"], "3500.00")

    def test_missing_cost_stays_unknown_not_zero(self):
        l = ledger()
        l["products"][1]["unit_cost"] = None
        r = evaluate(l, {"proposal": proposal()})
        self.assertIsNone(r["gross_profit_after_declared_trial_costs"])
        self.assertFalse(r["eligible_for_merchant_review"])

    def test_missing_records_do_not_imply_complete(self):
        l = ledger()
        l["completeness"]["obligations_complete"] = False
        self.assertTrue(any("obligations_complete" in x for x in evaluate(l, {"proposal": proposal()})["unknowns"]))

    def test_stock_and_workload_checked(self):
        p = proposal()
        p["items"][0]["quantity"] = 100
        p["weekly_hours"] = 100
        codes = {c["code"] for c in evaluate(ledger(), {"proposal": p})["checks"]}
        self.assertTrue({"STOCK_EXCEEDED", "WORKLOAD_EXCEEDED"} <= codes)

    def test_fractional_cents_are_avoided_in_half_sales(self):
        p = proposal()
        p["items"][0].update(quantity=1, price="0.01", variable_cash_cost="0.01")
        r = evaluate(ledger(), {"proposal": p})
        self.assertEqual(r["scenarios"][1]["ending_cash"], "3500.00")

    def test_variable_costs_count_toward_trial_budget(self):
        p = proposal()
        p["items"][0]["variable_cash_cost"] = "400.00"
        self.assertIn("BUDGET_EXCEEDED", {c["code"] for c in evaluate(ledger(), {"proposal": p})["checks"]})

    def test_future_overdue_receivables_not_credited(self):
        l = ledger()
        l["receivables"] = [{"id": "late", "date": "2026-10-01", "amount": "99999.00", "source_id": "cash_fixture"}]
        r = evaluate(l, {"proposal": proposal()})
        self.assertEqual(r["scenarios"][0]["ending_cash"], "3500.00")
        self.assertTrue(any("逾期应收" in x for x in r["unknowns"]))

    def test_no_double_sku_and_no_float_or_nonfinite_money(self):
        p = proposal()
        p["items"].append(deepcopy(p["items"][0]))
        with self.assertRaises(ValidationError):
            evaluate(ledger(), {"proposal": p})
        for value in (True, 0.1, "NaN", "Infinity", "1.001", "-1"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                money(value)

    def test_temporal_validation(self):
        p = proposal()
        p["items"][0]["receipt_date"] = "2026-10-01"
        with self.assertRaises(ValidationError):
            evaluate(ledger(), {"proposal": p})

    def test_duplicate_source_records_rejected(self):
        l = ledger()
        l["obligations"].append(deepcopy(l["obligations"][0]))
        with self.assertRaises(ValidationError):
            validate_ledger(l)


class CollaborationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "test.sqlite3")
        self.store.put_ledger(ledger())

    def tearDown(self):
        self.tmp.cleanup()

    def test_end_to_end_revision_is_data_driven_and_evidenced(self):
        class FaultFixture(RuleProvider):
            """Deliberate invalid proposal for the regression test, not app behavior."""
            def step(self, context):
                action = super().step(context)
                if context["role"] == "customer" and context["phase"] == "propose":
                    proposals = action.get("result", {}).get("proposals", [])
                    if action.get("name") == "proposal_evaluate":
                        proposals = [action["arguments"]["proposal"]]
                    for p in proposals:
                        p["upfront_cost"] = "3000.00"
                        p["items"][0]["sku"] = "TOP_01"
                return action
        report = Engine(self.store, FaultFixture()).execute("sample_clothing")
        self.assertEqual(report["status"], "rehearsal_only")
        self.assertEqual(report["result"]["revision_rounds"], 1)
        revisions = [e for e in report["events"] if e["kind"] == "proposal_revision"]
        self.assertEqual(len(revisions), 1)
        r = revisions[0]["data"]
        self.assertEqual(r["before"]["upfront_cost"], "3000.00")
        self.assertEqual(r["after"]["upfront_cost"], "500.00")
        self.assertNotIn("TOP_01", {i["sku"] for i in r["after"]["items"]})
        self.assertTrue(r["review_refs"][0]["objections"])
        self.assertTrue(all(not p["evaluation"]["checks"] for p in report["result"]["proposals"]))
        for role in ("inventory", "customer", "cash"):
            self.assertTrue(any(e["actor"] == role and e["kind"] == "tool_result" for e in report["events"]))

    def test_merchant_isolation(self):
        run, _ = self.store.new_run("sample_clothing", "rules")
        with self.assertRaises(ValidationError):
            self.store.result("another_merchant", run)
        with self.assertRaises(ValidationError):
            self.store.event("another_merchant", run, "cash", "tool_result", {})

    def test_ledger_snapshot_does_not_change_midrun(self):
        run, snapshot = self.store.new_run("sample_clothing", "rules")
        l = ledger()
        l["cash_balance"] = "1.00"
        self.store.put_ledger(l)
        self.assertEqual(snapshot["cash_balance"], "12000.00")
        self.assertEqual(json.loads(self.store.check("sample_clothing", run)["snapshot"])["cash_balance"], "12000.00")

    def test_fake_evidence_rejected(self):
        run, _ = self.store.new_run("sample_clothing", "rules")
        p = proposal()
        p["evidence_ids"] = ["e9999"]
        with self.assertRaises(ValidationError):
            Engine(self.store, RuleProvider()).validate_result("sample_clothing", run, "customer", "propose", {"proposals": [p]}, [])

    def test_stale_proposal_review_rejected(self):
        run, _ = self.store.new_run("sample_clothing", "rules")
        ev = self.store.event("sample_clothing", run, "cash", "tool_result", {})
        obj = {"proposal_id": "customer_trial", "version": 1, "reason": "test", "request": "test", "evidence_ids": [ev]}
        p = proposal()
        p["version"] = 2
        with self.assertRaises(ValidationError):
            Engine(self.store, RuleProvider()).validate_result("sample_clothing", run, "cash", "review", {"objections": [obj]}, [p])

    def test_unbounded_tool_calls_fail_and_leave_audit(self):
        class LoopProvider:
            mode = "test"
            def step(self, context):
                return {"action": "tool", "name": "cash_baseline", "arguments": {}}
        with self.assertRaises(ProviderError):
            Engine(self.store, LoopProvider(), max_steps=2).execute("sample_clothing")
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM runs").fetchone()[0], "failed")

    def test_cloud_failure_cannot_turn_into_success(self):
        class FailProvider:
            mode = "agentarts"
            def step(self, context):
                raise ProviderError("offline")
        with self.assertRaises(ProviderError):
            Engine(self.store, FailProvider()).execute("sample_clothing")
        with self.store.connect() as db:
            row = db.execute("SELECT status, mode FROM runs").fetchone()
        self.assertEqual(tuple(row), ("failed", "agentarts"))


class AdapterTests(unittest.TestCase):
    def test_direct_json(self):
        action = {"action": "final", "result": {"notes": []}}
        self.assertEqual(decode_response(json.dumps(action).encode(), "application/json"), action)

    def test_nested_end_json(self):
        action = {"action": "tool", "name": "cash_baseline", "arguments": {}}
        payload = {"event": "message", "data": {"node_type": "End", "text": json.dumps(action)}}
        self.assertEqual(decode_response(json.dumps(payload).encode(), "application/json"), action)

    def test_sse_incremental_legacy(self):
        action = '{"action":"final","result":{}}'
        raw = "".join("data:"+json.dumps({"event": "message", "content": s})+"\n\n" for s in [action[:12], action[12:]])
        self.assertEqual(decode_response(raw.encode(), "text/event-stream")["action"], "final")

    def test_sse_end_takes_priority_over_intermediate(self):
        action = '{"action":"final","result":{"notes":["end"]}}'
        events = [{"event": "message", "content": "untrusted intermediate"},
                  {"event": "message", "data": {"node_type": "End", "text": action}}]
        raw = "".join("data:"+json.dumps(e)+"\n\n" for e in events)
        self.assertEqual(decode_response(raw.encode(), "text/event-stream")["result"]["notes"], ["end"])

    def test_plain_prose_rejected(self):
        with self.assertRaises(ProviderError):
            decode_response(b'{"content":"everything is good"}', "application/json")

    def test_missing_cloud_config_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ProviderError):
            AgentArtsProvider(ROOT / "config" / "agentarts.example.json")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "api.sqlite3")
        self.handler = make_handler(self.store, "missing.json")

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, path, data=None, headers=None, raw=False):
        # Feed actual HTTP bytes into BaseHTTPRequestHandler without an OS socket.
        # This exercises routing/headers/serialization under a network-restricted sandbox.
        body = json.dumps(data).encode() if data is not None else b""
        h = {"Host": "127.0.0.1:8765", "Content-Type": "application/json", "Content-Length": str(len(body)), **(headers or {})}
        head = ("POST" if data is not None else "GET")+" "+path+" HTTP/1.0\r\n"
        head += "".join(k+": "+v+"\r\n" for k, v in h.items())+"\r\n"
        class Transport:
            def __init__(self):
                self.output = bytearray()
            def makefile(self, mode, *args):
                return BytesIO(head.encode()+body)
            def sendall(self, value):
                self.output.extend(value)
        transport = Transport()
        self.handler(transport, ("127.0.0.1", 1), SimpleNamespace(server_port=8765))
        response_head, response_body = bytes(transport.output).split(b"\r\n\r\n", 1)
        status = int(response_head.split(b" ")[1])
        if status >= 400:
            raise urllib.error.HTTPError(path, status, "test", {}, None)
        if raw:
            return response_head, response_body
        return json.loads(response_body)

    def test_import_then_tool_api(self):
        self.request("/api/ledgers", ledger())
        r = self.request("/api/tools/sample_clothing/cash_baseline", {})
        self.assertEqual(r["conservative_budget_ceiling"], "2000.00")

    def test_cross_origin_access_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.request("/health", headers={"Origin": "https://untrusted.example"})
        self.assertEqual(cm.exception.code, 403)

    def test_mode_cannot_be_implicit(self):
        self.request("/api/ledgers", ledger())
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.request("/api/runs", {"merchant_id": "sample_clothing"})
        self.assertEqual(cm.exception.code, 400)

    def test_cloud_calls_are_disabled_by_default(self):
        self.request("/api/ledgers", ledger())
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.request("/api/runs", {"merchant_id": "sample_clothing", "mode": "agentarts"})
        self.assertEqual(cm.exception.code, 403)

    def test_question_and_answer_routes(self):
        self.request("/api/ledgers", ledger())
        pending = self.request("/api/merchants/sample_clothing/questions")
        self.assertTrue(any(q["id"] == "merchant_confirmation" for q in pending["questions"]))
        response = self.request("/api/merchants/sample_clothing/answers", {"answers": [
            {"question_id": "merchant_confirmation", "value": True, "source_note": "确认合成示例结构"}]})
        self.assertEqual(len(response["accepted"]), 1)

    def test_local_page_and_assets_are_served_with_security_headers(self):
        head, html = self.request("/", raw=True)
        self.assertIn(b"Content-Security-Policy:", head)
        self.assertIn(b"text/html", head)
        self.assertIn(b'id="ledger-form"', html)
        self.assertIn(b'src="/core.js"', html)
        for path, kind in (("/app.css", b"text/css"), ("/app.js", b"javascript"),
                           ("/core.js", b"javascript"), ("/favicon.svg", b"image/svg+xml")):
            headers, body = self.request(path, raw=True)
            self.assertIn(kind, headers)
            self.assertTrue(body)

    def test_static_allowlist_cannot_read_source_or_secrets(self):
        for path in ("/../rebirth/store.py", "/config.local.json", "/.env", "/index.html/../server.py"):
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as cm:
                self.request(path)
            self.assertEqual(cm.exception.code, 404)

    def test_browser_workflow_uses_persisted_backend_data(self):
        self.assertEqual(self.request("/api/merchants")["merchants"], [])
        sample = self.request("/api/example")
        self.request("/api/ledgers", sample)
        merchant = sample["merchant_id"]
        self.assertEqual(self.request("/api/merchants/"+merchant)["cash_balance"], "12000.00")
        self.assertEqual(len(self.request("/api/merchants")["merchants"]), 1)
        report = self.request("/api/runs", {"merchant_id": merchant, "mode": "rules"})
        self.assertEqual(report["mode"], "rules")
        self.assertFalse(report["ledger_changed"])
        history = self.request(f"/api/merchants/{merchant}/runs")["runs"]
        self.assertEqual(history[0]["id"], report["run_id"])
        self.request(f"/api/merchants/{merchant}/answers", {"answers": [{
            "question_id": "merchant_confirmation", "value": True, "source_note": "确认合成示例结构"}]})
        stale = self.request(f"/api/merchants/{merchant}/runs/{report['run_id']}")
        self.assertTrue(stale["ledger_changed"])
        self.assertEqual(stale["events"], report["events"])


if __name__ == "__main__":
    unittest.main()
