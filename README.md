LangChain K8s Tool Server
==========================

Lightweight FastAPI + LangServe service that scales a Kubernetes Deployment and waits for
replicas to become ready and available. It exposes both a LangServe tool endpoint and a
custom HTTP endpoint for direct POST calls.

Features
--------
- Scale a Deployment and wait until ready + available replicas equal desired
- LangServe tool endpoint for Agent/tool usage
- Custom HTTP POST endpoint for Rust ZeroClaw
- In-cluster config with kubeconfig fallback for local dev

Requirements
------------
- Python 3.13+
- Access to a Kubernetes cluster (in-cluster or via kubeconfig)

Install
-------
```
pip install -e .
```

Run
---
```
uvicorn main:app --host 0.0.0.0 --port 8000
```

Configuration
-------------
- SCALE_WAIT_TIMEOUT_S (default: 300)
- SCALE_WAIT_POLL_INTERVAL_S (default: 2.0)
- LOG_LEVEL (default: INFO)

Endpoints
---------
- GET /healthz
- GET /readyz
- POST /scale
- POST /langserve/scale/invoke

Custom POST Example
-------------------
Request:
```
POST /scale
Content-Type: application/json

{
	"namespace": "default",
	"name": "my-deployment",
	"replicas": 3,
	"timeout_s": 300
}
```

Response:
```
{
	"status": "success",
	"message": "Scale complete",
	"desired": 3,
	"ready": 3,
	"available": 3,
	"elapsed_s": 12.4
}
```

LangServe Invoke Example
------------------------
Request:
```
POST /langserve/scale/invoke
Content-Type: application/json

{
	"input": {
		"namespace": "default",
		"name": "my-deployment",
		"replicas": 3,
		"timeout_s": 300
	}
}
```

Notes
-----
- Success requires both ready and available replicas to equal desired.
- On timeout or error, the response includes the current replica counts.
