---
name: yh-autoresearch-access
description: Activate, download, verify, install, or update the client-side YH Autoresearch internal beta skill. Use when the user asks to access, install, load, update, or repair YH Autoresearch on Codex or another agent.
---

# YH Autoresearch Access

This is a distribution bootstrap, not a research runner. The complete research harness is downloaded into the user's agent workspace and all subsequent research work remains on the user side.

## Activation workflow

1. Read [references/installation.md](references/installation.md) before installing or updating.
2. Use an exact URL supplied by the user or `YH_AUTORESEARCH_ACCESS_URL`; otherwise use the canonical internal-beta host `https://43.153.65.53/release/yh-autoresearch`. Never invent another host.
3. Run `scripts/install_yh_autoresearch.py` with the resolved host and target agent.
4. Let the user enter the access code through the script's hidden prompt or through the host's HTTPS activation page. Do not write access codes into source files, command history, logs, Git, or conversation summaries.
5. Require checksum and manifest verification to pass before installation.
6. Report the installed version and destination. Ask the user to start a new agent session when the active client only discovers skills at session start.

## Execution boundary

- Do not send research inputs, datasets, repositories, memory, run state, or artifacts to the access host.
- The access host may receive only activation data, release/version requests, and ordinary HTTP metadata.
- After installation, route research requests to the installed `yh-autoresearch` skill. Do not imitate the full harness from this bootstrap.
- Do not claim that a web/mobile agent can execute shell, Python, GPU, or filesystem operations unless that client actually exposes those capabilities.

## Failure behavior

- On `401` or `403`, report activation failure without echoing the code.
- On checksum, manifest, archive-path, or signature mismatch, stop and preserve the existing installed version.
- On an unavailable host, do not fall back to an unverified mirror.
- Never delete an existing installation before the replacement bundle is fully verified.
