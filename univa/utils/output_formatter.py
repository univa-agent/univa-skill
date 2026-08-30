"""
Output Formatter — Implements the output-formatter skill.

Provides consistent, human-readable formatting for all user-facing output.
Replaces raw JSON dict dumps with structured natural-language presentation.

All formatting logic is driven by skills/meta/output-formatter.md.
"""

from typing import Dict, List, Any, Optional
import os


class OutputFormatter:
    """
    Formats agent output for human consumption.

    Usage:
        fmt = OutputFormatter()
        print(fmt.format_capabilities_intro())
        print(fmt.format_execution_plan(plan_data))
        print(fmt.format_step_result(1, step, result))
        print(fmt.format_task_complete(plan, results))
        print(fmt.format_error(3, step, "API timeout"))
    """

    # ── Tool name → Human-readable label mapping ──────────────────────

    TOOL_LABELS = {
        'text2video_gen': 'Text-to-video',
        'image2video_gen': 'Image-to-video',
        'frame2frame_video_gen': 'Frame-to-frame video',
        'video_extension': 'Video Extension',
        'storyvideo_gen': 'Story video generation',
        'entity2video': 'Entity video generation',
        'text2image_generate': 'Text-to-image',
        'image2image_generate': 'Image-to-image',
        'sequential_image_gen': 'Sequential image generation',
        'depth_modify': 'Depth edit (background replacement)',
        'style_transfer': 'Style transfer',
        'repainting': 'Repainting',
        'pose_reference': 'Pose reference generation',
        'vision2text_gen': 'Video content analysis',
        'video_referring_segmentation': 'Object tracking segmentation',
        'audio_gen': 'Audio generation',
        'speech_gen': 'Speech synthesis',
        'merge2videos': 'Video merge',
    }

    @staticmethod
    def _tool_label(tool_name: str) -> str:
        """Get human-readable label for a tool name."""
        return OutputFormatter.TOOL_LABELS.get(tool_name, tool_name)

    @staticmethod
    def _status_emoji(status) -> str:
        """Get emoji for a step status."""
        if status in [True, 'True', 'true', 'success']:
            return '✅'
        elif status in [False, 'False', 'false', 'failed', 'failure']:
            return '❌'
        elif status in ['ongoing', 'in_progress']:
            return '⏳'
        elif status == 'pending':
            return '⬜'
        return '❓'

    @staticmethod
    def _resolve_path(path: Optional[str]) -> str:
        """Resolve a path for display. Handles relative paths correctly.

        If the path is relative (e.g., 'skills/user/foo.md'), resolves it
        against the UniVA project root, not the CWD (which may be in a
        subdirectory like univa/univa/).
        """
        if not path:
            return ''
        if os.path.isabs(path):
            return path
        # Resolve relative to project root (2 levels up from this file)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)
        )))
        abs_path = os.path.join(project_root, path)
        return os.path.abspath(abs_path)

    @staticmethod
    def _separator(char: str = '─', width: int = 56) -> str:
        return char * width

    # ── Format: Capabilities Intro ─────────────────────────────────────

    def format_capabilities_intro(self) -> str:
        """Format the system capabilities introduction."""
        return """
╔══════════════════════════════════════════════════════╗
║              UniVA Video Assistant                      ║
╚══════════════════════════════════════════════════════╝

I focus on intelligent video generation, editing, and understanding.

  🎬  Video Generation
      • Text-to-video — Enter a text description and generate video using configured or requested duration
      • Image-to-video — Generate dynamic video from a reference image plus prompt
      • Story Video — Storyboard -> characters -> keyframes -> final video workflow
      • Video Extension — Extend existing video content

  ✂️  Video Editing
      • Background Replacement — Separate foreground/background using depth information
      • Style transfer — Convert video to a specified art style
      • Repainting — Replace specific objects in video

  🔍  Video Understanding
      • Content Analysis — Perform deep visual understanding on video/image
      • Object Tracking — Locate and segment target objects in video

  🎵  Supporting Capabilities
      • Image generation, audio generation, and video merge/concat

{sep}

Describe what you want to do, for example:
  → "Generate a video of a panda eating bamboo in a bamboo forest"
  → "Analyze this video style and rhythm"
  → "Replace the video background with a beach"
""".format(sep=self._separator())

    # ── Format: Execution Plan ─────────────────────────────────────────

    def format_execution_plan(self, plan_data: Dict) -> str:
        """Format the execution plan for display."""
        if not plan_data or 'execution_plan' not in plan_data:
            return self._separator() + "\n⚠️  Could not generate a valid execution plan\n" + self._separator()

        task_analysis = plan_data.get('task_analysis', 'unspecified')
        exec_plan = plan_data['execution_plan']
        steps = exec_plan.get('steps', [])
        total = len(steps)
        pipeline = plan_data.get('pipeline', '')

        lines = []
        lines.append(self._separator('═'))
        lines.append(f"📋  Execution Plan")
        lines.append(self._separator('═'))
        lines.append(f"Analysis: {task_analysis}")
        if pipeline:
            lines.append(f"Pipeline: {pipeline}")
        lines.append(f"Steps: total {total} steps")
        lines.append('')

        for i, step in enumerate(steps):
            n = step.get('step_number', i + 1)
            desc = step.get('action_description', 'No description')
            tool = step.get('tool', {})
            tool_name = tool.get('name', 'none')
            tool_purpose = tool.get('purpose', '')
            deps = step.get('dependencies', [])
            status = step.get('status', 'pending')

            lines.append(f"  Step {n}  {self._status_emoji(status)}  {desc}")
            if tool_name and tool_name != 'no specific tool':
                lines.append(f"     Tool: {self._tool_label(tool_name)}")
                if tool_purpose:
                    lines.append(f"     Purpose: {tool_purpose}")
            if deps:
                lines.append(f"     Depends on: Step {', '.join(map(str, deps))}")
            lines.append('')

        lines.append(self._separator())
        return '\n'.join(lines)

    # ── Format: Step Result ────────────────────────────────────────────

    def format_step_result(self, step_num: int, step: Dict, result: Dict) -> str:
        """Format a single step execution result."""
        desc = step.get('action_description', f'Step {step_num}')
        tool_name = step.get('tool', {}).get('name', 'unknown')
        success = result.get('success', False) if result else False
        is_ok = success in [True, 'True', 'true']
        message = result.get('message', '') if result else ''
        output_path = result.get('output_path', '') if result else ''
        content = result.get('content', '') if result else ''

        emoji = self._status_emoji(success)
        label = self._tool_label(tool_name) if tool_name != 'no specific tool' else ''

        lines = []
        lines.append(f"  {emoji}  Step {step_num} — {desc}")

        if label:
            lines.append(f"      Tool: {label}")

        if message:
            lines.append(f"      Result: {message}")

        if output_path:
            lines.append(f"      Output: {self._resolve_path(output_path)}")

        if not is_ok and content:
            # Show error details concisely
            detail = content[:200]
            lines.append(f"      Details: {detail}")

        return '\n'.join(lines)

    # ── Format: Task Complete ──────────────────────────────────────────

    def format_task_complete(self, plan_data: Dict, results: Dict[int, Any]) -> str:
        """Format the final task completion summary."""
        if not plan_data or 'execution_plan' not in plan_data:
            return self._separator() + "\nTask complete (no plan data)\n" + self._separator()

        steps = plan_data['execution_plan'].get('steps', [])
        total = len(steps)
        succeeded = sum(
            1 for r in results.values()
            if isinstance(r, dict) and r.get('success') in [True, 'True', 'true']
        )

        lines = []
        lines.append('')
        lines.append(self._separator('═'))
        lines.append(f"✅  Task complete")
        lines.append(self._separator('═'))
        lines.append(f"Total {total} steps; succeeded {succeeded} steps")
        lines.append('')

        for i, step in enumerate(steps):
            n = i + 1
            desc = step.get('action_description', f'Step {n}')
            result = results.get(n, {})
            success = result.get('success', False) if isinstance(result, dict) else False
            emoji = self._status_emoji(success)
            message = result.get('message', '') if isinstance(result, dict) else ''
            output_path = result.get('output_path', '') if isinstance(result, dict) else ''

            lines.append(f"  {emoji} Step {n}: {desc}")
            if message:
                lines.append(f"     → {message}")
            if output_path:
                lines.append(f"     📁 {self._resolve_path(output_path)}")

        # Find final output path
        final_output = ''
        for r in reversed(list(results.values())):
            if isinstance(r, dict) and r.get('output_path'):
                final_output = r['output_path']
                break

        lines.append('')
        if final_output:
            lines.append(f"📁  Final output: {self._resolve_path(final_output)}")
        lines.append(self._separator('═'))

        return '\n'.join(lines)

    # ── Format: Error ──────────────────────────────────────────────────

    def format_error(self, step_num: int, step: Dict, error_msg: str,
                     completed_count: int = 0, total_steps: int = 0) -> str:
        """Format an execution error report."""
        desc = step.get('action_description', f'Step {step_num}') if step else f'Step {step_num}'

        lines = []
        lines.append('')
        lines.append(self._separator('─'))
        lines.append(f"⚠️  Execution interrupted")
        lines.append(self._separator('─'))
        lines.append(f"Failed step: Step {step_num} — {desc}")
        lines.append(f"Error: {error_msg}")
        if total_steps > 0:
            lines.append(f"Completed: {completed_count}/{total_steps} steps")
        lines.append('')
        lines.append("💡 Suggestions:")
        lines.append("   • Check whether input parameters are correct")
        lines.append("   • Confirm required file paths are valid")
        lines.append("   • Adjust the request and retry")
        lines.append(self._separator('─'))

        return '\n'.join(lines)

    # ── Format: Stream Events (SSE-compatible) ─────────────────────────

    def format_stream_event(self, event_type: str, data: Any) -> Dict:
        """
        Format a streaming event for SSE output.
        Returns a dict ready to be serialized to JSON and sent as SSE.

        This enriches the raw event with human-readable formatting
        while keeping the machine-readable structure for the frontend.
        """
        if event_type == 'content':
            return {'type': 'content', 'content': str(data)}

        elif event_type == 'tool_start':
            tool_name = data if isinstance(data, str) else data.get('tool', 'unknown')
            label = self._tool_label(tool_name)
            return {
                'type': 'tool_start',
                'tool': tool_name,
                'label': label,
                'message': f'Running: {label}...'
            }

        elif event_type == 'tool_end':
            result = data if isinstance(data, dict) else {}
            success = result.get('success', False)
            message = result.get('message', '')
            output_path = result.get('output_path', '')
            return {
                'type': 'tool_end',
                'result': result,
                'formatted': f"  {self._status_emoji(success)} {message}"
                + (f"\n  📁 {self._resolve_path(output_path)}" if output_path else '')
            }

        elif event_type == 'finish':
            return {
                'type': 'finish',
                'session_id': data if isinstance(data, str) else data.get('session_id', ''),
                'message': '✅ Task completed'
            }

        elif event_type == 'error':
            return {
                'type': 'error',
                'content': str(data),
                'message': f'⚠️ {data}'
            }

        elif event_type == 'pipeline':
            return {
                'type': 'pipeline',
                'pipeline': data.get('pipeline', '') if isinstance(data, dict) else str(data),
                'message': f"📋 Using pipeline: {data.get('pipeline', '') if isinstance(data, dict) else data}"
            }

        elif event_type == 'pipeline_start':
            return {
                'type': 'pipeline_start',
                'pipeline': data.get('pipeline', '') if isinstance(data, dict) else str(data),
                'stages': data.get('stages', []) if isinstance(data, dict) else [],
                'message': f"🚀 Starting pipeline: {data.get('pipeline', '') if isinstance(data, dict) else data}"
            }

        elif event_type == 'pipeline_stage_start':
            return {
                'type': 'pipeline_stage_start',
                'stage': data.get('stage', '') if isinstance(data, dict) else str(data),
                'index': data.get('index', 0) if isinstance(data, dict) else 0,
                'total': data.get('total', 0) if isinstance(data, dict) else 0,
                'message': f"⏳ Running stage: {data.get('stage', '') if isinstance(data, dict) else data}"
            }

        elif event_type == 'pipeline_stage_complete':
            return {
                'type': 'pipeline_stage_complete',
                'stage': data.get('stage', '') if isinstance(data, dict) else str(data),
                'message': f"✅ Stage completed: {data.get('stage', '') if isinstance(data, dict) else data}"
            }

        elif event_type == 'pipeline_suspended':
            return {
                'type': 'pipeline_suspended',
                'stage': data.get('stage', '') if isinstance(data, dict) else str(data),
                'continuation_token': data.get('continuation_token', '') if isinstance(data, dict) else '',
                'prompt': data.get('prompt', '') if isinstance(data, dict) else '',
                'data': data.get('data', {}) if isinstance(data, dict) else {},
                'message': f"⏸️  Waiting for user input ({data.get('stage', '') if isinstance(data, dict) else ''})"
            }

        elif event_type == 'pipeline_complete':
            delivery = data.get('delivery_report', {}) if isinstance(data, dict) else {}
            msg = "✅ Pipeline completed"
            if isinstance(delivery, dict) and delivery.get('output_path'):
                msg += f"\n📁 Final output: {OutputFormatter._resolve_path(delivery['output_path'])}"
            return {
                'type': 'pipeline_complete',
                'delivery_report': delivery,
                'message': msg,
            }

        elif event_type == 'budget_update':
            budget = data.get('budget', {}) if isinstance(data, dict) else {}
            msg = "💰 Budget updated"
            if isinstance(budget, dict):
                msg += f" (spent ${budget.get('total_spent_usd', 0):.4f} / ${budget.get('budget_limit_usd', 0):.2f})"
            return {
                'type': 'budget_update',
                'budget': budget,
                'message': msg,
            }

        # Default: pass through
        return {'type': event_type, 'data': data}

    # ── Format: General Chat Response ──────────────────────────────────

    def format_chat_response(self, content: str) -> str:
        """Format a general chat/answer response."""
        return f"{content}\n\n{self._separator('─')}\n💡 Tell me what video task you want to do."

    # ── Format: No-plan Response (direct answer, no tools needed) ──────

    def format_direct_answer(self, plan_data: Dict, results: Dict) -> str:
        """
        Format a direct answer where no tools were actually called
        (e.g., answering "what can you do").
        """
        # Extract the actual content from the results
        if results:
            first_result = list(results.values())[0] if results else {}
            if isinstance(first_result, dict):
                content = first_result.get('content', '')
                if content:
                    return f"{content}\n\n{self._separator('─')}\n💡 Describe what you want to do and I will create an execution plan."
        return self.format_task_complete(plan_data, results)
