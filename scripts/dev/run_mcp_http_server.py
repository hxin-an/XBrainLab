#!/usr/bin/env python3
"""Run the local XBrainLab MCP HTTP adapter."""

from __future__ import annotations

import argparse
import logging
import os

from XBrainLab.mcp import run_http_server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address. Use 127.0.0.1 for local desktop-safe usage.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="HTTP port for POST /mcp and GET /health.",
    )
    parser.add_argument(
        "--token-env",
        default="XBRAINLAB_MCP_HTTP_TOKEN",
        help="Environment variable containing an optional bearer token.",
    )
    parser.add_argument(
        "--max-body-bytes",
        type=int,
        default=1_048_576,
        help="Maximum accepted JSON-RPC request body size.",
    )
    args = parser.parse_args()

    logging.getLogger("XBrainLab").setLevel(logging.WARNING)
    token = os.environ.get(args.token_env) or None
    return run_http_server(
        host=args.host,
        port=args.port,
        auth_token=token,
        max_body_bytes=args.max_body_bytes,
    )


if __name__ == "__main__":
    raise SystemExit(main())
