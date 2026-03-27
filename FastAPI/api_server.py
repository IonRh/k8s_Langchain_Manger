import json
import os
from fastapi import FastAPI, Header, HTTPException
from k8s_tools.api_server.info_api import get_dict_info
from k8s_tools.node.pods.pods_info import collect_abnormal_reasons
from k8s_tools.self_heal.self_heal_agent import _load_rules, build_self_heal_plan, DEFAULT_RULES_PATH
from k8s_tools.self_heal.self_heal_actions import apply_action
from k8s_tools.api_server.server_api import load_kube_config
from kubernetes import client

TOKEN_ENV = ""

app = FastAPI(title="ZeroClaw K8s Self-Heal API")


def _verify_token(token):
    if TOKEN_ENV != "":
        if not token:
            raise HTTPException(status_code=401, detail="Missing token")
        expected = os.getenv(TOKEN_ENV)
        if expected and token != expected:
            raise HTTPException(status_code=403, detail="Invalid token")

def _load_rules_or_400():
    try:
        return _load_rules(DEFAULT_RULES_PATH)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail="Rules file not found. Provide rules or rules_config in payload.",
        ) from exc


def _apply_rule_overrides(rules_config, overrides):
    if not overrides:
        return rules_config
    if not isinstance(overrides, dict):
        raise HTTPException(status_code=400, detail="Invalid overrides format")

    rules = rules_config.get("rules") or []
    rule_map = {rule.get("name"): rule for rule in rules if rule.get("name")}
    for rule_name, changes in overrides.items():
        rule = rule_map.get(rule_name)
        if not rule or not isinstance(changes, dict):
            continue

        if "match" in changes:
            match = rule.get("match") or {}
            match.update(changes.get("match") or {})
            rule["match"] = match

        action = rule.get("action") or {}
        action_update = changes.get("action") if "action" in changes else changes
        if isinstance(action_update, dict) and action_update:
            action.update(action_update)
            rule["action"] = action

    return rules_config


def _resolve_rules_config(payload):
    if payload is None:
        return _load_rules_or_400()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload format")

    if "rules_config" in payload:
        rules_config = payload.get("rules_config") or {}
    elif "rules" in payload:
        rules_config = payload
    else:
        rules_config = _load_rules_or_400()

    if "dry_run" in payload:
        rules_config["dry_run"] = payload["dry_run"]
    if "max_actions_per_cycle" in payload:
        rules_config["max_actions_per_cycle"] = payload["max_actions_per_cycle"]

    overrides = payload.get("overrides")
    if overrides:
        rules_config = _apply_rule_overrides(rules_config, overrides)

    return rules_config


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    return {"status": "ready"}


@app.get("/cluster/info")
def cluster_info(x_token: str | None = Header(default=None, alias="X-Token")):
    _verify_token(x_token)
    return json.loads(get_dict_info())


@app.get("/pods/abnormal")
def pods_abnormal(x_token: str | None = Header(default=None, alias="X-Token")):
    _verify_token(x_token)
    info = json.loads(get_dict_info())
    pods = info.get("pods") or []
    abnormal = []
    for pod in pods:
        reasons = collect_abnormal_reasons(pod)
        if reasons:
            pod_view = dict(pod)
            pod_view["reasons"] = reasons
            abnormal.append(pod_view)
    return {
        "count": len(abnormal),
        "pods": abnormal,
    }


@app.get("/self-heal/plan")
def self_heal_plan(payload: dict | None = None, x_token: str | None = Header(default=None, alias="X-Token")):
    _verify_token(x_token)
    rules_config = _load_rules("self_heal_rules.json")
    plan = build_self_heal_plan(rules_config)
    return plan


@app.post("/self-heal/execute")
def self_heal_execute(payload: dict | None = None, x_token: str | None = Header(default=None, alias="X-Token")):
    _verify_token(x_token)
    rules_config = _resolve_rules_config(payload)
    dry_run = rules_config.get("dry_run", True)

    load_kube_config()
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    batch_v1 = client.BatchV1Api()

    plan = build_self_heal_plan(rules_config)
    results = []
    for item in plan.get("planned") or []:
        apply_action(item, apps_v1, batch_v1, v1, dry_run)
        results.append(
            {
                "pod": item.get("pod"),
                "rule": item.get("rule"),
                "action": item.get("action"),
            }
        )
    return {
        "dry_run": dry_run,
        "executed": results,
        "count": len(results),
    }
