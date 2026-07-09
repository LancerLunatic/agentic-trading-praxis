# BRIEFING — 2026-07-08T20:38:00-04:00

## Mission
Remediate the four specific integrity violations identified during the Forensic Audit.

## 🔒 My Identity
- Archetype: worker
- Roles: implementer, qa, specialist
- Working directory: c:/Users/apoll/Documents/agentic-trading-praxis/.agents/worker_remediation
- Original parent: 18cdffbe-5044-414c-b1c2-b9fc246c1c2d
- Milestone: integrity_remediation

## 🔒 Key Constraints
- CODE_ONLY network mode (no external web access, no curl/wget, etc.)
- Do not cheat (no hardcoded test results, expected outputs, or verification strings in source code)
- Maintain real state and produce real behavior
- Scale verification effort; run pytest and simulation

## Current Parent
- Conversation ID: 18cdffbe-5044-414c-b1c2-b9fc246c1c2d
- Updated: not yet

## Task Summary
- **What to build**: Remediate: 1) Dynamic Candidate Selection of 75/90+ equities, 2) Options chains for all 75 screened candidates, 3) Empty initial portfolio inventory, 4) Execute liquidations first in executor even if user_approved is False.
- **Success criteria**: All pytests pass, simulation.py runs cleanly without exception, and correct dynamic option/liquidation logic is implemented.
- **Interface contracts**: c:/Users/apoll/Documents/agentic-trading-praxis/PROJECT.md or equivalent if present
- **Code layout**: Source in `agents/` and tests.

## Key Decisions Made
- Will check existing source code files to locate violations.

## Artifact Index
- c:/Users/apoll/Documents/agentic-trading-praxis/.agents/worker_remediation/handoff.md — Handoff report detailing remediation and verification results.

## Change Tracker
- **Files modified**: [TBD]
- **Build status**: [TBD]
- **Pending issues**: [TBD]

## Quality Status
- **Build/test result**: [TBD]
- **Lint status**: [TBD]
- **Tests added/modified**: [TBD]

## Loaded Skills
- **Source**: None
- **Local copy**: None
- **Core methodology**: None
