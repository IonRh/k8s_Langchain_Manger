import json
import os
from kubernetes import client
from k8s_tools.api_server.server_api import load_kube_config
from k8s_tools.self_heal.self_heal_actions import apply_action

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DEFAULT_RULES_PATH = os.path.join(ROOT_DIR, "self_heal_rules.json")


def _load_rules(path):
    # 加载自愈规则 JSON（驱动检测与动作）。
    if not os.path.isfile(path):
        raise FileNotFoundError("Rules file not found: {}".format(path))
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _match_value(expected, actual):
    if isinstance(expected, list):
        return actual in expected
    return actual == expected


def _get_owner_ref(owner_refs):
    if not owner_refs:
        return None
    for owner in owner_refs:
        if getattr(owner, "controller", False):
            return owner
    return owner_refs[0]


def _build_pod_signal(pod):
    # 将 Pod 状态归一成可匹配的信号结构。
    status = pod.status
    metadata = pod.metadata

    ready = None
    unschedulable = False
    if status and status.conditions:
        for cond in status.conditions:
            if cond.type == "Ready":
                ready = cond.status == "True"
            if cond.type == "PodScheduled":
                if cond.status == "False" and cond.reason == "Unschedulable":
                    unschedulable = True

    containers = []
    restart_count = 0
    status_list = []
    if status:
        status_list.extend(status.init_container_statuses or [])
        status_list.extend(status.container_statuses or [])

    for cs in status_list:
        state = None
        reason = None
        message = None
        if cs.state:
            if cs.state.waiting:
                state = "Waiting"
                reason = cs.state.waiting.reason
                message = cs.state.waiting.message
            elif cs.state.terminated:
                state = "Terminated"
                reason = cs.state.terminated.reason
                message = cs.state.terminated.message
            elif cs.state.running:
                state = "Running"

        last_reason = None
        if cs.last_state and cs.last_state.terminated:
            last_reason = cs.last_state.terminated.reason

        restart_count += cs.restart_count or 0
        containers.append(
            {
                "name": cs.name,
                "image": cs.image,
                "ready": cs.ready,
                "state": state,
                "reason": reason,
                "message": message,
                "last_reason": last_reason,
                "restart_count": cs.restart_count or 0,
            }
        )

    owner_refs = metadata.owner_references or []
    owner_info = [
        {
            "kind": owner.kind,
            "name": owner.name,
            "controller": getattr(owner, "controller", False),
        }
        for owner in owner_refs
    ]

    return {
        "namespace": metadata.namespace,
        "name": metadata.name,
        "labels": metadata.labels or {},
        "phase": status.phase if status else None,
        "pod_reason": status.reason if status else None,
        "pod_message": status.message if status else None,
        "ready": ready,
        "unschedulable": unschedulable,
        "restart_count": restart_count,
        "containers": containers,
        "owner_refs": owner_info,
    }


def _match_container_field(containers, field, allowed, container_name=None):
    if container_name:
        for container in containers:
            if container.get("name") == container_name:
                return container.get(field) in allowed, container_name
        return False, container_name

    for container in containers:
        if container.get(field) in allowed:
            return True, container.get("name")
    return False, None


def _match_rule(rule, signal):
    # 用单条规则匹配一个 Pod 信号。
    match = rule.get("match") or {}
    container_name = None

    if "namespace" in match:
        namespaces = set(_as_list(match["namespace"]))
        if signal.get("namespace") not in namespaces:
            return False, {}

    if "name_prefix" in match:
        prefix = match["name_prefix"]
        if not signal.get("name", "").startswith(prefix):
            return False, {}

    if "phase" in match:
        allowed = _as_list(match["phase"])
        if not _match_value(allowed, signal.get("phase")):
            return False, {}

    if "ready" in match:
        if signal.get("ready") is None or signal.get("ready") != match["ready"]:
            return False, {}

    if "unschedulable" in match:
        if signal.get("unschedulable") != match["unschedulable"]:
            return False, {}

    if "restart_count_gt" in match:
        if not (signal.get("restart_count", 0) > match["restart_count_gt"]):
            return False, {}

    if "restart_count_gte" in match:
        if not (signal.get("restart_count", 0) >= match["restart_count_gte"]):
            return False, {}

    if "pod_reason" in match:
        allowed = set(_as_list(match["pod_reason"]))
        if signal.get("pod_reason") not in allowed:
            return False, {}

    if "label_selector" in match:
        selector = match["label_selector"] or {}
        labels = signal.get("labels") or {}
        for key, expected in selector.items():
            if isinstance(expected, list):
                if labels.get(key) not in expected:
                    return False, {}
            else:
                if labels.get(key) != expected:
                    return False, {}

    if "container_name" in match:
        container_name = match["container_name"]
        if container_name not in {c.get("name") for c in signal.get("containers") or []}:
            return False, {}

    if "container_reason" in match:
        allowed = set(_as_list(match["container_reason"]))
        matched, container_name = _match_container_field(
            signal.get("containers") or [],
            "reason",
            allowed,
            container_name,
        )
        if not matched:
            return False, {}

    if "container_last_reason" in match:
        allowed = set(_as_list(match["container_last_reason"]))
        matched, container_name = _match_container_field(
            signal.get("containers") or [],
            "last_reason",
            allowed,
            container_name,
        )
        if not matched:
            return False, {}

    if "container_state" in match:
        allowed = set(_as_list(match["container_state"]))
        matched, container_name = _match_container_field(
            signal.get("containers") or [],
            "state",
            allowed,
            container_name,
        )
        if not matched:
            return False, {}

    return True, {"container": container_name}


def _resolve_controller(signal, apps_v1, batch_v1):
    # 将 Pod owner 解析到上层控制器（尽量上溯到 Deployment/CronJob）。
    owner = None
    for owner_ref in signal.get("owner_refs") or []:
        if owner_ref.get("controller"):
            owner = owner_ref
            break
    if not owner and signal.get("owner_refs"):
        owner = signal.get("owner_refs")[0]

    if not owner:
        return None

    namespace = signal.get("namespace")
    kind = owner.get("kind")
    name = owner.get("name")

    if kind == "ReplicaSet":
        try:
            rs = apps_v1.read_namespaced_replica_set(name=name, namespace=namespace)
        except Exception:
            return {"kind": kind, "name": name, "namespace": namespace}
        rs_owner = _get_owner_ref(rs.metadata.owner_references or [])
        if rs_owner and rs_owner.kind == "Deployment":
            return {"kind": "Deployment", "name": rs_owner.name, "namespace": namespace}
        return {"kind": "ReplicaSet", "name": name, "namespace": namespace}

    if kind == "Job":
        try:
            job = batch_v1.read_namespaced_job(name=name, namespace=namespace)
        except Exception:
            return {"kind": kind, "name": name, "namespace": namespace}
        job_owner = _get_owner_ref(job.metadata.owner_references or [])
        if job_owner and job_owner.kind == "CronJob":
            return {"kind": "CronJob", "name": job_owner.name, "namespace": namespace}
        return {"kind": "Job", "name": name, "namespace": namespace}

    return {"kind": kind, "name": name, "namespace": namespace}


def _plan_actions(signals, rules, apps_v1, batch_v1, max_actions):
    # 每个 Pod 只命中第一条规则，保证动作稳定可控。
    plans = []
    for signal in signals:
        for rule in rules:
            if not rule or not rule.get("action"):
                continue
            if rule.get("enabled") is False:
                continue

            matched, context = _match_rule(rule, signal)
            if not matched:
                continue

            controller = _resolve_controller(signal, apps_v1, batch_v1)
            container_names = [c.get("name") for c in signal.get("containers") or []]
            plans.append(
                {
                    "rule": rule.get("name"),
                    "action": rule.get("action"),
                    "pod": {
                        "namespace": signal.get("namespace"),
                        "name": signal.get("name"),
                    },
                    "container": context.get("container"),
                    "container_names": container_names,
                    "controller": controller,
                }
            )
            break

        if max_actions and len(plans) >= max_actions:
            break

    return plans


def build_self_heal_plan(rules_config):
    # 生成自愈计划（供 API 使用）。
    rules = rules_config.get("rules") or []
    max_actions = rules_config.get("max_actions_per_cycle", 5)

    load_kube_config()
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    batch_v1 = client.BatchV1Api()

    pods = v1.list_pod_for_all_namespaces(watch=False)
    signals = [_build_pod_signal(pod) for pod in pods.items]

    plans = _plan_actions(signals, rules, apps_v1, batch_v1, max_actions)
    return {
        "planned": plans,
        "total_planned": len(plans),
    }


def run_self_heal(rules_path=DEFAULT_RULES_PATH):
    # 主流程：加载规则 → 采集信号 → 生成计划 → 执行动作。
    rules_config = _load_rules(rules_path)
    rules = rules_config.get("rules") or []
    dry_run = rules_config.get("dry_run", True)
    max_actions = rules_config.get("max_actions_per_cycle", 5)

    load_kube_config()
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    batch_v1 = client.BatchV1Api()

    pods = v1.list_pod_for_all_namespaces(watch=False)
    signals = [_build_pod_signal(pod) for pod in pods.items]

    plans = _plan_actions(signals, rules, apps_v1, batch_v1, max_actions)
    if not plans:
        print("没有可执行的自愈动作。")
        return

    for plan in plans:
        print("计划 rule={} pod={}/{} action={}".format(
            plan.get("rule"),
            plan["pod"]["namespace"],
            plan["pod"]["name"],
            plan["action"].get("type"),
        ))
        # apply_action(plan, apps_v1, batch_v1, v1, dry_run)
