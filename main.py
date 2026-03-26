from kubernetes import client, config
import json
from datetime import datetime
from k8s_tools.api_server.server_api import load_kube_config
from k8s_tools.api_server.info_api import get_dict_info

def get_cluster_info():
    """获取集群全面信息"""
    info = json.loads(get_dict_info())
    print(f"⏱️ 采集时间: {info.get('timestamp')}")

    cluster_version = info.get("cluster_version") or {}
    print(
        "✅ 集群版本: {git} (major={major}, minor={minor}, platform={platform})".format(
            git=cluster_version.get("git_version"),
            major=cluster_version.get("major"),
            minor=cluster_version.get("minor"),
            platform=cluster_version.get("platform"),
        )
    )

    nodes = info.get("nodes") or []
    print(f"✅ 获取到 {len(nodes)} 个节点")
    for node in nodes:
        print("- 节点: {name} ({status})".format(name=node.get("name"), status=node.get("status")))
        roles = node.get("roles") or []
        print(f"  角色: {', '.join(roles) if roles else 'none'}")
        print(
            "  Kubelet: {kubelet} | OS: {os}".format(
                kubelet=node.get("kubelet_version"),
                os=node.get("os_image"),
            )
        )
        capacity = node.get("capacity") or {}
        allocatable = node.get("allocatable") or {}
        print(
            "  容量: cpu={cpu}, memory={memory}, pods={pods}".format(
                cpu=capacity.get("cpu"),
                memory=capacity.get("memory"),
                pods=capacity.get("pods"),
            )
        )
        print(
            "  可分配: cpu={cpu}, memory={memory}".format(
                cpu=allocatable.get("cpu"),
                memory=allocatable.get("memory"),
            )
        )

    namespaces = info.get("namespaces") or []
    print(f"✅ 获取到 {len(namespaces)} 个命名空间")
    if namespaces:
        print("  " + ", ".join(namespaces))

    pods_summary = info.get("pods_summary") or {}
    pods_total = pods_summary.get("total", 0)
    pods_by_phase = pods_summary.get("by_phase") or {}
    print(f"✅ 全集群 Pods: {pods_total} 个")
    if pods_by_phase:
        phases = ", ".join([f"{phase}={count}" for phase, count in pods_by_phase.items()])
        print(f"  状态分布: {phases}")

    deployments_total = (info.get("deployments_summary") or {}).get("total", 0)
    print(f"✅ 全集群 Deployments: {deployments_total} 个")

    resources = info.get("resources") or {}
    print("✅ 资源汇总:")
    print(resources if resources else "  (empty)")

if __name__ == "__main__":
    get_cluster_info()