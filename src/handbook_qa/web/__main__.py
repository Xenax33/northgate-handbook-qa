"""Start the web app:  uv run python -m handbook_qa.web   then open http://127.0.0.1:8000

Options: --port 8080, --host 0.0.0.0 (to reach it from another machine on the network).
"""

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"Loading the handbook and the search model, then serving on http://{args.host}:{args.port}")
    uvicorn.run("handbook_qa.web.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
