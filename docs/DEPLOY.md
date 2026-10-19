> Deployment is paused at the user's request. Vercel is the requested frontend target,
> and rendering must be fully cloud-hosted. That architecture is not implemented.
> Docker/auth/storage preparation below is a draft. The Render example is retained
> only as research; Render is unavailable to the user. No service is deployed.

# Online deployment (single owner)

This is a Docker-based Python application, not a GitHub Pages/static site. The
container includes FFmpeg, Piper and the LJ Speech voice. AI Horde remains free and
optional; no paid image provider is enabled. Ollama and Google Drive are not
configured in this container. Write narration manually; Drive needs separate setup.

The online instance uses an owner password and HTTPS. It is not a multi-user product.
Only one process and one service instance may use a project database.

## Push from Windows

The implementation is already committed locally. In PowerShell:

```powershell
cd D:\SelahFrame
git status
git push -u origin main
```

Do not add a force flag. If the push is rejected, keep the rejection text and resolve
it before deploying. Do not commit .env, data/, output/, voices/, tokens or credentials.
Source and deployment files are tracked; local media/project history is not uploaded
by Git. An online deployment starts a new library unless existing projects are
migrated separately (Windows database media paths need rebasing before Linux use).

## Render dashboard

Checked against official docs on 2026-10-19:
https://render.com/docs/docker
https://render.com/docs/disks
https://render.com/docs/compute-plans
https://render.com/docs/environment-variables
https://render.com/docs/blueprint-spec
https://render.com/pricing

The example blueprint uses the legacy Standard name, now 1c-2g: one CPU, 2 GB RAM,
currently $25/month. Its 10 GB persistent disk is billed separately. Review the
current total in Render before confirming. A 2 GB service is a starting configuration,
not a benchmark guarantee. Free instances have 512 MB RAM and do not support the
persistent disk this SQLite/media setup needs. Do not use Free for saved projects.
A Docker-capable VPS with sufficient RAM/storage is an alternative; no provider
account has been created or purchase made for you.

1. Sign in to Render with GitHub.
2. Choose New > Blueprint and select Rohan-Ktksu/selahframe, branch main.
3. Render reads render.yaml. Review the paid compute and disk charges, then deploy
   only if you accept them. The blueprint generates the owner password as a secret.
   Automatic deploys are disabled so a future push does not interrupt a running job.
4. Once the service is Live, open its HTTPS onrender.com address.
5. The browser asks for a username/password. Username: owner. Copy the generated
   SELAHFRAME_PASSWORD value from the service's Environment page. Keep it private.
6. Create a test project, save and approve narration, generate one AI Horde scene,
   then render 720p first. Check the audio, captions, download and restart persistence
   before using longer 1080p projects.

For a manual New > Web Service setup, choose Docker with these settings instead:

| Setting | Value |
| --- | --- |
| Repository / branch | Rohan-Ktksu/selahframe / main |
| Dockerfile | ./Dockerfile |
| Compute | 1c-2g (Standard) or adequate larger plan |
| Health check | /healthz |
| Persistent disk mount | /var/lib/selahframe |
| Disk size | 10 GB to start; monitor growth |
| SELAHFRAME_USER | owner |
| SELAHFRAME_PASSWORD | A unique random password of at least 24 characters |
| SELAHFRAME_ONLINE | 1 |
| SELAHFRAME_STORAGE | /var/lib/selahframe |

Leave build/start commands at their Docker defaults. Render supplies PORT and
RENDER_EXTERNAL_URL. The container uses those to listen and configure the allowed
host/origin. For a custom domain, set SELAHFRAME_PUBLIC_URL to its HTTPS origin,
without a path, and use that origin in your browser. Never put passwords in GitHub.

## Behavior and checks

- Without a valid online URL and strong password, container startup fails closed.
- Every page, API, image, voice/music preview and export requires owner authentication.
  Only /healthz is public and returns a minimal ok response.
- Data, output and scratch use the persistent storage root. Model weights are built
  into the image, not downloaded on each application start.
- Keep one instance/worker. Do not run migrations in a separate process while jobs
  are running. Deploying stops the current server; active jobs become explicitly
  failed on restart and can be retried. Local files are retained.
- Storage is bounded per media job, not by total lifetime history. Monitor the disk,
  export backups and remove/archive projects deliberately as the library grows.
- Online and local libraries are separate. This setup does not publicly publish your
  local D: files or upload your current SQLite database.
- Change SELAHFRAME_PASSWORD in the hosting environment to revoke the previous
  password. Basic authentication uses the browser's sign-in dialog over HTTPS.

Validation: offline authentication/origin/startup tests and the existing local Windows
media pipeline were exercised. Docker is not installed on this workstation, so the
Linux image build and an actual hosted render have not been tested here. Treat the
first Render build and short render as deployment acceptance checks. No live service
has been created or paid plan purchased by the agent.
