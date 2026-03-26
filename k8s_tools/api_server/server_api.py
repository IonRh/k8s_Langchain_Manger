from kubernetes import client, config
import json
from datetime import datetime

def load_kube_config():
    """加载 kubeconfig，支持本地远程控制"""
    try:
        # 本地运行：使用 ~/.kube/config（或指定路径）
        config.load_kube_config(config_file="k8s_config/config")          # 支持多 context
        # 如果想指定某个 context 或 config 文件：
        # config.load_kube_config(config_file="/path/to/kubeconfig", context="my-context")
        print("✅ 已加载 kubeconfig（本地远程模式）")
    except Exception:
        # 如果在 Pod 内运行（In-Cluster）
        config.load_incluster_config()
        print("✅ 已加载 In-Cluster 配置（Pod 内模式）")

