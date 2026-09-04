#!/usr/bin/env python3
"""Small UniVA API client for terminal-first coding agents.

It intentionally talks to the existing FastAPI server instead of duplicating
PlanAgent/ActAgent behavior. Start the server first, then use this script from
repo root.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from typing import Any

import requests


DEFAULT_BASE_URL = os.environ.get("UNIVA_AGENT_API", "http://127.0.0.1:8000")


def _headers(access_code: str | None = None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if access_code:
        headers["X-Access-Code"] = access_code
    return headers


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _request(method: str, url: str, **kwargs: Any) -> requests.Response:
    try:
        response = requests.request(method, url, timeout=kwargs.pop("timeout", 30), **kwargs)
    except requests.RequestException as exc:
        raise SystemExit(f"Request failed: {exc}") from exc
    if response.status_code >= 400:
        raise SystemExit(f"HTTP {response.status_code}: {response.text[:2000]}")
    return response


def cmd_health(args: argparse.Namespace) -> None:
    response = _request("GET", f"{args.base_url}/health")
    _print_json(response.json())


def cmd_skills(args: argparse.Namespace) -> None:
    params = {"category": args.category} if args.category else None
    response = _request("GET", f"{args.base_url}/skills", params=params, headers=_headers(args.access_code))
    _print_json(response.json())


def cmd_skill(args: argparse.Namespace) -> None:
    response = _request("GET", f"{args.base_url}/skills/{args.skill_path}", headers=_headers(args.access_code))
    data = response.json()
    if args.content_only:
        print(data.get("content", ""))
    else:
        _print_json(data)


def cmd_pipelines(args: argparse.Namespace) -> None:
    response = _request("GET", f"{args.base_url}/pipelines", headers=_headers(args.access_code))
    _print_json(response.json())


def cmd_pipeline(args: argparse.Namespace) -> None:
    response = _request("GET", f"{args.base_url}/pipelines/{args.pipeline_name}", headers=_headers(args.access_code))
    _print_json(response.json())


def _iter_sse_json(response: requests.Response):
    for raw in response.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        payload = raw[5:].strip()
        if not payload:
            continue
        try:
            yield json.loads(payload)
        except json.JSONDecodeError:
            yield {"type": "raw", "content": payload}


def cmd_chat(args: argparse.Namespace) -> None:
    session_id = args.session_id or str(uuid.uuid4())
    payload: dict[str, Any] = {
        "prompt": args.prompt,
        "session_id": session_id,
    }
    if args.project_id:
        payload["project_id"] = args.project_id
    if args.project_name:
        payload["project_name"] = args.project_name

    headers = _headers(args.access_code)
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "text/event-stream"
    if args.client == "editor":
        headers["X-UniVA-Client"] = "editor"

    response = _request(
        "POST",
        f"{args.base_url}/chat/stream",
        headers=headers,
        json=payload,
        stream=True,
        timeout=args.timeout,
    )

    last_event = None
    for event in _iter_sse_json(response):
        last_event = event
        if args.raw:
            _print_json(event)
            continue
        event_type = event.get("type", "event")
        content = event.get("content") or event.get("message") or event.get("stage") or ""
        if event_type in {
            "content", "error", "pre_generation_gate", "pipeline_suspended",
            "pipeline_complete", "finish",
        }:
            print(f"[{event_type}] {content}")
            if event_type in {"pre_generation_gate", "pipeline_suspended"}:
                _print_json(event)
        elif args.verbose:
            _print_json(event)

    if args.show_session:
        print(f"session_id={session_id}", file=sys.stderr)
    if last_event is None:
        print("No SSE events received", file=sys.stderr)


def cmd_resume(args: argparse.Namespace) -> None:
    payload = {
        "session_id": args.session_id,
        "continuation_token": args.continuation_token or "",
        "user_input": args.user_input,
    }
    headers = _headers(args.access_code)
    headers["Content-Type"] = "application/json"
    response = _request("POST", f"{args.base_url}/chat/resume", headers=headers, json=payload, timeout=args.timeout)
    _print_json(response.json())


def cmd_pipeline_state(args: argparse.Namespace) -> None:
    response = _request("GET", f"{args.base_url}/chat/pipeline/{args.session_id}", headers=_headers(args.access_code))
    _print_json(response.json())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UniVA API client for external coding agents")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--access-code", default=os.environ.get("UNIVA_ACCESS_CODE"))
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("health")
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("skills")
    p.add_argument("--category")
    p.set_defaults(func=cmd_skills)

    p = sub.add_parser("skill")
    p.add_argument("skill_path")
    p.add_argument("--content-only", action="store_true")
    p.set_defaults(func=cmd_skill)

    p = sub.add_parser("pipelines")
    p.set_defaults(func=cmd_pipelines)

    p = sub.add_parser("pipeline")
    p.add_argument("pipeline_name")
    p.set_defaults(func=cmd_pipeline)

    p = sub.add_parser("chat")
    p.add_argument("--prompt", required=True)
    p.add_argument("--session-id")
    p.add_argument("--project-id")
    p.add_argument("--project-name")
    p.add_argument("--client", choices=["api", "editor"], default="api")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--raw", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--show-session", action="store_true")
    p.set_defaults(func=cmd_chat)

    p = sub.add_parser("resume")
    p.add_argument("--session-id", required=True)
    p.add_argument("--user-input", required=True)
    p.add_argument("--continuation-token", required=True)
    p.add_argument("--timeout", type=int, default=900)
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("pipeline-state")
    p.add_argument("--session-id", required=True)
    p.set_defaults(func=cmd_pipeline_state)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
