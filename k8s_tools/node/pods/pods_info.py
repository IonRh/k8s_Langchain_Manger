RESTART_THRESHOLD = 3
ALLOW_SUCCEEDED_PHASE = True


def _pod_ref(pod):
    return "{ns}/{name}".format(
        ns=pod.get("namespace"),
        name=pod.get("name"),
    )


def _restart_threshold_exceeded(restart_count):
    if RESTART_THRESHOLD is None:
        return False
    return restart_count > RESTART_THRESHOLD


def _collect_abnormal_reasons(pod):
    reasons = []

    phase = pod.get("phase") or "Unknown"
    normal_phases = {"Running"}
    if ALLOW_SUCCEEDED_PHASE:
        normal_phases.add("Succeeded")

    if phase not in normal_phases:
        reasons.append("phase={}".format(phase))

    if phase == "Running":
        ready = pod.get("ready")
        if ready != "True":
            reasons.append("ready={}".format(ready or "unknown"))

        if pod.get("reason") or pod.get("message"):
            reasons.append("pod_status_reason")

    restart_count = pod.get("restart_count") or 0
    if _restart_threshold_exceeded(restart_count):
        reasons.append("restarts={}".format(restart_count))

    if phase == "Running":
        for container in pod.get("containers") or []:
            name = container.get("name")
            if container.get("ready") is False:
                reasons.append("container_not_ready={}".format(name))
            state = container.get("state")
            if state and state != "Running":
                reasons.append("container_state={0}={1}".format(name, state))
            if container.get("reason") or container.get("message"):
                reasons.append("container_reason={}".format(name))

    return reasons


def collect_abnormal_reasons(pod):
    return _collect_abnormal_reasons(pod)


def print_abnormal_pods(pods):
    abnormal = []
    for pod in pods:
        reasons = _collect_abnormal_reasons(pod)
        if reasons:
            abnormal.append((pod, reasons))

    print(f"⚠️ 异常 Pods: {len(abnormal)} 个")
    if not abnormal:
        return

    for pod, reasons in abnormal:
        print(
            "- Pod: {ref} (phase={phase}, ready={ready}, restarts={restarts})".format(
                ref=_pod_ref(pod),
                phase=pod.get("phase"),
                ready=pod.get("ready"),
                restarts=pod.get("restart_count"),
            )
        )
        print("  Node: {node} | PodIP: {pod_ip} | HostIP: {host_ip}".format(
            node=pod.get("node"),
            pod_ip=pod.get("pod_ip"),
            host_ip=pod.get("host_ip"),
        ))
        print("  Reasons: {reasons}".format(reasons=", ".join(reasons)))
        if pod.get("reason") or pod.get("message"):
            print(
                "  PodReason: {reason} | Message: {message}".format(
                    reason=pod.get("reason"),
                    message=pod.get("message"),
                )
            )

        for container in pod.get("containers") or []:
            print(
                "  - Container: {name} ({image})".format(
                    name=container.get("name"),
                    image=container.get("image"),
                )
            )
            print(
                "    Ready: {ready} | State: {state} | Restarts: {restarts}".format(
                    ready=container.get("ready"),
                    state=container.get("state"),
                    restarts=container.get("restart_count"),
                )
            )
            if container.get("reason") or container.get("message"):
                print(
                    "    Reason: {reason} | Message: {message}".format(
                        reason=container.get("reason"),
                        message=container.get("message"),
                    )
                )


def print_healthy_pods(pods):
    healthy = []
    for pod in pods:
        if not _collect_abnormal_reasons(pod):
            healthy.append(pod)

    print(f"✅ 健康 Pods: {len(healthy)} 个")
    for pod in healthy:
        print(
            "- Pod: {ref} (phase={phase}, ready={ready}, restarts={restarts})".format(
                ref=_pod_ref(pod),
                phase=pod.get("phase"),
                ready=pod.get("ready"),
                restarts=pod.get("restart_count"),
            )
        )
        print(
            "  Node: {node} | PodIP: {pod_ip} | HostIP: {host_ip}".format(
                node=pod.get("node"),
                pod_ip=pod.get("pod_ip"),
                host_ip=pod.get("host_ip"),
            )
        )
        print(
            "  Created: {created} | Started: {started}".format(
                created=pod.get("creation_timestamp"),
                started=pod.get("start_time"),
            )
        )
        print("  QoS: {qos}".format(qos=pod.get("qos_class")))


def print_pod_resources(pods):
    print("✅ Pods 资源信息:")
    if not pods:
        print("  (empty)")
        return

    for pod in pods:
        print("- Pod: {ref}".format(ref=_pod_ref(pod)))
        containers = pod.get("containers") or []
        if not containers:
            print("  (no containers)")
            continue
        for container in containers:
            requests = container.get("requests") or {}
            limits = container.get("limits") or {}
            print(
                "  - Container: {name} ({image})".format(
                    name=container.get("name"),
                    image=container.get("image"),
                )
            )
            print(
                "    Requests: {requests} | Limits: {limits}".format(
                    requests=requests if requests else "(empty)",
                    limits=limits if limits else "(empty)",
                )
            )
