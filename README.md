# Skill Taxonomy Dispatcher

A high-performance, deterministic skill taxonomy indexer, gated lifecycle dispatcher, and complementary pod assembler for AI agent workspaces (such as Google Antigravity).

Designed to manage **100+ skills** without context window bloat, token taxes, or single-point-of-failure routing.

---

## Key Highlights

- **Sub-Millisecond Gate ($< 0.02\text{ms}$)**: Evaluates prompts in pure Python regex and word boundaries to bypass casual chat, greetings, and single-line typo fixes without touching an LLM.
- **Zero Token Tax**: Bypasses routine conversation without burning context window tokens on routing meta-prompts.
- **Zero Drift (Single Source of Truth)**: Auto-indexes category and tag metadata directly from `SKILL.md` YAML frontmatter. No hand-maintained JSON registries to fall out of sync.
- **$O(1)$ In-Memory Cache with `mtime` Invalidation**: Fast disk scans check file modification times before reading, keeping warm scans under a few milliseconds.
- **Dynamic 5% Sizing Formula**: Scales resolution budget dynamically: $\min(5, \max(3, \lceil 0.05 \times N \rceil))$. Standard catalogs up to 60 skills budget 3 skills; 80 skills budget 4; 100+ skill enterprise catalogs budget up to 5 skills. Explicit caller overrides (`max_skills=1` or `2`) remain strictly respected.
- **Complementary Pod Pairing (The Triad Architecture)**: High-level human briefs never stop at 1 isolated skill. The dispatcher recruits complementary, cross-functional partners to form balanced 2–3 skill pods (**Domain Lead + Implementation Engineering + Verification QA**).
- **Strict Negative Selection & Mutual Exclusion**: Automatically enforces mutual exclusion rings (e.g., visual styling authorities) and suppresses all UI/frontend skills on pure backend, database, and smart contract briefs.
- **Interactive Command Workbench**: Embedded monochromatic UI for visual simulation, latency auditing, and progressive disclosure exploration (`taxonomy ui`).
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

### 4. Interactive Web Workbench

Launch the local web workbench to visually simulate prompt routing, inspect category scores, and explore progressive disclosure:

```bash
taxonomy ui
```

### 5. Overlap & Redundancy Scanner

Detect redundant skills with overlapping tags and descriptions:

```bash
taxonomy overlap --threshold 0.45
```

### 6. Stale & Unused Skill Audit

Track usage frequency and flag skills with zero hits:

```bash
taxonomy unused
```

### 7. Progressive Disclosure Inspection

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

Run the full evaluation suite across all 47 unit, security, DAG, telemetry, pod resolution, and scale tests:

```bash
pytest -v
```

```text
tests/test_checkpoint_audit.py ........                                  [ 17%]
tests/test_cli_ui.py ..                                                  [ 21%]
tests/test_conflicts_and_disclosure.py ...                               [ 27%]
tests/test_dag.py ...                                                    [ 34%]
tests/test_doctor.py .                                                   [ 36%]
tests/test_eval_suite.py ......                                          [ 48%]
tests/test_hook.py ..                                                    [ 53%]
tests/test_overlap.py ..                                                 [ 57%]
tests/test_phase_aware.py .                                              [ 59%]
tests/test_pod_resolution.py .......                                     [ 74%]
tests/test_scale_benchmark.py ..                                         [ 78%]
tests/test_security.py ....                                              [ 87%]
tests/test_semantic_gate.py ...                                          [ 93%]
tests/test_telemetry.py ..                                               [ 97%]
tests/test_tracker.py .                                                  [100%]

============================= 47 passed in 3.57s ==============================
```

---

## License

This project is open-source software licensed under the [MIT License](LICENSE).  
The embedded typography (Satoshi) is licensed under the [Indian Type Foundry Free Font License (FFL)](src/taxonomy/web/fonts/Satoshi-LICENSE.txt).
