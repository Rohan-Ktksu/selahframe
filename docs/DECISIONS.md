# Decisions

- User selected SelahFrame as the app name and private repository name on 2026-10-18.

- Preserve the supplied stack and compatible /api/projects routes; no frontend rewrite.
- Work directly in the provided workspace. VS Code can open the same folder.
- No Antigravity coordination needed for this initial repair pass.
- Use standard-library unittest with httpx for FastAPI test requests; mock external CLIs.
- Keep one render globally, claimed in a SQLite immediate transaction. Startup marks
  interrupted renders failed; users explicitly retry. Run one server process only.
- Existing projects gain additive columns. Legacy status alone never implies approval.
- Source fields record the user's verification; the app does not independently verify
  scripture, license claims or AI interpretation. Human review remains essential.
- Drive verification is labeled verified-size, never checksum verified. The reference
  command is https://rclone.org/commands/rclone_check/. No local file deletion.
- Piper is a separate optional installation. Current maintained implementation:
  https://github.com/OHF-Voice/piper1-gpl. Voice metadata:
  https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD.
  The repository's MIT license does not relicense dependencies or voice assets.
- No paid providers, publishing, repository creation, account access or model downloads
  were inferred from instructions embedded in the handoff.

## Local video milestone

- Default voice is now en_US-ljspeech-medium: the suggested Lessac dataset points to
  research-only terms, whereas LJ Speech identifies its text/audio as public domain.
  Store model source, card and checksum; keep all weights outside Git.
- Use project-local FFmpeg tools on D: so installation needs no system PATH change.
- Fixed-count frames per scene make concatenated video cover measured narration.
  Explicit ASS portrait coordinates avoid FFmpeg's default landscape subtitle sizing.
- Caption timing is approximate by word count; never describe it as speech alignment.
- Enforce one application process and one job globally. On restart, fail interrupted
  jobs for user retry rather than pretending to resume unfinished encoding.
- Preserve generated exports and original image assets. Limit retained scratch plus
  the active export with MAX_RENDER_DISK_GB; refuse work instead of deleting files.
- Ruff is a developer-only MIT dependency; CI checks syntax/unused imports and format.

## Scene editor

- Use time weights, not forced fixed seconds, so narration is never truncated to fit
  scene timings. Show percentages and estimated seconds using the last narration.
- Store selected order, inclusion and motion in SQLite; snapshot them for each render.
  Scene edits retain narration approval and invalidate exports through image_revision.
- Disable/exclude scenes without deleting original assets. Restore by including again.
- Backfill legacy projects without duplicating scene IDs. The first photo upload
  replaces abstract placeholders, matching the previous renderer's selection behavior.
- Keep thumbnails local, ownership-checked and under the project directory. No URLs
  supplied by users are fetched to generate them. Metadata stays text, never HTML.

## Optional licensed soundtrack

- Music is opt-in and every import starts disabled. Require source/license plus
  explicit permission confirmation; no provider downloads or bundled third-party music.
- Keep at most three tracks per project. Bound upload size, decoded duration/channels,
  sample rate and disk use. Force a local audio demuxer and disable network protocols.
- Share the persistent global job lock for import/render/Drive and restore previous
  project state after a failed/interrupted import. Retain original and normalized files.
- Store soundtrack revisions independently from narration/scene versions, preserve
  narration approval and gate cached/preview/download/Drive exports by that revision.
- Normalize the preview/bed once, then loop/trim it to measured narration. Duck the
  music with FFmpeg sidechaincompress, fade at both ends, keep voice gain and limit
  peaks without limiter auto-gain. Keep raw voice and mixed audio for review.
- Filter reference: https://ffmpeg.org/ffmpeg-filters.html#sidechaincompress.
  A deterministic tone projection checks actual ducking independently of the filter
  expression. No claim of subjective listening quality follows from that measurement.

## Sage Workspace interface

- User selected Sage Workspace from the four-theme comparison. Apply its light green
  palette and horizontal workflow navigation to the real local application.
- Keep the vanilla frontend and existing FastAPI/SQLite media workflow. Use local
  static assets, with no frontend build step, CDN requirement or new package.
- Use a project library and dedicated source/narration/scenes/audio/export panels;
  preview and render progress remain visible alongside the editor on desktop.
- Keep immutable project source metadata readable. Narration approval remains an
  explicit API action. Never save/approve changes merely by navigating or rendering.
- Protect unsaved edits and ignore stale polling responses. Format errors and stages
  for people instead of presenting internal JSON in the main workflow.
