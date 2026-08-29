"""
cli.py — Command-Line Interface for the Evaluation Agent SDK.
"""

import sys
import os
import argparse
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

try:
    from .sandbox import create_sandbox
    from .orchestrator import EvalOrchestrator
except (ImportError, ValueError):
    from sandbox import create_sandbox
    from orchestrator import EvalOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("eval-sdk")


def parse_args():
    parser = argparse.ArgumentParser(description="AI Code Evaluation & Self-Healing Agent SDK")
    parser.add_argument("cases", nargs="*", help="Specific case IDs to evaluate (e.g. 1 20). If 'serve', launches the interactive Web console.")
    parser.add_argument("--serve", action="store_true", help="Launch the interactive Human-in-the-Loop web console (FastAPI)")
    parser.add_argument("--port", "-p", type=int, default=8000, help="Port for the HITL web console (default: 8000)")
    parser.add_argument("--concurrency", "-c", type=int, default=5, help="Maximum concurrent cases (default: 5)")
    parser.add_argument("--sandbox", "-s", type=str, default="utm", choices=["utm", "orbstack", "local"], help="Sandbox isolation provider")
    parser.add_argument("--work-dir", "-w", type=str, default=os.getcwd(), help="Root directory of cases and evaluation data")
    parser.add_argument("--no-repair", action="store_true", help="Disable repair and patch verification")
    parser.add_argument("--allow-automatic-repair", action="store_true", help="Allow batch runs to apply patches without per-case HITL approval")
    parser.add_argument("--model", "-m", type=str, default=None, help="LLM model name override (e.g. claude-3-7-sonnet, deepseek-v4-flash)")
    return parser.parse_args()


def load_yaml_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to parse {config_path}: {e}")
        return {}


async def async_main():
    load_dotenv()
    args = parse_args()

    # Check if user wants to seed demo data
    if args.cases and args.cases[0] == "seed":
        try:
            from .seed import seed_demo_cases
        except (ImportError, ValueError):
            from seed import seed_demo_cases
        seed_demo_cases(Path(args.work_dir).resolve())
        return

    # Check if user wants to launch the HITL web console
    if args.serve or (args.cases and args.cases[0] == "serve"):
        try:
            from .server import start_server_async
        except (ImportError, ValueError):
            from server import start_server_async
        await start_server_async(port=args.port)
        return

    work_dir = Path(args.work_dir).resolve()
    cfg = load_yaml_config(work_dir / "eval_config.yaml")

    pipeline_cfg = cfg.get("pipeline", {})
    sandbox_cfg = cfg.get("sandbox", {})
    llm_cfg = cfg.get("llm", {})

    concurrency = args.concurrency if args.concurrency != 5 else pipeline_cfg.get("max_concurrency", 5)
    sandbox_type = args.sandbox if args.sandbox != "utm" else sandbox_cfg.get("type", "utm")
    model_name = args.model or llm_cfg.get("default_model")
    enable_repair = not args.no_repair if args.no_repair else pipeline_cfg.get("enable_auto_repair", True)
    allow_automatic_repair = args.allow_automatic_repair or pipeline_cfg.get("allow_automatic_repair", False)

    # Collect case list
    if args.cases:
        case_ids = args.cases
    else:
        case_ids = []
        for p in sorted(work_dir.iterdir()):
            if p.is_dir() and (p.name.isdigit() or p.name.startswith("case")):
                case_ids.append(p.name)

    if not case_ids:
        logger.warning(f"No case directories found in {work_dir}")
        return

    logger.info(f"Loaded {len(case_ids)} cases to evaluate: {case_ids}")
    logger.info(f"Sandbox Provider: {sandbox_type.upper()} | Max Concurrency: {concurrency} | Model: {model_name}")

    sandbox_kwargs = {}
    if sandbox_type == "utm":
        sandbox_kwargs = sandbox_cfg.get("utm", {})
    elif sandbox_type == "orbstack":
        sandbox_kwargs = sandbox_cfg.get("orbstack", {})

    sandbox = create_sandbox(sandbox_type, **sandbox_kwargs)
    orchestrator = EvalOrchestrator(
        work_dir=str(work_dir),
        sandbox=sandbox,
        max_concurrency=concurrency,
        enable_auto_repair=enable_repair,
        allow_automatic_repair=allow_automatic_repair,
        model_name=model_name
    )

    summaries = await orchestrator.run_batch(case_ids)
    
    # Output summary
    passed = sum(1 for s in summaries if s.overall_verdict == "PASS")
    failed = len(summaries) - passed
    print("\n" + "=" * 60)
    print(f"Evaluation Complete: {passed} PASSED, {failed} FAILED / {len(summaries)} TOTAL")
    print(f"Summary Report: {work_dir}/eval/output.md")
    print(f"HTML Dashboard: {work_dir}/eval/output_viz.html")
    print("=" * 60)


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("\nEvaluation interrupted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
