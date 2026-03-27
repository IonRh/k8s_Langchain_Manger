import importlib.util
import os
from pathlib import Path


def _load_api_app():
    api_path = Path(__file__).resolve().parent / "FastAPI" / "api_server.py"
    if not api_path.exists():
        raise FileNotFoundError("API server not found at {}".format(api_path))

    spec = importlib.util.spec_from_file_location("zeroclaw_api_server", str(api_path))
    if not spec or not spec.loader:
        raise RuntimeError("Failed to load API server module")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "app"):
        raise RuntimeError("API server module does not define app")
    return module.app


def run_api_server():
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is required to run the API server") from exc

    uvicorn.run(_load_api_app(), host=host, port=port)


if __name__ == "__main__":
    run_api_server()