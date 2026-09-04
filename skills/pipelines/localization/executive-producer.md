# Localization Executive Producer - Pipeline Skill

## Stage Flow

`preflight -> transcribe -> translate -> confirm -> voiceover -> render -> locale_qa -> deliver`

## Responsibilities

- Accept a local media path plus source/target locale requirements.
- Use supplied SRT/VTT when available; otherwise call `transcribe_media`.
- Record `backend_unavailable` as blocked rather than generating placeholder text.
- Preserve cue IDs and timing when translating and present source/target cues.
- At `confirm`, show exact TTS and render requests, output dimensions, whether
  subtitles are bilingual, and whether original audio is preserved.
- Skip voiceover unless the user explicitly requests dubbing or narration.
- Create new output files, run locale QA, and deliver the artifact/receipt chain.

## Approval Rule

Transcription and translation are read-only preparation. TTS, muxing, and
localized video rendering are media creation/mutation and may run only after
the displayed `approved_localization_contract` is explicitly approved.

## Output Truthfulness

Do not claim speaker diarization, lip sync, semantic reframing, or translated
speech unless the corresponding backend actually produced and validated it.
