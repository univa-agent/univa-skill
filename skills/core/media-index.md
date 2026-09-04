# Media Index - Core Skill

## When to Use

Use for durable local video indexing, time-coded segment lookup, and keyword
search before deep understanding or long-footage editing.

## Covered Tools

- `index_video_media`
- `update_video_index_segments`
- `search_video_moments`
- `get_video_moment`

## Tool Contracts

### `index_video_media`

- Parameters: `video_path` (required), `segment_duration_seconds` (default `5.0`), `force` (default `false`).
- Returns `success`, `index_id`, `source_path`, `metadata`, `reused`, and `segments`.
- Each segment contains `start_seconds`, `end_seconds`, `thumbnail_path`, `caption`, `transcript`, and `keywords`.
- Indexing uses local `ffprobe` and `ffmpeg`; it does not require a GPU or an embedding model.

### `update_video_index_segments`

- Parameters: `media_path`, `annotations`, and optional `replace_existing`.
- Each annotation requires `start_seconds`, `end_seconds`, and at least one of
  `caption`, `transcript`, or `keywords`; keywords may be a string or list.
- Text is written only to overlapping indexed segments. By default new text is
  merged without duplicates; replacement must be explicit.
- Use this after trusted ASR, VLM analysis, imported captions, or user-provided
  annotations. Never invent text merely to make search return results.

### `search_video_moments`

- Parameters: `query` (required), `media_path` (optional), `top_k` (default `10`).
- Returns matching segments with normalized `score` and exact timecodes.
- The current implementation searches indexed text fields. `semantic_search` is `false` until an embedding backend is configured.

### `get_video_moment`

- Parameters: `media_path`, `start_seconds`, `end_seconds`.
- Returns every indexed segment overlapping the requested interval.

## Required Behavior

- Validate that the source is a readable local video and report `success: false`
  with an explicit error on failure.
- Repeated indexing of an unchanged file reuses its existing index.
- Never claim captions, transcripts, OCR, speakers, or embeddings that have not
  actually been written by an enrichment backend.
- Preserve absolute source and thumbnail paths under the configured data root.

## External Agent Execution

Use this order for a request such as "find every train scene and return exact
timecodes":

1. Call `index_video_media` and reuse an unchanged index when possible.
2. If trusted timed captions, ASR, VLM segment analysis, or user annotations
   exist, write them with `update_video_index_segments`.
3. Call `search_video_moments` for text/keyword lookup or `get_video_moment`
   for an explicit interval.
4. Return exact `start_seconds` and `end_seconds` with source/thumbnail paths.

An index containing only metadata and thumbnails cannot visually identify an
object by keyword. In that case, enrich segments with real timed analysis or
state that text search has no searchable annotations. Do not claim semantic
search while `semantic_search` is `false`.
