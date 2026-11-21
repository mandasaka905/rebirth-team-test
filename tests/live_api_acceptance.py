"""Explicit localhost-only synthetic API acceptance; not browser/visual verification."""
import argparse
import json
from pathlib import Path
import time
import urllib.request
import urllib.error
from urllib.parse import urlsplit
from uuid import uuid4


def run(url):
    parsed=urlsplit(url)
    if parsed.scheme!="http" or parsed.hostname not in ("127.0.0.1","localhost") or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("验收脚本仅允许本机HTTP地址")
    def call(path,data=None,expected=200):
        body=json.dumps(data,ensure_ascii=False).encode() if data is not None else None
        req=urllib.request.Request(url.rstrip("/")+path,data=body,headers={"Content-Type":"application/json"} if body else {})
        try:
            with urllib.request.urlopen(req,timeout=10) as response:
                value=json.load(response)
                assert response.status==expected,(path,response.status,value)
                return value
        except urllib.error.HTTPError as exc:
            value=json.loads(exc.read())
            if exc.code!=expected:raise AssertionError((path,exc.code,value)) from None
            return value
    assert call("/health")["cloud_connected"] is False
    assert call("/api/preflight")["can_request_cloud"] is False
    ledger=call("/api/planning-example")
    merchant="apiqa_"+uuid4().hex[:12];ledger["merchant_id"]=merchant
    call("/api/ledgers",ledger,201);root="/api/merchants/"+merchant
    def analyze():
        started=call("/api/jobs",{"merchant_id":merchant,"mode":"rules","max_calls":64},202)
        deadline=time.monotonic()+45
        while True:
            job=call(root+"/jobs/"+started["job_id"])
            if job["state"]!="running":break
            if time.monotonic()>deadline:raise AssertionError("任务超时")
            time.sleep(.1)
        assert job["state"]=="completed",job
        return call(root+"/runs/"+job["run_id"])
    report=analyze();p=report["result"]["proposals"][0]["proposal"]
    assert p["model_refs"] and p["model_refs"][0]["version"]==1
    trial=call(root+"/experiments",{"run_id":report["run_id"],"proposal_id":p["id"],"proposal_version":p["version"],"hypothesis":"合成API验收","success_metric":"预先冻结后评价","end_date":"2026-11-01","stop_budget":report["result"]["proposals"][0]["evaluation"]["trial_cash_commitment"],"status":"planned","source_note":"合成，未实际开展","acknowledged":True},201)
    draft=next(d for d in report["result"]["experiment_drafts"] if d["proposal_id"]==p["id"])
    pending=call(root+"/workbench")
    link=next(l for l in pending["lineage"] if l["run_id"]==report["run_id"] and l["proposal_id"]==p["id"])
    assert draft["id"] in next(t for t in link["trials"] if t["id"]==trial["id"])["draft_ids"]
    preview=call(root+"/draft-preview",{"trial_id":trial["id"],"draft_id":draft["id"]},201)
    design=preview["design"]
    assert design["scope_confirmed"] is False
    call(root+"/design",design,400)
    design.update(scope_confirmed=True,observe_end="2026-11-01",source_note="人工确认的合成草案，低目标仅验证达标与改善的区别",target_value="50.00",
                  exit_rules=[{"id":"cash_guard","metric":"closing_cash","op":"lte","value":"3000.00","description":"合成结构化现金退出线"}])
    frozen=call(root+"/design",design,201)
    call(root+"/experiments",{**trial,"status":"active","acknowledged":True},201)
    obs={"design_id":frozen["id"],"end":"2026-11-01","revenue":"800.00","goods_cost":"500.00","expenses":"100.00",
         "visits":60,"buyers":20,"trial_spend":"100.00","closing_cash":"5000.00","scope_id":design["scope_id"],
         "count_basis":design["count_basis"],"source_note":"合成同口径汇总","change_reason":"首次合成观察","supersedes_id":None}
    first=call(root+"/measurement",obs,201)
    assert first["evaluation"]["status"]=="target_only"
    obs.update(supersedes_id=first["id"],revenue="8800.00",change_reason="合成更正，保留原记录")
    improved=call(root+"/measurement",obs,201)
    assert improved["evaluation"]["status"]=="target_met"
    call(root+"/measurement",{**obs,"supersedes_id":improved["id"],"scope_id":"other_scope"},400)
    obs.update(supersedes_id=improved["id"],closing_cash="2500.00",change_reason="验证结构化退出而非硬底线")
    stopped=call(root+"/measurement",obs,201)
    assert stopped["evaluation"]["status"]=="stop"
    assert stopped["evaluation"]["rule_hits"][0]["id"]=="cash_guard"
    models=call(root)["business_models"];models[0]["channel"]="合成新渠道"
    call(root+"/models",{"models":models,"source_note":"合成模式修订"},201)
    workbench=call(root+"/workbench")
    assert workbench["lineage"][0]["model_snapshots"][0]["version"]==1
    assert call(root)["business_models"][0]["version"]==2
    cohorts=call(root)["customer_cohorts"]
    for row in cohorts:row["base_size"]=120
    call(root+"/cohorts",{"cohorts":cohorts,"source_note":"应拒绝改分母"},400)
    call(root+"/experiments",{**trial,"status":"stopped","source_note":"合成验收停止投入","acknowledged":True},201)
    obs.update(supersedes_id=stopped["id"],revenue="8900.00",change_reason="停止后补齐最终核对，保持停止状态")
    final_observation=call(root+"/measurement",obs,201)
    assert next(t for t in call(root+"/experiments")["experiments"] if t["id"]==trial["id"])["status"]=="stopped"
    next_report=analyze()
    assert next_report["result"]["proposals"][0]["proposal"]["model_refs"][0]["version"]==2
    assert not next(e["data"]["experiment_reviews"] for e in next_report["events"] if e["kind"]=="history_snapshot")
    export=call(root+"/export")
    assert len([r for r in export["workbench_history"] if r["kind"]=="measurement"])==4
    return {"merchant_id":merchant,"mode":"rules","model_version_chain":[1,2],
            "draft_source":"rules, same contract as future AgentArts","human_confirmation_required":True,
            "evaluation_states":[first["evaluation"]["status"],improved["evaluation"]["status"],stopped["evaluation"]["status"]],
            "scope_mismatch_rejected":True,"cohort_denominator_change_rejected":True,
            "cohort_rates":[r["retention"] for r in workbench["cohorts"]["windows"]],
            "future_measurements_filtered":True,"measurement_history":4,"pending_trial_draft_link_verified":True,
            "stopped_trial_observation_saved_without_reactivation":True,"cloud_contacted":False,
            "browser_verified":False}


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",default="http://127.0.0.1:8767")
    parser.add_argument("--report")
    args=parser.parse_args()
    result=run(args.url)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.report:Path(args.report).write_text(text+"\n",encoding="utf-8")
    print(text)

