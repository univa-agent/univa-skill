#!/usr/bin/env python3
"""Codex-native video generation runner for UniVA.

This script is intentionally not a FastAPI client. It lets a terminal-first
agent use the repo skills for planning, then call the existing UniVA tool
functions directly in-process.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORYBOARD_REVIEW_SCHEMA_VERSION = 2
DEFAULT_SKILL_FILES = [
    "AGENTS.md",
    "skills/INDEX.md",
    "skills/agent-integrations/codex-univa-video-ops/SKILL.md",
    "skills/agent-integrations/univa-external-agent-bridge/SKILL.md",
    "skills/meta/generate-pipeline.md",
    "skills/creative/creative-brief.md",
    "skills/creative/copywriting.md",
    "skills/creative/styleframe-direction.md",
    "skills/creative/energy-arc.md",
    "skills/creative/shot-recipe-library.md",
    "skills/creative/duration-planning.md",
    "skills/creative/material-matching.md",
    "skills/creative/transition-sound-caption.md",
    "skills/creative/remotion-packaging.md",
    "skills/creative/creative-quality-gate.md",
    "skills/creative/shot-planning.md",
    "skills/creative/asset-generation.md",
    "skills/core/prompt-validator.md",
    "skills/core/wavespeed-video-gen.md",
    "skills/core/ffmpeg-merge.md",
    "skills/core/remotion-compose.md",
    "skills/core/audio-gen.md",
]


def _safe_slug(text: str, limit: int = 48) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", text.strip())[:limit]
    return slug.strip("_") or "video"


def _response_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {"success": False, "error": "Tool returned None."}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return {"success": False, "error": f"Unsupported tool response: {type(value).__name__}"}


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
    max_total_chars: int = 18000,
    max_file_chars: int = 1400,
) -> str:
    """Create a bounded instruction bundle for the planning LLM."""
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


def _task_related_skill_paths(prompt: str, limit: int = 12) -> list[Path]:
    required = [
        "skills/meta/generate-pipeline.md",
        "skills/meta/help-to-make-user.md",
        "skills/meta/checkpoint-protocol.md",
        "skills/core/prompt-validator.md",
        "skills/core/wavespeed-video-gen.md",
        "skills/creative/video-gen-prompting.md",
        "skills/creative/shot-planning.md",
        "skills/creative/duration-planning.md",
        "skills/creative/creative-quality-gate.md",
        "skills/creative/asset-generation.md",
    ]
    paths = [PROJECT_ROOT / rel for rel in required]
    try:
        from univa.utils.skill_loader import SkillLoader

        loader = SkillLoader(project_root=str(PROJECT_ROOT))
        for skill_path in loader._fallback_skill_match(prompt) + loader.find_skills_for_task(prompt)[:limit]:
            paths.append(PROJECT_ROOT / "skills" / f"{skill_path}.md")
    except Exception:
        pass

    deduped = []
    seen = set()
    for item in paths:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _read_skill_files(scope: str, prompt: str = "") -> list[dict[str, str]]:
    if scope == "none":
        return []
    if scope == "all":
        paths = sorted((PROJECT_ROOT / "skills").rglob("*.md"))
        paths.extend([PROJECT_ROOT / "AGENTS.md"])
    else:
        paths = [PROJECT_ROOT / rel for rel in DEFAULT_SKILL_FILES]
        paths.extend(_task_related_skill_paths(prompt))

    loaded: list[dict[str, str]] = []
    seen = set()
    for path in paths:
        if not path.exists():
            continue
        rel = str(path.relative_to(PROJECT_ROOT))
        if rel in seen:
            continue
        seen.add(rel)
        loaded.append(
            {
                "path": rel,
                "content": path.read_text(encoding="utf-8"),
            }
        )
    return loaded


def _probe(path: str | None) -> dict[str, Any]:
    if not path:
        return {"exists": False}
    file_path = Path(path)
    info: dict[str, Any] = {
        "path": str(file_path),
        "exists": file_path.exists(),
        "bytes": file_path.stat().st_size if file_path.exists() else 0,
    }
    try:
        from univa.mcp_tools.video_gen import _probe_video_duration

        info["duration_seconds"] = _probe_video_duration(str(file_path))
    except Exception as exc:
        info["probe_error"] = str(exc)
    return info


def _strip_audio(video_path: str | None, run_dir: Path) -> dict[str, Any]:
    if not video_path:
        return {"success": False, "error": "No video path to strip."}
    source = Path(video_path)
    if not source.exists():
        return {"success": False, "error": f"Video path does not exist: {source}"}
    output_path = run_dir / f"{source.stem}_silent{source.suffix}"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-an",
        "-c:v",
        "copy",
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0 or not output_path.exists():
        return {
            "success": False,
            "error": completed.stderr.strip() or "ffmpeg audio stripping failed",
            "source_path": str(source),
            "output_path": str(output_path),
        }
    return {
        "success": True,
        "source_path": str(source),
        "output_path": str(output_path),
        "message": "Audio stream stripped for silent delivery.",
    }


def _shot_prompt(shot: dict[str, Any], *, allow_fallback: bool = False) -> str:
    prompt = str(shot.get("expanded_generation_prompt") or "").strip()
    if prompt or not allow_fallback:
        return prompt
    return str(shot.get("visual_prompt") or shot.get("scene_blueprint") or "").strip()


def _shot_duration(shot: dict[str, Any]) -> int | float | None:
    timing = shot.get("timing") if isinstance(shot.get("timing"), dict) else {}
    return (
        shot.get("duration_seconds")
        or shot.get("duration_sec")
        or shot.get("duration")
        or timing.get("duration_seconds")
        or timing.get("duration_sec")
        or timing.get("duration")
    )

def _shot_aspect_ratio(plan: dict[str, Any], shot: dict[str, Any], fallback: str = "16:9") -> str:
    return str(shot.get("aspect_ratio") or plan.get("aspect_ratio") or fallback)


def _generation_handoff(plan: dict[str, Any], *, fallback_aspect_ratio: str = "16:9") -> dict[str, Any]:
    requests = []
    for index, shot in enumerate(plan.get("shots") or [], start=1):
        if not isinstance(shot, dict):
            continue
        prompt = _shot_prompt(shot)
        requests.append(
            {
                "shot_id": shot.get("id") or shot.get("shot_id") or f"shot_{index:02d}",
                "generation_tool": shot.get("generation_tool") or "text2video_gen",
                "prompt_field": "shots[*].expanded_generation_prompt",
                "prompt": prompt,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "generation_contract_sha256": shot.get("generation_contract_sha256"),
                "duration_seconds": _shot_duration(shot),
                "aspect_ratio": _shot_aspect_ratio(plan, shot, fallback_aspect_ratio),
                "image_path": shot.get("image_path") or shot.get("reference_image") or shot.get("keyframe_path"),
            }
        )
    return {
        "schema_version": 1,
        "status": "frozen_provider_requests",
        "plan_prompt_set_sha256": (plan.get("generation_contract") or {}).get("plan_prompt_set_sha256"),
        "rule": "Each request.prompt is exactly the reviewed expanded_generation_prompt and is not rewritten at execution.",
        "requests": requests,
    }


def _wants_voiceover(prompt: str) -> bool:
    lowered = prompt.lower()
    negative_markers = [
        "no voiceover", "no narration", "without voiceover", "without narration",
        "无旁白", "不要旁白", "无解说", "不要解说", "不要配音",
    ]
    if any(marker in lowered for marker in negative_markers):
        return False
    markers = [
        "voiceover",
        "narration",
        "spoken",
        "dialogue",
        "旁白",
        "解说",
        "配音",
        "对白",
    ]
    return any(marker in lowered for marker in markers)


def _wants_no_audio(prompt: str) -> bool:
    lowered = prompt.lower()
    markers = ["mute", "silent", "no audio", "without audio", "静音", "无音频", "无声音", "不要声音"]
    return any(marker in lowered for marker in markers)


def _wants_no_music(prompt: str) -> bool:
    lowered = prompt.lower()
    markers = [
        "no music", "no bgm", "without music", "无音乐", "不要音乐", "没有音乐", "不要bgm", "无bgm",
        "无旁白或音乐", "无解说或音乐", "无配音或音乐",
    ]
    return any(marker in lowered for marker in markers)


def _wants_no_sfx(prompt: str) -> bool:
    lowered = prompt.lower()
    markers = ["no sfx", "no sound effects", "without sound effects", "无音效", "不要音效", "没有音效"]
    return any(marker in lowered for marker in markers)


def _wants_caption_packaging(prompt: str) -> bool:
    lowered = prompt.lower()
    negative_markers = [
        "no captions",
        "no subtitles",
        "without captions",
        "without subtitles",
        "无字幕",
        "不要字幕",
        "不配字幕",
    ]
    if any(marker in lowered for marker in negative_markers):
        return False
    markers = [
        "caption",
        "captions",
        "subtitle",
        "subtitles",
        "cta",
        "lower-third",
        "title card",
        "selling point card",
        "字幕",
        "宣传字幕",
        "标题卡",
        "卖点卡",
    ]
    return any(marker in lowered for marker in markers)


def _plan_has_caption_packaging(plan: dict[str, Any]) -> bool:
    remotion_handoff = plan.get("remotion_handoff") if isinstance(plan.get("remotion_handoff"), dict) else {}
    edit_decisions = plan.get("edit_decisions") if isinstance(plan.get("edit_decisions"), dict) else {}
    edit_handoff = edit_decisions.get("remotion_handoff") if isinstance(edit_decisions.get("remotion_handoff"), dict) else {}
    return bool(
        (plan.get("caption_plan") if isinstance(plan.get("caption_plan"), list) else None)
        or (plan.get("visual_overlays") if isinstance(plan.get("visual_overlays"), list) else None)
        or (remotion_handoff if remotion_handoff.get("enabled") or remotion_handoff.get("captions") else None)
        or (edit_handoff if edit_handoff.get("enabled") or edit_handoff.get("captions") else None)
    )


def _caption_packaging_defaults(total_duration_seconds: float, prompt: str, plan: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    total = max(4.0, float(total_duration_seconds or 5.0))
    lowered = prompt.lower()
    electric_markers = ["electric", "ev", "electric vehicle", "car", "sedan", "电车", "电动", "新能源"]
    if any(marker in lowered for marker in electric_markers):
        if any(marker in prompt for marker in ("电车", "电动", "新能源")):
            title = "电感出发"
            subtitle = "城市智能出行新姿态"
            lead = "电感出发"
            body = "动态响应 即刻到位"
            cta = "即刻预约体验"
            brand_name = "EV"
        else:
            title = "Electric Start"
            subtitle = "A new way to move through the city"
            lead = "Electric Start"
            body = "Instant response for city driving"
            cta = "Book a test drive"
            brand_name = "EV"
    else:
        subject = plan.get("title") or plan.get("preliminary_video_info", {}).get("core_message") or "Launch with energy"
        title = str(subject)[:12] or "Launch with energy"
        subtitle = "Premium texture with motion"
        lead = title
        body = "Clear dynamic selling points"
        cta = "Book a test drive"
        brand_name = "UniVA"

    lead_end = round(min(max(total * 0.32, 1.2), total - 2.0), 1)
    body_end = round(min(max(total * 0.72, lead_end + 1.2), total - 1.0), 1)
    if body_end <= lead_end:
        body_end = round(min(total - 1.0, lead_end + 1.6), 1)
    if body_end <= lead_end:
        body_end = round(total - 1.2, 1)
    if body_end <= lead_end:
        body_end = round(min(total - 0.8, lead_end + 0.8), 1)

    caption_plan = [
        {"text": lead, "start_seconds": 0.2, "end_seconds": lead_end},
        {"text": body, "start_seconds": lead_end, "end_seconds": body_end},
        {"text": cta, "start_seconds": body_end, "end_seconds": round(total, 1)},
    ]
    remotion_handoff = {
        "enabled": True,
        "reason": "User requested promotional subtitles; use deterministic post-production captions and CTA packaging.",
        "title": title,
        "subtitle": subtitle,
        "brand": {"name": brand_name},
        "captions": caption_plan,
        "overlays": [
            {
                "type": "cta",
                "text": cta,
                "start_seconds": body_end,
                "end_seconds": round(total, 1),
                "position": "bottom_center",
            }
        ],
        "fallback_to_ffmpeg_subtitles": True,
        "show_progress": True,
        "fit": "cover",
    }
    return caption_plan, remotion_handoff


def _apply_caption_packaging(plan: dict[str, Any], args: argparse.Namespace, *, approved_plan: bool) -> dict[str, Any]:
    if not _wants_caption_packaging(args.prompt):
        return plan

    existing_caption_plan = plan.get("caption_plan") if isinstance(plan.get("caption_plan"), list) else None
    existing_remotion = plan.get("remotion_handoff") if isinstance(plan.get("remotion_handoff"), dict) else {}

    if approved_plan and not existing_caption_plan and not existing_remotion.get("enabled"):
        raise RuntimeError(
            "Approved plan does not include the required caption_plan/remotion_handoff for a subtitle request. "
            "Replan and approve the captioned storyboard before generation."
        )

    if existing_caption_plan and existing_remotion.get("enabled"):
        return plan

    total_duration = float(plan.get("target_duration_seconds") or args.duration or 5.0)
    caption_plan, remotion_handoff = _caption_packaging_defaults(total_duration, args.prompt, plan)
    plan["caption_plan"] = existing_caption_plan or caption_plan

    merged_handoff = dict(existing_remotion) if existing_remotion else {}
    merged_handoff.setdefault("enabled", True)
    merged_handoff.setdefault("reason", remotion_handoff["reason"])
    merged_handoff.setdefault("title", remotion_handoff["title"])
    merged_handoff.setdefault("subtitle", remotion_handoff["subtitle"])
    merged_handoff.setdefault("brand", remotion_handoff["brand"])
    merged_handoff.setdefault("captions", plan["caption_plan"])
    merged_handoff.setdefault("overlays", remotion_handoff["overlays"])
    merged_handoff.setdefault("fallback_to_ffmpeg_subtitles", True)
    merged_handoff.setdefault("show_progress", True)
    merged_handoff.setdefault("fit", "cover")
    plan["remotion_handoff"] = merged_handoff
    return plan


def _remotion_handoff_from_plan(plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    handoff = plan.get("remotion_handoff") if isinstance(plan.get("remotion_handoff"), dict) else {}
    if not handoff:
        edit_decisions = plan.get("edit_decisions") if isinstance(plan.get("edit_decisions"), dict) else {}
        handoff = edit_decisions.get("remotion_handoff") if isinstance(edit_decisions.get("remotion_handoff"), dict) else {}

    enabled = bool(handoff.get("enabled")) or bool(args.remotion_compose) or _plan_has_caption_packaging(plan)
    if args.no_remotion:
        enabled = False

    title = args.remotion_title or handoff.get("title") or plan.get("title")
    subtitle = args.remotion_subtitle or handoff.get("subtitle") or plan.get("subtitle")
    brand = handoff.get("brand") if isinstance(handoff.get("brand"), dict) else {}
    if args.remotion_brand:
        brand = {**brand, "name": args.remotion_brand}

    return {
        **handoff,
        "enabled": enabled,
        "reason": (
            handoff.get("reason")
            or ("CLI requested Remotion final packaging." if enabled else "Remotion packaging not requested by approved plan or CLI.")
        ),
        "title": title,
        "subtitle": subtitle,
        "brand": brand,
        "theme": handoff.get("theme"),
        "show_progress": handoff.get("show_progress", True),
        "fit": handoff.get("fit", "cover"),
        "browser_executable_path": args.remotion_browser_executable or handoff.get("browser_executable_path"),
        "binaries_directory": args.remotion_binaries_directory or handoff.get("binaries_directory") or handoff.get("remotion_binaries_directory"),
        "fallback_to_ffmpeg_subtitles": False if args.no_remotion_ffmpeg_fallback else handoff.get("fallback_to_ffmpeg_subtitles"),
    }


def _approved_audio_context(user_prompt: str, plan: dict[str, Any]) -> str:
    preliminary = plan.get("preliminary_video_info") if isinstance(plan.get("preliminary_video_info"), dict) else {}
    shots = []
    for index, shot in enumerate(plan.get("shots") or [], start=1):
        if not isinstance(shot, dict):
            continue
        shots.append(
            {
                "shot_id": shot.get("id") or shot.get("shot_id") or f"shot_{index:02d}",
                "duration_seconds": _shot_duration(shot),
                "creative_generation_prompt": shot.get("creative_generation_prompt"),
                "negative_constraints": shot.get("negative_constraints"),
                "transition_context": shot.get("transition_context"),
            }
        )
    audio_context = {
        "user_request": user_prompt,
        "hard_constraints": preliminary.get("hard_constraints"),
        "audio_plan": plan.get("audio_plan"),
        "timeline_plan": plan.get("timeline_plan"),
        "transitions": plan.get("transitions"),
        "shots": shots,
    }
    return (
        "Generate only the audio explicitly allowed by this approved plan. Do not add music, sound "
        "effects, ambience, speech, or narration that the plan excludes. Keep timing aligned to shot "
        "durations and transitions. APPROVED_AUDIO_CONTEXT_JSON: "
        + json.dumps(audio_context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _research_queries(prompt: str) -> list[str]:
    normalized = " ".join(prompt.split())
    short_prompt = normalized[:120]
    return [
        f"{short_prompt} visual reference facts",
        f"{short_prompt} current context official sources",
        f"{short_prompt} places people objects production design references",
    ]


def _collect_research_brief(args: argparse.Namespace) -> dict[str, Any]:
    notes: list[dict[str, Any]] = []
    for note in args.research_note or []:
        text = str(note).strip()
        if text:
            notes.append({"type": "note", "source": "cli", "content": text})

    for research_file in args.research_file or []:
        file_path = Path(research_file).resolve()
        if not file_path.exists():
            notes.append({"type": "missing_file", "source": str(file_path), "content": ""})
            continue
        if file_path.suffix.lower() == ".json":
            notes.append({"type": "json_file", "source": str(file_path), "content": _read_json(file_path)})
        else:
            notes.append({"type": "text_file", "source": str(file_path), "content": file_path.read_text(encoding="utf-8")})

    return {
        "status": "provided" if notes else "missing_external_research",
        "external_research_required": not bool(notes),
        "suggested_queries": _research_queries(args.prompt),
        "notes": notes,
        "policy": (
            "Before media generation, the operating agent should search current and domain-relevant "
            "references for the user's subject, summarize useful factual/visual context, and pass it "
            "with --research-note or --research-file. Missing research is allowed only for local/offline "
            "tests or when an already approved plan is supplied."
        ),
    }


def _research_context_text(research_brief: dict[str, Any]) -> str:
    if not research_brief.get("notes"):
        return (
            "No external research notes were supplied. Treat this as a draft plan that must be reviewed "
            "and supplemented by the operating agent before any media API call."
        )

    rendered = []
    for item in research_brief.get("notes", []):
        content = item.get("content")
        if isinstance(content, (dict, list)):
            content_text = json.dumps(content, ensure_ascii=False)
        else:
            content_text = str(content or "")
        rendered.append(f"- Source {item.get('source', 'unknown')}: {content_text[:3000]}")
    return "\n".join(rendered)


def _planning_prompt(
    args: argparse.Namespace,
    research_brief: dict[str, Any],
    loaded_skills: list[dict[str, str]],
) -> str:
    revision_note = f"\n\nUser/agent revision note:\n{args.revision_note}" if args.revision_note else ""
    return f"""
Original user request:
{args.prompt}

Research context gathered before planning:
{_research_context_text(research_brief)}

Repo skill context loaded for this task:
Use these UniVA skill excerpts as operating constraints for planning, prompt expansion, duration control, material/audio handling, quality gates, and user approval. The complete loaded skill texts are recorded in skill_context_full.json.
{_skill_context_text(loaded_skills)}

Mandatory pre-production workflow:
1. Convert the user request and research context into preliminary_video_info: subject, audience/use, factual visual anchors, constraints, style, and hard exclusions.
2. Create an initial storyboard with narrative beats, scene intent, camera intent, and tentative durations.
3. Expand every storyboard shot into detailed cinematic content. Expansion means richer description only: subject appearance, body/face/action details when people appear, foreground/midground/background, static environment detail, dynamic motion, lighting, camera, visual continuity, and negative constraints. Expansion must not add extra total duration by itself.
4. After expansion, rebalance shot count and shot durations dynamically against the user's requested duration, provider min/max duration, action complexity, readability, and continuity. Do not default to equal or fixed shot lengths unless the content and user request make that the best timing.
5. Ensure each shot has visual logic with neighboring shots: object match, camera direction, composition contrast, energy progression, motion handoff, or a deliberate transition. Continuity is visual as well as narrative.
6. The final expanded_generation_prompt for each shot is the exact prompt that will be sent to the generation model. Do not replace it with keywords, a summary, or visual_prompt.
7. If the user asks for subtitles, captions, CTA text, lower-thirds, title cards, or other final packaging text, include a timed caption_plan and remotion_handoff in the plan. Do not rely on the video model to draw readable text inside the generated frames.
{revision_note}
""".strip()


def _plan_duration_total(plan: dict[str, Any]) -> float:
    total = 0.0
    for shot in plan.get("shots") or []:
        if not isinstance(shot, dict):
            continue
        duration = _shot_duration(shot)
        try:
            total += float(duration or 0)
        except (TypeError, ValueError):
            continue
    return total


def _prompt_detail_score(prompt: str) -> dict[str, Any]:
    words = prompt.split()
    return {
        "word_count": len(words),
        "char_count": len(prompt),
        "has_scene": bool(re.search(r"scene|environment|foreground|midground|background", prompt, re.I)),
        "has_motion": bool(re.search(r"motion|moves|running|camera|dolly|pan|push", prompt, re.I)),
    }


def _validate_storyboard_plan(
    plan: dict[str, Any],
    args: argparse.Namespace,
    research_brief: dict[str, Any],
    *,
    approved_plan: bool = False,
    contract_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    if contract_validation and not contract_validation.get("ready_for_generation"):
        for issue in contract_validation.get("issues") or []:
            issues.append({"area": "generation_contract", **issue})
    shots = plan.get("shots")
    if not isinstance(shots, list) or not shots:
        issues.append({"severity": "high", "area": "storyboard", "problem": "Plan contains no shots."})
        shots = []

    if research_brief.get("external_research_required") and not approved_plan and not args.allow_missing_research:
        issues.append(
            {
                "severity": "high",
                "area": "research",
                "problem": "No external research notes were supplied before planning.",
                "fix": "Search relevant sources, add notes with --research-note/--research-file, then replan or approve explicitly.",
            }
        )

    target = args.duration
    total = _plan_duration_total(plan)
    if target is not None and total and total > float(target) + 0.5:
        issues.append(
            {
                "severity": "high",
                "area": "duration",
                "problem": f"Planned shot total is {total:g}s, above requested {float(target):g}s.",
                "fix": "Rebalance shot durations or reduce shot count before generation.",
            }
        )

    for index, shot in enumerate(shots, start=1):
        shot_id = shot.get("id") or shot.get("shot_id") or f"shot_{index:02d}"
        prompt = _shot_prompt(shot)
        if not prompt:
            issues.append(
                {
                    "severity": "high",
                    "area": "prompt",
                    "item": shot_id,
                    "problem": "expanded_generation_prompt is missing.",
                    "fix": "Expand the shot into a complete final generation prompt before calling video tools.",
                }
            )
            continue

        detail = _prompt_detail_score(prompt)
        if detail["word_count"] < 50 and detail["char_count"] < 240:
            issues.append(
                {
                    "severity": "medium",
                    "area": "prompt",
                    "item": shot_id,
                    "problem": "expanded_generation_prompt appears too brief to describe a full cinematic shot.",
                    "fix": "Add concrete subject, environment, motion, camera, spatial layers, continuity, and negative constraints.",
                }
            )
        if not (detail["has_scene"] and detail["has_motion"]):
            issues.append(
                {
                    "severity": "medium",
                    "area": "prompt",
                    "item": shot_id,
                    "problem": "Prompt does not clearly expose scene and motion details.",
                    "fix": "Describe foreground/midground/background, dynamic action, and camera movement.",
                }
            )
        if not shot.get("visual_logic") and index > 1:
            issues.append(
                {
                    "severity": "medium",
                    "area": "visual_logic",
                    "item": shot_id,
                    "problem": "Shot lacks explicit visual logic linking it to neighboring shots.",
                    "fix": "Add visual_logic with link_from_previous, composition_change, and link_to_next.",
                }
            )

    high_count = sum(1 for issue in issues if issue.get("severity") == "high")
    return {
        "status": "pass" if not issues else ("blocked" if high_count else "revise"),
        "ready_for_generation": not issues,
        "issue_count": len(issues),
        "high_issue_count": high_count,
        "planned_duration_seconds": total,
        "issues": issues,
    }


def _review_summary(plan: dict[str, Any]) -> list[dict[str, Any]]:
    summary = []
    request_by_shot = {item["shot_id"]: item for item in _generation_handoff(plan)["requests"]}
    for index, shot in enumerate(plan.get("shots") or [], start=1):
        if not isinstance(shot, dict):
            continue
        shot_id = shot.get("id") or shot.get("shot_id") or f"shot_{index:02d}"
        summary.append(
            {
                "id": shot_id,
                "duration_seconds": _shot_duration(shot),
                "narrative_role": shot.get("narrative_role"),
                "scene_blueprint": shot.get("scene_blueprint"),
                "camera_motion": shot.get("camera_motion") or shot.get("camera_movement"),
                "start_state": shot.get("start_state"),
                "end_state": shot.get("end_state"),
                "visual_logic": shot.get("visual_logic"),
                "creative_generation_prompt": shot.get("creative_generation_prompt"),
                "expanded_generation_prompt": _shot_prompt(shot),
                "generation_prompt_sha256": shot.get("generation_prompt_sha256"),
                "generation_contract": shot.get("generation_contract"),
                "provider_request_preview": request_by_shot.get(shot_id),
            }
        )
    return summary


def _write_storyboard_review(
    run_dir: Path,
    args: argparse.Namespace,
    research_brief: dict[str, Any],
    plan: dict[str, Any],
    validation: dict[str, Any],
) -> Path:
    review_path = run_dir / "storyboard_review.json"
    payload = {
        "schema_version": STORYBOARD_REVIEW_SCHEMA_VERSION,
        "status": "awaiting_human",
        "interaction_type": "storyboard_approval",
        "prompt": args.prompt,
        "generation_contract": plan.get("generation_contract"),
        "provider_handoff_preview": _generation_handoff(plan, fallback_aspect_ratio=args.aspect_ratio),
        "research_brief": research_brief,
        "plan_path": str(run_dir / "shot_plan.json"),
        "validation_path": str(run_dir / "storyboard_validation.json"),
        "planned_duration_seconds": validation.get("planned_duration_seconds"),
        "caption_plan": plan.get("caption_plan") if isinstance(plan.get("caption_plan"), list) else [],
        "remotion_handoff": plan.get("remotion_handoff") if isinstance(plan.get("remotion_handoff"), dict) else {},
        "shots": _review_summary(plan),
        "validation": validation,
        "instructions": {
            "approve": "If the storyboard is acceptable, rerun codex_video_runner.py with --approved-plan set to plan_path.",
            "revise": "Edit shot_plan.json directly or rerun planning with --revision-note describing the requested changes.",
            "block": "Do not call video generation tools until this review is approved.",
        },
    }
    _write_json(review_path, payload)
    return review_path


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from univa.mcp_tools.video_gen import (
        _verify_generation_contracts,
        image2video_gen,
        _freeze_generation_contracts,
        merge2videos,
        plan_video_shots,
        text2video_gen,
    )

    run_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else PROJECT_ROOT / "results" / f"codex_direct_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_safe_slug(args.prompt)}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    loaded_skills = _read_skill_files(args.skills_scope, args.prompt)
    _write_json(run_dir / "skill_context.json", _skill_audit(loaded_skills))
    _write_json(run_dir / "skill_context_full.json", loaded_skills)

    research_brief = _collect_research_brief(args)
    _write_json(run_dir / "research_brief.json", research_brief)

    if args.approved_plan:
        plan = _read_json(args.approved_plan)
        if not isinstance(plan, dict):
            raise RuntimeError(f"Approved plan is not a JSON object: {args.approved_plan}")
        plan_response = {
            "success": True,
            "content": plan,
            "message": "Loaded approved storyboard plan without rewriting its frozen generation prompts.",
        }
    else:
        try:
            plan_response = _response_to_dict(
                await plan_video_shots(
                    prompt=_planning_prompt(args, research_brief, loaded_skills),
                    target_duration_seconds=args.duration,
                    aspect_ratio=args.aspect_ratio,
                )
            )
        except Exception as exc:
            plan_response = {"success": False, "error": str(exc), "stage": "planning"}
            _write_json(run_dir / "shot_plan_response.json", plan_response)
            _write_json(
                run_dir / "delivery_report.json",
                {
                    "success": False,
                    "mode": "codex_direct",
                    "stage": "planning",
                    "run_dir": str(run_dir),
                    "prompt": args.prompt,
                    "loaded_skills": [item["path"] for item in loaded_skills],
                    "research_brief_path": str(run_dir / "research_brief.json"),
                    "plan_response_path": str(run_dir / "shot_plan_response.json"),
                    "final": {"success": False, "error": str(exc)},
                },
            )
            raise RuntimeError(f"Shot planning failed: {exc}") from exc

    _write_json(run_dir / "shot_plan_response.json", plan_response)
    if not plan_response.get("success"):
        _write_json(
            run_dir / "delivery_report.json",
            {
                "success": False,
                "mode": "codex_direct",
                "stage": "planning",
                "run_dir": str(run_dir),
                "prompt": args.prompt,
                "loaded_skills": [item["path"] for item in loaded_skills],
                "plan_response_path": str(run_dir / "shot_plan_response.json"),
                "final": plan_response,
            },
        )
        raise RuntimeError(plan_response.get("error") or plan_response.get("message") or "Shot planning failed.")

    plan = plan_response.get("content") or {}
    plan = _apply_caption_packaging(plan, args, approved_plan=bool(args.approved_plan))
    if not args.approved_plan:
        plan["original_user_request"] = args.prompt
        plan["requested_duration_seconds"] = args.duration
        plan["requested_aspect_ratio"] = args.aspect_ratio
        plan = _freeze_generation_contracts(plan)
        plan_response["content"] = plan
        _write_json(run_dir / "shot_plan_response.json", plan_response)

    contract_validation = _verify_generation_contracts(plan)
    if _wants_caption_packaging(args.prompt) and not _plan_has_caption_packaging(plan):
        validation_error = {
            "status": "blocked",
            "ready_for_generation": False,
            "issue_count": 1,
            "high_issue_count": 1,
            "planned_duration_seconds": _plan_duration_total(plan),
            "issues": [
                {
                    "severity": "high",
                    "area": "caption_packaging",
                    "problem": "Prompt requests subtitles/captions/CTA, but the plan does not include caption_plan or remotion_handoff.",
                    "fix": "Replan with timed captions and Remotion packaging before approval.",
                }
            ],
        }
        _write_json(run_dir / "storyboard_validation.json", validation_error)
        review_path = _write_storyboard_review(run_dir, args, research_brief, plan, validation_error)
        report = {
            "success": True,
            "mode": "storyboard_review",
            "stage": "awaiting_storyboard_approval",
            "run_dir": str(run_dir),
            "prompt": args.prompt,
            "loaded_skills": [item["path"] for item in loaded_skills],
            "research_brief_path": str(run_dir / "research_brief.json"),
            "plan_path": str(run_dir / "shot_plan.json"),
            "review_path": str(review_path),
            "validation_path": str(run_dir / "storyboard_validation.json"),
            "generation_handoff_path": str(run_dir / "generation_handoff.json"),
            "validation": validation_error,
            "message": "Storyboard review is required before generation. Ask the user to approve or revise shot_plan.json, then rerun with --approved-plan.",
        }
        _write_json(run_dir / "delivery_report.json", report)
        return report
    handoff = _generation_handoff(plan, fallback_aspect_ratio=args.aspect_ratio)
    _write_json(run_dir / "generation_handoff.json", handoff)
    _write_json(run_dir / "shot_plan.json", plan)
    validation = _validate_storyboard_plan(
        plan,
        args,
        research_brief,
        approved_plan=bool(args.approved_plan),
        contract_validation=contract_validation,
    )
    _write_json(run_dir / "storyboard_validation.json", validation)
    if args.dry_run:
        review_path = _write_storyboard_review(run_dir, args, research_brief, plan, validation)
        return {
            "success": True,
            "mode": "dry_run",
            "run_dir": str(run_dir),
            "plan_path": str(run_dir / "shot_plan.json"),
            "review_path": str(review_path),
            "validation_path": str(run_dir / "storyboard_validation.json"),
            "generation_handoff_path": str(run_dir / "generation_handoff.json"),
            "validation": validation,
            "loaded_skills": [item["path"] for item in loaded_skills],
        }

    if not args.approved_plan and not args.auto_approve_storyboard:
        review_path = _write_storyboard_review(run_dir, args, research_brief, plan, validation)
        report = {
            "success": True,
            "mode": "storyboard_review",
            "stage": "awaiting_storyboard_approval",
            "run_dir": str(run_dir),
            "prompt": args.prompt,
            "loaded_skills": [item["path"] for item in loaded_skills],
            "research_brief_path": str(run_dir / "research_brief.json"),
            "plan_path": str(run_dir / "shot_plan.json"),
            "review_path": str(review_path),
            "validation_path": str(run_dir / "storyboard_validation.json"),
            "generation_handoff_path": str(run_dir / "generation_handoff.json"),
            "validation": validation,
            "message": "Storyboard review is required before generation. Ask the user to approve or revise shot_plan.json, then rerun with --approved-plan.",
        }
        _write_json(run_dir / "delivery_report.json", report)
        return report

    if validation["high_issue_count"]:
        raise RuntimeError(
            "Storyboard or frozen generation contract has blocking issues. Replan and review before generation."
        )

    shots = plan.get("shots")
    if not isinstance(shots, list) or not shots:
        raise RuntimeError("Shot plan contains no shots.")

    approved_audio_prompt = args.audio_prompt or _approved_audio_context(args.prompt, plan)
    approved_audio_intent = " ".join(
        [args.prompt]
        + [str(shot.get("creative_generation_prompt") or "") for shot in shots if isinstance(shot, dict)]
    )
    include_voiceover = args.include_voiceover or _wants_voiceover(approved_audio_intent)
    silent_delivery = args.no_audio or _wants_no_audio(approved_audio_intent)
    include_bgm = not silent_delivery and not _wants_no_music(approved_audio_intent)
    include_sfx = not silent_delivery and not _wants_no_sfx(approved_audio_intent)
    auto_audio = not silent_delivery and (include_bgm or include_sfx or include_voiceover)
    audio_policy = {
        "auto_audio": auto_audio,
        "include_bgm": include_bgm,
        "include_sfx": include_sfx,
        "include_voiceover": include_voiceover,
        "audio_prompt": approved_audio_prompt,
        "priority_order": [
            "video_api_native_audio",
            "dedicated_audio_generation_api",
            "ffmpeg_synthetic_fallback",
        ],
        "intermediate_clip_policy": (
            "Single-shot generation passes auto_audio to the video tool. Multi-shot generation keeps "
            "intermediate clip auto_audio disabled and applies cohesive audio at merge time."
        ),
    }
    _write_json(run_dir / "audio_handoff.json", audio_policy)

    clip_results: list[dict[str, Any]] = []
    clip_paths: list[str] = []
    for index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            continue
        prompt = _shot_prompt(shot, allow_fallback=args.allow_prompt_fallback)
        if not prompt:
            raise RuntimeError(
                f"Shot {index} has no expanded_generation_prompt. "
                "Generation requires the approved detailed shot prompt, not visual_prompt keywords."
            )

        generation_tool = str(shot.get("generation_tool") or "text2video_gen")
        image_path = shot.get("image_path") or shot.get("reference_image") or shot.get("keyframe_path")
        if not image_path and args.images:
            image_path = args.images[min(index - 1, len(args.images) - 1)]
        clip_auto_audio = auto_audio if len(shots) == 1 else False

        if generation_tool == "image2video_gen" or image_path:
            if not image_path:
                raise RuntimeError(f"Shot {index} requires image2video_gen but has no image path.")
            result = _response_to_dict(
                await image2video_gen(
                    prompt=prompt,
                    image_path=str(Path(image_path).resolve()),
                    duration_seconds=_shot_duration(shot),
                    auto_audio=clip_auto_audio,
                    aspect_ratio=_shot_aspect_ratio(plan, shot, args.aspect_ratio),
                    include_voiceover=include_voiceover if clip_auto_audio else False,
                    audio_prompt=approved_audio_prompt if clip_auto_audio else None,
                )
            )
        else:
            result = _response_to_dict(
                await text2video_gen(
                    prompt=prompt,
                    duration_seconds=_shot_duration(shot),
                    auto_audio=clip_auto_audio,
                    aspect_ratio=_shot_aspect_ratio(plan, shot, args.aspect_ratio),
                    include_voiceover=include_voiceover if clip_auto_audio else False,
                    audio_prompt=approved_audio_prompt if clip_auto_audio else None,
                )
            )
        result["shot_id"] = shot.get("id") or shot.get("shot_id") or f"shot_{index:02d}"
        result["prompt_source"] = "shots[*].expanded_generation_prompt" if shot.get("expanded_generation_prompt") else "fallback"
        result["probe"] = _probe(result.get("output_path"))
        clip_results.append(result)
        _write_json(run_dir / "clip_results.json", clip_results)

        if not result.get("success") or not result.get("output_path"):
            raise RuntimeError(result.get("error") or result.get("message") or f"Shot {index} generation failed.")
        clip_paths.append(str(Path(result["output_path"]).resolve()))

    final_result: dict[str, Any]
    remotion_handoff = _remotion_handoff_from_plan(plan, args)
    edit_decisions = plan.get("edit_decisions") if isinstance(plan.get("edit_decisions"), dict) else {}
    caption_plan = (
        plan.get("caption_plan")
        or edit_decisions.get("caption_plan")
        or remotion_handoff.get("captions")
        or []
    )
    visual_overlays = (
        plan.get("visual_overlays")
        or edit_decisions.get("visual_overlays")
        or remotion_handoff.get("overlays")
        or []
    )
    _write_json(
        run_dir / "remotion_handoff.json",
        {
            **remotion_handoff,
            "caption_count": len(caption_plan) if isinstance(caption_plan, list) else 0,
            "overlay_count": len(visual_overlays) if isinstance(visual_overlays, list) else 0,
        },
    )

    if len(clip_paths) == 1 and not remotion_handoff.get("enabled"):
        final_result = {
            "success": True,
            "output_path": clip_paths[0],
            "message": "Single generated clip; merge skipped.",
            "clip_result": clip_results[0] if clip_results else None,
        }
    else:
        final_result = _response_to_dict(
            await merge2videos(
                video_paths=clip_paths,
                transition=args.transition,
                transition_duration_seconds=args.transition_duration,
                transition_plan=plan.get("transitions") if args.transition is None else None,
                auto_audio=auto_audio,
                include_voiceover=include_voiceover,
                include_bgm=include_bgm,
                include_sfx=include_sfx,
                audio_prompt=approved_audio_prompt,
                remotion_compose=bool(remotion_handoff.get("enabled")),
                remotion_title=remotion_handoff.get("title"),
                remotion_subtitle=remotion_handoff.get("subtitle"),
                caption_plan=caption_plan,
                visual_overlays=visual_overlays,
                brand=remotion_handoff.get("brand"),
                remotion_theme=remotion_handoff.get("theme"),
                remotion_browser_executable_path=remotion_handoff.get("browser_executable_path"),
                remotion_binaries_directory=remotion_handoff.get("binaries_directory"),
                remotion_fallback_to_ffmpeg_subtitles=remotion_handoff.get("fallback_to_ffmpeg_subtitles"),
            )
        )

    if not auto_audio:
        strip_result = _strip_audio(final_result.get("output_path"), run_dir)
        final_result["audio_strip"] = strip_result
        if not strip_result.get("success"):
            raise RuntimeError(strip_result.get("error") or "Failed to strip audio from silent video deliverable.")
        final_result["output_path"] = strip_result["output_path"]

    final_result["probe"] = _probe(final_result.get("output_path"))
    report = {
        "success": bool(final_result.get("success")),
        "mode": "codex_direct",
        "run_dir": str(run_dir),
        "prompt": args.prompt,
        "loaded_skills": [item["path"] for item in loaded_skills],
        "research_brief_path": str(run_dir / "research_brief.json"),
        "plan_path": str(run_dir / "shot_plan.json"),
        "validation_path": str(run_dir / "storyboard_validation.json"),
        "clip_paths": clip_paths,
        "clip_results_path": str(run_dir / "clip_results.json"),
        "generation_handoff_path": str(run_dir / "generation_handoff.json"),
        "audio_handoff_path": str(run_dir / "audio_handoff.json"),
        "remotion_handoff_path": str(run_dir / "remotion_handoff.json"),
        "audio_policy": audio_policy,
        "remotion_handoff": remotion_handoff,
        "final": final_result,
    }
    _write_json(run_dir / "delivery_report.json", report)
    if not final_result.get("success"):
        raise RuntimeError(final_result.get("error") or final_result.get("message") or "Final merge failed.")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run UniVA video generation directly from Codex without the backend server.")
    parser.add_argument("--prompt", required=True, help="User video generation request.")
    parser.add_argument("--duration", type=float, help="Requested total duration in seconds.")
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--output-dir")
    parser.add_argument("--image", dest="images", action="append", default=[], help="Reference image path for image-to-video shots. Can be repeated.")
    parser.add_argument("--research-note", action="append", default=[], help="Research note gathered before planning. Can be repeated.")
    parser.add_argument("--research-file", action="append", default=[], help="Text or JSON file containing external research notes.")
    parser.add_argument("--revision-note", help="User/agent revision instruction to apply while replanning the storyboard.")
    parser.add_argument("--approved-plan", help="Path to a user-approved shot_plan.json to generate from without replanning.")
    parser.add_argument("--auto-approve-storyboard", action="store_true", help="Bypass the storyboard review gate. Intended only for tests or explicit full pre-approval.")
    parser.add_argument("--allow-missing-research", action="store_true", help="Allow generation even when no research notes were supplied.")
    parser.add_argument("--allow-prompt-fallback", action="store_true", help="Allow legacy fallback to visual_prompt/scene_blueprint if expanded_generation_prompt is missing.")
    parser.add_argument("--skills-scope", choices=["relevant", "all", "none"], default="relevant")
    parser.add_argument("--transition")
    parser.add_argument("--transition-duration", type=float)
    parser.add_argument("--audio-prompt")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--include-voiceover", action="store_true")
    parser.add_argument("--remotion-compose", action="store_true", help="Apply Remotion final packaging after merge/audio.")
    parser.add_argument("--no-remotion", action="store_true", help="Disable Remotion even when the approved plan contains remotion_handoff.enabled=true.")
    parser.add_argument("--remotion-title")
    parser.add_argument("--remotion-subtitle")
    parser.add_argument("--remotion-brand")
    parser.add_argument("--remotion-browser-executable", help="Local Chrome/Chromium executable for Remotion rendering.")
    parser.add_argument("--remotion-binaries-directory", help="Local Remotion compositor/ffmpeg binaries directory for Linux compatibility.")
    parser.add_argument("--no-remotion-ffmpeg-fallback", action="store_true", help="Disable FFmpeg ASS subtitle fallback when Remotion rendering fails.")
    parser.add_argument("--dry-run", action="store_true", help="Only load skills and generate the shot plan.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        report = asyncio.run(_run(args))
    except Exception as exc:
        raise SystemExit(f"codex video runner failed: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
