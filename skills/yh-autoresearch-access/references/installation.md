# Installation and update contract

## Codex and filesystem-capable agents

Run the installer from the public bootstrap repository:

```powershell
$env:YH_AUTORESEARCH_ACCESS_URL='https://43.153.65.53/release/yh-autoresearch'
py skills/yh-autoresearch-access/scripts/install_yh_autoresearch.py --base-url $env:YH_AUTORESEARCH_ACCESS_URL --agent codex
```

The installer obtains a short-lived download token, downloads the release ZIP, rejects unsafe archive paths, verifies every file in `manifest.json`, and then installs atomically. An existing installation is moved to a timestamped sibling backup only after verification succeeds.

Default destinations:

- Codex: `$CODEX_HOME/skills/yh-autoresearch` when `CODEX_HOME` is set, otherwise `~/.codex/skills/yh-autoresearch`.
- Claude-compatible agent: `~/.claude/skills/yh-autoresearch`.
- Generic agent: `.agents/skills/yh-autoresearch` under the current workspace.

Use `--destination` when the agent has a different skill directory.

## Web and mobile agents

Open [the canonical HTTPS activation page](https://43.153.65.53/release/yh-autoresearch/), enter the internal-beta code, and download the verified ZIP. Install or attach the `yh-autoresearch` directory using that agent's supported skill/file flow. The bundle is self-contained after download.

A client without filesystem, code execution, or experiment tools can still use the workflow, schemas, research planning, evidence tracking, and state summaries. It cannot truthfully perform local code/GPU experiments until the client supplies those tools.

## Privacy boundary

The distribution host does not execute research. Do not upload research inputs or outputs to it. All `.autoresearch`, `runs`, allocated memory, checkpoints, evaluator outputs, and artifacts belong in the user's workspace.
