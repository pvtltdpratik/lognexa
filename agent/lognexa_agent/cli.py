"""Command-line entry point for the Lognexa agent.

    lognexa-agent run                 enrol if needed, then collect and ship
    lognexa-agent enroll --token ...  enrol only
    lognexa-agent status              show enrolment, buffer depth, collectors
    lognexa-agent collectors          list collectors and their availability
    lognexa-agent test-collectors     run one local collection cycle (no network)
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import signal
import sys

from lognexa_agent import __version__
from lognexa_agent.config import AgentConfig, State, is_privileged


def _setup_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _config(args) -> AgentConfig:
    cfg = AgentConfig.load(args.config)
    if getattr(args, "server", None):
        cfg.server_url = args.server.rstrip("/")
    if getattr(args, "token", None):
        cfg.enroll_token = args.token
    if getattr(args, "insecure_http", False):
        cfg.insecure_http_ok = True
    return cfg


def cmd_run(args) -> int:
    from lognexa_agent.agent import Agent

    cfg = _config(args)
    _setup_logging(cfg.log_level)
    agent = Agent(cfg)

    def _handle(_signum, _frame):
        agent.stop()

    for sig in (signal.SIGINT, getattr(signal, "SIGTERM", signal.SIGINT)):
        try:
            signal.signal(sig, _handle)
        except (ValueError, OSError):
            pass
    agent.run()
    return 0


def cmd_enroll(args) -> int:
    from lognexa_agent.agent import Agent

    cfg = _config(args)
    _setup_logging(cfg.log_level)
    agent = Agent(cfg)
    if agent.state.enrolled and not args.force:
        print(f"Already enrolled as device {agent.state.device_uid}. Use --force to re-enrol.")
        return 0
    if args.force:
        agent.state.data["credential"] = None
    agent.ensure_enrolled()
    print(f"Enrolled as device {agent.state.device_uid}")
    return 0


def cmd_status(args) -> int:
    cfg = _config(args)
    state = State(cfg.state_path)
    buffer_pending = None
    try:
        from lognexa_agent.buffer import EventBuffer

        buf = EventBuffer(cfg.buffer_path, cfg.max_buffer_events)
        buffer_pending = buf.pending()
        buf.close()
    except Exception as exc:  # noqa: BLE001
        buffer_pending = f"error: {exc}"
    print(json.dumps({
        "version": __version__,
        "os": platform.platform(),
        "privileged": is_privileged(),
        "server_url": cfg.server_url,
        "data_dir": str(cfg.data_dir),
        "enrolled": state.enrolled,
        "device_uid": state.device_uid,
        "buffer_pending": buffer_pending,
    }, indent=2))
    return 0


def cmd_collectors(args) -> int:
    from lognexa_agent.collectors import collectors_for_platform

    cfg = _config(args)
    state = State(cfg.state_path)
    rows = []
    for cls in collectors_for_platform():
        inst = cls(cfg, state)
        ok, status, detail = inst.available()
        rows.append({"name": inst.name, "available": ok, "status": status, "detail": detail,
                     "enabled": cfg.collector_enabled(inst.name)})
    print(json.dumps(rows, indent=2))
    return 0


def cmd_test_collectors(args) -> int:
    from lognexa_agent.collectors import collectors_for_platform

    cfg = _config(args)
    _setup_logging("INFO")
    state = State(cfg.state_path)
    total = 0
    for cls in collectors_for_platform():
        inst = cls(cfg, state)
        ok, status, detail = inst.available()
        if not ok:
            print(f"- {inst.name}: {status} ({detail})")
            continue
        events = inst.run()
        total += len(events)
        print(f"- {inst.name}: {len(events)} event(s), status={inst.health.status}")
        for ev in events[: args.limit]:
            print(f"    {ev.timestamp:%H:%M:%S} {ev.category}/{ev.event_type} {ev.process_name or ev.username or ev.dst_ip or ''}")
    print(f"Total: {total} event(s) in one cycle (nothing was sent).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lognexa-agent", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"lognexa-agent {__version__}")
    parser.add_argument("-c", "--config", help="path to config.json")
    parser.add_argument("--server", help="override server URL")
    parser.add_argument("--insecure-http", action="store_true", help="allow plain HTTP to a localhost dev server")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="enrol if needed, then run continuously")
    p_run.add_argument("--token", help="enrolment token (first run only)")
    p_run.set_defaults(func=cmd_run)

    p_enroll = sub.add_parser("enroll", help="enrol this host and exit")
    p_enroll.add_argument("--token", required=False, help="enrolment token")
    p_enroll.add_argument("--force", action="store_true", help="re-enrol even if already enrolled")
    p_enroll.set_defaults(func=cmd_enroll)

    for name, fn, helptext in [
        ("status", cmd_status, "show agent status"),
        ("collectors", cmd_collectors, "list collectors and availability"),
    ]:
        p = sub.add_parser(name, help=helptext)
        p.set_defaults(func=fn)

    p_test = sub.add_parser("test-collectors", help="run one local collection cycle without sending")
    p_test.add_argument("--limit", type=int, default=5, help="sample events to print per collector")
    p_test.set_defaults(func=cmd_test_collectors)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
