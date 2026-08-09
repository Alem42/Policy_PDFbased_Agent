# Policy in Action Library

## Run with Docker

Requirements: Docker Engine with Docker Compose and internet access for the first image build.

From the repository root:

```bash
docker compose up
```

Open <http://localhost>. The health endpoint is
<http://localhost/api/v1/health>. Port 80 must be available on the host.

The first build downloads the frontend, backend and PostgreSQL/pgvector images.
Subsequent starts reuse the local images and persistent volumes. Stop the stack
with `Ctrl+C`, or use `docker compose down` when it runs detached. Do not use
`docker compose down -v` unless you intend to delete the database.

No environment file is required. The root `.env.example` contains optional
Docker Compose overrides; `backend/.env.example` is only for running the backend
directly during development. They serve different runtimes and must not be
merged. Never commit populated `.env` files. API keys for optional AI features
are supplied by the customer in **Manage** after sign-in. The backend generates
its token-signing secret on first use and stores it in `backend/data`.

## Register the first administrator

Administrator registration is invitation-only. After the stack is healthy,
the host operator creates the initial, single-use invitation:

```bash
docker compose exec backend python -m app.modules.auth.bootstrap
```

Copy the displayed code, open <http://localhost>, choose **Create an account**
and **Administrator**, then enter an email address, choose credentials, and paste
the invitation. The code is shown only once and expires after seven days. Once
an administrator exists, the bootstrap command is disabled. Existing
administrators create or revoke additional codes under **Manage > Administrator
invites**.

Registration collects an email address but does not send or require an email
verification code. Email is reusable contact information rather than a login
identifier, so multiple accounts may use the same address. Each account must
have a unique username and signs in with that username. Administrator accounts
additionally require a single-use invitation.
