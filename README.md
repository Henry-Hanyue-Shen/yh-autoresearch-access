# YH Autoresearch Access

Public bootstrap and code-gated distribution host for the YH Autoresearch internal beta.

The host does **not** run research. It validates beta access and distributes a self-contained skill ZIP. Research execution, state, memory, checkpoints, experiments, and artifacts remain in the user's agent workspace.

## Repository boundary

- This public repository contains the bootstrap skill, installer, deterministic bundle builder, and minimal release host.
- The complete v4 source and built release ZIP stay in the private source/deployment boundary.
- Access codes and session secrets are deployment environment variables and must not be committed.

## Build the client-side bundle

```powershell
py scripts/build_bundle.py `
  --source ..\YH_Frontier_Autoresearcher_v0.4_UPLOAD_READY `
  --output dist\yh-autoresearch-0.4.0.zip `
  --version 0.4.0 `
  --source-release-sha256 2cdf77b7cfa350ea18828fbc0b5a3faa508d1a31564a784cc9f1461ab0f99e0e
```

## Run the access host

Set the internal beta code and a random session secret in the deployment environment. Do not place either value in this repository.

```powershell
$env:YH_ACCESS_CODE='<internal-beta-code>'
$env:YH_SESSION_SECRET='<at-least-32-random-characters>'
$env:YH_BUNDLE_PATH=(Resolve-Path 'dist\yh-autoresearch-0.4.0.zip')
$env:YH_SECURE_COOKIE='0' # local loopback only; keep Secure enabled behind HTTPS
py -m server.access_host --host 127.0.0.1 --port 8788
```

For an internet deployment, terminate HTTPS at the reverse proxy, keep secure cookies enabled, and expose only the access host. The bundle service does not need model credentials or access to user research data.

## Tencent release route

The included Tencent deployment publishes the activation host at:

```text
https://43.153.65.53/release/yh-autoresearch/
```

It runs the Python distributor only on `127.0.0.1:18788`, adds an isolated Nginx snippet, keeps the access code in `/etc/yh-autoresearch/access.env`, and installs the verified client bundle under `/opt/yh-autoresearch/releases/`. See `tencent/deploy.sh`.

## Install from Codex or another filesystem-capable agent

```powershell
$env:YH_AUTORESEARCH_ACCESS_URL='https://43.153.65.53/release/yh-autoresearch'
py skills\yh-autoresearch-access\scripts\install_yh_autoresearch.py --agent codex
```

The installer verifies the outer ZIP SHA-256, rejects unsafe paths and symlinks, verifies every manifest entry, and only then replaces the existing installation.

## Test and validate

```powershell
py -m unittest discover -s tests -v
py C:\path\to\skill-creator\scripts\quick_validate.py skills\yh-autoresearch-access
py C:\path\to\plugin-creator\scripts\validate_plugin.py .
```
