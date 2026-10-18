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
