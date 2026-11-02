"""No-network configuration inspection and conservative outbound-data minimization."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

ROLES = ("coordinator", "inventory", "customer", "cash")


def inspect_config(path, allow_cloud=False):
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(cfg, dict):
            raise ValueError()
    except (OSError, ValueError):
        cfg = {}
    checks = []
    for role in ROLES:
        entry = cfg.get("agents", {}).get(role, {}) if isinstance(cfg.get("agents", {}), dict) else {}
        if not isinstance(entry, dict):
            entry = {}
        url = str(entry.get("url", ""))
        try:
            parsed = urlsplit(url)
            valid = parsed.scheme == "https" and bool(parsed.hostname) and not any((parsed.username, parsed.password, parsed.query, parsed.fragment)) and "YOUR" not in url.upper()
            host = parsed.hostname if valid else None
        except ValueError:
            valid, host = False, None
        env = entry.get("token_env", "AGENTARTS_TOKEN")
        token = isinstance(env, str) and bool(os.environ.get(env))
        allowed = isinstance(cfg.get("allowed_hosts"), list) and host in cfg["allowed_hosts"]
        checks.append({"role": role, "https_endpoint": valid, "host": host, "host_confirmed": allowed,
            "credential_present": token, "auth_header_supported": entry.get("auth_header", "X-Auth-Token") in ("X-Auth-Token", "Authorization")})
    ready = all(all(r[k] for k in ("https_endpoint", "host_confirmed", "credential_present", "auth_header_supported")) for r in checks)
    return {"roles": checks, "configured": ready, "server_allows_cloud": allow_cloud,
        "can_request_cloud": ready and allow_cloud, "network_contacted": False,
        "remaining": "仍需发布四个真实工作流，按控制台请求示例联调，并在平台设置资源额度；本预检不证明接口可用或计费准确。",
        "notice": "预检只读配置和环境变量存在性，不显示凭证，不发网络请求；一次同意只对应一次任务。"}


def redact_context(context):
    data = deepcopy(context)
    merchant = data.get("ledger", {}).get("merchant_id", "")
    name = data.get("ledger", {}).get("name", "")
    def clean(obj, key=""):
        if key == "sources" and isinstance(obj, dict):
            return {k: "来源说明留存本机" for k in obj}
        if key in ("source_note", "change_reason"):
            return "原说明留存本机"
        if isinstance(obj, dict):
            return {k: clean(v, k) for k, v in obj.items()}
        if isinstance(obj, list):
            return [clean(v) for v in obj]
        if isinstance(obj, str):
            if key == "name" and obj == name:
                return "匿名服装零售店"
            if key == "merchant_id":
                return "merchant_" + hashlib.sha256(merchant.encode()).hexdigest()[:16]
            text = obj.replace(name, "匿名店铺") if name else obj
            text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号已遮蔽]", text)
            text = re.sub(r"(?<!\d)\d{17}[\dXx](?!\d)", "[身份证号已遮蔽]", text)
            return re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[邮箱已遮蔽]", text)
        return obj
    return clean(data)
