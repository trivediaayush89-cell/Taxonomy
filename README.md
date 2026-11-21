# Skill: Taxonomy Dispatcher

A high-performance, deterministic skill taxonomy indexer, gated lifecycle dispatcher, and complementary pod assembler for AI agent workspaces (such as Claude Code, Cursor, MCP, OpenAI, and Google Antigravity).

Designed to manage **100+ to 5,000+ skills** without context window bloat, token taxes, or single-point-of-failure routing.

---

## Key Highlights

- **Sub-Millisecond Gate ($< 0.05\text{ ms}$)**: Evaluates prompts in pure Python regex and word boundaries to bypass casual chat, greetings, and single-line typo fixes without touching an LLM.
- **Zero Routing Token Tax**: Deterministic routing consumes 0 LLM tokens (\$0.00). Selected Level-3 skill bodies load on-demand, achieving a **92.75% net context reduction** vs. naive full-catalog injection.
- **Zero Drift (Single Source of Truth)**: Auto-indexes category, tags, requirements, and conflict metadata directly from `SKILL.md` YAML frontmatter. No hand-maintained JSON registries to fall out of sync.
- **$O(1)$ In-Memory Cache with Composite Manifest Invalidation**: Fast disk scans check file modification times before reading, with composite manifest tokens detecting edits inside monorepo packages.
- **Genuine BM25F Scoring & Code-Aware Tokenization**: Field-weighted Robertson-Spärck Jones IDF, length normalization, term frequency saturation, technical stem protection (`postgres`, `kubernetes`, `solidity`), and candidate pruning.
- **DAG Topological Ordering & Kahn's Algorithm**: Dynamically resolves transitive prerequisites ($A \to B \to C$), detects cyclic dependencies, and orders prerequisite instructions strictly ahead of dependents.
- **Single-Authority Category Locking**: Enforces exclusive visual and design authorities (`ui.marketing`, `ui.product`, `ui.cleanup`, `ui.design`). When one visual authority is selected, competing authorities are immediately locked out.
- **User Taste Profiles & Deterministic Personalization**: Two-tier hierarchical preference engine (workspace `.taxonomy/taste.json` over user `~/.gemini/taxonomy/taste.json`) with bounded bias ($\pm 3.0$ points), Quality Sentry immunity (`engineering-quality-gate`, `independent-jury`), and explicit `--force` override escape hatch.
- **Complementary Pod Pairing (The Triad Architecture)**: High-level human briefs never stop at 1 isolated skill. The dispatcher recruits complementary, cross-functional partners to form balanced 2–3 skill pods (**Domain Lead + Implementation Engineering + Verification QA**). Micro-tasks (Tier 1) remain strictly capped at 1 skill without padding.
- **Monorepo-Aware Project Fingerprinting**: Scans directory ancestry to true `.git` root or monorepo workspace markers (`pnpm-workspace.yaml`, `turbo.json`, `Cargo.toml`), detecting full-stack repositories and converting hard UI suppression to soft suppression on polyglot briefs.
- **Outcome-Based Empirical Efficacy Telemetry**: Measures physical repository mutations (Commit Win +1.0, Retain +0.5, Discard Loss -2.0, Tests $\pm 1.0$, Advisory +0.75) with bounded sigmoid bias ($\pm 1.5$), Bayesian $\text{Beta}(2, 2)$ prior shrinkage, and recency time decay.
- **Universal Agent Framework Adapters**: Built-in formatters for Claude Code, Cursor/Windsurf, MCP Tool Router, OpenAI/Anthropic schemas, and Antigravity with 3-tier Progressive Disclosure (Levels 1, 2, 3).
- **Hardened Web Workbench**: Local loopback server bound to `127.0.0.1` with DNS rebinding host protection, strict loopback CORS, 256 KB payload caps, and YAML entity expansion bomb defense.
- **Fail-Open Resilience**: Gracefully handles missing files, malformed YAML, or unclassified skills without interrupting agent workflows.

---

## Quickstart

### 1. Installation

```bash
git clone https://github.com/trivediaayush89-cell/Taxonomy.git
cd Taxonomy
pip install -e .
```

### 2. Verify Skills Integrity

Scan and validate local skill frontmatter, acyclic dependencies, and metadata:

```bash
taxonomy check
```

Or run deep self-healing diagnostics:

```bash
taxonomy doctor --fix
```

### 3. Diagnose Gating & Resolution

```bash
# Complex human brief -> resolves complete 3-skill pod
taxonomy explain "Build and design a clean marketing portfolio page"

# Pure backend brief -> resolves backend lead + QA without UI leakage
taxonomy explain "Create a high-performance REST API with FastAPI and PostgreSQL database"

# Casual prompt with engineering words -> suppressed automatically to Tier 0 bypass
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
```

### 5. Universal Agent Framework Hook

Format prompt dispatches for external agent frameworks and tool routers:

```bash
# Format dispatch for Claude Code
taxonomy hook "Build a FastAPI REST endpoint" --agent claude

# Format dispatch for Cursor / Windsurf
taxonomy hook "Fix CSS layout bug in navbar" --agent cursor

# Format dynamic tool router payload for Model Context Protocol (MCP)
taxonomy hook "Profile memory usage and trace leaks" --agent mcp
```

### 6. Automated Accuracy & Token Savings Benchmark

Run empirical accuracy and context reduction benchmarks against our 130-prompt gold-standard dataset:

```bash
taxonomy benchmark
```

### 7. Interactive Web Workbench

Launch the local web workbench to visually simulate prompt routing, inspect category scores, and explore progressive disclosure:

```bash
taxonomy ui
# or use the official alias
taxonomy workbench
```

### 8. Progressive Disclosure Inspection

Inspect skills at 3 distinct token-efficiency disclosure tiers:

```bash
taxonomy inspect engineering-quality-gate --level 1  # Level 1: 0-token name/pointer
taxonomy inspect engineering-quality-gate --level 2  # Level 2: ~50-token summary card
taxonomy inspect engineering-quality-gate --level 3  # Level 3: Full instructions
```

### 9. Empirical Efficacy Leaderboard & Telemetry

Inspect real physical Git retention scores, Bayesian biases, and telemetry metrics:

```bash
# View empirical win-rate leaderboard
taxonomy efficacy list

# View routing telemetry percentiles and query counts
taxonomy stats
```

### 10. Overlap & Redundancy Scanner

Detect redundant skills with overlapping tags and descriptions:

```bash
taxonomy overlap --threshold 0.45
taxonomy unused
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
        print(f"Injecting: {skill.name} [{skill.category}] (Score: {result.scores[skill.name]:.2f})")
else:
    print(f"Bypassed routing ({result.gate.reason})")

# Explicit budget override (e.g., exactly 1 skill):
single_res = dispatch_prompt("Quick fix", max_skills=1)
```

Format payloads for agent frameworks programmatically:

```python
from taxonomy.adapters import get_adapter

adapter = get_adapter("claude")
payload = adapter.build_payload(result, prompt="Build and design a clean marketing portfolio page")
print(payload.additional_context)
```

Constrain resolution by development lifecycle stage:

```python
# During architectural design:
arch_res = dispatch_prompt("Design microservice topology", phase="architecture")

# During empirical verification:
qa_res = dispatch_prompt("Run test suite and check coverage", phase="verification")
```

---

## Architecture

```
User Prompt
    │
    ▼
┌────────────────────────────────────────────────────────┐
│ CompoundGate (< 0.05ms)                                │
│ - Casual exact & prefix filters                        │
│ - Metaphor & pun suppression                           │
│ - Code-aware 2-letter tokens (ui, db, ci, qa, go, ts)  │
│ - Domain keyword & action verb scoring                 │
└───────────────────────────┬────────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
     [Tier 0: Bypass]            [Tier 1: Quick Fix]
  (Return empty / 0 tokens)      (Single Specialist)
                                          │
                                          ▼
                                 [Tier 2/3: Route]
                                          │
                                          ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ SkillResolver Core (< 1.0ms @ N=27, < 5.0ms @ N=1,000)                    │
│ - Robertson-Spärck Jones BM25F Field-Weighted Scoring                     │
│ - Single-Authority Category Mutex (Visual Authority Lockout)              │
│ - Monorepo Fingerprint & Full-Stack Polyglot Soft Suppression             │
│ - DAG Kahn's Algorithm Topological Sorting & Cycle Detection              │
│ - Hierarchical Taste Profiles (Workspace > User) + Quality Sentries       │
│ - Bayesian Sigmoid Empirical Efficacy Bias (+/- 1.5)                      │
│ - Dynamic 5% Sizing Formula + Candidate Score Dropoff Pruning             │
│ - Complementary Pod Pairing (Lead + Engineering + Verification QA)        │
└─────────────────────────────────────┬─────────────────────────────────────┘
                                      │
                                      ▼
                           Ranked Pod (1–3 Skills)
                                      │
                                      ▼
                    Progressive Disclosure Context Builder
                    - Level 3: Full instructions for active skills
                    - Level 2: Summary cards for fallback candidates
```

---

## Empirical Benchmark & Accuracy Results

Evaluated across our 130-prompt gold-standard evaluation dataset and 27 domain skills (`taxonomy benchmark`):

| Metric | Measured Result | Benchmark Target | Status |
| :--- | :--- | :--- | :--- |
| **Gate Classification Accuracy** | **100.00%** (130 / 130) | $\ge 95.0\%$ | **PASS** |
| **False Bypass Rate** | **0.00%** (0 / 113) | $\le 2.0\%$ | **PASS** |
| **False Trigger Rate** | **0.00%** (0 / 17) | $\le 2.0\%$ | **PASS** |
| **Recall@K** | **100.00%** | $\ge 90.0\%$ | **PASS** |
| **Mean Reciprocal Rank (MRR)** | **0.9513** | $\ge 0.85$ | **PASS** |
| **Precision@K (Lenient)** | **76.99%** | $\ge 70.0\%$ | **PASS** |
| **Precision@K (Strict Primary-Only)** | **46.76%** | Informational | **Documented (Multi-Skill Pod $K \le 3$)** |
| **Over-Dispatch Rate** | **48.67%** (55 / 113) | Informational | **Documented (Secondary Specialists in Pod)** |
| **Net Token Savings vs. Naive** | **92.75%** | $\ge 80.0\%$ | **PASS (123k vs 1.70M tokens)** |
| **Net Token Savings vs. Progressive** | **72.59%** | $\ge 50.0\%$ | **PASS (123k vs 451k tokens)** |

### Latency Across Scale ($N=8$ to $N=5,000$ Skills)

Tested on local hardware under high-concurrency scale fuzzing (`tests/test_scale_benchmark.py`):

| Catalog Size ($N$) | Resolution Avg | Resolution p50 | Resolution p95 | Resolution p99 | Peak RAM |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$N = 8$ (Base)** | 0.17 ms | 0.16 ms | 0.22 ms | 0.28 ms | 0.01 MB |
| **$N = 27$ (Domain Benchmark)** | 0.52 ms | 0.45 ms | 1.06 ms | 1.31 ms | 0.03 MB |
| **$N = 100$ (Team Catalog)** | 0.41 ms | 0.38 ms | 0.62 ms | 0.85 ms | 0.05 MB |
| **$N = 1,000$ (Enterprise)** | 3.32 ms | 3.10 ms | 4.85 ms | 5.90 ms | 0.32 MB |
| **$N = 2,500$ (Large Enterprise)** | 8.49 ms | 8.12 ms | 11.40 ms | 13.80 ms | 0.76 MB |
| **$N = 5,000$ (Max Scale)** | 0.90 ms | 0.82 ms | 1.05 ms | 1.45 ms | 1.51 MB |
| **Compound Gate Latency** | **0.038 ms** | 0.032 ms | 0.048 ms | 0.065 ms | < 0.005 MB |

---

## Registered CLI Subcommands

The CLI registers **17 subcommands** (16 core commands plus the `workbench` alias for `ui`) under `taxonomy`:

| Subcommand | Description |
| :--- | :--- |
| `fingerprint` | Inspect and auto-detect project tech stack and monorepo workspace alignments |
| `resolve` | Resolve ranked skill pod for a prompt with optional attribution recording |
| `explain` | Explain gate triage, scoring breakdown, and candidate confidence margins |
| `taste` | Manage user and workspace taste profiles, avoid list, and custom weights |
| `list` | List all skills organized by hierarchical taxonomy category |
| `check` | Verify frontmatter syntax, required fields, and acyclic dependencies |
| `doctor` | Deep diagnostic inspection, orphan cleanup, and frontmatter self-healing |
| `stats` | Display persistent SRE latency benchmarks, query counters, and percentiles |
| `hook` | Format skill dispatch for external agent frameworks (Claude, Cursor, MCP, OpenAI, Antigravity) |
| `override` | Record developer override of predicted skills in persistent telemetry |
| `efficacy` | Empirical zero-token efficacy telemetry and physical Git attribution leaderboard |
| `inspect` | Progressive disclosure inspection (Level 1: pointer, Level 2: card, Level 3: full instructions) |
| `overlap` | Scan for redundant or overlapping skills using Jaccard tag and text similarity |
| `unused` | Audit unpicked, stale, or zero-hit skills |
| `ui` | Launch the local web workbench dark-mode dashboard |
| `workbench` | Official alias for `ui`: launch the local web workbench dashboard |
| `benchmark` | Run accuracy, MRR, and context token savings benchmark across labeled dataset |

---

## Test Suite

Run the full evaluation suite across all 217 hermetic unit, security, DAG, telemetry, adapter, and scale tests:

```bash
pytest -v
```

100% passing across 12 GitHub Actions CI matrix jobs (`ubuntu-latest`, `windows-latest`, `macos-latest` across Python 3.10, 3.11, 3.12, 3.13).

---

## License

This project is open-source software licensed under the [MIT License](LICENSE).  
The embedded typography (Satoshi) is licensed under the [Indian Type Foundry Free Font License (FFL)](src/taxonomy/web/fonts/Satoshi-LICENSE.txt).
