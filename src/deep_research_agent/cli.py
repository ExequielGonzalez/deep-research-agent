from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Sequence

from deep_research_agent.domain.models import HumanDecisionType, ResearchRequest
from deep_research_agent.runtime.service import ResearchRuntimeService, RunNotFoundError, render_json
from deep_research_agent.settings import AppSettings, resolve_runtime_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deep-research-agent", description="CLI for the deep research agent MVP runtime.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Start a new research run.")
    run_parser.add_argument("--query", required=True, help="Research question or objective.")
    run_parser.add_argument("--audience", default="general")
    run_parser.add_argument("--objective")
    run_parser.add_argument("--constraint", action="append", default=[])
    run_parser.add_argument("--deliverable-format", default="markdown")
    run_parser.add_argument("--max-iterations", type=int)

    resume_parser = subparsers.add_parser("resume", help="Resume a persisted research thread.")
    resume_parser.add_argument("--thread-id", required=True)
    resume_parser.add_argument("--decision", required=True, choices=[choice.value for choice in HumanDecisionType])
    resume_parser.add_argument("--summary", default="")
    resume_parser.add_argument("--payload-json")

    list_parser = subparsers.add_parser("list-pending", help="List interrupted runs waiting for human input.")
    list_parser.add_argument("--limit", type=int, default=20)

    return parser


async def amain(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    settings = resolve_runtime_settings(AppSettings())
    service = ResearchRuntimeService(settings)

    try:
        if args.command == "run":
            request = ResearchRequest(
                query=args.query,
                audience=args.audience,
                objective=args.objective,
                constraints=args.constraint,
                deliverable_format=args.deliverable_format,
            )
            result = await service.start_run(request, max_iterations=args.max_iterations)
            print(render_json(result.model_dump(mode="json")))
            return 0

        if args.command == "resume":
            payload = json.loads(args.payload_json) if args.payload_json else None
            result = await service.resume_run(
                thread_id=args.thread_id,
                decision_type=HumanDecisionType(args.decision),
                summary=args.summary,
                payload=payload,
            )
            print(render_json(result.model_dump(mode="json")))
            return 0

        pending_runs = await service.list_pending_runs(limit=args.limit)
        print(render_json({"count": len(pending_runs), "runs": [run.model_dump(mode="json") for run in pending_runs]}))
        return 0
    except RunNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(amain(argv))
