from .server_api import load_kube_config
from kubernetes import client, config
import json
from datetime import datetime

def get_dict_info() -> dict:
    """获取集群全面信息"""
    load_kube_config()
    
    # CoreV1Api：处理 Nodes、Pods、Namespaces、Services 等
    v1 = client.CoreV1Api()
    
    # AppsV1Api：处理 Deployments、StatefulSets、DaemonSets
    apps_v1 = client.AppsV1Api()
    
    # VersionApi：获取集群版本
    version_api = client.VersionApi()

    info = {
        "timestamp": datetime.now().isoformat(),
        "cluster_version": None,
        "nodes": [],
        "namespaces": [],
        "pods_summary": {"total": 0, "by_phase": {}},
        "deployments_summary": {"total": 0},
        "resources": {}
    }

    # 1. 集群版本信息
    try:
        version = version_api.get_code()
        info["cluster_version"] = {
            "major": version.major,
            "minor": version.minor,
            "git_version": version.git_version,
            "platform": version.platform
        }
    except Exception as e:
        print(f"⚠️ 获取版本失败: {e}")

    # 2. 获取所有 Nodes（含状态、容量、分配资源）
    try:
        nodes = v1.list_node()
        for node in nodes.items:
            node_info = {
                "name": node.metadata.name,
                "status": "Ready" if any(cond.type == "Ready" and cond.status == "True" for cond in node.status.conditions) else "NotReady",
                "roles": [label for label in node.metadata.labels.keys() if "node-role" in label or label == "kubernetes.io/role"],
                "kubelet_version": node.status.node_info.kubelet_version,
                "os_image": node.status.node_info.os_image,
                "capacity": {
                    "cpu": node.status.capacity.get("cpu"),
                    "memory": node.status.capacity.get("memory"),
                    "pods": node.status.capacity.get("pods")
                },
                "allocatable": {
                    "cpu": node.status.allocatable.get("cpu"),
                    "memory": node.status.allocatable.get("memory")
                }
            }
            info["nodes"].append(node_info)
    except Exception as e:
        print(f"⚠️ 获取节点失败: {e}")

    # 3. 获取所有 Namespaces
    try:
        namespaces = v1.list_namespace()
        info["namespaces"] = [ns.metadata.name for ns in namespaces.items]
    except Exception as e:
        print(f"⚠️ 获取命名空间失败: {e}")

    # 4. Pods 概览（全集群）
    try:
        pods = v1.list_pod_for_all_namespaces(watch=False)
        info["pods_summary"]["total"] = len(pods.items)
        for pod in pods.items:
            phase = pod.status.phase
            info["pods_summary"]["by_phase"][phase] = info["pods_summary"]["by_phase"].get(phase, 0) + 1
    except Exception as e:
        print(f"⚠️ 获取 Pods 失败: {e}")

    # 5. Deployments 概览
    try:
        deployments = apps_v1.list_deployment_for_all_namespaces()
        info["deployments_summary"]["total"] = len(deployments.items)
    except Exception as e:
        print(f"⚠️ 获取 Deployments 失败: {e}")

    # 输出 JSON（方便后续处理或 API 返回）
    # print(json.dumps(info, indent=2, ensure_ascii=False, default=str))
    dict_to_json = json.dumps(info, indent=2, ensure_ascii=False, default=str)
    return dict_to_json
