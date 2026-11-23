"""Start the web app:  uv run handbook-web   then open http://127.0.0.1:8000

Options: --port 8080, --host 0.0.0.0 (to reach it from another machine on the network). The HOST and
PORT environment variables set the same defaults; hosting services such as Render set PORT themselves.
"""

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()
    print(f"Loading the handbook and the search model, then serving on http://{args.host}:{args.port}")
    uvicorn.run("handbook_qa.web.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
