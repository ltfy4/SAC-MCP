# Security Policy

SAC-MCP brokers a Large Language Model's access to a SAP Analytics Cloud tenant. That makes it a sensitive piece of plumbing: a vulnerability here can leak tenant data, credentials, or allow unauthorized writes. Please take reports seriously and route them privately.

## Supported versions

The project is pre-1.0. Only the latest `main` branch receives security fixes. Once a stable `1.x` line exists, this section will be updated.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security problems.

Use **GitHub's private vulnerability reporting** instead:

1. Go to the repository's **Security** tab on GitHub.
2. Click **Report a vulnerability**.
3. Provide:
   - A clear description of the issue and its impact.
   - Steps to reproduce (or a minimal proof-of-concept).
   - The affected version / commit.
   - Any suggested mitigation, if you have one.

You should receive an acknowledgement within **5 business days**. We'll keep you updated on triage and remediation, and credit you in the release notes unless you'd prefer to stay anonymous.

If GitHub private reporting is unavailable for any reason, open a minimal public issue titled "Security contact request" (with no vulnerability details) and we'll arrange a private channel from there.

## What's in scope

- Authentication and authorization handling (`sac_mcp/client/auth.py`, `sac_mcp/client/csrf.py`).
- Secret handling and logging redaction (`sac_mcp/config.py`, `sac_mcp/logging.py`).
- HTTP transport security (`sac_mcp/transports/http.py` — bearer auth, CORS).
- Tool annotations that misclassify a destructive action as read-only.
- Any path that could exfiltrate tenant data outside the configured tenant URL.
- Any dependency vulnerability that affects the running server.

## What's out of scope

- Issues that require a malicious operator with full access to the host running SAC-MCP — at that point the attacker has the `.env` file and the server process itself.
- SAC platform vulnerabilities — report those directly to SAP (see [SAP Trust Center](https://www.sap.com/about/trust-center.html)).
- Social engineering, physical attacks, or vulnerabilities in unmodified upstream dependencies (report those to the upstream project; we'll consume the fix).

## Operator best practices

Most "security issues" in tools like this are deployment problems. Before reporting, please check that the deployment isn't doing one of these:

### Credentials

- **Never commit `.env`** — it is in `.gitignore` and should stay there.
- **Use OAuth 2.0 client credentials** (2-legged) with the *minimum* SAC roles the tool actually needs. The project does not implement 3-legged user-delegated OAuth yet.
- **Rotate the SAC client secret** if it has been pasted anywhere outside the host machine (chat, ticket, screenshot, backup that could leak).

### Streamable HTTP transport

- **`MCP_HTTP_BEARER` is a shared secret** — treat it like a password. Generate with `openssl rand -hex 32`. Never reuse across environments. Rotate periodically and immediately after suspected exposure.
- **Bind to `127.0.0.1`** for single-user dev work. Only bind to a public interface when you have a reverse proxy with TLS termination in front (the server itself does not terminate TLS).
- **Set `MCP_HTTP_CORS_ORIGINS` explicitly** to the exact origins you trust. The default is empty (no CORS) — that is the safe default.

### Logging

- The structured logger in `sac_mcp/logging.py` redacts `authorization`, `x-csrf-token`, `set-cookie`, `client_secret`, `access_token`, and `refresh_token` by default.
- If you add a new sensitive header or field, add it to `_REDACT_KEYS` in the same change.
- Do not log raw request or response bodies in production — they routinely contain PII pulled from SAC.

### Multi-tenant deployments

The current design uses a single SAC tenant per server process. If you front a single SAC-MCP instance with multiple users, every user effectively shares the same SAC identity. Per-session tenant credentials are a planned feature; until they ship, deploy one instance per tenant.

## Hardening checklist for production

- [ ] `.env` not committed; secrets injected via the deployment platform's secret store.
- [ ] `MCP_HTTP_BEARER` set to a fresh 32-byte random value, rotated on a schedule.
- [ ] Reverse proxy (nginx, Caddy, ALB, etc.) terminates TLS; SAC-MCP itself listens on `127.0.0.1` or a private network only.
- [ ] `MCP_HTTP_CORS_ORIGINS` restricted to known frontends.
- [ ] OAuth client in SAC scoped to the minimum required roles.
- [ ] Logs shipped to a sink with access control; raw bodies not logged.
- [ ] Dependency updates applied (`pip list --outdated`; review CHANGELOG before bumping majors).
