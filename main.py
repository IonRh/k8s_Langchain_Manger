from kubernetes import client, config
import json
from datetime import datetime
from k8s_tools.api_server.server_api import load_kube_config
from k8s_tools.api_server.info_api import get_dict_info

def get_cluster_info():
    """获取集群全面信息"""
    info = get_dict_info()
        # 3. 获取所有 Namespaces

    print("\n" + "="*60)
    print("📊 集群信息汇总（JSON 格式）:")
    print(info)

if __name__ == "__main__":
    get_cluster_info()