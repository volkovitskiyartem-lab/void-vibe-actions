# VOID VIBE Public Actions — coding-agent policy

This is a **PUBLIC runner-only** repository. Actual bot code, music, Telegram sessions and working state belong to the **PRIVATE** `volkovitskiyartem-lab/void-vibe-router` repository. Do not copy source code, raw audio, state, confidential logs or credentials here.

## Before changes
- Read `README.md`, inspect the specific workflow and the private repo's `TASK_ISOLATION.md` (if access is authorized).
- Identify which task is affected: music transfer, daily post, DJ trials or DJ release; preserve their separate private credentials/state branches.
- Most production jobs are controlled by `PUBLIC_RUNNER_ENABLED`; always verify actual branch variables and latest runs rather than trusting README.
- Never turn on switches, trigger real posts, execute recovery or rerun a job with side effects without explicit task-specific approval.

## Security and review
- No secrets or outputs that might reveal `TG_SESSION`, `TG_DAILY_SESSION`, `TG_DJ_SESSION`, `PRIVATE_REPO_TOKEN`, API credentials or private artifacts in PR descriptions, logs or public artifacts.
- PRs should not execute untrusted private code using privileged tokens; use `contents: read`, minimal scopes, explicit reviewed ref and `persist-credentials: false` when appropriate.
- Public Actions must not claim successful Telegram delivery based only on a green run.
- Keep billing, concurrency, idempotency, pause flags, release approval and rights gates intact.
- A safe documentation-only change must not modify cron triggers, secrets, variables or publish jobs.

The runner-specific Codex skill is `.agents/skills/void-vibe-runner-safety/SKILL.md`. Apply it to infrastructure tasks. Production changes require focused review and dry-run tests before any deployment.
