# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Michael Schertz
"""``x12-tidy-web`` -- run the web app, or repair one file from the shell.

    x12-tidy-web serve [--host H] [--port P] [--reload]
    x12-tidy-web repair FILE [--format markdown] [--max-iterations 5]

``serve`` is the usual entry point. ``repair`` is a convenience for scripting or
a quick check without starting the server; it writes the chosen report format to
stdout and exits non-zero when findings remain (``1``) or the input could not be
recovered (``2``).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from x12_tidy_web import __version__
from x12_tidy_web.engine import DEFAULT_MAX_ITERATIONS, repair
from x12_tidy_web.provenance import x12_tidy_release
from x12_tidy_web.reporting import FORMATS, render_report


def _default_port() -> int:
    """Serve port: ``$PORT`` if the host sets one (Cloud Run, Render, Fly,
    Railway all do), otherwise 8000."""
    raw = os.environ.get("PORT")
    if raw and raw.isdigit():
        return int(raw)
    return 8000


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="x12-tidy-web", description=__doc__)
    parser.add_argument(
        "--version",
        action="version",
        version=f"x12-tidy-web {__version__}, x12-tidy {x12_tidy_release()}",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the web application")
    serve.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    serve.add_argument(
        "--port",
        type=int,
        default=_default_port(),
        help="bind port (default: $PORT if set, else 8000)",
    )
    serve.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")
    serve.add_argument("--log-level", default="info", help="uvicorn log level (default: info)")

    rep = sub.add_parser("repair", help="repair one file and print a report")
    rep.add_argument("file", type=Path, help="path to an EDI file")
    rep.add_argument(
        "--format",
        default="text",
        choices=sorted(FORMATS),
        help="report format (default: text)",
    )
    rep.add_argument(
        "--max-iterations",
        type=int,
        default=DEFAULT_MAX_ITERATIONS,
        help=f"repair-pass cap (default: {DEFAULT_MAX_ITERATIONS})",
    )
    return parser


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "x12_tidy_web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


def _cmd_repair(args: argparse.Namespace) -> int:
    try:
        data = args.file.read_bytes()
    except OSError as exc:
        print(f"error: cannot read {args.file}: {exc}", file=sys.stderr)
        return 2

    run = repair(data, max_iterations=args.max_iterations)
    sys.stdout.write(render_report(run, args.format).content.decode("utf-8"))
    if not run.recovered:
        return 2
    return 0 if run.clean else 1


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "serve":
        return _cmd_serve(args)
    if args.command == "repair":
        return _cmd_repair(args)
    return 2  # pragma: no cover  (argparse enforces `required=True`)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
