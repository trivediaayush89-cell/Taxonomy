# Skill: Taxonomy Dispatcher

A high-performance, deterministic skill taxonomy indexer, gated lifecycle dispatcher, and complementary pod assembler for AI agent workspaces (such as Google Antigravity).

Designed to manage **100+ skills** without context window bloat, token taxes, or single-point-of-failure routing.

---

## Key Highlights

- **Sub-Millisecond Gate ($< 0.02\text{ms}$)**: Evaluates prompts in pure Python regex and word boundaries to bypass casual chat, greetings, and single-line typo fixes without touching an LLM.
- **Zero Token Tax**: Bypasses routine conversation without burning context window tokens on routing meta-prompts.
- **Zero Drift (Single Source of Truth)**: Auto-indexes category and tag metadata directly from `SKILL.md` YAML frontmatter. No hand-maintained JSON registries to fall out of sync.
- **$O(1)$ In-Memory Cache with `mtime` Invalidation**: Fast disk scans check file modification times before reading, keeping warm scans under a few milliseconds.
- **Zero-Config Project Fingerprinting**: Sub-millisecond ($< 0.5\text{ms}$) deterministic stack scanner detecting Next.js, React, Tailwind, TypeScript, Python (FastAPI/Django/Flask/Pytest), Foundry/Solidity, Rust, Go, and Docker. Automatically aligns framework preferences beneath user/workspace configurations without token cost or manual setup.
- **Dynamic 5% Sizing Formula**: Scales resolution budget dynamically: $\min(5, \max(3, \lceil 0.05 \times N \rceil))$. Standard catalogs up to 60 skills budget 3 skills; 80 skills budget 4; 100+ skill enterprise catalogs budget up to 5 skills. Explicit caller overrides (`max_skills=1` or `2`) remain strictly respected.
- **User Taste Profiles & Deterministic Personalization**: Two-tier hierarchical preference engine (workspace `.taxonomy/taste.json` over user `~/.gemini/taxonomy/taste.json`) with bounded additive bias ($\pm 3.0$ points), zero token cost, $<0.05\text{ms}$ in-memory cached latency, and Quality Sentry immunity.
- **Complementary Pod Pairing (The Triad Architecture)**: High-level human briefs never stop at 1 isolated skill. The dispatcher recruits complementary, cross-functional partners to form balanced 2–3 skill pods (**Domain Lead + Implementation Engineering + Verification QA**).
- **Strict Negative Selection & Mutual Exclusion**: Automatically enforces mutual exclusion rings (e.g., visual styling authorities) and suppresses all UI/frontend skills on pure backend, database, and smart contract briefs.
- **Curated Community Taste Presets & Export/Import**: Pre-configured archetypes (`minimalist-backend`, `solidity-auditor`, `design-heavy-frontend`, `product-saas-builder`, `strict-qa-sre`) with 1-click import/export supporting both JSON and YAML. Preserves Judicial Quality Sentry immunity (`engineering-quality-gate` cannot be downvoted or avoided).
- **Interactive Command Workbench & Taste UI**: Embedded monochromatic web dashboard (`taxonomy ui`) with real-time prompt triage simulation, zero-token project stack detection, interactive skill bias sliders ($-3.0$ to $+3.0$), category authority dropdowns, and 1-click persistence to workspace (`.taxonomy/taste.json`) or global user (`~/.gemini/taxonomy/taste.json`).
- **Fail-Open Resilience**: Gracefully handles missing files, malformed YAML, or unclassified skills without interrupting agent workflows.

---

## Quickstart

### 1. Installation

```bash
git clone https://github.com/<your-username>/skill-taxonomy-dispatcher.git
cd skill-taxonomy-dispatcher
pip install -e .
```

### 2. Verify Skills Integrity

Scan and validate local skill frontmatter, acyclic dependencies, and metadata:

```bash
taxonomy check
```

Or target specific directories:

```bash
taxonomy check --skills-dir path/to/skills
```

### 3. Diagnose Gating & Resolution

```bash
# Complex human brief -> resolves complete 3-skill pod
taxonomy explain "Build and design a clean marketing portfolio page"

# Pure backend brief -> resolves backend lead + QA without UI leakage
taxonomy explain "Create a high-performance REST API with FastAPI and PostgreSQL database"

# Casual prompt with engineering words -> suppressed automatically
taxonomy explain "How do I build a habit of reading code every morning?"
```

### 4. User Taste Profiles & Deterministic Preferences

Personalize skill dispatching using a declarative, zero-token, bounded preference engine:

```bash
# List active hierarchical taste preferences and loaded sources
taxonomy taste list

# Prefer a skill for a category (e.g. UI visual authority)
taxonomy taste set frontend.visual impeccable

# Assign bounded custom weight (-3.0 to +3.0)
taxonomy taste set impeccable 3.0

# Avoid a skill (-3.0 bias)
taxonomy taste avoid unslop

# Ad-hoc one-off preference override via CLI
taxonomy resolve "Build modern pricing card component" --prefer impeccable

# Explain scoring breakdown including lexical, category, and taste bias
taxonomy explain "Build modern pricing card component" --prefer impeccable

# List curated community taste presets
taxonomy taste presets

# 1-click apply a curated preset (e.g. minimalist-backend, solidity-auditor, strict-qa-sre)
taxonomy taste import minimalist-backend

# Export taste profile to stdout or file (JSON or YAML)
taxonomy taste export --yaml
taxonomy taste export profile.yaml --workspace

# Import custom taste profile from file with Quality Sentry immunity
taxonomy taste import profile.yaml --force
```

### 5. Zero-Config Project Fingerprinting

Inspect and detect local project frameworks and auto-aligned skill recommendations:

```bash
# View detected stack and recommended skills
taxonomy fingerprint

# Output raw JSON diagnostics
taxonomy fingerprint --json

# Persist detected recommendations into .taxonomy/taste.json
taxonomy fingerprint --apply
```

### 6. Interactive Web Workbench & Taste UI

Launch the local web workbench to tune taste profiles with visual sliders, apply auto-detected stack recommendations, and simulate prompt triage in real time:

```bash
# Launch on default port 8765
taxonomy ui

# Launch on custom port without opening default browser
taxonomy ui --port 9000 --no-open
```

**Built-In Workbench REST API**:
- `GET /api/taste`: Read active hierarchical taste profile, workspace, user, and detected stack.
- `POST /api/taste`: Persist tuned preferences, avoidances, and weights directly to `.taxonomy/taste.json` or `~/.gemini/taxonomy/taste.json`.
- `GET /api/presets`: Retrieve curated community taste presets (`minimalist-backend`, `solidity-auditor`, `design-heavy-frontend`, `product-saas-builder`, `strict-qa-sre`).
- `POST /api/presets/apply`: 1-click apply a domain preset to workspace or user scope.
- `GET /api/taste/export`: Export taste profile formatted in JSON or YAML.
- `POST /api/taste/import`: Import JSON/YAML profile or community preset with Quality Sentry immunity invariants.
- `GET /api/fingerprint`: Inspect detected project ecosystems, manifests, and pod recommendations.
- `POST /api/fingerprint/apply`: 1-click persist detected stack recommendations into workspace taste.
- `POST /api/resolve`: Real-time backend resolver evaluation with latency metrics.

### 7. Overlap & Redundancy Scanner

Detect redundant skills with overlapping tags and descriptions:

```bash
taxonomy overlap --threshold 0.45
```

### 8. Stale & Unused Skill Audit

Track usage frequency and flag skills with zero hits:

```bash
taxonomy unused
```

### 9. Progressive Disclosure Inspection

Inspect skills at 3 distinct token-efficiency disclosure tiers:

```bash
taxonomy inspect independent-jury --level 1  # Level 1: 0-token pointer
taxonomy inspect independent-jury --level 2  # Level 2: ~50-token summary card
taxonomy inspect independent-jury --level 3  # Level 3: Full instructions
```

---

## In-Process Python Integration

Call the dispatcher directly inside orchestrators (e.g., `development-director` or custom agent workflows):

```python
from taxonomy.hook import dispatch_prompt

# Dynamic 5% pod sizing (default):
result = dispatch_prompt("Build and design a clean marketing portfolio page")

if result.gate.should_route:
    for skill in result.selected_skills:
        print(f"Injecting: {skill.name} [{skill.category}] from {skill.path}")
else:
    print(f"Bypassed routing ({result.gate.reason})")

# Explicit budget override (e.g., exactly 1 skill):
single_res = dispatch_prompt("Quick fix", max_skills=1)
```

---

## Architecture

```
User Prompt
    │
    ▼
┌────────────────────────────────────────────────────────┐
│ CompoundGate (< 0.02ms)                                │
│ - Casual exact & prefix filters                        │
│ - Metaphor & pun suppression                           │
│ - Domain keyword & action verb scoring                 │
└───────────────────────────┬────────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
     [Tier 0/1: Bypass]          [Tier 2/3: Route]
  (Return empty / 0 tokens)               │
                                          ▼
                                ┌──────────────────────────────────────────────┐
                                │ SkillResolver                                │
                                │ - Frontmatter Tag & Category Scoring         │
                                │ - Domain Negative Selection (UI lockout)     │
                                │ - Conflict Ring & Dependency Enforcement     │
                                │ - Dynamic 5% Sizing: min(5, max(3, 0.05*N))  │
                                │ - Complementary Pod Pairing (Triad)          │
                                └──────────────────────┬───────────────────────┘
                                                       │
                                                       ▼
                                            Selected Pod (2–3 Skills)
                                            1. Domain Lead Specialist
                                            2. Implementation Partner
                                            3. Verification & QA Partner
```

---

## Benchmark & SRE Performance (1,000 Mock Skills)

Tested on Windows NTFS under high-concurrency scale fuzzing (`tests/test_scale_benchmark.py`):

| Metric | Result | Target / SLA | Status |
| :--- | :--- | :--- | :--- |
| **Cold Scan (1,000 Skills)** | **674 ms** | $< 2,000\text{ms}$ | **PASS (Parallel ThreadPool)** |
| **Warm Scan (1,000 Skills)** | **43.9 ms** | $< 100\text{ms}$ | **PASS (mtime Invalidation)** |
| **p50 Resolution Latency** | **6.08 ms** | $< 10\text{ms}$ | **PASS** |
| **p95 Resolution Latency** | **6.57 ms** | $< 12\text{ms}$ | **PASS** |
| **p99 Resolution Latency** | **7.08 ms** | $< 15\text{ms}$ | **PASS (2x Safety Margin)** |
| **Compound Gate Latency** | **0.013 ms** | $< 1.0\text{ms}$ | **PASS (70x Margin)** |

---

## Phase-Aware Orchestration Lifecycle

Orchestrators can constrain resolution by development lifecycle stage:

```python
from taxonomy.hook import dispatch_prompt

# During architectural design:
arch_res = dispatch_prompt(prompt, phase="architecture")

# During empirical verification:
qa_res = dispatch_prompt(prompt, phase="verification")

# During adversarial courtroom trial:
jury_res = dispatch_prompt(prompt, phase="review")
```

---

## Test Suite

Run the full evaluation suite across all 79 unit, security, DAG, telemetry, pod resolution, fingerprinting, curated presets, and scale tests:

```bash
pytest -v
```

```text
tests/test_checkpoint_audit.py ........                                  [ 10%]
tests/test_cli_ui.py ...                                                 [ 13%]
tests/test_conflicts_and_disclosure.py ...                               [ 17%]
tests/test_dag.py ...                                                    [ 21%]
tests/test_doctor.py .                                                   [ 22%]
tests/test_eval_suite.py ......                                          [ 30%]
tests/test_fingerprint.py .......                                        [ 39%]
tests/test_hook.py ..                                                    [ 41%]
tests/test_overlap.py ..                                                 [ 44%]
tests/test_phase_aware.py .                                              [ 45%]
tests/test_pod_resolution.py .......                                     [ 54%]
tests/test_presets_export_import.py .........                            [ 65%]
tests/test_scale_benchmark.py ..                                         [ 68%]
tests/test_security.py .....                                             [ 74%]
tests/test_semantic_gate.py ...                                          [ 78%]
tests/test_taste.py ..............                                       [ 96%]
tests/test_telemetry.py ..                                               [ 98%]
tests/test_tracker.py .                                                  [100%]

============================= 79 passed in 15.02s =============================
```

---

## License

This project is open-source software licensed under the [MIT License](LICENSE).  
The embedded typography (Satoshi) is licensed under the [Indian Type Foundry Free Font License (FFL)](src/taxonomy/web/fonts/Satoshi-LICENSE.txt).
