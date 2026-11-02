import argparse
import json
from pathlib import Path
import sys

from .domain import ValidationError
from .engine import Engine
from .providers import AgentArtsProvider, ProviderError, RuleProvider
from .store import Store


ROOT = Path(__file__).resolve().parent.parent


def compact(result):
    """Full audit and daily cash remain available through inspect --full."""
    view = {k: v for k, v in result.items() if k != "events"}
    if view.get("result") and "proposals" in view["result"]:
        import copy
        view = copy.deepcopy(view)
        for plan in view["result"]["proposals"]:
            for scenario in plan["evaluation"]["scenarios"]:
                scenario.pop("days", None)
    view["event_count"] = len(result.get("events", []))
    return view


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="逆势重生：本地经营计算与AgentArts协作服务")
    parser.add_argument("--db", default=str(ROOT / "var" / "rebirth.sqlite3"))
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="导入并校验JSON经营底账")
    imp.add_argument("file")
    run = sub.add_parser("run", help="运行一次有界协作任务")
    run.add_argument("merchant")
    run.add_argument("--mode", choices=("rules", "agentarts"), required=True)
    run.add_argument("--config", default=str(ROOT / "config.local.json"))
    inspect = sub.add_parser("inspect", help="查看某商户任务及证据")
    inspect.add_argument("merchant")
    inspect.add_argument("run_id")
    inspect.add_argument("--full", action="store_true", help="包括完整工具证据和逐日现金记录")
    ask = sub.add_parser("questions", help="列出缺失证据及专业角色的具体追问")
    ask.add_argument("merchant")
    answer = sub.add_parser("answer", help="录入有来源的结构化回答，原任务快照不受影响")
    answer.add_argument("merchant")
    answer.add_argument("file", help="JSON文件，顶层为answers列表")
    feedback = sub.add_parser("feedback", help="记录某一方案精确版本的实际试验反馈")
    feedback.add_argument("merchant")
    feedback.add_argument("file")
    history = sub.add_parser("history", help="查看商户既往试验反馈，不自动更改库存或现金")
    history.add_argument("merchant")
    backup = sub.add_parser("backup", help="完整SQLite备份，不覆盖已有文件")
    backup.add_argument("destination")
    serve = sub.add_parser("serve", help="启动仅本机可用的JSON API")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--config", default=str(ROOT / "config.local.json"))
    serve.add_argument("--allow-cloud", action="store_true", help="未来联调时显式允许API调用云服务，默认关闭")
    serve.add_argument("--open-browser", action="store_true", help="启动后在默认浏览器打开本地界面")
    args = parser.parse_args(argv)
    store = Store(args.db)
    try:
        if args.command == "import":
            ledger = store.put_ledger(json.loads(Path(args.file).read_text(encoding="utf-8-sig")))
            result = {"merchant_id": ledger["merchant_id"], "synthetic": ledger["synthetic"], "status": "imported"}
        elif args.command == "run":
            provider = RuleProvider() if args.mode == "rules" else AgentArtsProvider(args.config)
            result = Engine(store, provider).execute(args.merchant)
        elif args.command == "inspect":
            result = store.result(args.merchant, args.run_id)
        elif args.command == "questions":
            result = store.questions(args.merchant)
        elif args.command == "answer":
            data = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                raise ValidationError("回答文件必须为对象")
            result = store.answer(args.merchant, data.get("answers"))
        elif args.command == "feedback":
            result = store.record_feedback(args.merchant, json.loads(Path(args.file).read_text(encoding="utf-8-sig")))
        elif args.command == "history":
            result = {"merchant_id": args.merchant, "outcomes": store.feedback_history(args.merchant)}
        elif args.command == "backup":
            result = store.backup(args.destination)
        else:
            from .server import serve
            serve(store, args.port, args.config, allow_cloud=args.allow_cloud, open_browser=args.open_browser)
            return 0
        if args.command == "run" or (args.command == "inspect" and not args.full):
            result = compact(result)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValidationError, ProviderError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
