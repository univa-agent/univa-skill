# Localization - Core Skill

## When to Use

Use for ASR, timed captions, translation, bilingual subtitles, localized TTS,
horizontal/vertical localized rendering, and locale quality checks.

## Covered Tools

- `transcribe_media`
- `translate_captions`
- `prepare_localized_captions`
- `generate_localized_voiceover`
- `render_localized_video`
- `validate_localized_media`

## Tool Contracts

### `transcribe_media`

- Parameters: `media_path`, optional `language`, `word_timestamps` (default
  `true`), and `model_size` (default `small`).
- Uses the optional local `faster-whisper` backend. If unavailable, returns
  `success: false` and `error_code: backend_unavailable`; it never invents a
  transcript.
- Successful output contains normalized caption cues and real word timings.

### `translate_captions`

- Parameters: SRT/VTT path, text, or cue list in `captions`, required
  `target_language`, and optional `source_language`.
- Uses the configured OpenAI-compatible LLM endpoint and requires strict JSON.
- Cue IDs, count, order, and timing must remain unchanged. Partial translation
  is a failure.

### `prepare_localized_captions`

- Parameters: `captions`, optional `translated_captions`, `bilingual`,
  `output_path`, and `output_format` (`srt` or `vtt`).
- Repairs invalid durations and overlaps, creates a new file, and returns the
  normalized cue list and absolute output path.

### `generate_localized_voiceover`

- Parameters: `video_path`, approved `captions`, optional `output_path`,
  `voice`, `emotion`, and `keep_original_audio`.
- Reuses UniVA `generate_audio_assets_from_plan` and its configured TTS
  provider. Each cue is placed at its approved start time.
- This is a media mutation and must not run before localization approval.

### `render_localized_video`

- Parameters: `video_path`, approved `captions`, optional `output_path`,
  `bilingual`, `aspect_ratio` (`16:9`, `9:16`, `1:1`, or source), and `title`.
- Reuses `remotion_compose_video`; its existing FFmpeg ASS fallback remains
  available. It always creates a new output.
- This is a media mutation and must not run before localization approval.

### `validate_localized_media`

- Parameters: rendered `video_path` and final `captions`.
- Checks non-empty output, ffprobe readability, cue bounds, overlap, and a
  maximum two-line subtitle layout.

## Required Behavior

1. Transcribe or ingest supplied subtitles and record backend limitations.
2. Keep source text, cue IDs, and exact timing through translation.
3. Show source/target cues, TTS settings, render dimensions, preservation
   rules, and exact tool requests at the `confirm` checkpoint.
4. Generate voiceover only when explicitly requested.
5. Execute only the approved contract, preserve source media, run locale QA,
   and link all artifacts and receipts in delivery reporting.

## External Agent Execution

- For ASR-only requests, read this contract and call the existing
  `univa.mcp_tools.localization.transcribe_media` in process. The FastAPI
  server and Web editor are not required.
- `transcribe_media` is read-only and does not require media-mutation
  approval. Save its real `transcript`, `captions`, and optional `words`
  result; stop with `backend_unavailable` if `faster-whisper` cannot import.
- To create an SRT/VTT sidecar, pass successful `captions` unchanged to
  `prepare_localized_captions`. Do not translate, dub, or burn captions unless
  the user requested those additional operations.
- For translation-only work, preserve every cue ID and time range. Translation
  requires the configured LLM key.
- Before `generate_localized_voiceover` or `render_localized_video`, write and
  display the exact localization plan/review, stop at `awaiting_human`, and
  execute only the approved version.
- Use the full `localization` Pipeline when the request combines ASR,
  translation, voiceover, rendering, and locale QA.

### ASR Request Order

1. Verify the source path exists and is an audio/video file.
2. Call `transcribe_media(media_path, language, word_timestamps, model_size)`.
3. Check `success`; never replace failed ASR with guessed text.
4. Persist JSON and optional SRT/VTT under `results/localization/`.
5. Verify output files are non-empty and report detected language and cue count.

## Common Pitfalls

- Treating missing ASR or translation configuration as a successful empty result.
- Translating without preserving cue IDs and timing.
- Starting TTS or subtitle rendering before explicit approval.
- Claiming intelligent reframing when only deterministic dimensions and
  `contain` fitting were used.
