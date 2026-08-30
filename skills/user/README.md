# User Preference Skills

This directory stores user-level preference skills that can be applied by UniVA planning and generation flows.

- `preference_config.yaml` records the active preference skill.
- `preference_XX.md` files describe reusable visual, narrative, mood, color, camera, and applicability preferences.
- Only the active preference named by `active_skill_name` is applied at runtime.
- Preference files should guide style and planning, but must not override safety review, media approval, tool contracts, explicit user instructions, or factual constraints.
