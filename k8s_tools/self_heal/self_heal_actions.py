from datetime import datetime


def _is_placeholder(value):
    if value is None:
        return True
    if isinstance(value, str) and "REPLACE_ME" in value:
        return True
    return False


def _has_placeholders(resource_dict):
    if not resource_dict:
        return True
    for value in resource_dict.values():
        if _is_placeholder(value):
            return True
    return False


def _patch_workload_template(kind, namespace, name, template, apps_v1, batch_v1):
    if kind in {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet"}:
        body = {"spec": {"template": template}}
        if kind == "Deployment":
            return apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body=body)
        if kind == "StatefulSet":
            return apps_v1.patch_namespaced_stateful_set(name=name, namespace=namespace, body=body)
        if kind == "DaemonSet":
            return apps_v1.patch_namespaced_daemon_set(name=name, namespace=namespace, body=body)
        return apps_v1.patch_namespaced_replica_set(name=name, namespace=namespace, body=body)

    if kind in {"Job", "CronJob"}:
        body = {"spec": {"template": template}}
        if kind == "CronJob":
            body = {"spec": {"jobTemplate": {"spec": body}}}
            return batch_v1.patch_namespaced_cron_job(name=name, namespace=namespace, body=body)
        return batch_v1.patch_namespaced_job(name=name, namespace=namespace, body=body)

    raise ValueError("Unsupported controller kind: {}".format(kind))


def _patch_workload_scale(kind, namespace, name, replicas, apps_v1):
    if kind not in {"Deployment", "StatefulSet", "ReplicaSet"}:
        raise ValueError("Scale not supported for kind: {}".format(kind))
    body = {"spec": {"replicas": replicas}}
    if kind == "Deployment":
        return apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body=body)
    if kind == "StatefulSet":
        return apps_v1.patch_namespaced_stateful_set(name=name, namespace=namespace, body=body)
    return apps_v1.patch_namespaced_replica_set(name=name, namespace=namespace, body=body)


def apply_action(plan, apps_v1, batch_v1, v1, dry_run):
    # 执行已计划的动作（dry_run 时只打印）。
    action = plan.get("action") or {}
    action_type = action.get("type")
    pod_ref = "{}/{}".format(plan["pod"]["namespace"], plan["pod"]["name"])

    if not action_type:
        return

    if action_type == "delete_pod":
        if dry_run:
            print("DRY-RUN 删除 Pod {}".format(pod_ref))
            return
        v1.delete_namespaced_pod(name=plan["pod"]["name"], namespace=plan["pod"]["namespace"])
        print("已删除 Pod {}".format(pod_ref))
        return

    controller = plan.get("controller")
    if not controller:
        print("跳过 {}（未找到控制器）：{}".format(action_type, pod_ref))
        return

    kind = controller["kind"]
    namespace = controller["namespace"]
    name = controller["name"]

    if action_type == "rollout_restart":
        timestamp = datetime.utcnow().isoformat() + "Z"
        template = {"metadata": {"annotations": {"self-heal/restarted-at": timestamp}}}
        if dry_run:
            print("DRY-RUN 重启 {} {}/{}（来源 Pod {}）".format(kind, namespace, name, pod_ref))
            return
        _patch_workload_template(kind, namespace, name, template, apps_v1, batch_v1)
        print("已重启 {} {}/{}（来源 Pod {}）".format(kind, namespace, name, pod_ref))
        return

    if action_type == "patch_image":
        image = action.get("image")
        if _is_placeholder(image):
            print("跳过 patch_image（未设置镜像）：{}".format(pod_ref))
            return

        container = action.get("container") or plan.get("container")
        if not container:
            container = (plan.get("container_names") or [None])[0]
        if not container:
            print("跳过 patch_image（未找到容器）：{}".format(pod_ref))
            return

        template = {
            "spec": {
                "containers": [
                    {
                        "name": container,
                        "image": image,
                    }
                ]
            }
        }
        if dry_run:
            print("DRY-RUN 更新镜像 {} {}/{} {} -> {}".format(
                kind, namespace, name, container, image
            ))
            return
        _patch_workload_template(kind, namespace, name, template, apps_v1, batch_v1)
        print("已更新镜像 {} {}/{} {} -> {}".format(
            kind, namespace, name, container, image
        ))
        return

    if action_type == "patch_resources":
        requests = action.get("requests") or {}
        limits = action.get("limits") or {}
        if _has_placeholders(requests) and _has_placeholders(limits):
            print("跳过 patch_resources（未设置 requests/limits）：{}".format(pod_ref))
            return

        container = action.get("container") or plan.get("container")
        if not container:
            container = (plan.get("container_names") or [None])[0]
        if not container:
            print("跳过 patch_resources（未找到容器）：{}".format(pod_ref))
            return

        resources = {}
        if requests:
            resources["requests"] = requests
        if limits:
            resources["limits"] = limits

        template = {
            "spec": {
                "containers": [
                    {
                        "name": container,
                        "resources": resources,
                    }
                ]
            }
        }
        if dry_run:
            print("DRY-RUN 更新资源 {} {}/{} {}".format(
                kind, namespace, name, container
            ))
            return
        _patch_workload_template(kind, namespace, name, template, apps_v1, batch_v1)
        print("已更新资源 {} {}/{} {}".format(
            kind, namespace, name, container
        ))
        return

    if action_type == "scale":
        replicas = action.get("replicas")
        if replicas is None:
            print("跳过 scale（未设置 replicas）：{}".format(pod_ref))
            return
        if dry_run:
            print("DRY-RUN 扩缩容 {} {}/{} -> {}".format(kind, namespace, name, replicas))
            return
        _patch_workload_scale(kind, namespace, name, replicas, apps_v1)
        print("已扩缩容 {} {}/{} -> {}".format(kind, namespace, name, replicas))
        return

    print("跳过未知动作 {}（Pod {}）".format(action_type, pod_ref))
