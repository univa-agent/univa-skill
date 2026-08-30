#!/usr/bin/env python3
"""Codex-native video understanding/editing runner for UniVA.

This complements scripts/codex_video_runner.py. It keeps Codex on the repo-local
skill and MCP-tool path without starting the FastAPI backend for ordinary
terminal-first understanding and editing tasks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

TASK_SKILLS: dict[str, list[str]] = {
    "understand": [
        "AGENTS.md",
        "skills/INDEX.md",
        "skills/agent-integrations/codex-univa-video-ops/SKILL.md",
        "skills/agent-integrations/univa-external-agent-bridge/SKILL.md",
        "skills/meta/understand-pipeline.md",
        "skills/pipelines/video-understand/executive-producer.md",
        "skills/pipelines/video-understand/analyze-director.md",
        "skills/pipelines/video-understand/present-director.md",
        "skills/pipelines/video-understand/refine-director.md",
        "skills/core/video-understanding.md",
        "skills/creative/video-analysis.md",
        "skills/meta/reviewer.md",
        "skills/meta/checkpoint-protocol.md",
        "skills/meta/help-to-make-user.md",
    ],
    "edit": [
        "AGENTS.md",
        "skills/INDEX.md",
        "skills/agent-integrations/codex-univa-video-ops/SKILL.md",
        "skills/agent-integrations/univa-external-agent-bridge/SKILL.md",
        "skills/meta/edit-pipeline.md",
        "skills/pipelines/video-edit/executive-producer.md",
        "skills/pipelines/video-edit/analyze-director.md",
        "skills/pipelines/video-edit/proposal-director.md",
        "skills/pipelines/video-edit/execute-director.md",
        "skills/core/video-editing.md",
        "skills/core/ark-video-reference-upload.md",
        "skills/core/video-understanding.md",
        "skills/creative/editing-strategy.md",
        "skills/creative/video-analysis.md",
        "skills/meta/reviewer.md",
        "skills/meta/checkpoint-protocol.md",
        "skills/meta/help-to-make-user.md",
    ],
}

UNDERSTANDING_PROMPTS = {
    "content": "understanding/video_caption.txt",
    "style": "understanding/video_style_analysis.txt",
    "quality": "understanding/director_check.txt",
    "segment": "understanding/seg_analysis.txt",
    "image": "understanding/image_caption.txt",
}

EDIT_TOOLS = {"depth_modify", "style_transfer", "repainting", "pose_reference"}


def _safe_slug(text: str, limit: int = 48) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", text.strip())[:limit]
    return slug.strip("_") or "video_task"


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _skill_audit(loaded_skills: list[dict[str, str]]) -> list[dict[str, Any]]:
    audit = []
    for item in loaded_skills:
        content = item.get("content", "")
        audit.append(
            {
                "path": item.get("path"),
                "chars": len(content),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
        )
    return audit


def _skill_context_text(
    loaded_skills: list[dict[str, str]],
    *,
    max_total_chars: int = 14000,
    max_file_chars: int = 1200,
) -> str:
    rendered: list[str] = []
    used = 0
    for item in loaded_skills:
        path = item.get("path", "unknown")
        content = (item.get("content") or "").strip()
        if not content:
            continue
        excerpt = content[:max_file_chars].rstrip()
        if len(content) > max_file_chars:
            excerpt += "\n...[truncated; full file recorded in skill_context_full.json]"
        block = f"### {path}\n{excerpt}"
        if used + len(block) > max_total_chars:
            rendered.append("...[additional relevant skills loaded and recorded in skill_context_full.json]")
            break
        rendered.append(block)
        used += len(block)
    return "\n\n".join(rendered) if rendered else "No repo skill context loaded."


def _response_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {"success": False, "message": "Tool returned None."}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return {"success": False, "message": f"Unsupported tool response: {type(value).__name__}"}


def _media_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return "image"
    return "video"


def _load_text(rel_path: str) -> str:
    path = PROJECT_ROOT / rel_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _task_related_skill_paths(task: str, prompt: str, limit: int = 10) -> list[Path]:
    paths = [PROJECT_ROOT / rel for rel in TASK_SKILLS.get(task, [])]
    try:
        from univa.utils.skill_loader import SkillLoader

        loader = SkillLoader(project_root=str(PROJECT_ROOT))
        for skill_path in loader._fallback_skill_match(prompt) + loader.find_skills_for_task(prompt)[:limit]:
            paths.append(PROJECT_ROOT / "skills" / f"{skill_path}.md")
    except Exception:
        pass

    deduped: list[Path] = []
    seen = set()
    for item in paths:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _read_skill_files(task: str, prompt: str, scope: str) -> list[dict[str, str]]:
    if scope == "none":
        return []
    if scope == "all":
        paths = sorted((PROJECT_ROOT / "skills").rglob("*.md")) + [PROJECT_ROOT / "AGENTS.md"]
    else:
        paths = _task_related_skill_paths(task, prompt)

    loaded: list[dict[str, str]] = []
    seen = set()
    for path in paths:
        if not path.exists():
            continue
        rel = str(path.relative_to(PROJECT_ROOT))
        if rel in seen:
            continue
        seen.add(rel)
        loaded.append({"path": rel, "content": path.read_text(encoding="utf-8")})
    return loaded


def _probe_file(path: str | None) -> dict[str, Any]:
    if not path:
        return {"exists": False}
    file_path = Path(path)
    info = {
        "path": str(file_path),
        "exists": file_path.exists(),
        "bytes": file_path.stat().st_size if file_path.exists() else 0,
    }
    if file_path.exists() and file_path.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
        try:
            from univa.mcp_tools.video_gen import _probe_video_duration

            info["duration_seconds"] = _probe_video_duration(str(file_path))
        except Exception as exc:
            info["probe_error"] = str(exc)
    return info


def _select_dimensions(args: argparse.Namespace, media_type: str) -> list[str]:
    if args.dimension:
        return args.dimension
    if media_type == "image":
        return ["image", "style", "quality"]
    lowered = args.prompt.lower()
    dims = ["content", "style", "quality"]
    if any(marker in lowered for marker in ["segment", "timeline", "rhythm", "structure", "shot"]):
        dims.append("segment")
    return dims


def _analysis_prompt(dimension: str, user_prompt: str, skill_context: str = "") -> str:
    rel = UNDERSTANDING_PROMPTS.get(dimension)
    base = _load_text(f"univa/prompts/{rel}") if rel else ""
    if not base:
        base = "Analyze the provided media with concrete, structured, actionable detail."
    return (
        f"{base}\n\n"
        f"Relevant UniVA skill/process constraints:\n{skill_context}\n\n"
        f"User focus: {user_prompt}\n"
        "Return detailed findings that can support downstream generation, editing, or review. "
        "Prefer structured, concrete observations over generic description."
    )


def _select_edit_tool(prompt: str, explicit_tool: str | None) -> str:
    if explicit_tool:
        if explicit_tool not in EDIT_TOOLS:
            raise ValueError(f"Unsupported edit tool: {explicit_tool}. Expected one of {sorted(EDIT_TOOLS)}")
        return explicit_tool
    lowered = prompt.lower()
    if any(marker in lowered for marker in ["repaint", "replace object", "inpaint", "local edit", "object"]):
        return "repainting"
    if any(marker in lowered for marker in ["background replace", "replace background", "foreground", "depth"]):
        return "depth_modify"
    if any(marker in lowered for marker in ["style", "stylize", "watercolor", "anime", "animation", "oil painting"]):
        return "style_transfer"
    if any(marker in lowered for marker in ["pose reference", "motion reference", "dance reference"]):
        return "pose_reference"
    return "style_transfer"


def _extract_label(prompt: str, explicit_label: str | None) -> str | None:
    if explicit_label:
        return explicit_label
    patterns = [
        r"label\s*[:：]\s*([A-Za-z0-9_\- ]+)",
        r"replace\s+(?:the\s+)?([A-Za-z0-9_\- ]+?)\s+(?:with|as)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return match.group(1).strip(" :,")
    return None


def _build_edit_proposal(
    args: argparse.Namespace,
    analysis: dict[str, Any] | None = None,
    skill_context: str = "",
) -> dict[str, Any]:
    tool_name = _select_edit_tool(args.prompt, args.edit_tool)
    label = _extract_label(args.prompt, args.label)
    if tool_name == "repainting" and not label:
        return {
            "success": False,
            "blocked": True,
            "reason": "repainting requires a concrete --label identifying the object to edit.",
        }
    if tool_name == "pose_reference" and not (args.media or args.image):
        return {
            "success": False,
            "blocked": True,
            "reason": "pose_reference requires --media video or --image pose reference.",
        }

    params: dict[str, Any] = {"prompt": args.prompt}
    if tool_name in {"depth_modify", "style_transfer", "repainting"}:
        params["video"] = str(Path(args.media).resolve())
    if tool_name == "repainting":
        params["label"] = label
    if tool_name == "pose_reference":
        if args.image:
            params["image"] = str(Path(args.image).resolve())
        if args.media:
            params["video"] = str(Path(args.media).resolve())

    return {
        "success": True,
        "source_path": str(Path(args.media).resolve()) if args.media else None,
        "analysis_used": bool(analysis),
        "tool_name": tool_name,
        "parameters": params,
        "expected_outcome": args.prompt,
        "skill_context_applied": bool(skill_context),
        "prompt_policy": "Use the complete approved edit prompt and parameters; do not reduce the task to style keywords.",
        "approval_required": True,
        "quality_checks": [
            "source file exists",
            "tool parameters match core/video-editing contract",
            "output_path must be absolute and verified after execution",
            "edited result should preserve requested source structure unless explicitly changed",
        ],
    }


def _write_review(run_dir: Path, task: str, payload: dict[str, Any]) -> Path:
    review_path = run_dir / ("edit_proposal_review.json" if task == "edit" else "understanding_review.json")
    _write_json(review_path, payload)
    return review_path


def _run_understand(
    args: argparse.Namespace,
    run_dir: Path,
    loaded_skills: list[dict[str, str]],
    skill_context: str,
) -> dict[str, Any]:
    if not args.media:
        raise RuntimeError("--media is required for understand tasks.")
    media_path = Path(args.media).resolve()
    if not media_path.exists():
        raise RuntimeError(f"Media path does not exist: {media_path}")

    media_type = _media_type(str(media_path))
    dimensions = _select_dimensions(args, media_type)
    plan = {
        "task": "understand",
        "prompt": args.prompt,
        "source_path": str(media_path),
        "media_type": media_type,
        "dimensions": dimensions,
        "pipeline_alignment": "video-understand: analyze -> present -> refine",
        "tool": "vision2text_gen",
    }
    _write_json(run_dir / "understanding_plan.json", plan)

    if args.dry_run:
        review = {
            "status": "planned",
            "plan_path": str(run_dir / "understanding_plan.json"),
            "skill_context_path": str(run_dir / "skill_context.json"),
            "skill_context_full_path": str(run_dir / "skill_context_full.json"),
            "message": "Dry run only; vision2text_gen was not called.",
        }
        review_path = _write_review(run_dir, "understand", review)
        return {"success": True, "mode": "dry_run", "run_dir": str(run_dir), "review_path": str(review_path), "loaded_skills": _skill_audit(loaded_skills), "skill_context_full_path": str(run_dir / "skill_context_full.json")}

    from univa.mcp_tools.video_understanding import vision2text_gen

    findings: dict[str, Any] = {}
    for dimension in dimensions:
        result = _response_to_dict(
            vision2text_gen(
                prompt=_analysis_prompt(dimension, args.prompt, skill_context),
                multimodal_path=str(media_path),
                type=media_type,
            )
        )
        findings[dimension] = result
        _write_json(run_dir / "raw_analysis.json", {"source_path": str(media_path), "media_type": media_type, "findings": findings})
        if not result.get("success"):
            break

    raw_analysis = {"source_path": str(media_path), "media_type": media_type, "findings": findings}
    structured_report = {
        "source_path": str(media_path),
        "media_probe": _probe_file(str(media_path)),
        "dimensions": dimensions,
        "summary": {key: value.get("content") or value.get("message") for key, value in findings.items()},
        "refine_prompt": "User may provide supplemental focus and rerun with --dimension or a more specific --prompt.",
    }
    _write_json(run_dir / "raw_analysis.json", raw_analysis)
    _write_json(run_dir / "structured_report.json", structured_report)
    review_path = _write_review(run_dir, "understand", {"status": "completed", "structured_report_path": str(run_dir / "structured_report.json")})
    report = {
        "success": all(_response_to_dict(value).get("success") for value in findings.values()),
        "mode": "codex_direct_understand",
        "run_dir": str(run_dir),
        "loaded_skills": _skill_audit(loaded_skills),
        "skill_context_full_path": str(run_dir / "skill_context_full.json"),
        "plan_path": str(run_dir / "understanding_plan.json"),
        "raw_analysis_path": str(run_dir / "raw_analysis.json"),
        "structured_report_path": str(run_dir / "structured_report.json"),
        "review_path": str(review_path),
    }
    _write_json(run_dir / "delivery_report.json", report)
    return report


def _run_edit(
    args: argparse.Namespace,
    run_dir: Path,
    loaded_skills: list[dict[str, str]],
    skill_context: str,
) -> dict[str, Any]:
    if args.approved_plan:
        proposal = _read_json(args.approved_plan)
        if not isinstance(proposal, dict):
            raise RuntimeError("Approved edit plan is not a JSON object.")
        _write_json(run_dir / "edit_proposal.json", proposal)
    else:
        if not args.media:
            raise RuntimeError("--media is required for edit tasks.")
        media_path = Path(args.media).resolve()
        if not media_path.exists():
            raise RuntimeError(f"Media path does not exist: {media_path}")
        analysis = None
        if not args.skip_analysis and not args.dry_run:
            from univa.mcp_tools.video_understanding import vision2text_gen

            analysis = _response_to_dict(
                vision2text_gen(
                    prompt=_analysis_prompt("content", f"Analyze source media before editing. Edit request: {args.prompt}", skill_context),
                    multimodal_path=str(media_path),
                    type=_media_type(str(media_path)),
                )
            )
            _write_json(run_dir / "media_analysis.json", analysis)
        proposal = _build_edit_proposal(args, analysis=analysis, skill_context=skill_context)
        _write_json(run_dir / "edit_proposal.json", proposal)

    review_payload = {
        "status": "awaiting_human" if not args.approved_plan else "approved",
        "interaction_type": "edit_proposal_approval",
        "proposal_path": str(run_dir / "edit_proposal.json"),
        "proposal": proposal,
        "instructions": {
            "approve": "Rerun with --approved-plan pointing at edit_proposal.json.",
            "revise": "Edit edit_proposal.json or rerun with a clearer --prompt/--edit-tool/--label.",
            "block": "Do not call video editing tools until proposal is approved.",
        },
    }
    review_path = _write_review(run_dir, "edit", review_payload)

    if args.dry_run or (not args.approved_plan and not args.auto_approve):
        report = {
            "success": True,
            "mode": "codex_direct_edit_review",
            "stage": "awaiting_edit_proposal_approval",
            "run_dir": str(run_dir),
            "loaded_skills": _skill_audit(loaded_skills),
            "skill_context_full_path": str(run_dir / "skill_context_full.json"),
            "proposal_path": str(run_dir / "edit_proposal.json"),
            "review_path": str(review_path),
        }
        _write_json(run_dir / "delivery_report.json", report)
        return report

    if not proposal.get("success"):
        raise RuntimeError(proposal.get("reason") or "Edit proposal is not executable.")

    tool_name = proposal.get("tool_name")
    params = proposal.get("parameters") or {}
    if tool_name not in EDIT_TOOLS:
        raise RuntimeError(f"Unsupported approved edit tool: {tool_name}")

    from univa.mcp_tools.video_editing import depth_modify, pose_reference, repainting, style_transfer

    tool_map = {
        "depth_modify": depth_modify,
        "style_transfer": style_transfer,
        "repainting": repainting,
        "pose_reference": pose_reference,
    }
    result = _response_to_dict(tool_map[tool_name](**params))
    if result.get("output_path"):
        result["probe"] = _probe_file(result.get("output_path"))
    _write_json(run_dir / "edit_result.json", result)

    report = {
        "success": bool(result.get("success")),
        "mode": "codex_direct_edit",
        "run_dir": str(run_dir),
        "loaded_skills": _skill_audit(loaded_skills),
        "skill_context_full_path": str(run_dir / "skill_context_full.json"),
        "proposal_path": str(run_dir / "edit_proposal.json"),
        "review_path": str(review_path),
        "edit_result_path": str(run_dir / "edit_result.json"),
        "final": result,
    }
    _write_json(run_dir / "delivery_report.json", report)
    if not result.get("success"):
        raise RuntimeError(result.get("error") or result.get("message") or "Edit tool failed.")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run UniVA video understanding/editing directly from Codex without the backend server.")
    parser.add_argument("--task", choices=["understand", "edit"], required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--media", help="Source image/video path.")
    parser.add_argument("--image", help="Optional image reference for pose_reference.")
    parser.add_argument("--dimension", action="append", choices=sorted(UNDERSTANDING_PROMPTS), help="Understanding dimension. Can be repeated.")
    parser.add_argument("--edit-tool", choices=sorted(EDIT_TOOLS), help="Explicit editing tool to use.")
    parser.add_argument("--label", help="Object label for repainting.")
    parser.add_argument("--approved-plan", help="Approved edit_proposal.json path for edit execution.")
    parser.add_argument("--auto-approve", action="store_true", help="Bypass edit proposal review. Intended for tests or explicit pre-approval.")
    parser.add_argument("--skip-analysis", action="store_true", help="Skip pre-edit vision analysis when creating edit proposal.")
    parser.add_argument("--skills-scope", choices=["relevant", "all", "none"], default="relevant")
    parser.add_argument("--output-dir")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    run_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else PROJECT_ROOT / "results" / f"codex_direct_{args.task}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_safe_slug(args.prompt)}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    loaded_skills = _read_skill_files(args.task, args.prompt, args.skills_scope)
    _write_json(run_dir / "skill_context.json", _skill_audit(loaded_skills))
    _write_json(run_dir / "skill_context_full.json", loaded_skills)
    skill_context = _skill_context_text(loaded_skills)

    try:
        if args.task == "understand":
            report = _run_understand(args, run_dir, loaded_skills, skill_context)
        else:
            report = _run_edit(args, run_dir, loaded_skills, skill_context)
    except Exception as exc:
        failure = {
            "success": False,
            "mode": f"codex_direct_{args.task}",
            "run_dir": str(run_dir),
            "loaded_skills": _skill_audit(loaded_skills),
            "skill_context_full_path": str(run_dir / "skill_context_full.json"),
            "error": str(exc),
        }
        _write_json(run_dir / "delivery_report.json", failure)
        raise SystemExit(f"codex video task runner failed: {exc}") from exc

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
