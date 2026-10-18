# Cost and privacy

Everything in the local export path runs on the CPU with no paid API. Ollama is an
optional local draft engine. Drive is optional storage, not a rendering server.

Scripture, private drafts, approval history, images and output remain under the project
folder on D:. .gitignore excludes databases, .env, media, voices, tools and scratch.
Back up data/projects.sqlite3 together with needed project media while the app is stopped.

Exports disclose AI-generated narration. Captions use approximate timing and must be
reviewed. User-entered sources/rights statements are recorded, not legally certified.

The launcher binds 127.0.0.1, host/origin checks reject unrelated browser origins, uploads
have payload/pixel/count limits, and subprocesses use argument lists with timeouts.
This is a single-user local application. Do not expose it with a public tunnel or bind
it to a network interface without a separate authentication/security review.

Google OAuth lives in rclone's user config outside the repository. Never share it.
The app queues copies to the existing consumer Drive, verifies names and sizes, and
retains local files. No credentialed Drive integration has been exercised yet.
