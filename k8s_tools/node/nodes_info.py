def print_nodes_info(nodes):
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
