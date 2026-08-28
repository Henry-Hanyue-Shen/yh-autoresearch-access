---
name: yh-autoresearch
description: Run the complete YH Frontier Autoresearch v4 workflow for rigorous, evidence-controlled research. Use when the user wants autonomous research, idea discovery, theory-first analysis, discriminating experiments, independent validation, research memory, or a bounded research-to-paper workflow.
---

# YH Autoresearch

This bundle executes in the user's agent workspace. The distribution host has no research execution or data authority.

## Start

1. Read `START_HERE.md` and `AGENTS.md` completely.
2. Read `shared/skills/frontier-autoresearch/SKILL.md`, `shared/skills/proportional-engineering/SKILL.md`, and `shared/skills/yh-memory/SKILL.md` completely before research actions.
3. Treat the user's target project or a user-approved run directory as the work root. Do not store run state in the installed skill directory.
4. Use the included `scripts/yh-ar.py` control plane when the client provides Python and filesystem execution. Otherwise preserve the same state, evidence, budget, approval, and transition contracts in client-supported artifacts.
5. Keep research state, memory, checkpoints, evaluator outputs, and artifacts on the user side.

Follow the included harness contract and role references. Never invent unavailable shell, filesystem, network, GPU, external-agent, or background execution capabilities.
