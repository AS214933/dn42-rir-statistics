from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from .generator import generate_statistics, validate_output
from .repository import DEFAULT_BRANCH, DEFAULT_REMOTE, sync_registry
from .server import daily_scheduler, managed_process, run_rsync_daemon, serve_http


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dn42-rir-statistics",
        description="Generate and serve DN42 RIR statistics files.",
    )
    subparsers = parser.add_subparsers(required=True)

    generate_parser = subparsers.add_parser("generate", help="generate statistics files")
    add_registry_source_args(generate_parser)
    add_output_arg(generate_parser)
    generate_parser.add_argument("--date", help="generation date in yyyymmdd or yyyy-mm-dd")
    generate_parser.set_defaults(func=cmd_generate)

    validate_parser = subparsers.add_parser("validate", help="validate generated files")
    add_output_arg(validate_parser)
    validate_parser.set_defaults(func=cmd_validate)

    web_parser = subparsers.add_parser("web", help="serve generated files over http")
    add_output_arg(web_parser)
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8000)
    web_parser.set_defaults(func=cmd_web)

    rsync_parser = subparsers.add_parser("rsync", help="serve generated files over rsync")
    add_output_arg(rsync_parser)
    rsync_parser.add_argument("--host", default="127.0.0.1")
    rsync_parser.add_argument("--port", type=int, default=8730)
    rsync_parser.add_argument("--module", default="stats")
    rsync_parser.add_argument("--config", type=Path, default=Path("rsyncd.conf"))
    rsync_parser.set_defaults(func=cmd_rsync)

    serve_parser = subparsers.add_parser("serve", help="generate daily and serve http/rsync")
    add_registry_source_args(serve_parser)
    add_output_arg(serve_parser)
    serve_parser.add_argument("--web-host", default="127.0.0.1")
    serve_parser.add_argument("--web-port", type=int, default=8000)
    serve_parser.add_argument("--rsync-host", default="127.0.0.1")
    serve_parser.add_argument("--rsync-port", type=int, default=8730)
    serve_parser.add_argument("--rsync-module", default="stats")
    serve_parser.add_argument("--rsync-config", type=Path, default=Path("rsyncd.conf"))
    serve_parser.add_argument("--daily-at", default="03:00", help="daily UTC generation time")
    serve_parser.add_argument("--no-rsync", action="store_true")
    serve_parser.add_argument("--no-schedule", action="store_true")
    serve_parser.set_defaults(func=cmd_serve)

    return parser


def add_registry_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--registry-dir", type=Path, help="existing DN42 registry checkout")
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/dn42-registry"))
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)


def add_output_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", type=Path, default=Path("public"))


def registry_dir_from_args(args: argparse.Namespace) -> Path:
    if args.registry_dir:
        return args.registry_dir.resolve()
    return sync_registry(args.remote, args.branch, args.cache_dir)


def cmd_generate(args: argparse.Namespace) -> int:
    registry_dir = registry_dir_from_args(args)
    result = generate_statistics(registry_dir, args.output_dir, args.date)
    print_generation_result(result)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    result = validate_output(args.output_dir)
    if result.ok:
        print(f"validated {result.checked_files} delegated files")
        return 0
    for error in result.errors:
        print(error, file=sys.stderr)
    return 1


def cmd_web(args: argparse.Namespace) -> int:
    try:
        serve_http(args.output_dir, args.host, args.port)
        return 0
    except KeyboardInterrupt:
        return 130


def cmd_rsync(args: argparse.Namespace) -> int:
    process = run_rsync_daemon(
        args.output_dir,
        args.host,
        args.port,
        module=args.module,
        config_path=args.config,
    )
    print(f"rsync server listening on rsync://{args.host}:{args.port}/{args.module}/")
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return 130


def cmd_serve(args: argparse.Namespace) -> int:
    registry_dir = registry_dir_from_args(args)
    result = generate_statistics(registry_dir, args.output_dir)
    print_generation_result(result)

    stop_event = threading.Event()
    if not args.no_schedule:
        daily_scheduler(
            remote=args.remote,
            branch=args.branch,
            cache_dir=args.cache_dir,
            output_root=args.output_dir,
            daily_at=args.daily_at,
            stop_event=stop_event,
        )

    rsync_process = None
    if not args.no_rsync:
        rsync_process = run_rsync_daemon(
            args.output_dir,
            args.rsync_host,
            args.rsync_port,
            module=args.rsync_module,
            config_path=args.rsync_config,
        )
        print(
            "rsync server listening on "
            f"rsync://{args.rsync_host}:{args.rsync_port}/{args.rsync_module}/"
        )

    try:
        with managed_process(rsync_process):
            serve_http(args.output_dir, args.web_host, args.web_port)
    except KeyboardInterrupt:
        stop_event.set()
        return 130
    finally:
        stop_event.set()
    return 0


def print_generation_result(result) -> None:
    total_records = sum(result.record_counts.values())
    print(
        f"generated {len(result.registries)} registries and {total_records} records "
        f"for {result.generation_date} under {result.output_root / 'stats'}"
    )
    if result.warnings:
        print(f"{len(result.warnings)} warnings", file=sys.stderr)
        for warning in result.warnings[:20]:
            print(warning, file=sys.stderr)
        if len(result.warnings) > 20:
            print(f"... {len(result.warnings) - 20} more warnings", file=sys.stderr)
