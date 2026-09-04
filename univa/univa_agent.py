import asyncio
import json
import os
import re
import traceback
import sys
from pathlib import Path
from dotenv import load_dotenv

from typing import List, Dict, Any, Optional
import logging

from agno.agent import Agent
from agno.tools.mcp import MultiMCPTools
from agno.db.sqlite import SqliteDb

def _init_env():
    base = Path(__file__).resolve().parents[1]
    env_file = base / ".env"
    if not env_file.exists():
        raise RuntimeError("Config missing: please copy .env.example to .env and fill your keys.")
    load_dotenv(dotenv_path=str(env_file), override=False)

_init_env()

from univa.config.config import config
from univa.utils.model_factory import create_model
from univa.utils.skill_loader import get_skill_loader, SkillLoader
from univa.utils.output_formatter import OutputFormatter
from univa.utils.budget_tracker import BudgetTracker
from univa.utils.pipeline_orchestrator import PipelineOrchestrator, PipelineState
from univa.utils.pipeline_state_store import PipelineStateStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global output formatter instance
output_fmt = OutputFormatter()

_PROMPT_SESSION = None


async def _read_user_input(prompt_text: str) -> str:
    """Read interactive CLI input with reliable CJK width handling.

    Python's builtin input/readline can leave stale wide-character glyphs on
    some terminals while backspacing Chinese text. prompt_toolkit redraws the
    line using wcwidth-aware cursor positioning. Use prompt_async here because
    the CLI already runs inside asyncio.run(main()).
    """
    if not sys.stdin.isatty():
        return await asyncio.to_thread(input, prompt_text)

    try:
        from prompt_toolkit import PromptSession
    except Exception:
        return await asyncio.to_thread(input, prompt_text)

    global _PROMPT_SESSION
    if _PROMPT_SESSION is None:
        _PROMPT_SESSION = PromptSession()
    return await _PROMPT_SESSION.prompt_async(prompt_text)


# ── Intent Classification for Auto-Routing ────────────────────────────────

def classify_intent(user_request: str) -> str:
    """
    Auto-classify user intent for pipeline routing.

    Returns one of: 'generate', 'edit', 'understand', 'compound', 'direct'
    Never prompts the user to choose a pipeline.

    Enhanced with:
    - Sequential dependency patterns ("first...then...", "analyze...then generate...")
    - Conditional patterns ("if...then...", "based on...generate...")
    - Compound conjunction detection
    """
    text = user_request.lower()

    # ── Weighted keyword scoring ──────────────────────────────────────────
    # Strong indicators (verbs/actions) get higher weight
    # Weak indicators (nouns/objects like "video") get lower weight

    # Edit intent: strong action verbs
    edit_strong = ['edit', 'modify', 'replace', 'replace with', 'turn into', 'change to',
                   'add filter', 'color grade', 'edit', 'modify', 'replace',
                   'transform', 'repaint', 'depth']
    edit_weak = ['change', 'process', 'change', 'make', 'turn red', 'turn blue', 'turn green']
    edit_score = sum(3 for kw in edit_strong if kw in text) + \
                 sum(1 for kw in edit_weak if kw in text)

    # Understand intent: strong analysis verbs
    understand_strong = ['analyze', 'understand', 'describe', 'parse', 'analyze',
                         'understand', 'describe', 'explain', 'examine',
                         'what is this', 'what it says', 'what content', 'what style']
    understand_weak = ['what is the content', 'what exists', "what is", "what's in",
                       'content', 'assessment']
    understand_score = sum(3 for kw in understand_strong if kw in text) + \
                       sum(1 for kw in understand_weak if kw in text)

    # Generate intent: strong creation verbs
    generate_strong = ['generate', 'create', 'create', 'generate', 'create',
                       'produce', 'make', 'make one', 'help me make']
    generate_weak = ['video', 'video', 'short film', 'clip', 'make']
    generate_score = sum(3 for kw in generate_strong if kw in text) + \
                     sum(1 for kw in generate_weak if kw in text)

    scores = {
        'edit': edit_score,
        'understand': understand_score,
        'generate': generate_score,
    }

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    primary, primary_score = ranked[0]
    secondary, secondary_score = ranked[1]

    # If no clear intent, default to generate
    if primary_score == 0:
        return 'generate'

    # ── Compound intent detection: Enhanced ───────────────────────────────

    # Pattern 1: Sequential dependency connectors
    sequential_patterns = [
        'then', 'next', 'after', 'then', 'finally',
        'after that', 'then', 'next', 'finally',
        'first', 'first', 'first',
    ]
    has_sequential = any(p in text for p in sequential_patterns)

    # Pattern 2: Conditional/derived generation
    conditional_patterns = [
        'based on', 'based on', 'reference', 'imitate', 'according to', 'similar',
        'based on', 'according to', 'similar to', 'like',
        'if', 'if', 'if',
    ]
    has_conditional = any(p in text for p in conditional_patterns)

    # Pattern 3: Multi-phase process indicators
    multi_phase_patterns = [
        'then generate', 'then generate', 'analyze.*generate', 'understand.*create',
        'analyze.*generate', 'understand.*create', 'analyze.*then',
    ]
    import re as _re
    has_multi_phase = any(_re.search(p, text) for p in multi_phase_patterns)

    # Compound detection: multiple intent categories with meaningful scores
    compound_detected = False
    if secondary_score >= 2 and secondary_score >= primary_score * 0.4:
        strong_primary = any(kw in text for kw in {
            'edit': edit_strong, 'understand': understand_strong, 'generate': generate_strong
        }[primary])
        strong_secondary = any(kw in text for kw in {
            'edit': edit_strong, 'understand': understand_strong, 'generate': generate_strong
        }[secondary])
        if strong_primary and strong_secondary:
            compound_detected = True

    # Sequential/conditional patterns with different intent categories → compound
    if (has_sequential or has_conditional or has_multi_phase) and secondary_score >= 2:
        compound_detected = True

    # Three distinct intents all with sufficient scores → definitely compound
    tertiary = ranked[2][1]
    if primary_score >= 6 and secondary_score >= 3 and tertiary >= 3:
        compound_detected = True

    if compound_detected:
        return 'compound'

    return primary


def _preference_detection_text(user_request: str) -> str:
    """Extract the human request text from frontend/system wrappers."""
    text = (user_request or "").strip()
    lower = text.lower()
    marker = 'user request:'
    if marker in lower:
        idx = lower.rfind(marker)
        text = text[idx + len(marker):].strip()
    if '---' in text:
        text = text.split('---')[-1].strip()
    return text


def detect_user_preference_intent(user_request: str) -> Optional[Dict[str, Any]]:
    """
    Detect user-level preference operations before normal video routing.

    Returns a dict with operation: create | update | switch | query, or None.
    """
    text = _preference_detection_text(user_request)
    lowered = text.lower()
    if not text:
        return None

    has_pref_word = any(word in lowered for word in ['preference', 'preference', 'preference'])
    has_style_save = 'save style' in text or 'add style' in text or 'add style' in text
    if not has_pref_word and not has_style_save:
        return None

    query_patterns = [
        r'what preferences are available', r'view.*preference', r'list.*preference', r'show.*preference',
        r'current.*preference', r'default.*preference.*(what is|which)', r'preference.*(what is|what are available|how many)',
        r'list.*preference', r'show.*preference', r'current.*preference',
    ]
    if any(re.search(pattern, lowered) for pattern in query_patterns):
        return {'operation': 'query', 'text': text}

    # Do not intercept task prompts that merely specify a preference to use.
    task_verbs = ['generate', 'create', 'edit', 'analyze', 'understand', 'generate', 'create video', 'edit ', 'analyze']
    contains_task = any(verb in lowered for verb in task_verbs)

    switch_patterns = [
        r'(set as|set as|change to|switch to|switch to).*default.*preference',
        r'(switch|switch to|use).*preference$',
        r'(set|switch).*preference',
    ]
    if not contains_task and any(re.search(pattern, lowered) for pattern in switch_patterns):
        target = None
        number_match = re.search(r'#?\s*(\d+)|preference_(\d+)', lowered)
        if number_match:
            target = number_match.group(1) or number_match.group(2)
        else:
            target_match = re.search(r'(?:switch to|switch to|switch to|use|set as|set as)\s*(.+?)(?:preference|style|$)', text)
            if target_match:
                target = target_match.group(1).strip(' :,')
        return {'operation': 'switch', 'target': target, 'text': text}

    update_patterns = [
        r'(modify|update|adjust|add details).*preference', r'preference.*(add more|add|remove|delete|change to)',
        r'(update|modify|adjust).*preference',
    ]
    if not contains_task and any(re.search(pattern, lowered) for pattern in update_patterns):
        number_match = re.search(r'#?\s*(\d+)|preference_(\d+)', lowered)
        target = (number_match.group(1) or number_match.group(2)) if number_match else None
        return {'operation': 'update', 'target': target, 'text': text}

    create_patterns = [
        r'add.*preference', r'add.*preference', r'create.*preference', r'save.*preference',
        r'save.*style', r'add.*style', r'add.*style', r'remember.*(like|preference|style)',
        r'always', r'from now on', r'use by default', r'save.*preference',
        r'add.*preference', r'remember.*preference', r'my preference is',
    ]
    if any(re.search(pattern, lowered) for pattern in create_patterns):
        make_active = any(word in lowered for word in ['set as default', 'use by default', 'default', 'active'])
        return {'operation': 'create', 'text': text, 'make_active': make_active}

    return None


async def classify_intent_llm(user_request: str, plan_agent=None) -> dict:
    """
    LLM-enhanced intent classification for complex/ambiguous requests.

    Uses a lightweight LLM call to perform semantic intent analysis,
    returning a structured decomposition of compound intents.

    Args:
        user_request: The user's request text.
        plan_agent: Optional PlanAgent instance for LLM access.

    Returns:
        dict with keys: 'primary_intent', 'is_compound', 'sub_intents',
                        'decomposition_mode', 'confidence'
    """
    # Fast-path: if no plan_agent available, use keyword-based
    if plan_agent is None:
        kw_result = classify_intent(user_request)
        return {
            'primary_intent': kw_result,
            'is_compound': kw_result == 'compound',
            'sub_intents': [],
            'decomposition_mode': 'sequential' if kw_result == 'compound' else 'none',
            'confidence': 0.6,
        }

    classification_prompt = f"""Analyze this user request for video tasks. Classify the intent(s).

User request: "{user_request}"

Output a JSON object with:
- primary_intent: one of "generate", "edit", "understand", "track"
- is_compound: true if the request contains multiple distinct task types (e.g., analyze THEN generate)
- sub_intents: list of intents in execution order (only if is_compound)
- decomposition_mode: "sequential", "conditional", "parallel", or "none"
- confidence: 0.0 to 1.0

Rules:
- "analyzeXthen generateY" → is_compound=true, sub_intents=["understand", "generate"], mode="sequential"
- "generate one video" → is_compound=false, primary_intent="generate"
- "replace this video background with a beach" → is_compound=false, primary_intent="edit"
- Sequential connectors (then, next, then, then, after) strongly indicate compound
- Conditional patterns (based on, based on, if, based on) indicate compound

Output ONLY the JSON, no other text:"""

    try:
        response = await plan_agent.agent.arun(
            input=classification_prompt,
            stream=False,
        )
        content = response.content or ""

        # Extract JSON
        import re as _re
        match = _re.search(r'\{.*\}', content, _re.DOTALL)
        if match:
            import json
            result = json.loads(match.group(0))
            result.setdefault('primary_intent', 'generate')
            result.setdefault('is_compound', False)
            result.setdefault('sub_intents', [])
            result.setdefault('decomposition_mode', 'none')
            result.setdefault('confidence', 0.7)
            return result
    except Exception:
        pass

    # Fallback to keyword-based
    kw_result = classify_intent(user_request)
    return {
        'primary_intent': kw_result,
        'is_compound': kw_result == 'compound',
        'sub_intents': [],
        'decomposition_mode': 'sequential' if kw_result == 'compound' else 'none',
        'confidence': 0.5,
    }


def is_chat_request(user_request: str) -> bool:
    """
    Determine if a user request is a chat/info request (should be answered
    directly without plan generation) or a work request (needs Plan-Act flow).

    Chat requests are questions, greetings, help requests, or status checks
    that don't require tool execution.

    Returns True for chat requests, False for work requests.
    """
    full_text = user_request.lower().strip()

    # Extract ONLY the user's actual request if there's a media preamble
    # (the full text may include frontend directives and media lists that
    #  contain work-like keywords like "edit", "analyze", "generate")
    check_text = full_text
    user_part_start = full_text.find('user request:')
    if user_part_start >= 0:
        check_text = full_text[user_part_start + len('user request:'):].strip()
        # Also check if the user part is empty or just punctuation
        if len(check_text) < 4:
            check_text = full_text  # Fall back to full text

    # ── Strong chat indicators (weight 3) ────────────────────────────
    chat_strong = [
        'what can you do', 'what can you do', 'help', 'help',
        'hello', 'hello', 'hi', 'hey', 'thanks', 'thanks', 'thank you',
        'how many current', 'how many assets', 'what files are available', 'asset list', 'how many available assets',
        'list videos', 'video name', 'video name', 'list assets', 'asset name', 'asset order',
        'how to use', 'how to use', 'how to use', 'how to operate', 'how to', 'what formats are supported',
        'what is', 'what is', 'what is', 'explain', 'explain',
        'today weather', 'who are you', 'who are you',
        'goodbye', 'bye', 'goodbye',
        'ok', 'ok', 'okay', 'confirm', 'received', 'understood',
        'answer only', 'only answer', 'do not generate', 'no generation needed',
        'asset', 'available', 'how many',
        # ── Preference / state queries (informational) ──
        'how manypreference', 'what is the preference', 'default preference', 'what is the user preference',
        'current preference', 'what preference', 'which preferences', 'preference number',
        'what preferences do I have', 'what are my preferences',
        'currently active', 'currently used', 'currently using',
        'preference list', 'list preferences', 'view preferences',
    ]
    chat_score = sum(3 for kw in chat_strong if kw in check_text)

    # ── Weak chat indicators (weight 1) ──────────────────────────────
    chat_weak = [
        'what can do', 'capabilities', 'introduction', 'how', 'how',
        '?', 'question',
    ]
    chat_score += sum(1 for kw in chat_weak if kw in check_text)

    # ── Work indicators ──────────────────────────────────────────────
    question_patterns = ['what is', 'what is', 'how to use', 'how to use', 'how to use', 'how to operate', 'how to operate']
    is_question_about_tool = any(p in check_text for p in question_patterns)
    work_kw = [
        'generate', 'create', 'create', 'make', 'make one',
        'edit', 'modify', 'replace', 'replace with', 'turn into', 'change to',
        'analyze', 'understand', 'describe',
        'generate', 'create', 'make', 'produce',
        'edit', 'modify', 'change', 'replace',
        'analyze', 'understand', 'describe',
        'make', 'set', 'for', 'help',
    ]
    work_score = sum(3 for kw in work_kw if kw in check_text)
    # If it's a question about a tool/concept, it's chat regardless of keywords
    if is_question_about_tool and work_score <= 3:
        return True

    # Decision
    # When there's a media preamble and the user request is short, it's
    # likely asking about available files (chat) — UNLESS work keywords present
    if '## available media files' in full_text and user_part_start >= 0:
        if len(check_text) < 40:
            has_work_kw = any(kw in check_text for kw in work_kw)
            if not has_work_kw:
                return True  # Short question about media → chat
    if work_score > chat_score:
        return False  # Work request
    if chat_score > work_score:
        return True   # Chat request
    return work_score == 0


# ── Skill Loader Initialization ───────────────────────────────────────────

def _get_skill_loader() -> SkillLoader:
    """Get the global skill loader, auto-detecting project root."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return get_skill_loader(project_root)


# ── Legacy prompt loading (kept for Layer 3 prompts referenced by skills) ─

def load_prompt(prompt_name: str) -> str:
    """
    Load a Layer 3 prompt file.

    NOTE: This function is kept for backward compatibility with Layer 3 prompts
    (generation/, understanding/, track/). Agent-level instructions now come from
    skill files via SkillLoader, not from plan.txt.
    """
    prompt_dir = config.get('prompt_dir')
    prompt_path = os.path.join(prompt_dir, f"{prompt_name}.txt")

    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()


def generate_todo_progress_event(plan_data: Dict) -> Dict:
    """based on plan_data generate todo_progress event"""
    if not plan_data or "execution_plan" not in plan_data:
        return None

    steps = plan_data["execution_plan"]["steps"]
    todo_items = []

    for i, step in enumerate(steps):
        status = step.get("status", "pending")
        description = step.get("action_description", f"Step {i+1}")

        if status == "success":
            todo_status = "completed"
        elif status == "ongoing":
            todo_status = "in_progress"
        else:
            todo_status = "pending"

        todo_items.append({
            "id": i,
            "description": description,
            "status": todo_status,
            "tool": step.get("tool", {}),
            "output": step.get("output", "")
        })

    return {
        "type": "todo_progress",
        "items": todo_items,
        "overall_description": plan_data["execution_plan"].get("overall_description", "")
    }


class PlanAgent:
    """
    Plan Agent — generates structured execution plans from user requests.

    Now powered by skill files instead of hardcoded plan.txt:
    - Loads plan-agent-protocol skill for role + output format
    - Loads pipeline-loader skill for pipeline selection
    - References INDEX.md for tool overview
    """

    def __init__(self, mcp_tools: MultiMCPTools, plan_db, skill_loader: Optional[SkillLoader] = None, budget_tracker: Optional[BudgetTracker] = None):
        self.mcp_tools = mcp_tools
        self.skill_loader = skill_loader or _get_skill_loader()
        self.budget_tracker = budget_tracker  # Optional: for pipeline budget tracking

        # Build instructions from skill files (replaces load_prompt("plan"))
        try:
            plan_instructions = self.skill_loader.load_agent_protocol("plan")
            logger.info("Plan Agent: loaded instructions from skill files")
        except Exception as e:
            logger.warning(f"Failed to load plan agent skills, using fallback: {e}")
            plan_instructions = load_prompt("plan")

        # Get model configuration from config / .env
        plan_model_provider = config.get('plan_model_provider', 'openai')
        plan_model_id = config.get('plan_model_id', 'gpt-5-2025-08-07')
        plan_model_api_key = config.get('plan_model_api_key', '')
        plan_model_base_url = config.get('plan_model_base_url', '')
        plan_model_extra_params = config.get('plan_model_extra_params', '')

        self.agent = Agent(
            name="Univideo Plan Agent",
            model=create_model(
                provider=plan_model_provider,
                model_id=plan_model_id,
                api_key=plan_model_api_key,
                base_url=plan_model_base_url or None,
                extra_params=plan_model_extra_params,
            ),
            instructions=plan_instructions,
            db=plan_db,
            add_history_to_context=True,
            num_history_messages=10,
            session_state={
                "execution_history": []
            }
        )

    def _get_available_tools_description(self) -> str:
        tools_info = []
        if hasattr(self.mcp_tools, 'tools') and self.mcp_tools.tools:
            for tool in self.mcp_tools.tools:
                tools_info.append(f"- {tool.name}: {tool.description}")
        return "\n".join(tools_info) if tools_info else "No tools available"

    @staticmethod
    def assess_request_completeness(user_request: str) -> dict:
        """
        Assess the completeness of a user request for clarification decisions.

        Follows the clarification-protocol skill's trigger conditions.
        Returns a dict with completeness_score (0.0-1.0) and missing fields.
        """
        text = user_request.lower()
        checks = {
            "subject": False,    # Has specific subject/topic
            "action": False,     # Has action/plot description
            "style": False,      # Has visual style specification
            "duration": False,   # Has duration specification
            "platform": False,   # Has platform/use-case
        }

        # Check subject
        subject_indicators = [
            'cat', 'dog', 'person', 'car', 'mountain', 'sea', 'city', 'forest', 'person', 'character',
            'cat', 'dog', 'person', 'car', 'mountain', 'ocean', 'city', 'forest',
            'animal', 'landscape', 'building', 'food',
        ]
        checks["subject"] = any(w in text for w in subject_indicators) or len(text) > 20

        # Check action
        action_indicators = [
            'walk', 'run', 'jump', 'fly', 'eat', 'drink', 'speak', 'sing', 'dance', 'hit', 'write',
            'walk', 'run', 'jump', 'fly', 'eat', 'dance', 'sing', 'fight',
            'move', 'rotate', 'transform', 'transition', 'show',
        ]
        checks["action"] = any(w in text for w in action_indicators)

        # Check style
        style_indicators = [
            'style', 'cinematic', 'animation', 'realistic', 'cartoon', 'cyber', 'retro', 'modern',
            'style', 'cinematic', 'anime', 'realistic', 'cartoon', 'cyberpunk',
            'tone', 'warm', 'cool', 'bright', 'dark', 'color',
            'light', 'atmosphere',
        ]
        checks["style"] = any(w in text for w in style_indicators)

        # Check duration
        duration_patterns = [
            r'\d+\s*seconds', r'\d+\s*minutes', r'\d+\s*min', r'\d+\s*sec',
            r'\d+s\b', r'\d+m\b', 'duration', 'duration', 'length',
        ]
        import re as _re
        checks["duration"] = any(_re.search(p, text) for p in duration_patterns)

        # Check platform
        platform_indicators = [
            'TikTok', 'tiktok', 'youtube', 'bilibili', 'bilibili', 'Xiaohongshu',
            'wechat', 'wechat', 'Moments', 'ad', 'demo', 'product',
            'platform', 'platform', 'publish',
        ]
        checks["platform"] = any(w in text for w in platform_indicators)

        score = sum(1 for v in checks.values() if v) / len(checks)

        missing = [k for k, v in checks.items() if not v]
        return {
            "completeness_score": round(score, 2),
            "missing_fields": missing,
            "needs_clarification": score < 0.4,  # < 40% → must clarify
            "suggest_clarification": 0.4 <= score < 0.7,  # 40-70% → suggest
        }

    def extract_plan_from_content(self, content: str) -> Optional[Dict]:
        try:
            match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                start = content.find('{')
                end = content.rfind('}')
                if start != -1 and end != -1 and end > start:
                    json_str = content[start:end+1]
                else:
                    return content

            parsed_content = json.loads(json_str)
            if "execution_plan" in parsed_content:
                return parsed_content
            # JSON found but no execution_plan — return the JSON as-is
            return parsed_content if isinstance(parsed_content, dict) else content
        except (json.JSONDecodeError, Exception):
            # Cannot parse as plan JSON — return raw content
            # Callers must handle non-dict return (see execute_task guard)
            return content

    async def generate_plan(self, session_id, user_request: str) -> Optional[Dict]:
        """
        Generate an execution plan from a user request.

        Layer 2 on-demand loading: when the PlanAgent receives a user request,
        relevant skill content is loaded dynamically based on the task category.
        This keeps the agent's base system prompt lightweight (Layer 1 only)
        while providing detailed guidance when needed.
        """
        input_context = f"User Request: {user_request}\n"

        # Layer 2: Load task-relevant skills on demand
        skill_context = self._get_relevant_skill_context(user_request)
        if skill_context:
            input_context += f"\n### Relevant Skill Context\n{skill_context}\n"

        # Layer 2: Load pipeline & domain skills if task matches known patterns
        layer2_skills = self.skill_loader.load_layer2_skills(user_request)
        if layer2_skills:
            input_context += f"\n{layer2_skills}\n"

        # ── Inject real user preference state (prevent hallucination) ──
        try:
            profiles = self.skill_loader.list_user_preference_profiles()
            if profiles:
                pref_state = "\n### Current User Preference State (REAL DATA — do not fabricate)\n"
                for p in profiles:
                    markers = []
                    if p['is_core']: markers.append('CORE/DEFAULT')
                    pref_state += f"- #{p['number']} [{'/'.join(markers)}] {p['name']}"
                    if p['summary']: pref_state += f" — {p['summary'][:80]}"
                    pref_state += "\n"
                pref_state += f"\nTotal: {len(profiles)} preference profile(s). Next new preference will be #{self.skill_loader._get_next_preference_number()}.\n"
                input_context += pref_state
                logger.info(f"PlanAgent: injected real preference state ({len(profiles)} profiles)")
            else:
                input_context += (
                    "\n### Current User Preference State\n"
                    "No user preference profiles exist yet. "
                    "If the user asks to save preferences, the FIRST one will be #1 [CORE].\n"
                )
                logger.info("PlanAgent: no preferences exist, creating #1 will be first")
        except Exception as e:
            logger.debug(f"Could not inject preference state: {e}")

        try:
            execution_historys = self.agent.get_session_state(session_id).get("execution_history", None)
        except Exception:
            execution_historys = None

        if execution_historys:
            input_context += "\n### Previous Execution Results:\n"
            input_context += json.dumps(execution_historys, indent=2, ensure_ascii=False)
            input_context += "\n\nPlease consider the above execution results when generating the new plan.\n"
            input_context += "Note that the new plan step should only include the user's latest request task and not contain steps from previous tasks."

        response = await self.agent.arun(
            input=input_context,
            stream=False,
            session_id=session_id
        )

        plan_output = response.content
        plan_output_format = self.extract_plan_from_content(plan_output)
        plan_output_format = self._ensure_video_shot_planning_step(
            plan_output_format, user_request
        )

        # Track token usage for budget
        if self.budget_tracker:
            tokens_in = BudgetTracker.estimate_tokens(input_context)
            tokens_out = BudgetTracker.estimate_tokens(str(plan_output))
            self.budget_tracker.record_llm_call(
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                stage="plan",
            )

        return plan_output_format

    def _ensure_video_shot_planning_step(self, plan_data: Optional[Dict], user_request: str) -> Optional[Dict]:
        """
        Add a lightweight planning step before multi-shot or duration-sensitive
        generation plans when the LLM omitted it.

        This keeps direct one-shot generations cheap, but prevents common
        failures in complex video tasks: fixed-duration splitting, repeated
        adjacent shots, and missing continuity anchors.
        """
        if not isinstance(plan_data, dict):
            return plan_data

        execution_plan = plan_data.get("execution_plan")
        if not isinstance(execution_plan, dict):
            return plan_data

        steps = execution_plan.get("steps")
        if not isinstance(steps, list) or not steps:
            return plan_data

        tool_names = [
            step.get("tool", {}).get("name")
            for step in steps
            if isinstance(step, dict)
        ]
        if "plan_video_shots" in tool_names:
            return plan_data

        video_generation_tools = {
            "text2video_gen",
            "image2video_gen",
            "frame2frame_video_gen",
            "video_extension",
            "storyvideo_gen",
            "entity2video",
            "merge2videos",
        }
        if not any(tool in video_generation_tools for tool in tool_names):
            return plan_data

        text = f"{user_request}\n{execution_plan.get('overall_description', '')}".lower()
        complexity_markers = (
            "then", "next", "after", "then", "finally", "first", "multiple", "multi-shot",
            "shot", "storyboard", "story", "narrative", "transition", "transition", "turn into", "change",
            "morph", "duration", "seconds", "minutes", "story", "narrative", "shot",
            "transition", "morph", "duration", "seconds", "minutes",
        )
        generation_step_count = sum(tool in video_generation_tools for tool in tool_names)
        needs_planner = (
            generation_step_count > 1
            or any(marker in text for marker in complexity_markers)
            or any(tool in {"storyvideo_gen", "entity2video", "merge2videos"} for tool in tool_names)
        )
        if not needs_planner:
            return plan_data

        planning_step = {
            "step_number": 1,
            "action_description": (
                "Plan dynamic shot durations, continuity anchors, transitions, "
                "bridge clips, generation order, and expanded per-shot generation prompts "
                "before media generation."
            ),
            "tool": {
                "name": "plan_video_shots",
                "purpose": (
                    "Prevent fixed-duration splitting, repeated adjacent shots, "
                    "continuity drift, and under-specified per-shot prompts in video generation."
                ),
                "input_requirements": [
                    "Use the original user request as the creative brief",
                    "Infer target_duration_seconds and aspect_ratio from the request when present",
                    "Return shots[*].expanded_generation_prompt for every shot; each prompt must include subject, environment, action timing, camera, spatial composition, atmosphere, style anchors, transition context, continuity anchor, duplicate guard, and negative constraints",
                    "Later shot prompts must preserve the main theme and not conflict with earlier shot prompts",
                ],
            },
            "dependencies": [],
            "status": "ongoing",
            "output": "",
        }

        adjusted_steps = [planning_step]
        for original_idx, step in enumerate(steps, start=2):
            if not isinstance(step, dict):
                continue

            updated = dict(step)
            updated["step_number"] = original_idx
            updated["status"] = "pending"

            dependencies = updated.get("dependencies", [])
            if isinstance(dependencies, list):
                shifted = [
                    dep + 1 if isinstance(dep, int) else dep
                    for dep in dependencies
                ]
                if updated.get("tool", {}).get("name") in video_generation_tools and 1 not in shifted:
                    shifted.insert(0, 1)
                updated["dependencies"] = shifted
            elif updated.get("tool", {}).get("name") in video_generation_tools:
                updated["dependencies"] = [1]

            adjusted_steps.append(updated)

        execution_plan["steps"] = adjusted_steps
        execution_plan["total_steps"] = len(adjusted_steps)
        if execution_plan.get("overall_description"):
            execution_plan["overall_description"] = (
                f"{execution_plan['overall_description']} "
                "Includes a pre-generation shot plan for duration and continuity."
            )
        return plan_data

    def _get_relevant_skill_context(self, user_request: str) -> str:
        """
        Find and summarize skills relevant to the user's task.

        This gives the Plan Agent contextual knowledge about tools and
        workflows before generating a plan.
        """
        try:
            relevant_skills = self.skill_loader.find_skills_for_task(user_request)
            if not relevant_skills:
                return ""

            # Load top 3 most relevant skills and extract key parts
            context_parts = []
            for skill_path in relevant_skills[:3]:
                try:
                    content = self.skill_loader.load_skill(skill_path)
                    # Extract just the "When to Use" and key info
                    when_idx = content.find("## When to Use")
                    if when_idx >= 0:
                        # Take ~500 chars from When to Use section
                        excerpt = content[when_idx:when_idx+800]
                        context_parts.append(f"### {skill_path}\n{excerpt}\n")
                except Exception:
                    continue

            return "\n".join(context_parts) if context_parts else ""
        except Exception as e:
            logger.debug(f"Could not load skill context: {e}")
            return ""

    def inject_execution_results(self, session_id, plan, execution_results: Dict[int, Any]) -> Dict:
        try:
            current_state = self.agent.get_session_state(session_id).get("execution_history", [])
        except Exception:
            current_state = []

        current_state.append(
            {
                "plan": plan,
                "execution_results": execution_results
            }
        )

        self.agent.update_session_state(
            session_state_updates={"execution_history": current_state},
            session_id=session_id
        )


class ActAgent:
    """
    Act Agent — executes plan steps by calling MCP tools.

    Now powered by skill files instead of hardcoded instructions:
    - Loads act-agent-protocol skill for execution protocol
    - Loads reviewer skill for quality self-checks
    - References core skills for tool-specific guidance
    """

    def __init__(self, mcp_tools: MultiMCPTools, act_db=None, skill_loader: Optional[SkillLoader] = None, budget_tracker: Optional[BudgetTracker] = None):
        self.mcp_tools = mcp_tools
        self.skill_loader = skill_loader or _get_skill_loader()
        self.budget_tracker = budget_tracker  # Optional: for pipeline budget tracking

        # Build instructions from skill files (replaces hardcoded instructions)
        try:
            act_instructions = self.skill_loader.load_agent_protocol("act")
            logger.info("Act Agent: loaded instructions from skill files")
        except Exception as e:
            logger.warning(f"Failed to load act agent skills, using fallback: {e}")
            act_instructions = """
            # Intelligent Video Task Execution Assistant
            ## Core Role Definition
            You are an intelligent video task execution assistant (Video Act LLM), specialized in executing video generation, editing, and processing plans. You follow plans provided by the Plan Model while conducting intelligent thinking, calling, wait and feedback throughout the video production workflow.
            ## Output Format
            After received the tool execution result, you should output a JSON object with the following format:
            {
                "success": "True/False",
                "message": "Like Image generated successfully.",
                "content": "The content of the tool execution result, such as the generated image URL.",
                "output_path": "The output path of the tool execution result, such as the generated image file path."
            }
            """

        # Get model configuration from config / .env
        act_model_provider = config.get('act_model_provider', 'openai')
        act_model_id = config.get('act_model_id', 'gpt-5-2025-08-07')
        act_model_api_key = config.get('act_model_api_key', '')
        act_model_base_url = config.get('act_model_base_url', '')
        act_model_extra_params = config.get('act_model_extra_params', '')

        self.agent = Agent(
            name="Univideo Act Agent",
            model=create_model(
                provider=act_model_provider,
                model_id=act_model_id,
                api_key=act_model_api_key,
                base_url=act_model_base_url or None,
                extra_params=act_model_extra_params,
            ),
            tools=[mcp_tools],
            instructions=act_instructions,
            tool_call_limit=15,
        )

    async def execute_plan(self, question, plan) -> Dict[str, Any]:
        # ── Guard: plan must be a dict with execution_plan ──
        if not isinstance(plan, dict) or 'execution_plan' not in plan:
            logger.error(
                f"execute_plan received invalid plan type={type(plan).__name__}. "
                f"Plan content (first 300 chars): {str(plan)[:300]}"
            )
            return {
                "error": "Invalid plan format",
                "plan_type": type(plan).__name__,
                "raw_content": str(plan)[:500] if plan else "",
            }
        execution_results: Dict[int, Any]={}

        for idx, step in enumerate(plan['execution_plan']['steps']):
            try:
                logger.info(f"Executing step {idx+1}: {step.get('action_description', 'Unknown')}")
                result = await self._execute_step(step, question, plan, execution_results)

                execution_results[idx+1] = result
                plan = self.update_plan(plan, result, idx)
                logger.info(f"Step {idx+1} completed successfully")

            except Exception as e:
                error_msg = f"step {idx+1} execution failed: {str(e)}"
                logger.error(error_msg)
                return error_msg

        return execution_results

    async def _execute_step(self, step, question, plan, execution_results) -> Any:
        """
        Execute a single plan step with skill-enhanced context.

        Injects the relevant Core Skill for the tool being used, so the
        Act Agent has best-practice guidance for tool-specific parameters.
        """
        tool_name = step.get('tool', {}).get('name', 'unknown')

        # Build skill-enhanced context for this step
        skill_context = self._get_step_skill_context(tool_name)

        input_context = f"""
### User Request
{question}

### Whole Plan
{plan['execution_plan']}

### Completed Steps
{execution_results}

### Current Step
{step}
"""

        if skill_context:
            input_context += f"\n### Tool Skill Reference for '{tool_name}'\n{skill_context}\n"

        if tool_name in {
            'text2video_gen', 'image2video_gen', 'frame2frame_video_gen',
            'video_extension', 'storyvideo_gen', 'entity2video'
        }:
            input_context += (
                "\n### Mandatory Per-Shot Prompt Use\n"
                "If Completed Steps contains a plan_video_shots result, use the matching "
                "shots[*].expanded_generation_prompt as the generation prompt for this step. "
                "Do not pass the original user request or a short visual_prompt directly to the video generation tool unless no expanded_generation_prompt exists. "
                "When using a shot plan, also pass the shot duration_seconds and preserve continuity_anchor/start_state/end_state/duplicate_guard. "
                "For multi-shot workflows set auto_audio=False only on intermediate clips before merge2videos, then apply cohesive audio at merge time. "
                "For single-shot delivery, pass the approved auto_audio/audio_prompt/include_voiceover options so native video API audio can be preserved before any fallback.\n"
            )

        input_context += "\nYou can only perform the tasks specified in the current step."

        max_attempts = 3
        last_result = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = await self.agent.arun(
                    input=input_context,
                    stream=False
                )

                # Track token usage for budget
                if self.budget_tracker:
                    tokens_in = BudgetTracker.estimate_tokens(input_context)
                    tokens_out = BudgetTracker.estimate_tokens(str(response.content))
                    self.budget_tracker.record_llm_call(
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        stage="act",
                    )

                result = self.extract_json(response.content)

                if result is None:
                    logger.warning(f"No JSON found in response, treating as text message. Content: {response.content[:200]}...")
                    result = {
                        'success': False,
                        'message': response.content,
                        'content': response.content,
                        'output_path': None
                    }

                logger.info(f"Extracted result: {result}")
                last_result = result

                # ── Intercept: User skill operations ──
                # The ActAgent LLM cannot write files or modify preference_config.yaml directly.
                # We intercept three types of operations and handle them programmatically:
                #   1. CREATE: save_user_skill() → new numbered preference file
                #   2. SWITCH: set_core_preference() → update preference_config.yaml only
                #   3. UPDATE: update_user_skill() → modify existing preference file

                if self._is_core_switch_step(step):
                    # SWITCH: Only update preference_config.yaml, no file creation
                    handled = self._handle_core_switch(step, result)
                    if handled and handled.get('success') in [True, 'True', 'true']:
                        logger.info(f"Core switch handled programmatically: {handled.get('message')}")
                        result = handled
                        last_result = result
                    else:
                        logger.warning(f"Core switch failed: {handled.get('message')}")

                elif self._is_user_skill_creation_step(step, result):
                    # CREATE: New preference file with auto-numbering
                    saved = self._handle_user_skill_creation(
                        step, result, response.content
                    )
                    if saved and saved.get('success'):
                        logger.info(f"User skill saved programmatically: {saved.get('output_path')}")
                        result = saved
                        last_result = result
                    else:
                        logger.warning(
                            f"User skill creation interception failed: {saved.get('message') if saved else 'unknown'}"
                        )

                # ── Post-execution file verification ──
                # If the result claims to have created/saved a file, verify it
                # actually exists on disk. LLMs sometimes fabricate file paths.
                result = self._verify_output_files(result, step)

                if (
                    attempt < max_attempts
                    and self._is_transient_tool_failure(result)
                ):
                    delay = min(2 ** (attempt - 1), 5)
                    logger.warning(
                        "Transient tool failure in %s; retrying attempt %s/%s in %ss: %s",
                        tool_name,
                        attempt + 1,
                        max_attempts,
                        delay,
                        result.get('message') or result.get('content'),
                    )
                    await asyncio.sleep(delay)
                    continue

                self.current_step = {
                    "step": step,
                    "result": result
                }

                return result

            except Exception as e:
                if attempt >= max_attempts or not self._is_transient_failure_message(str(e)):
                    raise

                delay = min(2 ** (attempt - 1), 5)
                logger.warning(
                    "Transient act execution error in %s; retrying attempt %s/%s in %ss: %s",
                    tool_name,
                    attempt + 1,
                    max_attempts,
                    delay,
                    e,
                )
                await asyncio.sleep(delay)

        return last_result

    @staticmethod
    def _is_success_result(result: Any) -> bool:
        if not isinstance(result, dict):
            return False
        return result.get('success') in [True, 'True', 'true', 'success']

    def _verify_output_files(self, result: dict, step: dict) -> dict:
        """
        Verify claimed output files exist. If not and this is a user skill
        creation step, attempt to extract the content and actually save it.
        """
        if not isinstance(result, dict):
            return result

        output_path = result.get('output_path')
        if not output_path or not isinstance(output_path, str):
            return result

        import os as _os

        # Check if the file exists
        if _os.path.exists(output_path):
            # File exists — normalize to absolute path
            result['output_path'] = _os.path.abspath(output_path)
            return result

        # File doesn't exist — try alternate paths
        project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        for candidate_rel in [
            output_path,
            output_path.replace('univa/univa/', 'univa/'),  # Fix double univa
            output_path.replace('univa/skills/', 'skills/').replace('skills/user/', ''),
        ]:
            alt = _os.path.join(project_root, 'skills', 'user',
                              candidate_rel.split('skills/user/')[-1] if 'skills/user/' in candidate_rel
                              else candidate_rel.split('/')[-1])
            if _os.path.exists(alt):
                result['output_path'] = _os.path.abspath(alt)
                logger.info(f"Found file at alternate path: {alt}")
                return result

        # File truly doesn't exist — check if this is a user skill creation
        action = step.get('action_description', '').lower()
        is_skill_creation = (
            any(kw in action for kw in ['create', 'save', 'generate', 'create', 'save', 'preference', 'preference', 'skill'])
            and 'skills/user' in str(output_path) + str(result.get('message', '')) + str(result.get('content', ''))
        )

        if is_skill_creation:
            # Try to salvage: extract content from the LLM response and save
            logger.warning(
                f"User skill creation claimed but file not found. "
                f"Attempting salvage save. Claimed: {output_path}"
            )
            # Pass both the content field (for direct extraction) and the
            # full result dict serialized (for markdown code block extraction)
            raw_for_extraction = str(result.get('content', '') or '')
            if result.get('message'):
                raw_for_extraction += '\n' + str(result.get('message', ''))
            saved = self._handle_user_skill_creation(
                step, result, raw_for_extraction
            )
            if saved and saved.get('success'):
                logger.info(f"Salvage save succeeded: {saved.get('output_path')}")
                return saved
            else:
                logger.error("Salvage save also failed")

        # Downgrade to failure
        if any(kw in action for kw in ['create', 'save', 'generate', 'create', 'save', 'generate', 'write', 'write']):
            result['success'] = 'False'
            result['message'] = (
                f"File creation claimed but not verified on disk. "
                f"Claimed path '{output_path}' does not exist."
            )
            result['output_path'] = None
            logger.error(f"Downgraded fabricated file creation to failure: {action[:100]}")

        return result

    @staticmethod
    def _is_transient_failure_message(message: str) -> bool:
        text = (message or '').lower()
        markers = (
            'temporary failure in name resolution',
            'failed to resolve',
            'nameresolutionerror',
            'name or service not known',
            'dns',
            'max retries exceeded',
            'connection aborted',
            'connection reset',
            'connection refused',
            'connection timed out',
            'read timed out',
            'connect timeout',
            'readtimeout',
            'connecttimeout',
            'httpsconnectionpool',
            'temporarily unavailable',
            'server disconnected',
            'bad gateway',
            'service unavailable',
            'gateway timeout',
        )
        return any(marker in text for marker in markers)

    def _is_transient_tool_failure(self, result: Any) -> bool:
        if self._is_success_result(result) or not isinstance(result, dict):
            return False

        message = f"{result.get('message', '')}\n{result.get('content', '')}"
        return self._is_transient_failure_message(message)

    # Tools that require prompt validation before calling
    _PROMPT_VALIDATION_TOOLS = {
        'text2video_gen', 'image2video_gen', 'frame2frame_video_gen',
        'video_extension', 'storyvideo_gen', 'entity2video',
        'text2image_generate', 'image2image_generate', 'sequential_image_gen',
    }

    def _get_step_skill_context(self, tool_name: str) -> str:
        """
        Load the Core Skill content for a specific tool.

        This gives the Act Agent detailed usage guidance, parameter tips,
        and common pitfalls for the tool it's about to call.

        For generation tools, also loads the prompt-validator skill
        to enforce mandatory prompt quality checks before calling the tool.
        """
        # Tool-to-skill mapping
        tool_skill_map = {
            'plan_video_shots': 'core/wavespeed-video-gen',
            'text2video_gen': 'core/wavespeed-video-gen',
            'image2video_gen': 'core/wavespeed-video-gen',
            'frame2frame_video_gen': 'core/wavespeed-video-gen',
            'video_extension': 'core/wavespeed-video-gen',
            'storyvideo_gen': 'core/wavespeed-video-gen',
            'entity2video': 'core/wavespeed-video-gen',
            'text2image_generate': 'core/wavespeed-image-gen',
            'image2image_generate': 'core/wavespeed-image-gen',
            'sequential_image_gen': 'core/wavespeed-image-gen',
            'depth_modify': 'core/video-editing',
            'style_transfer': 'core/video-editing',
            'repainting': 'core/video-editing',
            'pose_reference': 'core/video-editing',
            'vision2text_gen': 'core/video-understanding',
            'index_video_media': 'core/media-index',
            'update_video_index_segments': 'core/media-index',
            'search_video_moments': 'core/media-index',
            'get_video_moment': 'core/media-index',
            'video_referring_segmentation': 'core/video-tracking',
            'audio_gen': 'core/audio-gen',
            'speech_gen': 'core/audio-gen',
            'plan_audio_for_video': 'core/audio-gen',
            'generate_audio_assets_from_plan': 'core/audio-gen',
            'mux_audio_timeline': 'core/audio-gen',
            'transcribe_media': 'core/localization',
            'translate_captions': 'core/localization',
            'prepare_localized_captions': 'core/localization',
            'generate_localized_voiceover': 'core/localization',
            'render_localized_video': 'core/localization',
            'validate_localized_media': 'core/localization',
            'merge2videos': 'core/ffmpeg-merge',
        }

        skill_path = tool_skill_map.get(tool_name)
        sections = []

        # ── Load tool-specific Core Skill ──
        if skill_path:
            try:
                content = self.skill_loader.load_skill(skill_path)
                for header in ["## Tool Contracts", "## Process", "## Common Pitfalls"]:
                    idx = content.find(header)
                    if idx >= 0:
                        next_idx = content.find("\n## ", idx + len(header))
                        if next_idx == -1:
                            sections.append(content[idx:])
                        else:
                            sections.append(content[idx:next_idx])
                if not sections:
                    sections.append(content[:1500])
            except Exception as e:
                logger.debug(f"Could not load skill {skill_path}: {e}")
        else:
            # Try to find matching skills dynamically
            matching = self.skill_loader.find_skills_for_tool(tool_name)
            if matching:
                try:
                    content = self.skill_loader.load_skill(matching[0])
                    sections.append(content[:1500])
                except Exception as e:
                    logger.debug(f"Could not load dynamic skill: {e}")

        # ── MANDATORY: Load prompt-validator for generation tools ──
        if tool_name in self._PROMPT_VALIDATION_TOOLS:
            try:
                validator_content = self.skill_loader.load_skill("core/prompt-validator")
                # Extract the mandatory validation process (most critical sections)
                validator_sections = []
                for header in [
                    "## Mandatory Validation Process",
                    "## Enforced Output Format",
                    "## Common Pitfalls",
                ]:
                    idx = validator_content.find(header)
                    if idx >= 0:
                        next_idx = validator_content.find("\n## ", idx + len(header))
                        if next_idx == -1:
                            validator_sections.append(validator_content[idx:])
                        else:
                            validator_sections.append(validator_content[idx:next_idx])

                if validator_sections:
                    sections.insert(0, (
                        "\n\n## ⚠️ MANDATORY: Prompt Validation Required Before Tool Call\n"
                        "You MUST complete ALL steps of the Prompt Validation process below. "
                        "Do NOT call the tool until the prompt passes all 5 validation steps. "
                        "Output the Prompt Validation Report BEFORE making the tool call.\n"
                        + "\n".join(validator_sections)
                    ))
                else:
                    sections.insert(0, validator_content[:2000])
                logger.debug(f"Injected prompt-validator for tool '{tool_name}'")
            except FileNotFoundError:
                logger.warning(f"prompt-validator skill not found — prompt validation skipped for '{tool_name}'")
            except Exception as e:
                logger.warning(f"Could not load prompt-validator: {e}")

        # ── HIGH PRIORITY: Load user preferences for this tool ──
        try:
            user_prefs = self.skill_loader.get_user_preference_for_tool(tool_name)
            if user_prefs:
                sections.insert(0, user_prefs)
                logger.debug(f"Injected user preferences for tool '{tool_name}'")
        except Exception as e:
            logger.debug(f"Could not load user preferences for tool '{tool_name}': {e}")

        return "\n".join(sections) if sections else ""

    # ── User Skill Creation Interception ─────────────────────────────────
    #
    # Three categories of preference operations:
    #   CREATE: "save preference", "add preference" → save_user_skill() → NEW file with number
    #   SWITCH: "set #2 set as default", "set as default" → set_core_preference() → update preference_config.yaml only
    #   UPDATE: "modify #2", "add more to the preference..." → update_user_skill() → modify existing file
    #
    # Each has its own detection and handler. SWITCH is the simplest —
    # it ONLY updates preference_config.yaml, no file creation needed.

    @staticmethod
    def _is_user_skill_creation_step(step: dict, result: dict = None) -> bool:
        """
        Detect if a plan step is about CREATING a NEW user skill file.

        ONLY matches creation — NOT switching core, NOT updating existing.
        """
        action_desc = step.get('action_description', '').lower()
        tool_purpose = step.get('tool', {}).get('purpose', '').lower()

        # Keywords that indicate CREATION (new file)
        creation_keywords = [
            'create new preference', 'add preference', 'add a new', 'create user', 'new preference',
            'create new preference', 'new preference file',
            'save preference', 'save my preference', 'remember me', 'save as preference',
            'generate preference', 'create user skill', 'generate skills',
            'save my preference', 'save preference',
            'user-level skill file', 'user level skill file',
            'create preference', 'create user preference', 'create skill',
        ]
        combined = f"{action_desc} {tool_purpose}"
        is_create = any(kw in combined for kw in creation_keywords)

        # Exclude SWITCH, UPDATE, and informational operations
        exclude_keywords = [
            'set as default', 'set as default preference', 'switch default', 'switch to default',
            'set as default', 'set default', 'switch default',
            'modify #', 'update #', 'modify preference', 'update preference',
            'update preference', 'modify preference',
            'change pointer to', 'pointer file', 'preference_config', '.core',
            'read', 'show', 'show', 'list', 'view',
            'read', 'show', 'display', 'list',
        ]
        is_excluded = any(kw in combined for kw in exclude_keywords)

        return is_create and not is_excluded

    @staticmethod
    def _is_core_switch_step(step: dict) -> bool:
        """
        Detect if a plan step's PRIMARY action is SWITCHING the core preference.

        This only requires updating preference_config.yaml — no new files.
        Does NOT match suggestions, informational messages, or "you could..." hints.
        """
        action_desc = step.get('action_description', '').lower()
        tool_purpose = step.get('tool', {}).get('purpose', '').lower()
        combined = f"{action_desc} {tool_purpose}"

        # Must contain a switch directive
        switch_keywords = [
            'set as default', 'set as default preference', 'switch default', 'switch to default', 'change to default',
            'set as default', 'set default preference', 'switch default',
            'set #', 'make #', 'change pointer to',
        ]
        has_switch = any(kw in combined for kw in switch_keywords)
        if not has_switch:
            return False

        # Exclude: suggestions, informational messages, "you could" hints
        exclude_patterns = [
            'if needed', 'can tell', 'if', 'you can', 'you can',
            'can tell', 'hint', 'tell user', 'show user',
            'read existing', 'show saved', 'you could', 'if you want',
            'read', 'show', 'show', 'list',
        ]
        is_excluded = any(kw in combined for kw in exclude_patterns)

        return not is_excluded

    def _handle_core_switch(self, step: dict, llm_result: dict) -> dict:
        """
        Handle a core-preference switch by directly calling set_core_preference().

        Extracts the target preference number from the step description or
        the LLM output, and updates ONLY preference_config.yaml.
        No new files are created.
        """
        import re as _re

        # Try to extract target number from step description
        action_desc = step.get('action_description', '')
        num_match = _re.search(r'#\s*(\d+)', action_desc)
        if not num_match:
            # Try from LLM output
            msg = str(llm_result.get('message', '') + ' ' + str(llm_result.get('content', '')))
            num_match = _re.search(r'#\s*(\d+)', msg)

        if num_match:
            number = num_match.group(1)
        else:
            # Fallback: try to find the number in the whole step
            step_str = str(step)
            num_match = _re.search(r'preference_(\d+)|pref-(\d+)', step_str)
            number = (num_match.group(1) or num_match.group(2)) if num_match else None

        if not number:
            logger.warning("Could not extract preference number for core switch")
            return {
                'success': False,
                'message': 'Could not determine the target preference number to switch to',
                'output_path': None,
            }

        result = self.skill_loader.set_core_preference(number)
        logger.info(
            f"Core preference switch handled: #{number}, "
            f"success={result.get('success')}"
        )
        return {
            'success': 'True' if result.get('success') else 'False',
            'message': result.get('message', f'Default preference switched to #{number}'),
            'content': f'Active preference switched to #{number} (preference_config.yaml updated)',
            'output_path': self.skill_loader.user_preferences_config_path,
        }

    def _handle_user_skill_creation(
        self, step: dict, llm_result: dict, raw_response_content: str
    ) -> dict:
        """
        Handle a user-skill-creation step by actually writing the file to disk.

        Extracts the skill content from the LLM response and calls
        skill_loader.save_user_skill() to persist it.

        Returns the real file-write result, or None on failure.
        """
        import re as _re

        # Try to extract markdown content from the LLM response
        skill_content = None
        skill_filename = None

        # Strategy 0: Extract from parsed JSON content field (most reliable)
        if llm_result.get('content'):
            content_text = str(llm_result['content'])
            # Check if it contains markdown (possibly with JSON-escaped newlines)
            if content_text.startswith('#') or '## ' in content_text or '\\n' in content_text:
                # Unescape JSON-escaped newlines
                skill_content = content_text.replace('\\n', '\n').replace('\\t', '\t')
                if skill_content.startswith('#') or '## ' in skill_content:
                    logger.info("Extracted skill content from JSON content field")

        # Strategy 1: Extract markdown code block from raw response body
        if not skill_content:
            # Find the largest markdown code block (not json)
            all_blocks = list(_re.finditer(
                r'```(?:markdown|md)?\s*\n(.*?)\n\s*```',
                raw_response_content, _re.DOTALL
            ))
            if all_blocks:
                # Use the largest block (most likely the actual content)
                largest = max(all_blocks, key=lambda m: len(m.group(1)))
                skill_content = largest.group(1).strip()
                logger.info("Extracted skill content from largest markdown code block")

        # Strategy 2: Search raw text for markdown with headers
        if not skill_content:
            # Find the longest stretch of text that looks like markdown
            md_sections = list(_re.finditer(
                r'(?:^|\n)(#{1,3}\s+[^\n]+\n(?:[^`\n].*\n?)+)',
                raw_response_content, _re.MULTILINE
            ))
            if md_sections:
                largest = max(md_sections, key=lambda m: len(m.group(0)))
                candidate = largest.group(0).strip()
                if len(candidate) > 100:
                    skill_content = candidate
                    logger.info("Extracted skill content from markdown section in raw text")

        # Strategy 3: Use message field
        if not skill_content and llm_result.get('message'):
            msg = str(llm_result['message'])
            if '## ' in msg and len(msg) > 100:
                skill_content = msg
                logger.info("Using message field as skill content")

        if not skill_content:
            logger.warning(
                "Could not extract skill content from LLM response. "
                f"Response keys: {list(llm_result.keys()) if llm_result else 'None'}"
            )
            return None

        # Determine filename from step description or LLM output
        action_desc = step.get('action_description', '')
        filename_match = _re.search(
            r'([a-zA-Z0-9_\-]+\.md)',
            f"{action_desc} {str(llm_result.get('output_path', ''))} {str(llm_result.get('message', ''))}"
        )
        if filename_match:
            skill_filename = filename_match.group(1)
        else:
            # Generate a filename based on content
            title_match = _re.search(r'^#\s+(.+)$', skill_content, _re.MULTILINE)
            if title_match:
                skill_filename = _re.sub(r'[^a-z0-9\-]', '-', title_match.group(1).lower())[:50]
                skill_filename = _re.sub(r'-+', '-', skill_filename).strip('-') + '.md'
            else:
                skill_filename = f"user-preference-{hash(skill_content) % 10000:04d}.md"

        # Actually write the file via SkillLoader
        result = self.skill_loader.save_user_skill(skill_filename, skill_content)
        logger.info(
            f"User skill creation: filename={skill_filename}, "
            f"success={result.get('success')}, path={result.get('output_path')}"
        )
        return result

    def get_layer3_context(self, stage_name: str = "") -> str:
        """
        Layer 3: Load execution-time protocols (reviewer + checkpoint)
        on demand. Called when a pipeline stage completes or when
        human approval is needed.

        This keeps the ActAgent's base system prompt lightweight (Layer 1)
        while loading detailed quality-review and checkpoint instructions
        only when they are actually needed.
        """
        return self.skill_loader.load_layer3_protocols(stage_name)

    def extract_json(self, content: str) -> Optional[Dict]:
        try:
            match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
            if match:
                json_str = match.group(1)
                logger.info("Found JSON in code block format")
            else:
                start = content.find('{')
                end = content.rfind('}')
                if start != -1 and end != -1 and end > start:
                    json_str = content[start:end+1]
                    logger.info("Found JSON without code block")
                else:
                    logger.warning("No JSON structure found in content")
                    return None

            try:
                parsed_content = json.loads(json_str)
            except json.JSONDecodeError:
                # Common LLM issue: unescaped newlines/tabs in string values
                # Try to sanitize: escape control chars inside JSON strings
                sanitized = self._sanitize_json_string(json_str)
                try:
                    parsed_content = json.loads(sanitized)
                    logger.info("JSON parsed after sanitization")
                except json.JSONDecodeError as e2:
                    logger.error(f"JSON decode error even after sanitization: {e2}")
                    logger.error(f"Failed JSON (first 200): {json_str[:200]}...")
                    return None

            logger.info(f"Successfully parsed JSON with keys: {list(parsed_content.keys())}")
            return parsed_content
        except Exception as e:
            logger.error(f"Unexpected error in extract_json: {e}")
            return None

    @staticmethod
    def _sanitize_json_string(json_str: str) -> str:
        """
        Fix common LLM JSON output issues: unescaped newlines, tabs, etc.
        inside JSON string values.

        Strategy: find string values (between unescaped quotes after a key)
        and escape literal newlines/tabs within them.
        """
        import re as _re
        # Replace literal newlines that are inside JSON string values
        # This is a best-effort fix — we look for patterns like "key": "value\nwith\nnewlines"
        # and escape the newlines within the quoted values.

        result = []
        in_string = False
        escape_next = False
        for ch in json_str:
            if escape_next:
                result.append(ch)
                escape_next = False
                continue
            if ch == '\\':
                result.append(ch)
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                result.append(ch)
                continue
            if in_string:
                if ch == '\n':
                    result.append('\\n')
                elif ch == '\t':
                    result.append('\\t')
                elif ch == '\r':
                    result.append('\\r')
                else:
                    result.append(ch)
            else:
                result.append(ch)

        return ''.join(result)

    def update_plan(self, plan, step_result, idx):
        if step_result is None:
            logger.error(f"step_result is None for step {idx+1}")
            plan['execution_plan']['steps'][idx]['status'] = 'failed'
            plan['execution_plan']['steps'][idx]['output'] = 'Step result is None'
            return plan

        if not isinstance(step_result, dict):
            logger.error(f"step_result is not a dict for step {idx+1}: {type(step_result)}")
            plan['execution_plan']['steps'][idx]['status'] = 'failed'
            plan['execution_plan']['steps'][idx]['output'] = f'Invalid result type: {type(step_result)}'
            return plan

        plan['execution_plan']['steps'][idx]['status'] = step_result.get('success', False)
        plan['execution_plan']['steps'][idx]['output'] = step_result.get('output_path') or step_result.get('content', 'No output')

        return plan


class PlanActSystem:
    """
    Plan-Act System — orchestrates the Plan Agent and Act Agent.

    Integrates the skill framework:
    - Plan Agent uses skill-based instructions (not hardcoded plan.txt)
    - Act Agent uses skill-based execution protocol (not hardcoded instructions)
    - Step execution injects tool-specific Core Skills for guidance
    - Pipeline-aware: loads pipeline definitions for structured workflows
    - Supports interactive pipelines with pause/resume via PipelineOrchestrator
    """

    def __init__(self, mcp_command: List[str], db_file: str = "plan_act_system"):
        """
        init PlanActSystem

        Args:
            mcp_command: mcp server command list
            db_file: db file path
        """
        mcp_tools_path = config.get('mcp_tools_path')
        self.mcp_tools = MultiMCPTools(
            commands=mcp_command,
            env={
                "PYTHONPATH": mcp_tools_path,
                "CWD": mcp_tools_path
            },
            timeout_seconds=600,
            refresh_connection=True
        )

        # Initialize skill loader
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.skill_loader = get_skill_loader(project_root)

        self._plan_db = SqliteDb(db_file=f"{db_file}_plan.db")
        self.plan_agent = None
        self.act_agent = None

        # Pipeline orchestration
        self._pipeline_orchestrator: Optional[PipelineOrchestrator] = None
        self._active_budget_tracker: Optional[BudgetTracker] = None
        self._pipeline_state_db = str(
            Path(project_root) / "data" / ".univa" / "pipeline_state.db"
        )

    async def __aenter__(self):
        """asynchronous context manager enter"""
        await self.mcp_tools.connect()

        self.plan_agent = PlanAgent(self.mcp_tools, self._plan_db, self.skill_loader)
        self.act_agent = ActAgent(self.mcp_tools, skill_loader=self.skill_loader)
        self._pipeline_orchestrator = PipelineOrchestrator(
            self.skill_loader,
            state_store=PipelineStateStore(self._pipeline_state_db),
        )

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """asynchronous context manager exit"""
        await self.mcp_tools.close()

    def _format_user_preference_profiles(self) -> str:
        profiles = self.skill_loader.list_user_preference_profiles()
        config_rel = os.path.relpath(
            self.skill_loader.user_preferences_config_path,
            self.skill_loader.project_root,
        )
        if not profiles:
            return (
                "No user preferences have been saved yet.\n"
                f"Config file: {config_rel}\n"
                "After the first preference is saved, the system will write it to active_skill_name automatically."
            )

        lines = ["Current user preferences:"]
        for profile in profiles:
            markers = []
            if profile.get('is_core'):
                markers.append('default/currently active')
            marker = f" [{' / '.join(markers)}]" if markers else ""
            summary = f" - {profile['summary']}" if profile.get('summary') else ""
            lines.append(
                f"- #{profile['number']} {profile['key'].replace('user/', '')}{marker}: "
                f"{profile['name']}{summary}"
            )
        active = self.skill_loader.get_active_user_skill()
        active_name = self.skill_loader._normalize_preference_skill_name(active) if active else "not set"
        lines.append(f"Current active_skill_name: {active_name}")
        lines.append(f"Config file: {config_rel}")
        lines.append("For manual switching, edit active_skill_name in the config file directly.")
        return "\n".join(lines)

    def _format_preference_result(self, result: Dict[str, Any], operation: str) -> str:
        config_rel = os.path.relpath(
            self.skill_loader.user_preferences_config_path,
            self.skill_loader.project_root,
        )
        if not result.get('success') in [True, 'True', 'true']:
            return f"Preference handling failed: {result.get('message', 'unknown error')}"

        if operation == 'create':
            path = result.get('output_path') or ''
            rel_path = os.path.relpath(path, self.skill_loader.project_root) if path else ''
            active = self.skill_loader.get_active_user_skill()
            active_name = self.skill_loader._normalize_preference_skill_name(active) if active else 'not set'
            return (
                f"Saved user preference #{result.get('number')}\n"
                f"File: {rel_path}\n"
                f"Current active_skill_name: {active_name}\n"
                f"Config file: {config_rel}"
            )

        if operation == 'switch':
            active = self.skill_loader.get_active_user_skill()
            active_name = self.skill_loader._normalize_preference_skill_name(active) if active else 'not set'
            return (
                f"Switched active preference to {active_name}\n"
                f"Config file: {config_rel}"
            )

        if operation == 'update':
            path = result.get('output_path') or ''
            rel_path = os.path.relpath(path, self.skill_loader.project_root) if path else ''
            return f"Updated preference #{result.get('number')}\nFile: {rel_path}"

        return result.get('message', 'Preference handling completed')

    def _handle_user_preference_request(self, user_request: str) -> Optional[Dict[str, Any]]:
        intent = detect_user_preference_intent(user_request)
        if not intent:
            return None

        operation = intent.get('operation')
        if operation == 'query':
            content = self._format_user_preference_profiles()
            return {
                'success': 'True',
                'message': content,
                'content': content,
                'output_path': None,
                'preference_operation': operation,
            }

        if operation == 'switch':
            target = intent.get('target')
            if not target:
                content = "Specify the preference number or skill name to switch to, for example preference_02 or #2."
                return {
                    'success': 'False',
                    'message': content,
                    'content': content,
                    'output_path': None,
                    'preference_operation': operation,
                }
            result = self.skill_loader.set_core_preference(target)
            content = self._format_preference_result(result, operation)
            return {
                'success': 'True' if result.get('success') else 'False',
                'message': content,
                'content': content,
                'output_path': result.get('config_path'),
                'preference_operation': operation,
            }

        if operation == 'update':
            target = intent.get('target') or self.skill_loader.get_active_user_skill() or '1'
            result = self.skill_loader.update_user_skill(target, intent.get('text', user_request), mode='merge')
            content = self._format_preference_result(result, operation)
            return {
                'success': 'True' if result.get('success') else 'False',
                'message': content,
                'content': content,
                'output_path': result.get('output_path'),
                'preference_operation': operation,
            }

        if operation == 'create':
            existing = self.skill_loader.list_user_skills()
            number = self.skill_loader._get_next_preference_number()
            skill_name = self.skill_loader._preference_filename(number)[:-3]
            is_core = not existing or bool(intent.get('make_active'))
            content = self.skill_loader.build_user_preference_markdown(
                intent.get('text', user_request),
                number=number,
                is_core=is_core,
                active_skill_name=skill_name,
            )
            result = self.skill_loader.save_user_skill(f"{skill_name}.md", content, is_core=is_core)
            formatted = self._format_preference_result(result, operation)
            return {
                'success': 'True' if result.get('success') else 'False',
                'message': formatted,
                'content': formatted,
                'output_path': result.get('output_path'),
                'preference_operation': operation,
            }

        return None

    async def execute_task(self, session_id, user_request: str) -> Dict[str, Any]:
        """
        Execute a task using Plan-Act pattern with skill-enhanced agents.

        Steps:
        1. Plan Agent generates execution plan (with skill context)
        2. Pipeline detection: if a pipeline is specified, load its definition
        3. Act Agent executes steps (with tool-specific skill guidance)
        4. Results injected back into Plan Agent state
        """
        preference_result = self._handle_user_preference_request(user_request)
        if preference_result:
            return {
                "plan": None,
                "execution": {0: preference_result},
                "direct_answer": True,
            }

        execution_plan = await self.plan_agent.generate_plan(session_id, user_request)

        # ── Guard: if plan is not a valid dict, return it as a direct answer ──
        if not isinstance(execution_plan, dict) or 'execution_plan' not in execution_plan:
            logger.warning(
                f"PlanAgent returned non-plan response. "
                f"Treating as direct answer. Type: {type(execution_plan).__name__}"
            )
            return {
                "plan": execution_plan,
                "execution": {
                    0: {
                        "success": "True",
                        "message": str(execution_plan)[:2000] if execution_plan else "",
                        "content": str(execution_plan) if execution_plan else "",
                        "output_path": None,
                    }
                },
                "direct_answer": True,
            }

        # Detect pipeline mode
        pipeline_name = execution_plan.get('pipeline') if isinstance(execution_plan, dict) else None
        if pipeline_name:
            logger.info(f"Pipeline mode detected: {pipeline_name}")
            pipeline_def = self.skill_loader.load_pipeline(pipeline_name)
            if pipeline_def:
                logger.info(f"Loaded pipeline '{pipeline_name}' v{pipeline_def.get('version', '?')}")

        results = await self.act_agent.execute_plan(user_request, execution_plan)

        self.plan_agent.inject_execution_results(session_id, execution_plan, results)

        return {
            "plan": execution_plan,
            "execution": results
        }

    async def execute_task_stream(
        self,
        session_id,
        user_request: str,
        is_frontend: bool = False,
        project_context: Optional[Dict[str, Any]] = None,
        owner_id: str = "",
    ):
        """
        Stream task execution with SSE events.

        Enhanced with skill context:
        - Plan generation uses skill-based instructions
        - Each step execution injects tool-specific Core Skill guidance
        - Pipeline stages are tracked if a pipeline is specified
        - Interactive pipelines (creative-proposal) use PipelineOrchestrator
          for multi-stage execution with user interaction gates
        - When is_frontend=True, loads frontend-editor skill for media awareness
        """
        try:
            logger.info(f"[Stream] Starting task stream for session {session_id}")

            # ── Frontend Mode: Scan only the current project's data directory ─
            if is_frontend:
                project_name = (project_context or {}).get('project_name') or 'current project'
                project_dir = (project_context or {}).get('data_dir') or ''
                has_frontend_media_list = '## Available Media Files' in user_request

                if has_frontend_media_list:
                    scope = (
                        "[Frontend Editor Mode]\n"
                        f"Current project: {project_name}\n"
                        f"Project data directory: {project_dir or 'not provided'}\n"
                        "The prompt already contains the authoritative frontend media order. "
                        "Use that order and numbering exactly when answering media count, name, or reference questions. "
                        "Do not reorder by filename or filesystem scan order.\n\n"
                    )
                    user_request = f"{scope}---\n{user_request}"
                    logger.info("[Stream] Frontend mode — using frontend-provided media order")
                else:
                    media_list = self._build_frontend_media_list(project_context)
                    if media_list:
                        user_request = f"{media_list}\n\n---\n{user_request}"
                    else:
                        user_request = (
                            "[Frontend Editor Mode]\n"
                            f"Current project: {project_name}\n"
                            f"Project data directory: {project_dir or 'not provided'}\n"
                            "No files found in the current project's server data directory yet. "
                            "When the user uploads files through the editor, they will "
                            "appear here with absolute paths. Respond naturally.\n\n"
                            f"---\n{user_request}"
                        )
                    logger.info("[Stream] Frontend mode — scanned current project media files")

            # ── User Preference Fast Path ────────────────────────────────────
            # Preference management writes user-level skill files and config
            # directly, instead of entering normal video generation pipelines.
            preference_result = self._handle_user_preference_request(user_request)
            if preference_result:
                logger.info(
                    "[Stream] User preference request handled directly: %s",
                    preference_result.get('preference_operation'),
                )
                yield {'type': 'content', 'content': preference_result.get('content', '')}
                yield {'type': 'finish', 'session_id': session_id}
                return

            # ── Chat vs Work Classification ──────────────────────────────────
            # Chat requests (questions, greetings, status checks) skip the
            # Plan-Act flow entirely and receive a direct natural-language
            # answer.  Work requests (generate, edit, understand) proceed
            # through the normal pipeline.
            if is_chat_request(user_request):
                logger.info(f"[Stream] Chat request detected, answering directly")

                # ── Inject preference data for preference-related queries ──
                chat_context = user_request
                pref_keywords = ['preference', 'preference', 'default', 'core', 'number', 'profile']
                if any(kw in user_request.lower() for kw in pref_keywords):
                    try:
                        profiles = self.skill_loader.list_user_preference_profiles()
                        if profiles:
                            core = self.skill_loader.get_core_preference()
                            active = self.skill_loader.get_active_user_skill()
                            pref_data = "\n\n## Current User Preferences Data\n"
                            for p in profiles:
                                markers = []
                                if p['is_core']:
                                    markers.append('default')
                                if p.get('is_active') and p['key'] == active:
                                    markers.append('currently active')
                                marker_str = f" [{'/'.join(markers)}]" if markers else ""
                                pref_data += f"- #{p['number']}{marker_str}: {p['name']}"
                                if p['summary']:
                                    pref_data += f" — {p['summary'][:80]}"
                                pref_data += "\n"
                            pref_data += f"\nThere are  {len(profiles)} preference profiles."
                            pref_data += f"\ndefault preference: #{next((p['number'] for p in profiles if p['is_core']), '?')}"
                            pref_data += "\nAnswer the user based on the real data above. Do not fabricate."
                            chat_context = f"{user_request}\n{pref_data}"
                            logger.info(f"[Stream] Injected preference data for chat response ({len(profiles)} profiles)")
                    except Exception as e:
                        logger.debug(f"[Stream] Could not load preferences for chat: {e}")

                try:
                    response = await self.plan_agent.agent.arun(
                        input=chat_context,
                        stream=False,
                        session_id=session_id
                    )
                    plan_output = response.content or ""
                    extracted = self.plan_agent.extract_plan_from_content(plan_output)
                    if isinstance(extracted, dict) and 'execution_plan' in extracted:
                        answer = extracted.get('task_analysis', plan_output)
                    else:
                        answer = plan_output if isinstance(extracted, str) else str(extracted)
                    yield {'type': 'content', 'content': str(answer)}
                except Exception as e:
                    logger.error(f"[Stream] Chat LLM call failed: {e}")
                    yield {'type': 'content', 'content': f'Sorry, something went wrong while processing your request. Please try again later.'}
                finally:
                    yield {'type': 'finish', 'session_id': session_id}
                return

            # ── Work Request: Normal Plan-Act Flow ────────────────────────────

            # ── Clarification check (per clarification-protocol skill) ──
            completeness = PlanAgent.assess_request_completeness(user_request)
            logger.info(
                f"[Stream] Request completeness: score={completeness['completeness_score']}, "
                f"missing={completeness['missing_fields']}, "
                f"needs_clarification={completeness['needs_clarification']}"
            )

            if completeness['needs_clarification']:
                # Inject clarification protocol into the plan generation context
                try:
                    clarification_skill = self.skill_loader.load_skill("meta/clarification-protocol")
                    # Add instruction: if info is insufficient, ask user instead of guessing
                    clarification_context = (
                        "\n\n## ⚠️ Clarification Check\n"
                        f"Request completeness score: {completeness['completeness_score']:.0%}.\n"
                        f"Missing information: {', '.join(completeness['missing_fields'])}.\n"
                        "Per the Clarification Protocol: if critical information is missing, "
                        "do NOT guess. Instead, include a 'clarification_needed' section in "
                        "your task_analysis asking the user for the missing details. "
                        "Ask at most 3 questions with specific options.\n"
                    )
                    user_request = user_request + clarification_context
                    logger.info("[Stream] Injected clarification check into plan context")
                except Exception as e:
                    logger.debug(f"Could not load clarification-protocol: {e}")

            yield {'type': 'content', 'content': 'Generating execution plan...'}

            execution_plan = await self.plan_agent.generate_plan(session_id, user_request)
            if not isinstance(execution_plan, dict) or 'execution_plan' not in execution_plan:
                logger.error(f"[Stream] Plan generation failed for session {session_id}")
                yield {'type': 'content', 'content': f'Could not generate a valid plan.\n{execution_plan}'}
                yield {'type': 'finish', 'session_id': session_id}
                return

            logger.info(f"[Stream] Plan generated successfully with {len(execution_plan.get('execution_plan', {}).get('steps', []))} steps")

            # Yield formatted plan overview
            plan_summary = output_fmt.format_execution_plan(execution_plan)
            yield {'type': 'content', 'content': plan_summary}

            # Detect pipeline mode — use auto-routing for intent-based selection
            pipeline_name = execution_plan.get('pipeline') if isinstance(execution_plan, dict) else None

            has_explicit_video_target = any(
                marker in user_request.lower() for marker in [
                    "video", "short film", "video", "clip", ".mp4", ".mov", ".avi", ".mkv",
                ]
            )
            if pipeline_name == "video-edit" and not has_explicit_video_target and any(
                marker in user_request.lower() for marker in [
                    "image", "image", "photo", ".jpg", ".jpeg", ".png", ".webp",
                    "image", "picture", "photo", "audio", "audio", ".mp3", ".wav",
                ]
            ):
                pipeline_name = "media-atomic"
            localization_markers = [
                "localization", "localize", "transcribe", "asr",
                "subtitle translation", "bilingual subtitle", "dub", "dubbing",
                "本地化", "字幕翻译", "双语字幕", "转写", "配音",
            ]
            if any(marker in user_request.lower() for marker in localization_markers):
                pipeline_name = "localization"
            # Auto-route: if no pipeline explicitly set, classify intent
            decomposition_injected = False
            if not pipeline_name:
                intent = classify_intent(user_request)
                logger.info(f"[Stream] Auto-routing intent: {intent}")

                # ── Enhanced compound handling: LLM-based decomposition ──
                if intent == 'compound':
                    pipeline_name = 'master'
                    # Use LLM to semantically decompose the compound request
                    try:
                        llm_classification = await classify_intent_llm(
                            user_request, plan_agent=self.plan_agent
                        )
                        logger.info(
                            f"[Stream] LLM decomposition: is_compound={llm_classification.get('is_compound')}, "
                            f"sub_intents={llm_classification.get('sub_intents')}, "
                            f"mode={llm_classification.get('decomposition_mode')}, "
                            f"confidence={llm_classification.get('confidence', 0):.2f}"
                        )
                        # Inject decomposition into the plan context
                        if llm_classification.get('is_compound') and llm_classification.get('sub_intents'):
                            # Load intent-decomposer skill for structured decomposition guidance
                            try:
                                decomposer_skill = self.skill_loader.load_skill("meta/intent-decomposer")
                                # Inject decomposition guidance into a second plan pass.
                                sub_intents_str = " -> ".join(llm_classification['sub_intents'])
                                user_request = (
                                    f"{user_request}\n\n"
                                    "### Compound Task Routing Context\n"
                                    f"Decomposition mode: {llm_classification.get('decomposition_mode', 'sequential')}.\n"
                                    f"Sub-intents in order: {sub_intents_str}.\n"
                                    "Create executable sub-tasks where each sub-task's artifact output feeds the next.\n\n"
                                    f"### Intent Decomposer Skill\n{decomposer_skill[:2000]}"
                                )
                                decomposition_injected = True
                            except Exception:
                                pass
                    except Exception as e:
                        logger.warning(f"[Stream] LLM decomposition failed, falling back to keyword-based: {e}")

                elif intent == 'generate':
                    atomic_media_markers = [
                        'image', 'image', 'photo', 'image', 'picture', 'photo',
                        'audio', 'music', 'sfx', 'speech', 'dubbing', 'voiceover',
                        'audio', 'music', 'sound', 'speech', 'voiceover', 'tts',
                    ]
                    if not has_explicit_video_target and any(marker in user_request.lower() for marker in atomic_media_markers):
                        pipeline_name = 'media-atomic'
                elif intent == 'edit':
                    pipeline_name = (
                        'media-atomic' if not has_explicit_video_target and any(
                            marker in user_request.lower() for marker in [
                                'image', 'image', 'photo', '.jpg', '.jpeg', '.png', '.webp',
                                'image', 'picture', 'photo', 'audio', 'audio', '.mp3', '.wav',
                            ]
                        ) else 'video-edit'
                    )
                elif intent == 'understand':
                    pipeline_name = 'video-understand'
                # Non-media generate and read-only direct requests may stay on the standard Plan-Act flow.

                if pipeline_name:
                    logger.info(f"[Stream] Auto-routed to pipeline: {pipeline_name}")

            if decomposition_injected:
                yield {'type': 'content', 'content': 'Compound task detected; regenerating the execution plan by subtask dependencies...'}
                execution_plan = await self.plan_agent.generate_plan(session_id, user_request)
                if not isinstance(execution_plan, dict) or 'execution_plan' not in execution_plan:
                    logger.error(f"[Stream] Compound replanning failed for session {session_id}")
                    yield {'type': 'content', 'content': f'Compound task replanning failed.\n{execution_plan}'}
                    yield {'type': 'finish', 'session_id': session_id}
                    return
                pipeline_name = execution_plan.get('pipeline') or pipeline_name
                yield {'type': 'content', 'content': output_fmt.format_execution_plan(execution_plan)}

            interactive_pipeline_def = (
                self.skill_loader.load_pipeline(pipeline_name) if pipeline_name else None
            )
            has_human_gate = bool(
                interactive_pipeline_def
                and any(stage.get('human_approval_default') for stage in interactive_pipeline_def.get('stages', []))
            )
            # ── Interactive Pipeline Mode (any manifest with a human approval gate) ─────────────────
            if pipeline_name and has_human_gate and self._pipeline_orchestrator:
                async for event in self._execute_interactive_pipeline(
                    session_id,
                    user_request,
                    pipeline_name,
                    owner_id=owner_id,
                    project_id=(
                        (project_context or {}).get("project_id")
                        or (project_context or {}).get("safe_project_name")
                        or ""
                    ),
                ):
                    yield event
                return

            # ── Standard Pipeline / Direct Mode ───────────────────────────────
            if pipeline_name:
                pipeline_def = self.skill_loader.load_pipeline(pipeline_name)
                if pipeline_def:
                    logger.info(f"[Stream] Pipeline mode: {pipeline_name}")
                    yield output_fmt.format_stream_event('pipeline', {
                        'pipeline': pipeline_name,
                        'version': pipeline_def.get('version', '?'),
                        'stages': [s.get('name') for s in pipeline_def.get('stages', [])]
                    })

            todo_events = generate_todo_progress_event(execution_plan)
            logger.info(f"[Stream] Yielding todo_progress event")
            yield todo_events

            # execute plan step by step
            execution_results: Dict[int, Any] = {}
            steps = execution_plan.get('execution_plan', {}).get('steps', [])

            for idx, step in enumerate(steps):
                step_num = idx + 1
                logger.info(f"[Stream] Starting execution of step {step_num}/{len(steps)}: {step}")
                try:
                    action_desc = step.get('action_description', f'step {step_num}')
                    tool_name = step.get('tool', {}).get('name', 'unknown')

                    logger.info(f"[Stream] Yielding tool_start event for step {step_num}: {tool_name}")
                    yield output_fmt.format_stream_event('tool_start', tool_name)

                    logger.info(f"[Stream] Executing step {step_num}: {action_desc}")
                    result = await self.act_agent._execute_step(
                        step, user_request, execution_plan, execution_results
                    )

                    execution_results[step_num] = result
                    execution_plan = self.act_agent.update_plan(execution_plan, result, idx)

                    logger.info(f"[Stream] Yielding tool_end event for step {step_num}")
                    yield output_fmt.format_stream_event('tool_end', result)

                    # check step result, if failed then return value
                    if result and isinstance(result, dict):
                        success = result.get('success')
                        is_success = success in [True, 'True', 'true']

                        if not is_success:
                            error_msg = result.get('message', 'Step execution failed')
                            logger.error(f"[Stream] Step {step_num} failed: {error_msg}")
                            yield output_fmt.format_stream_event('error',
                                f"Step {step_num} failed: {error_msg}")
                            return

                    logger.info(f"[Stream] Step {step_num} completed successfully")

                except Exception as e:
                    error_msg = f"step {idx+1} execution failed: {str(e)}"
                    logger.error(f"[Stream] {error_msg}")
                    logger.error(traceback.format_exc())
                    yield output_fmt.format_stream_event('error',
                        f"Step {idx+1} errored: {error_msg}")
                    yield {'type': 'finish', 'session_id': session_id}
                    return

            # inject results back to plan agent
            logger.info(f"[Stream] Injecting execution results back to plan agent")
            self.plan_agent.inject_execution_results(session_id, execution_plan, execution_results)

            logger.info(f"[Stream] Yielding finish event for session {session_id}")
            yield output_fmt.format_stream_event('finish', session_id)

            logger.info(f"[Stream] Task stream completed successfully for session {session_id}")

        except Exception as e:
            logger.error(f"[Stream] Error in execute_task_stream: {e}")
            logger.error(traceback.format_exc())
            yield output_fmt.format_stream_event('error', str(e))
            yield {'type': 'finish', 'session_id': session_id}

    # ── Skill & Pipeline Access Methods ──────────────────────────────────

    def _build_frontend_media_list(self, project_context: Optional[Dict[str, Any]] = None) -> str:
        """
        Scan only the current frontend project's data directory and build a
        media list that the PlanAgent can use to resolve numbered references.
        """
        import os as _os

        if not project_context or not project_context.get('data_dir'):
            return ""

        data_dir = project_context['data_dir']
        if not _os.path.exists(data_dir):
            return ""

        files = []
        for f in sorted(_os.listdir(data_dir)):
            fpath = _os.path.join(data_dir, f)
            if not _os.path.isfile(fpath):
                continue
            ext = _os.path.splitext(f)[1].lower()
            if ext in ('.mp4', '.avi', '.mov', '.mkv', '.webm'):
                ftype, icon = 'video', '🎬'
            elif ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'):
                ftype, icon = 'image', '🖼️'
            elif ext in ('.wav', '.mp3', '.aac', '.ogg', '.flac'):
                ftype, icon = 'audio', '🎵'
            else:
                continue
            size_mb = _os.path.getsize(fpath) / (1024 * 1024)
            files.append((f, ftype, icon, fpath, size_mb))

        project_name = project_context.get('project_name') or 'current project'
        safe_name = project_context.get('safe_project_name') or _os.path.basename(data_dir)
        lines = [
            "## Frontend Project Context",
            f"Current project: {project_name}",
            f"Project data directory: {_os.path.abspath(data_dir)}",
            "Only use media files from this directory for this request. Do not scan or reference files from sibling project directories.",
            "Generated outputs for this frontend project should be saved in this project data directory when a save/output path is needed.",
            "",
        ]

        if not files:
            lines.append("No media files are available in this project yet.")
            lines.append("")
            return '\n'.join(lines)

        lines.append(f"## Available Media Files for {safe_name}")
        for i, (name, ftype, icon, fpath, size_mb) in enumerate(files):
            lines.append(
                f"[{i + 1}] {icon} {name} ({ftype}, {size_mb:.1f}MB) → {_os.path.abspath(fpath)}"
            )
        lines.append("")
        lines.append(
            "These files are on the server and can be used directly. "
            "Reference them by number like [1], [2] when calling MCP tools. "
            "Use only the absolute paths listed above as file path parameters."
        )
        lines.append("")
        return '\n'.join(lines)

    async def _execute_interactive_pipeline(
        self,
        session_id: str,
        user_request: str,
        pipeline_name: str,
        owner_id: str = "",
        project_id: str = "",
    ):
        """
        Execute an interactive pipeline with pause/resume
        at user interaction gates.

        Follows the help-to-make-user and pause-forhelp protocols:
        - Clear user instructions with formatted prompts
        - Proper blocking until user input received
        - Support for user-initiated pause at any stage
        - Structured interaction data for frontend rendering

        Yields SSE events for each stage, pausing at selection/confirm gates.
        """
        # Initialize fresh BudgetTracker for this pipeline run
        budget = BudgetTracker(budget_limit_usd=1.50)
        self._active_budget_tracker = budget

        # Attach budget tracker to agents
        self.plan_agent.budget_tracker = budget
        self.act_agent.budget_tracker = budget

        pipeline_def = self.skill_loader.load_pipeline(pipeline_name)
        yield output_fmt.format_stream_event('pipeline_start', {
            'pipeline': pipeline_name,
            'version': pipeline_def.get('version', '?'),
            'stages': [s.get('name') for s in pipeline_def.get('stages', [])],
        })

        stages = pipeline_def.get('stages', [])
        pipeline_state = PipelineState(
            pipeline_name=pipeline_name,
            session_id=session_id,
            owner_id=owner_id or "",
            project_id=project_id or "",
            original_user_request=user_request,
            budget=budget,
        )

        for idx, stage_def in enumerate(stages):
            stage_name = stage_def['name']
            pipeline_state.current_stage_index = idx

            # ── Pre-generation gate: offer pause before expensive stages ──
            if stage_name in ('generate', 'assets', 'execute') and idx > 0:
                prev_artifacts_summary = {
                    k: str(v)[:200] for k, v in pipeline_state.artifacts.items()
                }
                pipeline_state.status = "awaiting_human"
                pipeline_state.interaction_stage = "pre_generation"
                pipeline_state.interaction_data = {
                    "type": "user_approval",
                    "stage": "pre_generation",
                    "estimated_cost": f"${budget.budget_limit_usd * 0.4:.2f} - ${budget.budget_limit_usd * 0.7:.2f}",
                    "artifacts_so_far": prev_artifacts_summary,
                }
                pipeline_state.interaction_prompt = (
                    "Ready to start asset generation. Enter /go to continue, "
                    "or provide revision notes."
                )
                # Persist before yielding. A disconnected client must not lose
                # the approval checkpoint.
                if self._pipeline_orchestrator:
                    self._pipeline_orchestrator._active_states[session_id] = pipeline_state
                    self._pipeline_orchestrator._persist_state(pipeline_state)
                self.plan_agent.budget_tracker = None
                self.act_agent.budget_tracker = None
                self._active_budget_tracker = None
                yield {
                    'type': 'pre_generation_gate',
                    'stage': stage_name,
                    'continuation_token': pipeline_state.continuation_token,
                    'interaction_type': 'user_approval',
                    'data': {
                        'title': f'Preparing to enter {stage_name} stage (asset generation)',
                        'summary': 'The system is about to call APIs to generate media assets; this step may incur cost.',
                        'artifacts_so_far': prev_artifacts_summary,
                        'estimated_cost': f'${budget.budget_limit_usd * 0.4:.2f} - ${budget.budget_limit_usd * 0.7:.2f}',
                    },
                    'prompt': (
                        '⏸️  Ready to start asset generation. Enter /go to continue, or enter revision notes.\n'
                        '💡 Tip: enter /pause to pause, or enter revision notes to adjust the plan.'
                    ),
                    'available_commands': ['/go', '/pause', '/modify N <revision>', '/status'],
                }
                return

            # Check for interactive gate (following help-to-make-user protocol)
            if stage_def.get('human_approval_default') and stage_name in ('selection', 'confirm'):
                logger.info(f"[Pipeline] Suspending at interactive gate: {stage_name}")
                pipeline_state.status = "awaiting_human"
                pipeline_state.interaction_stage = stage_name
                pipeline_state.interaction_data = self._pipeline_orchestrator._build_interaction_data(
                    stage_name, pipeline_state
                )
                pipeline_state.interaction_prompt = self._pipeline_orchestrator._build_interaction_prompt(
                    stage_name, pipeline_state
                )
                # Persist before yielding: generator cleanup after a client
                # disconnect must not discard the checkpoint.
                self._pipeline_orchestrator._active_states[session_id] = pipeline_state
                self._pipeline_orchestrator._persist_state(pipeline_state)
                self.plan_agent.budget_tracker = None
                self.act_agent.budget_tracker = None
                self._active_budget_tracker = None

                # Build structured interaction data per help-to-make-user protocol
                if stage_name == 'selection':
                    proposals = pipeline_state.artifacts.get('proposal', {})
                    # Extract structured proposals from artifact
                    options = self._extract_proposal_options(proposals)
                    yield {
                        'type': 'pipeline_suspended',
                        'stage': stage_name,
                        'continuation_token': pipeline_state.continuation_token,
                        'interaction_type': 'user_choice',
                        'data': {
                            'title': '🎬 Choose a creative proposal',
                            'options': options if options else [
                                {'id': '1', 'label': 'Proposal 1', 'description': str(proposals)[:500]},
                            ],
                            'default': '1',
                            'input_hint': 'Enter a number to choose a proposal, or describe your requested changes',
                        },
                        'prompt': (
                            '╔══════════════════════════════════════════╗\n'
                            '║  ⏸️  Waiting for your choice                 ║\n'
                            '╠══════════════════════════════════════════╣\n'
                            '║  Choose one proposal above                   ║\n'
                            '║  Enter 1-3, or describe requested changes    ║\n'
                            '║  ⚠️ Execution will not continue before input ║\n'
                            '╚══════════════════════════════════════════╝'
                        ),
                        'available_commands': ['/status', '/abort'],
                    }
                elif stage_name == 'confirm':
                    storyboard = pipeline_state.artifacts.get('storyboard') or pipeline_state.artifacts.get('proposal', {})
                    yield {
                        'type': 'pipeline_suspended',
                        'stage': stage_name,
                        'continuation_token': pipeline_state.continuation_token,
                        'interaction_type': 'user_approval',
                        'data': {
                            'title': 'Confirm the creative or editing plan',
                            'content': str(storyboard)[:3000],
                            'default_action': 'confirm',
                        },
                        'prompt': (
                            '╔══════════════════════════════════════════╗\n'
                            '║  ⏸️  Waiting for your confirmation           ║\n'
                            '╠══════════════════════════════════════════╣\n'
                            '║  Review the creative or editing plan above   ║\n'
                            '║  Enter "confirm" to continue, or revise      ║\n'
                            '║  ⚠️ Generation will not start before approval ║\n'
                            '╚══════════════════════════════════════════╝'
                        ),
                        'available_commands': ['/status', '/abort', '/modify N <revision>'],
                    }

                return

            # Execute non-interactive stage
            yield output_fmt.format_stream_event('pipeline_stage_start', {
                'stage': stage_name,
                'index': idx + 1,
                'total': len(stages),
            })

            pipeline_state.start_stage(stage_name)
            try:
                if not self._pipeline_orchestrator:
                    raise RuntimeError("Pipeline orchestrator is not initialized")

                stage_result = await self._pipeline_orchestrator._execute_stage(
                    stage_def, pipeline_state, user_request, self
                )

                # Store artifact
                pipeline_state.artifacts[stage_name] = stage_result
                pipeline_state.end_stage(stage_name, "completed")
                post_stage_approval = bool(stage_def.get('human_approval_default'))
                if post_stage_approval:
                    self._pipeline_orchestrator._pause_for_stage_approval(
                        pipeline_state, stage_name
                    )
                self._pipeline_orchestrator._persist_state(pipeline_state)

                yield output_fmt.format_stream_event('pipeline_stage_complete', {
                    'stage': stage_name,
                    'status': 'completed',
                    'quality': pipeline_state.quality_reports.get(stage_name),
                })

                # Budget update
                if budget.tool_calls or budget.llm_calls:
                    yield {
                        'type': 'budget_update',
                        'budget': budget.summary(),
                    }

                if post_stage_approval:
                    self.plan_agent.budget_tracker = None
                    self.act_agent.budget_tracker = None
                    self._active_budget_tracker = None
                    yield {
                        'type': 'pipeline_suspended',
                        'stage': stage_name,
                        'continuation_token': pipeline_state.continuation_token,
                        'interaction_type': 'user_approval',
                        'data': pipeline_state.interaction_data,
                        'prompt': pipeline_state.interaction_prompt,
                        'available_commands': ['/status', '/abort', '/modify N <revision>'],
                    }
                    return

            except Exception as e:
                logger.error(f"[Pipeline] Stage '{stage_name}' failed: {e}")
                pipeline_state.end_stage(stage_name, "failed")
                pipeline_state.status = "failed"
                self._pipeline_orchestrator._persist_state(pipeline_state)
                self.plan_agent.budget_tracker = None
                self.act_agent.budget_tracker = None
                self._active_budget_tracker = None
                yield output_fmt.format_stream_event('error', f"Stage '{stage_name}' failed: {str(e)}")
                return

        # All stages completed
        pipeline_state.status = "completed"
        if self._pipeline_orchestrator:
            self._pipeline_orchestrator._persist_state(pipeline_state)

        # Build delivery report from budget tracker
        delivery_report = {
            'pipeline_name': pipeline_name,
            'output_path': (pipeline_state.artifacts.get('generate') or pipeline_state.artifacts.get('execute') or {}).get('output_path', ''),
            'budget_summary': budget.summary(),
            'stage_timeline': pipeline_state.stage_timeline,
        }

        yield {
            'type': 'pipeline_complete',
            'delivery_report': delivery_report,
        }

        # Clean up
        self.plan_agent.budget_tracker = None
        self.act_agent.budget_tracker = None
        self._active_budget_tracker = None
        self._pipeline_orchestrator.remove_state(session_id)

    def _build_pipeline_stage_request(
        self, stage_name: str, stage_def: Dict, state: PipelineState,
        original_request: str, skill_content: str,
    ) -> str:
        """Build a focused user request for a specific pipeline stage."""
        parts = [f"Execute the '{stage_name}' stage of the '{state.pipeline_name}' pipeline."]

        parts.append(f"\n### Original User Request\n{original_request}")

        if skill_content:
            parts.append(f"\n### Stage Instructions (from {stage_def.get('skill', '')})\n{skill_content[:2500]}")

        # Include previous stage results
        for art_name, artifact in state.artifacts.items():
            artifact_str = str(artifact)
            if len(artifact_str) > 1500:
                artifact_str = artifact_str[:1500] + "...(truncated)"
            parts.append(f"\n### Previous Stage '{art_name}' Result\n{artifact_str}")

        return '\n'.join(parts)

    def list_available_pipelines(self) -> List[str]:
        """List all available pipeline names."""
        return self.skill_loader.list_pipelines()

    def get_pipeline_info(self, pipeline_name: str) -> Optional[Dict]:
        """Get information about a pipeline."""
        return self.skill_loader.load_pipeline(pipeline_name)

    def list_skills(self, category: Optional[str] = None) -> List[str]:
        """List available skills, optionally by category."""
        return self.skill_loader.list_skills(category)

    def get_skill(self, skill_path: str) -> Optional[str]:
        """Get a skill's content by path."""
        try:
            return self.skill_loader.load_skill(skill_path)
        except FileNotFoundError:
            return None

    @staticmethod
    def _extract_proposal_options(proposals_artifact: Any) -> list:
        """
        Extract structured proposal options from pipeline artifacts.

        Follows help-to-make-user protocol for user_choice interaction type.
        Returns a list of {id, label, description} dicts for rendering.
        """
        options = []
        proposals_str = str(proposals_artifact)

        # Try to find numbered proposals in the text
        import re as _re
        # Match patterns like "Proposal 1:", "Proposal 1:", "### 1.", etc.
        proposal_patterns = [
            r'Proposal\s*(\d+)[::]\s*(.+?)(?=Proposal\s*\d|$)',
            r'[Pp]roposal\s*(\d+)[::]\s*(.+?)(?=[Pp]roposal\s*\d|$)',
            r'###\s*(\d+)[\.\s]\s*(.+?)(?=###\s*\d|$)',
        ]

        for pattern in proposal_patterns:
            matches = _re.findall(pattern, proposals_str, _re.DOTALL)
            if matches:
                for num, desc in matches:
                    desc_clean = desc.strip()[:200]
                    options.append({
                        'id': num,
                        'label': f'Proposal {num}',
                        'description': desc_clean,
                    })
                break

        # If no structured proposals found, create a single option from the artifact
        if not options:
            # Try to split into paragraphs as rough options
            paragraphs = [p.strip() for p in proposals_str.split('\n\n') if len(p.strip()) > 50]
            if len(paragraphs) >= 2:
                for i, para in enumerate(paragraphs[:3]):
                    options.append({
                        'id': str(i + 1),
                        'label': f'Proposal {i + 1}',
                        'description': para[:300],
                    })
            else:
                options.append({
                    'id': '1',
                    'label': 'Generated proposal',
                    'description': proposals_str[:500],
                })

        return options


def _validate_mcp_module(server_name: str, args: List[str]) -> bool:
    """
    Pre-flight check: verify the Python module referenced by an MCP server is importable.

    This prevents a single missing MCP module (e.g., audio_gen.py) from causing
    the entire MultiMCPTools connection to fail with functions=[].

    Returns True if the module is importable, False otherwise.
    """
    if not args or len(args) < 2:
        return True  # Non-Python MCP servers (e.g., npx) — skip validation

    # args[0] is "-m", args[1] is the module name (e.g., "univa.mcp_tools.audio_gen")
    if args[0] != "-m":
        return True

    module_name = args[1]
    try:
        import importlib
        importlib.import_module(module_name)
        return True
    except ImportError as e:
        logger.warning(
            f"MCP server '{server_name}' is configured but module '{module_name}' "
            f"cannot be imported: {e}. This server will be SKIPPED. "
            f"Check that the file exists at univa/mcp_tools/{module_name.split('.')[-1]}.py"
        )
        return False
    except Exception as e:
        logger.warning(
            f"MCP server '{server_name}': unexpected error importing '{module_name}': {e}. "
            f"This server will be SKIPPED."
        )
        return False


async def initialize_global_agents() -> PlanActSystem:
    # load MCP server configurations
    config_path = config.get('mcp_servers_config')

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            mcp_config = json.load(f)

        mcp_servers = mcp_config.get("mcpServers", {})
        logger.info(f"Loaded {len(mcp_servers)} MCP servers from config")

        # construct mcp commands with pre-flight module validation
        mcp_commands = []
        skipped_servers = []
        for server_name, server_config in mcp_servers.items():
            command = server_config.get("command", "")
            args = server_config.get("args", [])

            # Validate Python MCP modules before registering
            if not _validate_mcp_module(server_name, args):
                skipped_servers.append(server_name)
                continue

            # full command with args
            full_command = f"{command} {' '.join(args)}"

            mcp_commands.append(full_command)
            logger.info(f"Registered MCP server '{server_name}': {full_command}")

        if skipped_servers:
            logger.warning(
                f"Skipped {len(skipped_servers)} MCP server(s) due to missing modules: "
                f"{', '.join(skipped_servers)}. "
                f"The system will run in degraded mode — affected tools will be unavailable."
            )

        if not mcp_commands:
            logger.error("No MCP servers could be loaded! Using fallback filesystem server.")
            mcp_commands = ["npx -y @modelcontextprotocol/server-filesystem /tmp"]

    except FileNotFoundError:
        logger.warning(f"MCP config file not found: {config_path}, using default")
        mcp_commands = ["npx -y @modelcontextprotocol/server-filesystem /tmp"]
    except Exception as e:
        logger.error(f"Error loading MCP config: {e}, using default")
        mcp_commands = ["npx -y @modelcontextprotocol/server-filesystem /tmp"]

    global_plan_act_system = PlanActSystem(mcp_command=mcp_commands)
    await global_plan_act_system.__aenter__()

    logger.info("Global PlanActSystem initialized with skill framework")

    return global_plan_act_system


async def main():
    system = await initialize_global_agents()

    session_id = "test_interactive_session_001"

    try:
        print(output_fmt.format_capabilities_intro())

        while True:
            try:
                input_prompt = await _read_user_input("\n🧑 Enter a task (exit/quit to quit): ")
                if input_prompt.lower() in ['exit', 'quit']:
                    print("\n👋 Goodbye!")
                    break

                if not input_prompt.strip():
                    continue

                print(f"\n⏳ Processing: {input_prompt}\n")

                result = await system.execute_task(session_id, input_prompt)

                # Use OutputFormatter for human-readable output
                plan_data = result.get('plan', {})
                execution = result.get('execution', {})

                # ── Handle direct answer (non-plan response from PlanAgent) ──
                if result.get('direct_answer') or not isinstance(plan_data, dict):
                    # Direct answer: just display the content naturally
                    content = ""
                    if isinstance(plan_data, str):
                        content = plan_data
                    elif isinstance(execution, dict):
                        first = list(execution.values())[0] if execution else {}
                        content = first.get('content', '') if isinstance(first, dict) else str(first)
                    print(f"\n{content}\n{output_fmt._separator()}")
                elif execution and isinstance(execution, dict):
                    first_result = list(execution.values())[0] if execution else {}
                    if isinstance(first_result, dict):
                        tool_used = plan_data.get('execution_plan', {}).get('steps', [{}])[0].get('tool', {}).get('name', '')
                        if tool_used in ('no specific tool', '', None):
                            print(output_fmt.format_direct_answer(plan_data, execution))
                        else:
                            print(output_fmt.format_task_complete(plan_data, execution))
                    else:
                        print(output_fmt.format_task_complete(plan_data, execution))
                else:
                    print(output_fmt.format_task_complete(plan_data, execution))

            except KeyboardInterrupt:
                print("\n\n👋 Interrupted. Goodbye!")
                break
            except Exception as e:
                logger.error(f"error: {e}")
                print(output_fmt.format_error(0, {}, str(e)))

    finally:
        await system.__aexit__(None, None, None)


if __name__ == "__main__":
    asyncio.run(main())
