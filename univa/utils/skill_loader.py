"""
UniVA Skill Loader — Core module for loading and managing skills.

This module provides the SkillLoader class that serves as the bridge between
the agent system and the declarative skill files (Markdown + YAML).

Architecture:
  Layer 1: MCP Tools (Python code) — "what tools exist"
  Layer 2: Skills (Markdown/YAML)    — "how UniVA uses them"
  Layer 3: Prompts (txt files)       — "underlying model knowledge"

The SkillLoader reads Layer 2 skill files and provides their content to agents,
replacing the old hardcoded prompt approach with a flexible, discoverable skill system.
"""

import os
import re
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class SkillLoader:
    """
    Loads and manages skills from the skills/ directory.

    Skills are Markdown files organized by category:
      - core/       → MCP tool usage guides
      - creative/   → creative techniques
      - pipelines/  → pipeline stage directors
      - meta/       → cross-pipeline protocols
      - agent-integrations/ → external AI coding agent operating guides

    Usage:
        loader = SkillLoader(project_root="/path/to/univa")
        plan_instructions = loader.load_agent_protocol("plan")
        act_instructions = loader.load_agent_protocol("act")
        video_gen_skill = loader.load_skill("core/wavespeed-video-gen")
        pipeline = loader.load_pipeline("story-video")
    """

    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize the skill loader.

        Args:
            project_root: Path to the univa project root. If None, auto-detect
                          from this file's location.
        """
        if project_root is None:
            # Auto-detect: this file is in univa/utils/, project root is 2 levels up
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)
            )))

        self.project_root = project_root
        self.skills_dir = os.path.join(project_root, "skills")
        self.user_skills_dir = os.path.join(project_root, "skills", "user")
        self.user_preferences_config_path = os.path.join(
            self.user_skills_dir, "preference_config.yaml"
        )
        self.pipeline_defs_dir = os.path.join(project_root, "pipeline_defs")
        self.prompts_dir = os.path.join(project_root, "univa", "prompts")
        self.schemas_dir = os.path.join(project_root, "schemas")

        # Cache for loaded skills
        self._skill_cache: Dict[str, str] = {}
        self._user_skill_cache: Dict[str, str] = {}
        self._pipeline_cache: Dict[str, Dict] = {}
        self._index_cache: Optional[str] = None

        logger.info(f"SkillLoader initialized: skills_dir={self.skills_dir}")

    # ── Skill Loading ─────────────────────────────────────────────────────

    def load_skill(self, skill_path: str, use_cache: bool = True) -> str:
        """
        Load a skill file by its relative path (without .md extension).

        Args:
            skill_path: Relative path from skills/ dir, e.g. "core/wavespeed-video-gen"
            use_cache: Whether to use cached content.

        Returns:
            The full Markdown content of the skill file.

        Raises:
            FileNotFoundError: If the skill file does not exist.
        """
        if use_cache and skill_path in self._skill_cache:
            return self._skill_cache[skill_path]

        file_path = os.path.join(self.skills_dir, f"{skill_path}.md")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Skill not found: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if use_cache:
            self._skill_cache[skill_path] = content

        logger.debug(f"Loaded skill: {skill_path}")
        return content

    def load_skills_batch(self, skill_paths: List[str]) -> Dict[str, str]:
        """
        Load multiple skills at once.

        Args:
            skill_paths: List of skill paths (without .md extension).

        Returns:
            Dict mapping skill_path → content.
        """
        results = {}
        for path in skill_paths:
            try:
                results[path] = self.load_skill(path)
            except FileNotFoundError as e:
                logger.warning(f"Skill not found, skipping: {path} ({e})")
                results[path] = None
        return results

    def load_agent_protocol(self, agent_type: str) -> str:
        """
        Load the agent protocol skill for Plan or Act agent.

        This replaces the old hardcoded instructions and load_prompt("plan").

        Args:
            agent_type: "plan" or "act"

        Returns:
            Combined skill-based instructions for the agent.
        """
        if agent_type == "plan":
            return self._build_plan_agent_instructions()
        elif agent_type == "act":
            return self._build_act_agent_instructions()
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")

    # ── Three-Layer Skill Loading Architecture ─────────────────────────────
    #
    # Layer 1 (Startup — minimal tokens):
    #   - plan-agent-protocol: core role + output format (essential behavior)
    #   - act-agent-protocol: execution protocol (essential behavior)
    #   - skill_registry: names + one-line descriptions of ALL skills
    #
    # Layer 2 (Task Recognition — on-demand):
    #   - Full skill content loaded when PlanAgent identifies task category
    #   - pipeline-loader: loaded when a pipeline is matched
    #   - Creative/domain skills: loaded based on task keywords
    #
    # Layer 3 (Execution — on-demand):
    #   - Core Skills: loaded per tool at step execution time
    #   - Reviewer protocol: loaded when a stage completes
    #   - Checkpoint protocol: loaded when a checkpoint is needed

    def build_skill_registry(self) -> str:
        """
        Layer 1: Build a lightweight skill registry (names + one-line
        descriptions only).  This is the ONLY skill content loaded at agent
        startup — everything else loads on demand at Layer 2 or 3.

        Returns compact text suitable for injection into the agent's
        system prompt at minimal token cost.
        """
        lines = ["## Skill Registry (Layer 1 — lightweight index)"]
        lines.append("The following skills are available. Full instructions")
        lines.append("load on-demand when a relevant task is detected.\n")

        categories = {
            "core": "Core Skills — MCP tool usage guides",
            "creative": "Creative Skills — creative techniques & methods",
            "themes": "Theme Skills — topic-specific generation quality enhancers",
            "meta": "Meta Skills — cross-pipeline protocols",
            "pipelines": "Pipeline Directors — stage execution knowledge",
            "agent-integrations": "External Agent Integrations — Codex, Claude Code, and terminal agent guides",
        }

        for category, description in categories.items():
            skills = self.list_skills(category)
            if not skills:
                continue
            lines.append(f"### {description}")
            for skill_path in skills:
                try:
                    content = self.load_skill(skill_path)
                    # Extract the first meaningful line after "## When to Use"
                    when_idx = content.find("## When to Use")
                    if when_idx >= 0:
                        # Get the next non-empty line after the heading
                        after_heading = content[when_idx + len("## When to Use"):].strip()
                        first_line = after_heading.split('\n')[0].strip()
                        if first_line and len(first_line) > 10:
                            lines.append(f"- `{skill_path}`: {first_line[:120]}")
                            continue
                    # Fallback: use the title
                    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
                    if title_match:
                        lines.append(f"- `{skill_path}`: {title_match.group(1)[:120]}")
                except Exception:
                    lines.append(f"- `{skill_path}`: (available)")
            lines.append("")

        return '\n'.join(lines)

    def load_layer2_skills(self, task_description: str) -> str:
        """
        Layer 2: Load full skill content on demand when a task category
        is recognized by the PlanAgent.

        Called from PlanAgent.generate_plan() after initial task analysis.

        Returns the full content of the most relevant skills for this task.
        Falls back to loading the most commonly-applicable skills when
        no specific match is found.
        """
        theme_relevant = self.find_theme_skills_for_task(task_description)
        content_relevant = self.find_skills_for_task(task_description)

        # Put deterministic keyword matches first, then merge content-search
        # results. Content search can return broad matches for common words like
        # "video", while the fallback map encodes the minimum skill bundle for
        # common task classes and the intended creative workflow order.
        relevant = []
        seen = set()
        for skill_path in theme_relevant + self._fallback_skill_match(task_description) + content_relevant:
            if skill_path not in seen:
                relevant.append(skill_path)
                seen.add(skill_path)

        # Fallback: if no skills matched, load commonly-applicable skills
        # based on simple keyword detection in the task description
        if not relevant:
            relevant = self._fallback_skill_match(task_description)

        if not relevant:
            return ""

        parts = ["## Layer 2 — Task-Specific Skills (loaded on-demand)"]
        parts.append(f"Task: {task_description[:100]}\n")
        theme_context = self.build_theme_generation_context(task_description)
        if theme_context:
            parts.append(theme_context)

        # Load the most relevant core/creative skills fully. Creative video
        # tasks need more than prompt syntax: brief, style, shot, duration and
        # material constraints must be available together.
        loaded = 0
        max_loaded = 14
        for skill_path in relevant:
            if loaded >= max_loaded:
                break
            if skill_path.startswith("meta/") or skill_path.startswith("pipelines/"):
                continue
            try:
                content = self.load_skill(skill_path)
                parts.append(f"### {skill_path}")
                for header in ["## When to Use", "## Process", "## Generation Detail Expansion", "## Common Pitfalls"]:
                    idx = content.find(header)
                    if idx >= 0:
                        next_idx = content.find("\n## ", idx + len(header))
                        section = content[idx:next_idx] if next_idx != -1 else content[idx:]
                        parts.append(section.strip())
                loaded += 1
            except Exception as e:
                logger.debug(f"Layer 2 load failed for {skill_path}: {e}")

        # Also load pipeline-loader if task matches a pipeline
        try:
            pipeline_loader = self.load_skill("meta/pipeline-loader")
            parts.append("\n### Pipeline Reference (Layer 2)")
            for header in ["## Process", "## Stage Flow Rules"]:
                idx = pipeline_loader.find(header)
                if idx >= 0:
                    next_idx = pipeline_loader.find("\n## ", idx + len(header))
                    section = pipeline_loader[idx:next_idx] if next_idx != -1 else pipeline_loader[idx:]
                    parts.append(section.strip())
        except FileNotFoundError:
            pass

        return '\n\n'.join(parts)

    def _fallback_skill_match(self, task_description: str) -> List[str]:
        """
        Fallback skill matching based on simple keyword detection.
        Used when find_skills_for_task() returns no results.
        """
        task_lower = task_description.lower()
        matched = []

        # Video generation keywords
        video_gen_kw = ['generate', 'video', 'video', 'generate', 'create', 'gen', 'create', 'create']
        if any(kw in task_lower for kw in video_gen_kw):
            matched.extend([
                'meta/media-review-gate',
                'meta/generate-pipeline',
                'creative/creative-brief',
                'creative/copywriting',
                'creative/styleframe-direction',
                'creative/energy-arc',
                'creative/shot-recipe-library',
                'creative/duration-planning',
                'creative/material-matching',
                'creative/transition-sound-caption',
                'creative/remotion-packaging',
                'creative/creative-quality-gate',
                'core/wavespeed-video-gen',
                'creative/video-gen-prompting',
            ])

        # Image generation keywords
        image_kw = ['image', 'image', 'image', 'photo', 'picture', 'photo']
        if any(kw in task_lower for kw in image_kw):
            matched.extend([
                'meta/media-review-gate',
                'meta/generate-pipeline',
                'creative/creative-brief',
                'creative/styleframe-direction',
                'core/prompt-validator',
                'core/wavespeed-image-gen',
            ])

        # Audio and speech generation keywords
        audio_kw = ["audio", "music", "sfx", "dubbing", "voiceover", "speech", "audio", "music", "sound", "speech", "voiceover", "tts"]
        if any(kw in task_lower for kw in audio_kw):
            matched.extend([
                "meta/media-review-gate",
                "meta/generate-pipeline",
                "creative/creative-brief",
                "core/audio-gen",
            ])

        # Video editing keywords
        edit_kw = ['edit', 'modify', 'replace', 'edit', 'modify', 'style', 'style', 'depth', 'background']
        if any(kw in task_lower for kw in edit_kw):
            matched.extend([
                'meta/media-review-gate',
                'meta/edit-pipeline',
                'core/video-editing',
            ])

        # Story/narrative keywords
        story_kw = ['story', 'story', 'narrative', 'narrative', 'Camera', 'character', 'character', 'scene', 'scene']
        if any(kw in task_lower for kw in story_kw):
            matched.extend([
                'creative/story-video',
                'creative/copywriting',
                'creative/shot-planning',
                'creative/shot-recipe-library',
                'creative/character-consistency',
                'creative/remotion-packaging',
            ])

        # Production planning keywords
        planning_kw = ['storyboard', 'script', 'copy', 'spoken', 'caption', 'Pacing', 'duration', 'transition', 'asset', 'storyboard', 'script', 'copy', 'caption', 'duration', 'transition', 'material']
        if any(kw in task_lower for kw in planning_kw):
            matched.extend([
                'creative/copywriting',
                'creative/shot-recipe-library',
                'creative/material-matching',
                'creative/transition-sound-caption',
                'creative/remotion-packaging',
                'creative/creative-quality-gate',
            ])

        # Final packaging keywords
        remotion_kw = [
            'remotion', 'caption', 'title card', 'opening', 'ending', 'corner mark', 'brand', 'cta',
            'lower-third', 'lower third', 'progress bar', 'selling point card', 'spec card', 'data card',
            'caption', 'subtitle', 'title card', 'brand bug', 'overlay',
        ]
        if any(kw in task_lower for kw in remotion_kw):
            matched.extend([
                'creative/remotion-packaging',
                'core/remotion-compose',
            ])

        # Analysis keywords
        analysis_kw = ['analyze', 'understand', 'analyze', 'understand', 'describe', 'describe']
        if any(kw in task_lower for kw in analysis_kw):
            matched.extend([
                'core/video-understanding',
                'creative/video-analysis',
            ])

        theme_matches = self.find_theme_skills_for_task(task_description)
        if theme_matches:
            matched = theme_matches + matched

        # If still nothing matched, load the most general skills
        if not matched:
            matched = [
                'meta/media-review-gate',
                'meta/generate-pipeline',
                'core/wavespeed-video-gen',
                'creative/video-gen-prompting',
            ]

        # Deduplicate while preserving order
        seen = set()
        result = []
        for s in matched:
            if s not in seen:
                seen.add(s)
                result.append(s)
        return result

    def load_layer3_protocols(self, stage_name: str = "") -> str:
        """
        Layer 3: Load execution-time protocols on demand.

        Called when a pipeline stage completes (reviewer protocol)
        or when a checkpoint is needed (checkpoint protocol).

        Args:
            stage_name: Optional stage name for context-aware loading.
        """
        parts = [f"## Layer 3 — Execution Protocols (loaded on-demand)"]

        # Reviewer protocol (after each stage)
        try:
            reviewer = self.load_skill("meta/reviewer")
            parts.append("\n### Quality Review Protocol")
            parts.append(reviewer)
        except FileNotFoundError:
            logger.debug("reviewer.md not available at Layer 3")

        # Checkpoint protocol (when human approval or state persistence needed)
        try:
            checkpoint = self.load_skill("meta/checkpoint-protocol")
            parts.append("\n### Checkpoint Protocol")
            parts.append(checkpoint)
        except FileNotFoundError:
            logger.debug("checkpoint-protocol.md not available at Layer 3")

        return '\n\n'.join(parts)

    def _build_plan_agent_instructions(self) -> str:
        """
        Layer 1: Build Plan Agent instructions — CORE BEHAVIOR ONLY.

        Only the essential protocol (role, planning logic, output format)
        and the lightweight skill registry are loaded at startup.
        Everything else (tool details, pipeline flow, creative methods)
        loads on-demand at Layer 2/3.

        User preferences (skills/user/) are loaded FIRST with HIGH PRIORITY.
        """
        parts = []

        # 0. User Preferences — HIGHEST PRIORITY, loaded first
        try:
            user_context = self.get_user_preferences_context()
            if user_context:
                parts.append(user_context)
                logger.info("Plan Agent: loaded user preferences (HIGH PRIORITY)")
        except Exception as e:
            logger.debug(f"Could not load user preferences: {e}")

        # 1. Plan Agent protocol — core behavior + output format (ESSENTIAL)
        try:
            protocol = self.load_skill("meta/plan-agent-protocol")
            parts.append(protocol)
        except FileNotFoundError:
            logger.warning("meta/plan-agent-protocol.md not found, using fallback")
            parts.append(self._get_fallback_plan_prompt())

        # 2. Lightweight skill registry (names + descriptions only — minimal tokens)
        try:
            registry = self.build_skill_registry()
            parts.append(registry)
            parts.append(
                "\n> 💡 Full skill instructions for specific tasks load "
                "on-demand when a matching user request is detected (Layer 2). "
                "Tool-specific usage guides load at execution time (Layer 3).\n"
            )
        except Exception as e:
            logger.warning(f"Could not build skill registry: {e}")

        return "\n\n".join(parts)

    def _build_act_agent_instructions(self) -> str:
        """
        Layer 1: Build Act Agent instructions — EXECUTION PROTOCOL ONLY.

        Only the essential execution protocol is loaded at startup.
        Reviewer and checkpoint protocols load on-demand at Layer 3
        (when a pipeline stage completes or a checkpoint is needed).

        User preferences (skills/user/) are loaded FIRST with HIGH PRIORITY.
        """
        parts = []

        # 0. User Preferences — HIGHEST PRIORITY, loaded first
        try:
            user_context = self.get_user_preferences_context()
            if user_context:
                parts.append(user_context)
                logger.info("Act Agent: loaded user preferences (HIGH PRIORITY)")
        except Exception as e:
            logger.debug(f"Could not load user preferences: {e}")

        # 1. Act Agent protocol — core execution behavior (ESSENTIAL)
        try:
            protocol = self.load_skill("meta/act-agent-protocol")
            parts.append(protocol)
        except FileNotFoundError:
            logger.warning("meta/act-agent-protocol.md not found, using fallback")
            parts.append(self._get_fallback_act_prompt())

        # 2. Reference that Layer 3 protocols are available on-demand
        parts.append(
            "\n## Available Execution Protocols (Layer 3 — loaded on-demand)\n"
            "- `meta/reviewer` — quality self-review after each pipeline stage\n"
            "- `meta/checkpoint-protocol` — state persistence & human approval gates\n"
            "These load automatically when a stage completes or a checkpoint is needed.\n"
        )

        return "\n\n".join(parts)

    # ── Pipeline Loading ──────────────────────────────────────────────────

    def load_pipeline(self, pipeline_name: str) -> Optional[Dict[str, Any]]:
        """
        Load a pipeline definition from pipeline_defs/*.yaml.

        Args:
            pipeline_name: Name of the pipeline (e.g., "story-video")

        Returns:
            Pipeline definition dict, or None if not found.
        """
        if pipeline_name in self._pipeline_cache:
            return self._pipeline_cache[pipeline_name]

        file_path = os.path.join(self.pipeline_defs_dir, f"{pipeline_name}.yaml")
        if not os.path.exists(file_path):
            logger.error(f"Pipeline definition not found: {file_path}")
            return None

        with open(file_path, 'r', encoding='utf-8') as f:
            pipeline_def = yaml.safe_load(f)

        self._pipeline_cache[pipeline_name] = pipeline_def
        logger.info(f"Loaded pipeline: {pipeline_name} (v{pipeline_def.get('version', '?')})")
        return pipeline_def

    def list_pipelines(self) -> List[str]:
        """
        List all available pipeline names.

        Returns:
            List of pipeline names (without .yaml extension).
        """
        if not os.path.exists(self.pipeline_defs_dir):
            return []

        pipelines = []
        for f in os.listdir(self.pipeline_defs_dir):
            if f.endswith('.yaml'):
                pipelines.append(f[:-5])  # Remove .yaml
        return sorted(pipelines)

    def get_pipeline_stage_skill(self, pipeline_name: str, stage_name: str) -> Optional[str]:
        """
        Get the skill content for a specific pipeline stage.

        Args:
            pipeline_name: Name of the pipeline.
            stage_name: Name of the stage.

        Returns:
            Skill content, or None if not found.
        """
        pipeline = self.load_pipeline(pipeline_name)
        if not pipeline:
            return None

        # Find the stage definition
        stage_def = None
        for s in pipeline.get('stages', []):
            if s.get('name') == stage_name:
                stage_def = s
                break

        if not stage_def:
            logger.error(f"Stage '{stage_name}' not found in pipeline '{pipeline_name}'")
            return None

        skill_path = stage_def.get('skill')
        if not skill_path:
            logger.error(f"No skill defined for stage '{stage_name}'")
            return None

        try:
            return self.load_skill(skill_path)
        except FileNotFoundError:
            logger.error(f"Stage skill not found: {skill_path}")
            return None

    def get_pipeline_stage_context(self, pipeline_name: str, stage_name: str) -> Dict[str, Any]:
        """
        Get the full context for a pipeline stage, including skill content,
        review criteria, and tool requirements.

        Args:
            pipeline_name: Name of the pipeline.
            stage_name: Name of the stage.

        Returns:
            Dict with skill_content, review_focus, success_criteria, tools, etc.
        """
        pipeline = self.load_pipeline(pipeline_name)
        if not pipeline:
            return {}

        stage_def = None
        for s in pipeline.get('stages', []):
            if s.get('name') == stage_name:
                stage_def = s
                break

        if not stage_def:
            return {}

        skill_content = self.get_pipeline_stage_skill(pipeline_name, stage_name)

        return {
            'pipeline_name': pipeline_name,
            'stage_name': stage_name,
            'skill_content': skill_content,
            'review_focus': stage_def.get('review_focus', []),
            'success_criteria': stage_def.get('success_criteria', []),
            'tools_available': stage_def.get('tools_available', []),
            'required_tools': stage_def.get('required_tools', []),
            'produces': stage_def.get('produces', []),
            'required_artifacts_in': stage_def.get('required_artifacts_in', []),
            'checkpoint_required': stage_def.get('checkpoint_required', True),
            'human_approval_default': stage_def.get('human_approval_default', False),
        }

    # ── Skill Discovery ───────────────────────────────────────────────────

    def list_skills(self, category: Optional[str] = None) -> List[str]:
        """
        List available skills, optionally filtered by category.

        Args:
            category: One of 'core', 'creative', 'meta', 'pipelines',
                      'themes', 'agent-integrations', or None for all.

        Returns:
            List of skill paths (without .md extension).
        """
        skills = []

        if category:
            search_dir = os.path.join(self.skills_dir, category)
        else:
            search_dir = self.skills_dir

        if not os.path.exists(search_dir):
            return []

        for root, dirs, files in os.walk(search_dir):
            for f in files:
                if f.endswith('.md'):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, self.skills_dir)
                    skill_path = rel_path[:-3]  # Remove .md
                    skills.append(skill_path)

        return sorted(skills)

    # ── User Skills (HIGH PRIORITY) ─────────────────────────────────────

    def list_user_skills(self) -> List[str]:
        """
        List all user-level skills from skills/user/.

        Returns:
            List of user skill paths (relative to skills/ dir, without .md).
        """
        if not os.path.exists(self.user_skills_dir):
            return []

        skills = []
        for f in os.listdir(self.user_skills_dir):
            if f.endswith('.md') and f != 'README.md':
                skills.append(f"user/{f[:-3]}")  # Remove .md
        return sorted(skills)

    def load_user_skill(self, skill_name: str) -> Optional[str]:
        """
        Load a single user skill by its filename (without .md extension).

        Args:
            skill_name: The skill filename without .md (e.g., "preference_01").

        Returns:
            Skill content, or None if not found.
        """
        if skill_name.startswith("user/"):
            skill_name = skill_name[5:]

        cache_key = f"user/{skill_name}"
        if cache_key in self._user_skill_cache:
            return self._user_skill_cache[cache_key]

        file_path = os.path.join(self.user_skills_dir, f"{skill_name}.md")
        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self._user_skill_cache[cache_key] = content
            return content
        except Exception as e:
            logger.warning(f"Failed to load user skill '{skill_name}': {e}")
            return None

    def load_all_user_skills(self) -> Dict[str, str]:
        """Load ALL user skills from skills/user/ directory."""
        results = {}
        for skill_path in self.list_user_skills():
            content = self.load_user_skill(skill_path)
            if content:
                results[skill_path] = content
        return results

    def _normalize_preference_skill_name(self, skill_name: str) -> str:
        """Normalize user preference identifiers to the canonical file stem."""
        skill_name = (skill_name or "").strip()
        if skill_name.startswith("user/"):
            skill_name = skill_name[5:]
        if skill_name.endswith(".md"):
            skill_name = skill_name[:-3]

        legacy_match = re.match(r"pref-(\d+)", skill_name)
        if legacy_match:
            return f"preference_{int(legacy_match.group(1)):02d}"

        return skill_name

    def _preference_filename(self, number: int) -> str:
        return f"preference_{number:02d}.md"

    def _preference_skill_key(self, number: int) -> str:
        return f"user/{self._preference_filename(number)[:-3]}"

    def _read_preference_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.user_preferences_config_path):
            return {}
        try:
            with open(self.user_preferences_config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"Failed to read preference config: {e}")
            return {}

    def _write_preference_config(
        self,
        active_skill_name: Optional[str],
        *,
        core_skill_name: Optional[str] = None,
    ) -> None:
        os.makedirs(self.user_skills_dir, exist_ok=True)
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = self._read_preference_config()
        if not isinstance(data, dict):
            data = {}
        if "created_at" not in data:
            data["created_at"] = timestamp
        data["updated_at"] = timestamp
        data["version"] = 1
        data["active_skill_name"] = active_skill_name
        if core_skill_name is not None:
            data["core_skill_name"] = core_skill_name

        with open(self.user_preferences_config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def _get_config_active_preference(self) -> Optional[str]:
        config = self._read_preference_config()
        candidate = config.get("active_skill_name") or config.get("skill_name")
        if candidate:
            normalized = self._normalize_preference_skill_name(str(candidate))
            if f"user/{normalized}" in self.load_all_user_skills():
                return f"user/{normalized}"
            if normalized in self.load_all_user_skills():
                return normalized
        return None

    def _resolve_preference_identifier(self, identifier: str) -> Optional[str]:
        """Resolve a number/name/filename to a user preference key."""
        import re as _re

        all_skills = self.load_all_user_skills()
        if not all_skills:
            return None

        normalized_identifier = self._normalize_preference_skill_name(str(identifier))

        num_match = _re.match(r"#?\s*(\d+)", str(identifier).strip())
        if num_match:
            number = int(num_match.group(1))
            for key, content in all_skills.items():
                if self._get_preference_number(key, content) == number:
                    return key

        exact_key = f"user/{normalized_identifier}"
        if exact_key in all_skills:
            return exact_key

        if normalized_identifier in all_skills:
            return normalized_identifier

        for key, content in all_skills.items():
            title_match = _re.search(r'^#\s+(.+)$', content, _re.MULTILINE)
            title = title_match.group(1) if title_match else key
            if normalized_identifier.lower() in title.lower() or normalized_identifier.lower() in key.lower():
                return key

        return None

    def parse_user_preference_text(self, raw_text: str) -> Dict[str, Any]:
        """Normalize free-form user preference text into structured buckets."""
        import re as _re

        text = " ".join((raw_text or "").split()).strip()
        normalized = _re.sub(
            r'^(please)?(help me)?(add|add|save|remember|record|set as|switch|modify|update)'
            r'(preference|style|preference|setting)?[:: ]*',
            '',
            text,
            flags=_re.IGNORECASE,
        ).strip()
        normalized = normalized or text

        clauses = [
            part.strip(" ,.;")
            for part in _re.split(r'[,.;\n]+', normalized)
            if part.strip(" ,.;")
        ]
        if not clauses:
            clauses = [normalized] if normalized else []

        categories = {
            "visual_style": [],
            "color_palette": [],
            "pacing": [],
            "camera": [],
            "quality": [],
            "workflow": [],
            "output": [],
            "theme": [],
            "interaction": [],
            "general": [],
        }
        category_keywords = {
            "visual_style": ["style", "visual", "visual", "cinematic", "atmosphere", "texture", "style"],
            "color_palette": ["tone", "color", "warm color", "cool color", "bright", "dark", "palette", "palette"],
            "pacing": ["Pacing", "speed", "fast", "slow", "compact", "slow", "pacing"],
            "camera": ["Camera", "close-up", "wide shot", "medium shot", "camera movement", "viewpoint", "camera"],
            "quality": ["Quality", "sharp", "high definition", "detail", "precision", "quality"],
            "workflow": ["Workflow", "first", "then", "then", "confirm", "preview", "review", "workflow"],
            "output": ["export", "save", "format", "resolution", "path", "Output", "output"],
            "theme": ["Theme", "subject matter", "character", "scene", "content", "theme"],
            "interaction": ["every time", "always", "default", "automatic", "manual", "interaction"],
        }

        def _add_unique(bucket: List[str], value: str) -> None:
            if value not in bucket:
                bucket.append(value)

        for clause in clauses:
            clause_lower = clause.lower()
            matched = False
            for category, keywords in category_keywords.items():
                if any(keyword in clause or keyword.lower() in clause_lower for keyword in keywords):
                    _add_unique(categories[category], clause)
                    matched = True
            if not matched:
                _add_unique(categories["general"], clause)

        title_bits = []
        for category in [
            "visual_style", "color_palette", "pacing", "camera", "quality",
            "workflow", "output", "theme", "interaction", "general",
        ]:
            if categories[category]:
                title_bits.extend(categories[category][:1])
            if len(title_bits) >= 2:
                break
        title = " / ".join(title_bits) if title_bits else "User Preference"
        title = title[:60].strip(" /")

        return {
            "raw_text": text,
            "normalized_text": normalized,
            "clauses": clauses,
            "categories": categories,
            "title": title,
        }

    def build_user_preference_markdown(
        self,
        raw_text: str,
        *,
        number: int,
        is_core: bool,
        active_skill_name: Optional[str] = None,
    ) -> str:
        """Build a structured markdown skill from free-form user preference text."""
        import datetime

        parsed = self.parse_user_preference_text(raw_text)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        skill_name = active_skill_name or self._normalize_preference_skill_name(
            self._preference_skill_key(number)
        )
        marker = "DEFAULT" if is_core else "PROFILE"

        lines = [
            f"# {parsed['title']}",
            "",
            f"## Preference Number: {number} [{marker}]",
            f"> Created: {timestamp}",
            f"> Updated: {timestamp}",
            f"> Skill Name: {skill_name}",
            f"> Source: direct user preference input",
            "",
            "## Priority: HIGH",
            "> ⚠️ USER-LEVEL SKILL — OVERRIDES DEFAULTS",
            "",
            "## Original Description",
        ]
        for line in parsed["raw_text"].splitlines() or [parsed["raw_text"]]:
            lines.append(f"> {line}" if line.strip() else ">")

        lines.extend(["", "## Normalized Preference"])
        for clause in parsed["clauses"]:
            lines.append(f"- {clause}")

        display_map = {
            "visual_style": "Visual Style",
            "color_palette": "Color and Palette",
            "pacing": "Pacing",
            "camera": "Camera",
            "quality": "Quality",
            "workflow": "Workflow",
            "output": "Output",
            "theme": "Theme",
            "interaction": "Interaction",
            "general": "Other Details",
        }
        lines.extend(["", "## Structured Fields"])
        for category, label in display_map.items():
            values = parsed["categories"].get(category) or []
            if not values:
                continue
            lines.append(f"### {label}")
            for value in values:
                lines.append(f"- {value}")
            lines.append("")

        structured_payload = {
            "number": number,
            "active_skill_name": skill_name,
            "is_core": is_core,
            "raw_text": parsed["raw_text"],
            "normalized_text": parsed["normalized_text"],
            "clauses": parsed["clauses"],
            "categories": parsed["categories"],
        }
        lines.extend([
            "## Structured Data",
            "```yaml",
            yaml.safe_dump(structured_payload, allow_unicode=True, sort_keys=False).rstrip(),
            "```",
        ])

        return "\n".join(lines)

    def get_user_preferences_context(self, preference_name: Optional[str] = None) -> str:
        """
        Build a consolidated HIGH PRIORITY context block from the selected
        user preference profile.

        Selection priority:
        1. If preference_name is given (number "#2" or name keyword), use that.
        2. Otherwise, use active_skill_name from preference_config.yaml.
        3. Otherwise, use the legacy .core pointer if present.
        4. If nothing exists, return empty string.

        The context block lists all available profiles with their numbers
        so the PlanAgent and user can reference them.

        Args:
            preference_name: Optional "#N" number or name keyword.
        """
        all_skills = self.load_all_user_skills()
        if not all_skills:
            return ""

        import re as _re
        selected_skills = {}
        target_key = None

        if preference_name:
            # Try by number first: "#2", "2"
            num_match = _re.match(r'#?\s*(\d+)', str(preference_name).strip())
            if num_match:
                num = int(num_match.group(1))
                for key, content in all_skills.items():
                    if self._get_preference_number(key, content) == num:
                        target_key = key
                        break

            if not target_key:
                # Try by filename
                if f"user/{preference_name}" in all_skills:
                    target_key = f"user/{preference_name}"
                elif preference_name in all_skills:
                    target_key = preference_name
                else:
                    # Fuzzy name match
                    for key, content in all_skills.items():
                        title_match = _re.search(r'^#\s+(.+)$', content, _re.MULTILINE)
                        title = title_match.group(1) if title_match else key
                        if preference_name.lower() in title.lower() or preference_name.lower() in key.lower():
                            target_key = key
                            break

            if target_key:
                selected_skills[target_key] = all_skills[target_key]
            else:
                logger.warning(
                    f"Preference '{preference_name}' not found. "
                    f"Falling back to core preference."
                )

        if not selected_skills:
            # Use configured active/default preference
            target = self.get_active_user_skill() or self.get_core_preference()
            if target and target in all_skills:
                selected_skills[target] = all_skills[target]
            elif all_skills:
                first_key = list(all_skills.keys())[0]
                selected_skills[first_key] = all_skills[first_key]

        if not selected_skills:
            return ""

        # Build profile list
        profiles = self.list_user_preference_profiles()
        profile_lines = []
        for p in profiles:
            marker = '🎯 [default]' if p['is_core'] else '   '
            active_marker = ' ◀ active' if p.get('is_active') and not p['is_core'] else ''
            profile_lines.append(f"> #{p['number']} {marker} {p['name']}{active_marker}")

        parts = [
            "## 👤 User Preferences (HIGH PRIORITY — OVERRIDES DEFAULTS)",
            "",
        ]

        if len(profiles) > 1:
            parts.append(f"> 📋 Available preference profiles ({len(profiles)}):")
            parts.extend(profile_lines)
            parts.append("> 💡 use \"#N\" choose preference,such as \"use #2 preference for video generation\"")
        parts.append("")

        for skill_path, content in selected_skills.items():
            title_match = _re.search(r'^#\s+(.+)$', content, _re.MULTILINE)
            display_name = title_match.group(1) if title_match else skill_path
            num = self._get_preference_number(skill_path, content)
            num_str = f" #{num}" if num else ""

            parts.append(f"### 🎯 Selected Preference{num_str}: {display_name}")
            parts.append("")

            for section_name in [
                "## Original Description", "## Normalized Preference",
                "## Structured Fields", "## Structured Data",
                "## Visual Style", "## Content Type", "## Rendering Quality",
                "## Narrative & Editing", "## Color Guidelines",
                "## Applicable Scopes", "## Preference Detail",
                "## Overrides", "## Integration Rules",
                "## When to Apply",
            ]:
                idx = content.find(section_name)
                if idx >= 0:
                    next_idx = content.find("\n## ", idx + len(section_name))
                    section = content[idx:next_idx] if next_idx != -1 else content[idx:]
                    parts.append(section.strip())
                    parts.append("")

        parts.append("---")
        parts.append("")
        return '\n'.join(parts)

    def get_user_preference_for_tool(self, tool_name: str) -> str:
        """
        Get the ACTIVE user preference relevant to a specific MCP tool.

        Only the active preference is used to avoid conflicts between
        multiple user skills. When no active preference is set, uses
        the first available one.

        Args:
            tool_name: Name of the MCP tool (e.g., 'text2video_gen').

        Returns:
            Relevant preference content, or empty string.
        """
        tool_category_map = {
            'text2video_gen': ['style', 'visual', 'camera', 'quality'],
            'image2video_gen': ['style', 'visual', 'camera', 'quality'],
            'storyvideo_gen': ['style', 'visual', 'camera', 'quality', 'pacing', 'theme', 'workflow'],
            'entity2video': ['style', 'visual', 'camera', 'quality', 'pacing', 'theme'],
            'text2image_generate': ['style', 'visual', 'quality'],
            'image2image_generate': ['style', 'visual', 'quality'],
            'audio_gen': ['style', 'quality'],
            'speech_gen': ['style', 'quality'],
            'plan_audio_for_video': ['style', 'quality', 'pacing'],
            'generate_audio_assets_from_plan': ['style', 'quality', 'pacing'],
            'mux_audio_timeline': ['output', 'quality'],
            'merge2videos': ['output', 'quality'],
            'remotion_compose_video': ['output', 'quality', 'style', 'brand', 'caption'],
        }

        relevant_categories = tool_category_map.get(tool_name, ['style', 'quality'])

        # Use ONLY the active preference, not all user skills
        active = self.get_active_user_skill()
        if not active:
            # No active preference — try first available
            all_skills = self.list_user_skills()
            if not all_skills:
                return ""
            active = all_skills[0]

        content = self.load_user_skill(active)
        if not content:
            return ""

        # Check if this preference is relevant to the tool
        content_lower = content.lower()
        is_relevant = any(
            cat in content_lower or cat in active.lower()
            for cat in relevant_categories
        )
        if not is_relevant:
            return ""

        # Extract key sections
        parts = []
        for section_name in [
            "## Original Description", "## Normalized Preference",
            "## Structured Fields", "## Structured Data",
            "## Visual Style", "## Color Guidelines", "## Narrative",
            "## Rendering Quality", "## Preference Detail",
            "## Applicable Scopes", "## When to Apply",
        ]:
            idx = content.find(section_name)
            if idx >= 0:
                next_idx = content.find("\n## ", idx + len(section_name))
                section = content[idx:next_idx] if next_idx != -1 else content[idx:]
                parts.append(section.strip())

        if parts:
            return (
                "## 👤 Active User Preference for this Tool\n"
                "> ⚠️ Apply this preference. It OVERRIDES defaults.\n\n"
                + "\n\n".join(parts)
            )
        return ""

    def save_user_skill(self, filename: str, content: str,
                        is_core: bool = None) -> dict:
        """
        Save a NEW user preference skill under skills/user/.

        Preference files are named by creation number only:
        preference_01.md, preference_02.md, ... . The active/default
        preference is controlled by skills/user/preference_config.yaml.
        """
        import re as _re

        orig_content = content or ""
        content = orig_content.strip()
        code_block_match = _re.match(
            r'```(?:markdown|md)?\s*\n(.*?)\n\s*```\s*$',
            content,
            _re.DOTALL,
        )
        if code_block_match:
            content = code_block_match.group(1).strip()
            logger.info("Stripped markdown code block wrapper from user skill content")
        if content.startswith('```'):
            content = _re.sub(r'^```(?:markdown|md)?\s*\n', '', content)
            content = _re.sub(r'\n\s*```\s*$', '', content)
            content = content.strip()

        existing_skills = self.list_user_skills()
        number = 1 if not existing_skills else self._get_next_preference_number()
        if is_core is None:
            is_core = not existing_skills or self.get_core_preference() is None

        numbered_filename = self._preference_filename(number)
        skill_name = numbered_filename[:-3]
        skill_key = f"user/{skill_name}"

        if not content or len(content) < 10:
            return {
                'success': False,
                'output_path': None,
                'number': None,
                'message': 'Cannot save preference: the preference description is empty.',
            }

        if '## Preference Number:' not in content:
            content = self.build_user_preference_markdown(
                content,
                number=number,
                is_core=bool(is_core),
                active_skill_name=skill_name,
            )
        else:
            marker = 'DEFAULT' if is_core else 'PROFILE'
            content = _re.sub(
                r'## Preference Number:\s*\d+(?:\s*\[[^\]]+\])?',
                f'## Preference Number: {number} [{marker}]',
                content,
                count=1,
            )
            if '> Skill Name:' in content:
                content = _re.sub(r'> Skill Name:.*', f'> Skill Name: {skill_name}', content, count=1)
            else:
                content = _re.sub(
                    r'(## Preference Number:.*\n)',
                    r'\1> Skill Name: ' + skill_name + '\n',
                    content,
                    count=1,
                )

        body_lines = [
            line for line in content.split('\n')
            if line.strip()
            and not line.startswith('#')
            and not line.startswith('>')
            and not line.startswith('```')
            and not line.startswith('---')
        ]
        body_text = '\n'.join(body_lines).strip()
        stub_patterns = [
            r'^pref-\d{3}-.*\.md$',
            r'^preference_\d+\.md$',
            r'^skills/user/.*\.md$',
            r'^[a-z0-9\-_]+\.md$',
        ]
        is_stub = (
            len(body_text) < 30
            or any(_re.match(pattern, body_text) for pattern in stub_patterns)
        )
        if is_stub:
            logger.error(
                "save_user_skill REFUSED: content body is too short or appears "
                "to be a filename stub (%s chars): %r. Full input first 200 chars: %r",
                len(body_text),
                body_text[:100],
                orig_content[:200],
            )
            return {
                'success': False,
                'output_path': None,
                'number': None,
                'message': (
                    'Cannot save preference: the content body is empty or just a filename. '
                    f'Body: "{body_text[:80]}"'
                ),
            }

        os.makedirs(self.user_skills_dir, exist_ok=True)
        file_path = os.path.join(self.user_skills_dir, numbered_filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            self._user_skill_cache.clear()

            config_active = self._get_config_active_preference()
            should_activate = bool(is_core) or not existing_skills or config_active is None
            if should_activate:
                self._write_preference_config(skill_name, core_skill_name=skill_name)
            elif not os.path.exists(self.user_preferences_config_path):
                fallback = self.get_core_preference()
                if fallback:
                    fallback_name = self._normalize_preference_skill_name(fallback)
                    self._write_preference_config(fallback_name, core_skill_name=fallback_name)

            abs_path = os.path.abspath(file_path)
            logger.info("User preference saved: %s (#%s, active=%s)", abs_path, number, should_activate)
            return {
                'success': True,
                'output_path': abs_path,
                'number': number,
                'is_core': bool(is_core),
                'skill_name': skill_name,
                'config_path': self.user_preferences_config_path,
                'message': f'Preference #{number} saved: {numbered_filename}',
            }
        except Exception as e:
            logger.error(f"Failed to save user skill: {e}")
            return {
                'success': False,
                'output_path': None,
                'number': None,
                'message': f'Failed to save: {e}',
            }

    def _set_core_pointer(self, skill_key: str) -> None:
        """Legacy compatibility: set the old .core pointer file."""
        core_file = os.path.join(self.user_skills_dir, '.core')
        with open(core_file, 'w') as f:
            f.write(skill_key)

    def update_user_skill(self, identifier: str, new_content: str,
                          mode: str = 'merge') -> dict:
        """
        Update an EXISTING user preference by number or name.

        Args:
            identifier: Preference number ("2", "#2") or name keyword.
            new_content: New content to add or replace with.
            mode: 'merge' (append to existing) or 'replace' (overwrite).

        Returns:
            dict with 'success', 'output_path', 'number', 'message'.
        """
        import re as _re
        import datetime

        all_skills = self.load_all_user_skills()
        if not all_skills:
            return {'success': False, 'output_path': None, 'number': None,
                    'message': 'No existing preferences to update. Use "save preference" to create one.'}

        # Find target
        target_key = self._resolve_preference_identifier(identifier)

        if not target_key:
            return {'success': False, 'output_path': None, 'number': None,
                    'message': f"No preference matching '{identifier}'. {self._format_preference_list()}"}

        existing = self.load_user_skill(target_key)
        if not existing:
            return {'success': False, 'output_path': None, 'number': None,
                    'message': f'Could not load preference: {target_key}'}

        # Strip code blocks from new content
        new_content = new_content.strip()
        if new_content.startswith('```'):
            new_content = _re.sub(r'^```(?:markdown|md)?\s*\n', '', new_content)
            new_content = _re.sub(r'\n\s*```\s*$', '', new_content)
            new_content = new_content.strip()

        if mode == 'replace':
            updated = new_content
        else:
            # Merge: append new content sections, avoid duplicating headers
            existing_headers = set(_re.findall(r'^##\s+(.+)$', existing, _re.MULTILINE))
            new_lines = new_content.split('\n')
            filtered_lines = []
            skip_block = False
            for line in new_lines:
                header_match = _re.match(r'^##\s+(.+)$', line)
                if header_match:
                    skip_block = header_match.group(1) in existing_headers
                if not skip_block:
                    filtered_lines.append(line)
            append_content = '\n'.join(filtered_lines).strip()
            updated = existing.rstrip() + '\n\n' + append_content

        # Update timestamp
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        updated = _re.sub(r'> Updated:.*', f'> Updated: {timestamp}', updated)
        if '> Updated:' not in updated:
            updated = _re.sub(
                r'(> Created:.*)',
                r'\1\n> Updated: ' + timestamp, updated, count=1
            )

        # Write back
        fname = target_key.replace('user/', '') + '.md'
        file_path = os.path.join(self.user_skills_dir, fname)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(updated)

            self._user_skill_cache.clear()
            number = self._get_preference_number(target_key, updated)
            logger.info(f"User skill updated: {file_path} (#{number}, mode={mode})")
            return {
                'success': True,
                'output_path': os.path.abspath(file_path),
                'number': number,
                'message': f'Preference #{number} updated ({mode} mode): {fname}',
            }
        except Exception as e:
            return {'success': False, 'output_path': None, 'number': None,
                    'message': f'Failed to update: {e}'}

    # ── Multi-Preference Management (Numbered System) ──────────────────
    #
    # Each user preference profile is assigned a unique number.
    # Users can reference preferences by number ("use #2") or by name.
    # skills/user/preference_config.yaml tracks active_skill_name.

    def _get_preference_number(self, skill_key: str, content: str = None) -> Optional[int]:
        """Extract the assigned preference number from a skill's content."""
        import re as _re
        if content is None:
            content = self.load_user_skill(skill_key) or ""
        match = _re.search(r'## Preference Number:\s*(\d+)', content)
        if match:
            return int(match.group(1))
        # Fallback: try to extract from filename (preference_01 or legacy pref-001).
        fname = skill_key.replace('user/', '')
        match = _re.match(r'preference_(\d+)', fname)
        if match:
            return int(match.group(1))
        match = _re.match(r'pref-(\d+)', fname)
        return int(match.group(1)) if match else None

    def _get_next_preference_number(self) -> int:
        """Get the next available preference number."""
        all_skills = self.load_all_user_skills()
        max_num = 0
        for key, content in all_skills.items():
            num = self._get_preference_number(key, content)
            if num is not None and num > max_num:
                max_num = num
        return max_num + 1

    def get_core_preference(self) -> Optional[str]:
        """
        Get the configured active/default user preference key.

        preference_config.yaml is authoritative. Legacy .core is used only
        as a fallback for older installations.
        """
        active = self._get_config_active_preference()
        if active:
            return active

        core_file = os.path.join(self.user_skills_dir, '.core')
        if os.path.exists(core_file):
            try:
                with open(core_file, 'r', encoding='utf-8') as f:
                    core = f.read().strip()
                if core in self.load_all_user_skills():
                    core_name = self._normalize_preference_skill_name(core)
                    if not os.path.exists(self.user_preferences_config_path):
                        self._write_preference_config(core_name, core_skill_name=core_name)
                    return core
            except Exception:
                pass

        all_skills = self.load_all_user_skills()
        if not all_skills:
            return None

        fallback = None
        for key, content in all_skills.items():
            if self._get_preference_number(key, content) == 1:
                fallback = key
                break
        if fallback is None:
            fallback = list(all_skills.keys())[0]

        if not os.path.exists(self.user_preferences_config_path):
            fallback_name = self._normalize_preference_skill_name(fallback)
            self._write_preference_config(fallback_name, core_skill_name=fallback_name)
        return fallback

    def set_core_preference(self, identifier: str) -> dict:
        """
        Set the active/default preference in preference_config.yaml.

        Args:
            identifier: Preference number ("2", "#2"), skill name, or name keyword.
        """
        all_skills = self.load_all_user_skills()
        if not all_skills:
            return {'success': False, 'core_skill': None, 'number': None,
                    'message': 'No user preferences found'}

        target = self._resolve_preference_identifier(identifier)
        if not target:
            return {'success': False, 'core_skill': None, 'number': None,
                    'message': f"No preference matching '{identifier}'. "
                               f"Available: {self._format_preference_list()}"}

        old_core = self.get_core_preference()
        target_name = self._normalize_preference_skill_name(target)
        try:
            self._write_preference_config(target_name, core_skill_name=target_name)

            self._update_preference_marker(target, is_core=True)
            if old_core and old_core != target:
                self._update_preference_marker(old_core, is_core=False)

            self._user_skill_cache.clear()
            target_num = self._get_preference_number(target)
            return {
                'success': True,
                'core_skill': target,
                'active_skill': target,
                'skill_name': target_name,
                'number': target_num,
                'config_path': self.user_preferences_config_path,
                'message': f'Active preference set to #{target_num}: {target_name}',
            }
        except Exception as e:
            return {'success': False, 'core_skill': None, 'number': None, 'message': str(e)}

    def _update_preference_marker(self, skill_key: str, is_core: bool) -> None:
        """Update the [CORE]/[PROFILE] marker in a preference file."""
        content = self.load_user_skill(skill_key)
        if not content:
            return
        import re as _re
        if is_core:
            content = _re.sub(r'\[(PROFILE|DEFAULT)\]', '[DEFAULT]', content)
            if '[DEFAULT]' not in content:
                content = _re.sub(
                    r'(## Preference Number:\s*\d+)',
                    r'\1 [DEFAULT]', content, count=1
                )
        else:
            content = _re.sub(r'\[(CORE|DEFAULT)\]', '[PROFILE]', content)

        fname = skill_key.replace('user/', '') + '.md'
        file_path = os.path.join(self.user_skills_dir, fname)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            logger.warning(f"Failed to update preference marker for {skill_key}: {e}")

    def get_preference_by_number(self, number: int) -> Optional[str]:
        """
        Get a preference skill key by its number.

        Args:
            number: The preference number (1-based).

        Returns:
            Skill key (e.g., 'user/preference_01') or None.
        """
        for key, content in self.load_all_user_skills().items():
            if self._get_preference_number(key, content) == number:
                return key
        return None

    def _format_preference_list(self) -> str:
        """Build a human-readable numbered list of all preferences."""
        profiles = self.list_user_preference_profiles()
        parts = []
        for p in profiles:
            marker = '[default]' if p['is_core'] else '      '
            parts.append(f"#{p['number']} {marker} {p['name']}")
        return '; '.join(parts) if parts else '(none)'

    def set_active_user_skill(self, skill_name: str) -> dict:
        """
        Set the currently active preference by updating preference_config.yaml.

        This is the same persisted switch users can perform manually by
        editing the active_skill_name field in skills/user/preference_config.yaml.
        """
        result = self.set_core_preference(skill_name)
        return {
            'success': result.get('success'),
            'active_skill': result.get('active_skill') or result.get('core_skill'),
            'skill_name': result.get('skill_name'),
            'config_path': result.get('config_path'),
            'message': result.get('message'),
        }

    def get_active_user_skill(self) -> Optional[str]:
        """Get the preference selected by preference_config.yaml."""
        return self.get_core_preference()

    def list_user_preference_profiles(self) -> List[dict]:
        """
        List all user preference profiles with numbers, names, and summaries.

        Returns:
            List of dicts with 'key', 'number', 'name', 'summary', 'is_core', 'is_active'.
        """
        import re as _re
        all_skills = self.load_all_user_skills()
        core = self.get_core_preference()
        active = self.get_active_user_skill()
        profiles = []

        for key, content in all_skills.items():
            title_match = _re.search(r'^#\s+(.+)$', content, _re.MULTILINE)
            name = title_match.group(1) if title_match else key.replace('user/', '')

            summary = ''
            for line in content.split('\n'):
                line = line.strip()
                if line and not line.startswith('#') and not line.startswith('>') and len(line) > 20:
                    summary = line[:120]
                    break

            number = self._get_preference_number(key, content)

            profiles.append({
                'key': key,
                'number': number,
                'name': name,
                'summary': summary,
                'is_core': key == core,
                'is_active': key == active,
            })

        # Sort by number
        profiles.sort(key=lambda p: p['number'] or 999)
        return profiles

    def find_skills_for_tool(self, tool_name: str) -> List[str]:
        """
        Find skills relevant to a specific MCP tool.

        Searches skill content for references to the tool.

        Args:
            tool_name: Name of the MCP tool (e.g., "text2video_gen").

        Returns:
            List of skill paths that reference this tool.
        """
        matching = []
        for skill_path in self.list_skills():
            try:
                content = self.load_skill(skill_path)
                if tool_name in content:
                    matching.append(skill_path)
            except Exception:
                continue
        return matching

    def find_skills_for_task(self, task_description: str) -> List[str]:
        """
        Find skills potentially relevant to a user task.

        Performs keyword matching against skill content.

        Args:
            task_description: The user's task description.

        Returns:
            List of skill paths ranked by relevance (most relevant first).
        """
        keywords = self._extract_keywords(task_description)
        if not keywords:
            return []

        scores = {}
        for skill_path in self.list_skills():
            try:
                content = self.load_skill(skill_path)
                score = sum(1 for kw in keywords if kw.lower() in content.lower())
                if score > 0:
                    scores[skill_path] = score
            except Exception:
                continue

        # Sort by score descending
        return sorted(scores.keys(), key=lambda k: scores[k], reverse=True)

    def find_theme_skills_for_task(
        self,
        task_description: str,
        *,
        threshold: float = 0.8,
        limit: int = 3,
    ) -> List[str]:
        """
        Match topic-specific theme skills from skills/themes/.

        Theme skills are quality-enhancement context only. They may refine
        prompts, storyboard logic, scene direction, content structure, and audio
        planning, but never alter the core workflow, approval gates, safety
        review, user permissions, or exact approved tool handoff.
        """
        matches: List[tuple[str, float]] = []
        for skill_path in self.list_skills("themes"):
            metadata = self._load_skill_metadata(skill_path)
            if not metadata:
                continue
            score = self._score_theme_skill(task_description, metadata)
            if score >= threshold:
                matches.append((skill_path, score))

        matches.sort(key=lambda item: item[1], reverse=True)
        return [skill_path for skill_path, _score in matches[:limit]]

    def build_theme_generation_context(
        self,
        task_description: str,
        *,
        threshold: float = 0.8,
        limit: int = 3,
    ) -> str:
        """
        Build a compact, prompt-ready generation enhancement block for matched
        theme skills.

        This block is intentionally advisory: downstream planning may use it to
        enrich prompts, storyboards, scene plans, and audio plans, but it must
        not override user instructions, approval gates, safety review, or tool
        contracts.
        """
        theme_paths = self.find_theme_skills_for_task(
            task_description,
            threshold=threshold,
            limit=limit,
        )
        if not theme_paths:
            return ""

        lines = [
            "## Theme Generation Enhancement Context",
            "Use the following matched theme guides only to enrich final generation prompts, storyboard details, content structure, scene design, and audio plans. Do not change workflow, review gates, permissions, safety policy, tool contracts, or explicit user instructions.",
        ]
        for theme_path in theme_paths:
            metadata = self._load_skill_metadata(theme_path)
            guide = metadata.get("optimization_guide") or {}
            if not isinstance(guide, dict):
                guide = {}
            theme_name = metadata.get("name", theme_path)
            lines.append(f"### {theme_path} — {theme_name}")
            for key in [
                "prompt_enhancement",
                "visual_style",
                "storyboard_logic",
                "content_structure",
                "scene_design",
                "audio_design",
            ]:
                value = guide.get(key)
                if value:
                    lines.append(f"- {key}: {value}")
            lines.append("- theme_consistency_target: >= 0.8 before approved generation handoff; revise prompts or storyboard details when lower.")

        return "\n".join(lines)

    def _load_skill_metadata(self, skill_path: str) -> Dict[str, Any]:
        """Load YAML front matter from a skill file, if present."""
        try:
            content = self.load_skill(skill_path)
        except Exception:
            return {}

        if not content.startswith("---"):
            return {}

        end_idx = content.find("\n---", 3)
        if end_idx == -1:
            return {}

        raw = content[3:end_idx].strip()
        try:
            parsed = yaml.safe_load(raw) or {}
            return parsed if isinstance(parsed, dict) else {}
        except yaml.YAMLError as e:
            logger.warning(f"Invalid skill metadata for '{skill_path}': {e}")
            return {}

    def _score_theme_skill(self, task_description: str, metadata: Dict[str, Any]) -> float:
        """Return a deterministic 0..1 match score for a theme skill."""
        task = (task_description or "").lower()
        if not task:
            return 0.0

        def _contains(term: str) -> bool:
            return bool(term) and term.lower() in task

        score = 0.0
        name = str(metadata.get("name") or "")
        skill_id = str(metadata.get("skill_id") or "")
        trigger_keywords = metadata.get("trigger_keywords") or []
        match_rule = metadata.get("match_rule") or {}
        if not isinstance(trigger_keywords, list):
            trigger_keywords = []
        if not isinstance(match_rule, dict):
            match_rule = {}

        if _contains(name) or _contains(skill_id.replace("_", " ")):
            score = max(score, 0.95)

        exact_hits = [kw for kw in trigger_keywords if _contains(str(kw))]
        if exact_hits:
            score = max(score, min(1.0, 0.84 + 0.05 * len(exact_hits)))

        keyword_combinations = match_rule.get("keyword_combinations") or []
        if isinstance(keyword_combinations, list):
            for combo in keyword_combinations:
                if isinstance(combo, str):
                    terms = [combo]
                elif isinstance(combo, list):
                    terms = [str(term) for term in combo]
                else:
                    continue
                if terms and all(_contains(term) for term in terms):
                    score = max(score, 0.9)

        semantic_terms = match_rule.get("semantic_terms") or []
        if isinstance(semantic_terms, list) and semantic_terms:
            semantic_hits = [term for term in semantic_terms if _contains(str(term))]
            if semantic_hits:
                semantic_score = min(0.82, 0.44 + 0.19 * len(semantic_hits))
                score = max(score, semantic_score)

        return min(1.0, score)

    # ── Prompt File Loading (Layer 3, kept for skill reference) ────────────

    def load_prompt(self, prompt_name: str) -> Optional[str]:
        """
        Load a Layer 3 prompt file.

        These are kept for reference by skills but are no longer the primary
        source of agent instructions.

        Args:
            prompt_name: Prompt file name without .txt extension.
                         Can be a path like "generation/t2v_refine_prompt".

        Returns:
            Prompt content, or None if not found.
        """
        file_path = os.path.join(self.prompts_dir, f"{prompt_name}.txt")
        if not os.path.exists(file_path):
            logger.warning(f"Prompt file not found: {file_path}")
            return None

        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    # ── Schema Loading ────────────────────────────────────────────────────

    def load_schema(self, schema_path: str) -> Optional[Dict]:
        """
        Load a JSON schema file.

        Args:
            schema_path: Path relative to schemas/ dir, e.g. "artifacts/brief.schema.json"

        Returns:
            Schema dict, or None if not found.
        """
        import json
        file_path = os.path.join(self.schemas_dir, schema_path)
        if not os.path.exists(file_path):
            logger.warning(f"Schema not found: {file_path}")
            return None

        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_schema_path_for_artifact(self, artifact_name: str) -> Optional[str]:
        """Return the schema path for a pipeline artifact, if one exists."""
        artifact_schema_map = {
            'brief': 'artifacts/brief.schema.json',
            'script': 'artifacts/script.schema.json',
            'storyboard': 'artifacts/storyboard_detail.schema.json',
            'scene_plan': 'artifacts/scene_plan.schema.json',
            'asset_manifest': 'artifacts/asset_manifest.schema.json',
            'proposals': 'artifacts/proposals.schema.json',
            'proposal': 'artifacts/proposal.schema.json',
            'edit_decisions': 'artifacts/edit_decisions.schema.json',
            'delivery_report': 'artifacts/delivery_report.schema.json',
            'render_report': 'artifacts/delivery_report.schema.json',
        }
        return artifact_schema_map.get(artifact_name)

    def get_schema_for_artifact(self, artifact_name: str) -> Optional[Dict]:
        """
        Get the JSON Schema for a pipeline artifact by name.

        Maps artifact names (e.g., 'brief', 'script', 'scene_plan') to
        their corresponding JSON Schema files.

        Args:
            artifact_name: Name of the artifact (e.g., 'brief', 'proposals').

        Returns:
            Schema dict, or None if no schema exists for this artifact.
        """
        import json

        schema_path = self.get_schema_path_for_artifact(artifact_name)
        if not schema_path:
            return None

        return self.load_schema(schema_path)

    def validate_artifact_against_schema(
        self, artifact_name: str, artifact_data: Any
    ) -> dict:
        """
        Validate a pipeline stage artifact against its JSON Schema.

        Args:
            artifact_name: Name of the artifact type (e.g., 'brief').
            artifact_data: The artifact data to validate.

        Returns:
            dict with 'valid' (bool), 'errors' (list of str), 'schema_path' (str).
        """
        schema = self.get_schema_for_artifact(artifact_name)
        if not schema:
            return {
                'valid': True,
                'errors': [],
                'schema_path': None,
                'note': f'No schema defined for artifact "{artifact_name}"',
            }

        try:
            import jsonschema

            validator_cls = jsonschema.validators.validator_for(schema)
            validator_cls.check_schema(schema)
            validator = validator_cls(schema)
            instance = artifact_data if isinstance(artifact_data, dict) else {}
            errors = [
                f"{'.'.join(map(str, error.path)) or '<root>'}: {error.message}"
                for error in sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
            ]

            return {
                'valid': len(errors) == 0,
                'errors': errors,
                'schema_path': self.get_schema_path_for_artifact(artifact_name),
            }
        except ImportError:
            # jsonschema not installed — basic structural check
            errors = []
            if isinstance(schema, dict) and 'required' in schema:
                if isinstance(artifact_data, dict):
                    for req_field in schema['required']:
                        if req_field not in artifact_data:
                            errors.append(f"Missing required field: '{req_field}'")
            return {
                'valid': len(errors) == 0,
                'errors': errors,
                'schema_path': self.get_schema_path_for_artifact(artifact_name),
                'note': 'Basic validation only (jsonschema not installed)',
            }
        except Exception as e:
            logger.warning(f"Schema validation error for '{artifact_name}': {e}")
            return {
                'valid': False,
                'errors': [str(e)],
                'schema_path': self.get_schema_path_for_artifact(artifact_name),
            }

    # ── Internal Helpers ──────────────────────────────────────────────────

    def _load_index(self) -> str:
        """Load and cache the skill INDEX file."""
        if self._index_cache is not None:
            return self._index_cache

        index_path = os.path.join(self.skills_dir, "INDEX.md")
        if not os.path.exists(index_path):
            logger.warning("skills/INDEX.md not found")
            return ""

        with open(index_path, 'r', encoding='utf-8') as f:
            self._index_cache = f.read()

        return self._index_cache

    def _extract_index_section(self, content: str, start_header: str, end_header: str) -> str:
        """Extract a section from the INDEX.md between two headers."""
        start_idx = content.find(start_header)
        if start_idx == -1:
            return ""

        end_idx = content.find(end_header, start_idx + len(start_header))
        if end_idx == -1:
            return content[start_idx:]

        return content[start_idx:end_idx].strip()

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from task description."""
        # CJK + English keyword extraction
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                      'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                      'would', 'could', 'should', 'may', 'might', 'can', 'shall',
                      'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
                      'and', 'or', 'but', 'not', 'no', 'yes', 'this', 'that',
                      'done', 'in', 'is', 'I', 'have', 'and', 'then', 'not', 'person',
                      'all', 'one', 'one', 'on', 'also', 'very', 'to', 'speak', 'need', 'go',
                      'you', 'will', 'ing', 'none', 'look', 'good', 'self', 'this', 'he', 'she'}

        # Simple tokenization
        words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]{2,}', text.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 1]
        return list(set(keywords))

    def _get_fallback_plan_prompt(self) -> str:
        """Fallback plan agent prompt when skill files are unavailable."""
        return """# Unified Video Planner Agent

## Role
You are Univideo, an expert video generation and processing planner.
Your task is to analyze user requests and create detailed, step-by-step
execution plans using available tools.

## Output Format
Generate a JSON execution plan with the following structure:
{
  "task_analysis": "Brief description",
  "execution_plan": {
    "total_steps": N,
    "steps": [
      {
        "step_number": 1,
        "action_description": "What this step accomplishes",
        "tool": {"name": "tool_name", "purpose": "...", "input_requirements": [...]},
        "dependencies": [],
        "status": "pending",
        "output": ""
      }
    ]
  }
}

Always provide clear, actionable steps with specific tool selections.
"""

    def _get_fallback_act_prompt(self) -> str:
        """Fallback act agent prompt when skill files are unavailable."""
        return """# Intelligent Video Task Execution Assistant

## Core Role
You execute video generation, editing, and processing plans step by step.

## Output Format
After each tool execution, output JSON:
{
    "success": "True/False",
    "message": "Description of what happened",
    "content": "The content/result of the execution",
    "output_path": "File path of generated output if applicable"
}
"""


# ── Module-level convenience ──────────────────────────────────────────────

# Global loader instance (lazy init)
_global_loader: Optional[SkillLoader] = None


def get_skill_loader(project_root: Optional[str] = None) -> SkillLoader:
    """Get or create the global SkillLoader instance."""
    global _global_loader
    if _global_loader is None:
        _global_loader = SkillLoader(project_root)
    return _global_loader


def reset_skill_loader():
    """Reset the global SkillLoader (useful for testing)."""
    global _global_loader
    _global_loader = None
