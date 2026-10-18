---
name: void-vibe-runner-safety
description: Review VOID VIBE public GitHub Actions workflows, triggers, concurrency, private checkout permissions, artifact privacy and publication safety.
---

# VOID VIBE runner safety

Use for changing or troubleshooting public Actions workflows and their interaction with the private music router.

1. Read this repository's `AGENTS.md` and `README.md` plus the exact workflow; verify current Actions settings when accessible.
2. Confirm the workflow's source repository, ref, permissions, tokens, trigger, concurrency group, conditional guards, timeouts, expected output and private state branch.
3. Enforce separation of transfer, daily publishing and DJ sessions; never use the same journal or run two publishers for one task simultaneously.
4. Treat untrusted PR code and external dependencies as hostile to privileged runner contexts. Do not expose `PRIVATE_REPO_TOKEN`, Telegram StringSessions or audio through public logs, artifact uploads, caches, summaries or releases.
5. During migrations verify cutover and rollback order. Keep the private code private; do not turn on public runner or change publication flags automatically.
6. For incidents, distinguish runner was scheduled, started, ran successfully and **confirmed actual Telegram delivery** using private receipts. Report what's unverified.
7. For a change, run YAML/trigger lint and a non-publishing validation before any live workflow; document permission changes and rollback steps.
8. Never auto-approve DJ audio or bypass QC, human listening approval or rights confirmation.

A skill is an instruction set, not a daemon or permission to invoke Telegram side effects.
