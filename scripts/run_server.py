from __future__ import annotations

import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import uvicorn
except ImportError as exc:
    raise SystemExit(
        "Missing web dependencies. Activate the target environment and install: "
        "python -m pip install fastapi uvicorn python-multipart"
    ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Local Paper Reader server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("src.api.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
