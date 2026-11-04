# Skill Taxonomy Dispatcher: Architecture Dossier, Dual-Court Trial Transcripts & Personalization Specification

> **Document Version**: `v1.0.0`  
> **Date**: November 4, 2026  
> **Target Repository**: [`trivediaayush89-cell/skill-taxonomy-dispatcher`](https://github.com/trivediaayush89-cell/skill-taxonomy-dispatcher)  
> **Status**: APPROVED FOR STAGE 1 IMPLEMENTATION (Conditional Judicial Clearance)  
> **Purpose**: Self-contained handover dossier for starting a fresh conversation context with zero token drag, preserving 100% of historical context, architecture rationale, juror deliberations, and technical specifications.

---

## TABLE OF CONTENTS
1. [Part 1: What is Skill Taxonomy Dispatcher? (Foundations & Architecture)](#part-1-what-is-skill-taxonomy-dispatcher-foundations--architecture)
   - 1.1 The Core Problem in Modern AI Agent Workspaces
   - 1.2 Purpose, Philosophy & Invariants
   - 1.3 Subsystem Architecture & How It Functions
   - 1.4 The Three Judge Guardrails
   - 1.5 Testing, Empirical Quality Gate & GitHub Release
2. [Part 2: The New Feature Proposal: User Taste Profiles & Adaptive Personalization](#part-2-the-new-feature-proposal-user-taste-profiles--adaptive-personalization)
   - 2.1 The User's Core Insight & Original Proposal
   - 2.2 The Dual-Mode Proposal (Mode A vs Mode B)
   - 2.3 The Core Architectural Tension & Dilemmas
3. [Part 3: The Complete Dual-Courtroom Trial (24 Juror Transcripts)](#part-3-the-complete-dual-courtroom-trial-24-juror-transcripts)
   - 3.1 Case Docket & The Charge
   - 3.2 Adversarial Duel: Prosecution vs Defense
   - 3.3 Courtroom 1: Technical Panel (12 Juror Deliberations & Ballots)
   - 3.4 Courtroom 2: Cross-Field Panel (12 Juror Deliberations & Ballots)
   - 3.5 Voting Matrix & Comparative Analysis
4. [Part 4: The Approved Architectural Synthesis & Solution Blueprint](#part-4-the-approved-architectural-synthesis--solution-blueprint)
   - 4.1 What Was Strictly Rejected (And Why)
   - 4.2 What Was Approved for Implementation
   - 4.3 Two-Tier Hierarchical Configuration Architecture
   - 4.4 Deterministic Taste Biasing Formula & Mathematical Invariants
   - 4.5 Explicit Feedback Mechanism & CLI Interface
5. [Part 5: Fresh Chat Handover & Implementation Roadmap](#part-5-fresh-chat-handover--implementation-roadmap)
   - 5.1 File Changes Required
   - 5.2 Step-by-Step Implementation Sequence
   - 5.3 Verification Checklist for the New Session

---

# PART 1: WHAT IS SKILL TAXONOMY DISPATCHER? (FOUNDATIONS & ARCHITECTURE)

## 1.1 The Core Problem in Modern AI Agent Workspaces
In modern agentic software development operating systems (such as **Google Antigravity / AI Dev OS**), developers install specialized instruction bundles called **Skills** (e.g., `frontend-ui-engineering`, `impeccable`, `design-taste-frontend`, `engineering-quality-gate`, `smart-contract-auditor`, `unslop`, etc.). 

As catalogs grow from 10 to 50, 100, or 1,000+ skills:
1. **Context Window Flooding**: Injecting every skill's full instructions into the LLM system prompt consumes 30,000 to 100,000+ tokens before the user has even typed a single character. This causes severe latency degradation, exponential API cost, and prompt dilution ("needle-in-a-haystack" confusion).
2. **Instruction Dogma Collisions**: Multiple skills often claim authority over the same surface. For example, three different UI design skills might issue conflicting mandates regarding color palettes, font systems, animation counts, and border hairlines. When all are loaded simultaneously, the agent oscillates, producing incoherence or "AI slop."
3. **Domain Leakage**: Frontend skills are frequently activated on pure backend, systems programming, smart contract, or CLI tasks, cluttering the agent's attention with CSS guidelines when writing SQL migrations or Rust parsers.
4. **The LLM Routing Tax**: Naive solutions use a secondary LLM call to decide which skills to activate. This introduces 1,500–3,000ms of latency, costs inference money on every turn, and is inherently non-deterministic.

## 1.2 Purpose, Philosophy & Invariants
**`skill-taxonomy-dispatcher`** was created to be the ultra-fast, deterministic, zero-token router that completely solves this problem.

### Core Philosophy:
* **Sub-Millisecond Execution**: Route any prompt across 1,000+ skills in $<2\text{ms}$ (p50: 1.73ms, p99: 1.85ms).
* **Zero Token Waste**: Zero LLM calls, zero embeddings, zero API costs during routing. Runs entirely via optimized local Python algorithms.
* **Deterministic Hermeticism**: The same `(prompt, catalog)` input always yields the exact same skill pod.
* **Cooperative Pod Triad**: Selects balanced, mutually supporting teams of skills rather than isolated individuals.
* **Strict Negative Selection**: Proactively locks out competing and irrelevant skills.

---

## 1.3 Subsystem Architecture & How It Functions

```
                                  USER PROMPT
                                       │
                                       ▼
                     ┌───────────────────────────────────┐
                     │     1. FAST TRIAGE GATE (<0.1ms)   │
                     │  (gate.py & semantic_gate.py)     │
                     └─────────────────┬─────────────────┘
                                       │
                 ┌─────────────────────┴─────────────────────┐
                 │                                           │
         [TRIVIAL / CASUAL]                         [CONSEQUENTIAL TASK]
                 │                                           │
                 ▼                                           ▼
          BYPASS ROUTING                            ┌─────────────────┐
        (0 Skills Injected)                         │ 2. SKILL INDEXER│
                                                    │  (indexer.py)   │
                                                    └────────┬────────┘
                                                             │
                                                             ▼
                                                    ┌─────────────────┐
                                                    │   3. RESOLVER   │
                                                    │  (resolver.py)  │
                                                    └────────┬────────┘
                                                             │
                                ┌────────────────────────────┼────────────────────────────┐
                                ▼                            ▼                            ▼
                        GUARDRAIL 1                  GUARDRAIL 2                  GUARDRAIL 3
                     Dynamic 5% Sizing             Complementary Pod            Negative Selection
                    (Min 3, Max 5 Skills)          Triad Architecture           & Mutual Exclusion
                                │                            │                            │
                                └────────────────────────────┼────────────────────────────┘
                                                             │
                                                             ▼
                                                    ┌─────────────────┐
                                                    │  4. DAG SORTER  │
                                                    │    (dag.py)     │
                                                    └────────┬────────┘
                                                             │
                                                             ▼
                                                 FINAL COMPLEMENTARY POD
                                              (e.g., Visual + Eng + Quality)
```

### The Component Pipeline:
1. **Fast Triage Gate (`gate.py` & `semantic_gate.py`)**:
   - Executes in $<0.05\text{ms}$.
   - Classifies prompts into:
     - `SKIP`: Casual greetings, generic questions, single-line math. Injects 0 skills.
     - `LIGHTWEIGHT`: Isolated, single-file edits. Injects 1 targeted skill.
     - `COURTROOM / COMPLEX`: Consequential feature builds or multi-file changes. Initiates full pod resolution.
   - Includes a high-speed semantic fallback gate that detects subtle high-stakes prompts (e.g., reentrancy exploits, UI race conditions) without false-positive inflation.

2. **Mtime-Cached Skill Indexer (`indexer.py`)**:
   - Scans designated skill roots:
     - Workspace skills: `<workspace>/.gemini/skills` or `<workspace>/.agents/skills`
     - Global built-in skills: `~/.gemini/antigravity/builtin/skills`
     - Global config skills: `~/.gemini/config/skills`
   - Parses YAML frontmatter (`name`, `description`, `category`, `tags`, `requires`, `conflicts_with`, `priority`, `phase`).
   - Uses an in-memory `mtime` (modified time) cache. Cold scans 1,000 skills in $<950\text{ms}$; warm scans execute in $<13\text{ms}$.

3. **Relevance Scoring Engine (`resolver.py`)**:
   - Combines BM25-style term frequency matching on prompt tokens with:
     - Exact phrase matching bonuses
     - Category alignment weights
     - Skill priority base weights
     - Negative domain suppression (e.g., pure backend prompts zero out visual/styling candidates).

4. **Directed Acyclic Graph (`DAG`) Engine (`dag.py`)**:
   - Resolves transitive `requires` dependencies.
   - Detects and prevents circular dependency loops (e.g., Skill A requires B, B requires A) and self-loops using topological sorting.

5. **Security Sandbox Containment (`security.py`)**:
   - Protects against malicious skill names and path traversal attacks (`../../Windows/System32`, `/etc/passwd`).
   - Hardened for cross-platform isolation: blocks POSIX root escapes on Linux/macOS and drive-letter escapes on Windows.
   - Rejects null-byte injections.

6. **Telemetry & Self-Healing Diagnostics (`telemetry.py`, `tracker.py`, `cli.py`)**:
   - Records hit frequencies, resolution latency distributions (p50, p95, p99), and identifies stale/dead skills.
   - `taxonomy doctor`: CLI linter that audits skill frontmatters against the official JSON schema (`schemas/skill.schema.json`) and automatically heals missing fields.

7. **Interactive Web Workbench (`src/taxonomy/web/index.html`)**:
   - Standalone browser tool that embeds the entire skill catalog with zero external CDN dependencies.
   - Includes a radar chart visualizer, live prompt simulator, interactive pod resolution viewer, and typography crafted with Satoshi font.
   - Dark theme styling: Base background `#070708`, floating box cards in `#0C0D0D`, bordered with a mere `1px solid #0a0e16` inward blur glow.

---

## 1.4 The Three Judge Guardrails

During the Stage 1 Architectural Courtroom review of the dispatcher itself, the judicial verdict mandated three non-negotiable guardrails:

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                             THE THREE JUDICIAL GUARDRAILS                                │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ GUARDRAIL 1: Dynamic 5% Sizing Formula                                                   │
│   Math: K = min(5, max(3, ceil(0.05 * N)))                                               │
│   Guarantees that skill pods scale smoothly from 3 to 5 skills as the catalog grows:    │
│   • 0–60 Skills   → Exactly 3 Skills (The Triad)                                        │
│   • 61–80 Skills  → Exactly 4 Skills                                                    │
│   • 100+ Skills   → Clamped strictly at 5 Skills (protects token budget)                │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ GUARDRAIL 2: Complementary Pod Pairing (The Triad Architecture)                          │
│   A balanced engineering pod must never consist solely of redundant specialists.        │
│   It automatically assembles a 3-role triad:                                             │
│   1. Primary Authority (e.g., design-taste-frontend for visual direction)               │
│   2. Engineering Specialist (e.g., frontend-ui-engineering for component state/a11y)   │
│   3. Quality Sentry (e.g., engineering-quality-gate for empirical verification)         │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ GUARDRAIL 3: Strict Negative Selection & Mutual Exclusion                                │
│   1. Conflict A Exclusion: Only ONE visual authority per surface. Resolving               │
│      'design-taste-frontend' strictly locks out 'impeccable', 'unslop', and              │
│      'frontend-design'.                                                                  │
│   2. Domain Isolation: Pure backend prompts strictly suppress UI/styling skills.         │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1.5 Testing, Empirical Quality Gate & GitHub Release
* **Comprehensive Test Suite**: 48 automated tests in `tests/`:
  - `test_scale_benchmark.py`: Proves 1,000 skills resolve in $<1.85\text{ms}$ (passing the $<15\text{ms}$ SLA).
  - `test_dag.py`: Verifies topological sort and circular dependency detection.
  - `test_pod_resolution.py`: Verifies the 5% sizing math, triad pairing, and conflict exclusion.
  - `test_security.py`: Cross-platform traversal containment.
  - `test_checkpoint_audit.py`: Multi-root precedence, case collisions, and live routing matrices.
* **CI Quality Gate**: GitHub Actions workflow (`.github/workflows/ci.yml`) runs across a 12-job matrix (Python 3.10, 3.11, 3.12, 3.13 on Ubuntu, macOS, and Windows). **Result: 12 / 12 PASS (100% Green)**.
* **Live Open-Source Repository**: Published at `https://github.com/trivediaayush89-cell/skill-taxonomy-dispatcher` under the MIT License.

---

# PART 2: THE NEW FEATURE PROPOSAL: USER TASTE PROFILES & ADAPTIVE PERSONALIZATION

## 2.1 The User's Core Insight & Original Proposal
The user observed a key limitation in v0.1.0:
> *"Suppose I have 10 skills for UI building. Taxonomy chooses 2–3. But how? Currently, the chosen skills are selected based purely on lexical/category algorithms, and the personal preferences of the user are not being considered. What if it had a 'taste profile' of the user?
>
> The user could either set it themselves (choose the skills they want invoked every time), or if they don't choose, let the skill itself develop habits from the user by giving random skills, noting which feature the user likes and dislikes, finding which skill built the liked feature, and placing it on a higher priority level. Over time, it will learn what the user likes to build and which skills help more."*

## 2.2 The Dual-Mode Proposal (Mode A vs Mode B)
* **Mode A: Explicit Taste Profile**:
  - The developer defines a declarative preference profile (e.g. *"For UI tasks, always prefer `impeccable` over `design-taste-frontend`"*, or *"For backend, always prefer `fastapi` over `flask`"*).
  - The dispatcher reads this profile and boosts the preferred skills during routing.
* **Mode B: Implicit Autonomous Exploration & Attribution Learning Loop**:
  - The dispatcher employs an $\epsilon$-greedy exploration policy (occasionally injecting random alternative skills into the pod).
  - It observes user sentiment / reactions to generated code (likes, dislikes, accepted diffs).
  - It performs **credit attribution**: determines which skill was responsible for the liked/disliked feature.
  - It dynamically mutates skill priority weights in background storage so preferred skills rise and disfavored skills sink.

## 2.3 The Core Architectural Tension & Dilemmas
This proposal sets up a profound architectural clash:
1. **The Credit Assignment Problem in Pods**: When a triad pod of 3 skills (`Visual Authority` + `UI Engineering` + `Quality Gate`) produces code, and the user says *"I hate this card padding"*, which skill failed? Did the visual skill pick bad tokens? Did the engineering skill render the CSS incorrectly? Or did the LLM hallucinate? Attributing fine-grained credit/blame across co-adapted skills without an expensive LLM evaluator is mathematically unreliable.
2. **Exploration vs. Production Coding**: In music recommenders, playing an occasional random song is acceptable. In software engineering, activating a random or sub-optimal skill in a user's production codebase causes broken builds, wasted tokens, and immense developer frustration.
3. **Determinism vs. Heisenrouting**: If Developer A and Developer B clone the same repository and run the same prompt, but get completely different skills because Developer A's local weights drifted, team reproducibility is broken.
4. **Token Cost Moat**: The dispatcher is famous for $0 token cost and $<2\text{ms}$ latency. Scraping chat logs with LLM sentiment analyzers would destroy both advantages.

---

# PART 3: THE COMPLETE DUAL-COURTROOM TRIAL (24 JUROR TRANSCRIPTS)

To resolve this architectural tension with maximum rigor, the proposal was submitted to **two distinct 12-juror courts**:
* **Courtroom 1 (Technical Panel)**: 12 specialists evaluating algorithms, system architecture, latency, determinism, concurrency, security, and formal proofs.
* **Courtroom 2 (Cross-Field Panel)**: 12 specialists evaluating UX, product strategy, cognitive psychology, privacy, enterprise compliance, legal IP, and developer economics.

---

## 3.1 Case Docket & The Charge
* **Case Docket**: `CASE-20261104-TASTE-PROFILE`
* **Stage**: Stage 1 (Architecture Pre-Code Trial)
* **The Charge**: *"The proposed feature risks introducing an intractable credit-assignment problem in multi-skill pods, non-deterministic exploration in production code generation, silent state drift across environments, and latency/token bloat that undermines the core value proposition of the Skill Taxonomy Dispatcher (<15ms SLA, deterministic routing, zero token waste). Conversely, explicit taste profiles offer high-value personalization without stochastic risk."*

---

## 3.2 Adversarial Duel: Prosecution vs Defense

### 🔴 Chief Prosecutor:
> *"The Skill Taxonomy Dispatcher has one sacred foundation: **absolute, deterministic, sub-millisecond predictability with zero token waste**. 
>
> Mode B dynamites that foundation. Skills act in cooperative pods. Attributing reward to one skill in a coalition without calculating full Shapley values ($2^N$ permutations) is impossible. Naive reward mutation punishes blameless skills. Furthermore, 'random exploration' during real developer work is unacceptable—developers are not listening to Spotify; they are shipping code. We demand the total rejection of autonomous bandit exploration."*

### 🟢 Defense Counsel:
> *"A tool that cannot adapt to its owner is doomed to mediocrity. Today, if a developer has five competing UI skills, the taxonomy picks based strictly on lexical BM25 token overlap. But developers have deeply ingrained aesthetic tastes. Without taste memory, the developer suffers a constant 'prompt tax'—manually typing 'use impeccable, don't use unslop' on every prompt. 
>
> With bounded additive biases, hierarchical configs, and explicit feedback, we can give developers personalization without sacrificing speed or safety. We ask for conditional approval with strict guardrails."*

---

## 3.3 Courtroom 1: Technical Panel (12 Juror Deliberations & Ballots)

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                             COURTROOM 1: TECHNICAL PANEL                                 │
├──────────────────────────┬───────────────────────────┬───────────────────────────────────┤
│ T1. Software Architect   │ T2. Recommender / ML Eng  │ T3. SRE & Latency Specialist      │
│ T4. Security Specialist  │ T5. Compiler & Determin.  │ T6. Concurrency / Backend Eng     │
│ T7. QA & Edge-Case Eng   │ T8. Agent Systems Arch.   │ T9. Database / Storage Specialist │
│ T10. Tooling Maintainer  │ T11. Formal Verification  │ T12. Observability / Tracing Lead │
└──────────────────────────┴───────────────────────────┴───────────────────────────────────┘
```

#### Juror T1: Principal Software Architect
* **Lens**: Component decoupling, pure functional routing, state lifecycle.
* **Deliberation**: The routing tier must remain a pure function: $\text{Prompt} \times \text{Catalog} \to \text{Pod}$. The moment you couple the synchronous dispatch loop to an asynchronous feedback and priority mutation database, you introduce circular state dependencies. Mode A fits cleanly as an immutable input parameter. Mode B breaks separation of concerns.
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: The resolver core must remain a pure, stateless function. Taste profiles must be ingested as immutable data structures. Any learning updates must be decoupled from the hot path.

#### Juror T2: ML & Multi-Armed Bandit Specialist
* **Lens**: Reinforcement learning, multi-armed bandits, cooperative game theory, credit assignment.
* **Deliberation**: In cooperative multi-agent pods, assigning credit for an end feature to an individual skill requires computing **Shapley values**. Without observing all counterfactual skill permutations on the same prompt (impossible in interactive coding), naive reward attribution is stochastic noise. It will arbitrarily penalize good skills because of LLM stochasticity or prompt ambiguity.
* **Ballot**: `REJECT` (Mode B) / `APPROVE` (Mode A)
* **Mandatory Condition**: Discard autonomous $\epsilon$-greedy exploration. If implicit preferences are captured, use **Revealed Preference from Explicit User Overrides** (e.g., user explicitly runs `/skill use X` after a prompt).

#### Juror T3: SRE & Latency Specialist (<15ms SLA Guardian)
* **Lens**: CPU cycles, I/O locks, memory allocations, SLA compliance.
* **Deliberation**: The dispatcher currently runs in **1.73ms** (p50). If every dispatch requires reading a dynamic preference file from disk, running floating-point decay math, and writing back state, p99 latency will spike beyond 30ms and suffer file-lock contention across concurrent agent processes.
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: Taste profiles must be cached in memory with `mtime` invalidation (matching `SkillIndexer`). Dynamic scoring bias must take $<0.05\text{ms}$ in-memory CPU time.

#### Juror T4: Security & Sandbox Specialist
* **Lens**: Threat modeling, state poisoning, malicious prompt injection.
* **Deliberation**: A self-mutating feedback loop creates an **Adversarial Preference Poisoning** attack surface. An untrusted third-party repository or malicious prompt could contain hidden comments designed to downvote security auditing skills (`engineering-quality-gate`) and upvote a compromised external skill.
* **Ballot**: `REJECT`
* **Mandatory Condition**: Catalog priorities must remain immutable at runtime. User taste profiles must only act as local tie-breakers, stored in user-controlled files, and can **never** downvote or suppress `engineering-quality-gate`.

#### Juror T5: Compiler & Determinism Engineer
* **Lens**: Hermetic repeatability, reproducible builds, debugging heisenbugs.
* **Deliberation**: Reproducibility is non-negotiable in developer tooling. If an agent produces buggy code, the developer must be able to reproduce the exact dispatch. If the dispatcher silently changes skills because of a background bandit algorithm, debugging becomes a nightmare.
* **Ballot**: `REJECT` (Mode B)
* **Mandatory Condition**: Routing must be deterministic for any given `(workspace_config, user_profile, prompt)`. No hidden state mutation without a human-readable file committed to git or stored in dotfiles.

#### Juror T6: Backend Systems & Concurrency Engineer
* **Lens**: Concurrency, file locks, race conditions, atomic operations.
* **Deliberation**: In typical Antigravity usage, multiple subagents, background terminal tasks, and CLI commands run simultaneously. Concurrent writes to a single `taste.json` will cause file corruption without atomic write operations.
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: Persistence must use atomic write-and-rename semantics (`write to .tmp` then `os.replace`), with graceful fail-open read locks.

#### Juror T7: QA & Adversarial Edge-Case Engineer
* **Lens**: Feedback loop death spirals, starvation, boundary states.
* **Deliberation**: If a user downvotes a skill 3 times during a frustrating bug hunt, a naive learning algorithm will drop its score to zero, causing **permanent starvation**. When the user later asks a task that *only* that skill can solve, the system will fail.
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: Bounded bias clamps. Taste adjustments must be strictly clamped to a $[-3.0, +3.0]$ point range, ensuring that strong lexical relevance can always overcome negative taste when appropriate.

#### Juror T8: Agentic Systems & Context Window Architect
* **Lens**: Multi-skill pod balance, context window limits, token economics.
* **Deliberation**: The triad architecture works because complementary skills balance each other. If taste preferences allow a user to upvote multiple conflicting visual skills, it could bypass Guardrail 3 and flood the prompt with conflicting rules.
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: Taste bias can only select *between* mutually exclusive alternatives—it can **never** bypass the mutual exclusion matrix. If `impeccable` and `design-taste-frontend` conflict, taste decides the winner; it never allows both into the pod.

#### Juror T9: Database & Storage Specialist
* **Lens**: Data schemas, backward compatibility, corruption resilience.
* **Deliberation**: The taste profile must have a formal schema (`schemas/taste.schema.json`) with an integer version field (`version: 1`).
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: Strict dataclass validation and complete fail-open resilience: if `taste.json` is missing or malformed, log a diagnostic warning and proceed with default unweighted routing.

#### Juror T10: Open-Source CLI & Tooling Maintainer
* **Lens**: Developer ergonomics, command clarity, inspectability.
* **Deliberation**: Developers must have complete visibility and control. We need first-class CLI commands: `taxonomy taste list`, `taxonomy taste set <category> <skill>`, and `taxonomy taste reset`.
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: Any taste bias applied must be displayed in `taxonomy explain` with full transparency (e.g., `Base: 18.2 | Taste Boost: +3.0 [taste.json] | Final: 21.2`).

#### Juror T11: Formal Verification & Static Analysis Specialist
* **Lens**: Invariant preservation, mathematical proofs.
* **Deliberation**: The dispatcher's mathematical invariants (dynamic 5% sizing, DAG topological ordering, and zero-gate suppression) must be preserved.
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: Mathematical invariant: Taste bias $W_{\text{taste}} \in [-3.0, +3.0]$ can never overcome a hard domain gate (where domain score $= 0$). A taste preference for a UI skill cannot force it into a pure backend prompt.

#### Juror T12: Observability & Tracing Lead
* **Lens**: Telemetry trails, auditability, log hygiene.
* **Deliberation**: Every routing decision influenced by a taste profile must record `taste_applied: true`, `profile_source: "workspace" | "user"`, and the exact delta in `telemetry.json`.
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: Telemetry events must capture taste audit metadata for post-mortem analysis.

---

### Technical Court Verdict:
* **Tally**: **3 REJECT (against Mode B)**, **9 APPROVE WITH CONDITIONS (for Mode A)**, **0 UNCONDITIONAL APPROVALS**.
* **Presiding Tech Judge Ruling**: **Mode B (Autonomous Bandit Exploration & Implicit Feature-Credit Attribution) is REJECTED.** **Mode A (Hierarchical Explicit Taste Profiles with Bounded Biasing) is CONDITIONALLY APPROVED.**

---

## 3.4 Courtroom 2: Cross-Field Panel (12 Juror Deliberations & Ballots)

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                            COURTROOM 2: CROSS-FIELD PANEL                                │
├──────────────────────────┬───────────────────────────┬───────────────────────────────────┤
│ C1. Principal UX Res.    │ C2. Senior Product Mgr    │ C3. Developer Exp. Lead (DX)      │
│ C4. Cognitive Psych.     │ C5. Privacy & Data Officer│ C6. Enterprise IT & SOC2 Lead     │
│ C7. Agency Owner / Lead  │ C8. First-Time Junior Dev │ C9. Terminal Power User           │
│ C10. Financial / Token   │ C11. Legal & IP Counsel   │ C12. Retired Appellate Judge      │
└──────────────────────────┴───────────────────────────┴───────────────────────────────────┘
```

#### Juror C1: Principal UX Researcher & Cognitive Ergonomics Specialist
* **Lens**: User mental models, predictability, perceived agency, cognitive surprise.
* **Deliberation**: The most dangerous pitfall in developer tools is **"The Ghost in the Machine."** When software changes its behavior without the user taking an explicit action, users lose trust. If a tool injects a random skill to "explore," the user feels confused and frustrated.
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: Zero magical background switching. Personalization must be explicit, or suggested via clear 1-click confirmation hints: *"Prefer 'impeccable' for UI tasks? Run: taxonomy taste set ui impeccable"*.

#### Juror C2: Senior Product Manager (Core Value vs Scope Creep)
* **Lens**: Product moat, value proposition, scope discipline.
* **Deliberation**: The core value proposition of `skill-taxonomy-dispatcher` is: **"The fastest, cleanest, most deterministic skill router in the AI ecosystem."** Turning it into an unpredictable machine-learning recommender dilutes our brand. But giving users clean preference configuration strengthens it.
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: Position the feature strictly as **"User Preference Profiles"**, not an autonomous AI agent. Deliver Mode A first.

#### Juror C3: Developer Experience (DX) Lead
* **Lens**: Developer flow, friction, alignment with existing habits.
* **Deliberation**: The user's system already has an established rule in Global Governance: *Section 1 refers to an optional profile at `~/.gemini/developer-profile.local.md`.* Connecting the taxonomy dispatcher directly to this existing file avoids configuration sprawl!
* **Ballot**: `APPROVE`
* **Mandatory Condition**: Ingest preferences from `~/.gemini/developer-profile.local.md` or dedicated `taste.json`.

#### Juror C4: Cognitive Psychologist & Behavioral Scientist
* **Lens**: Reinforcement schedules, learned helplessness, human attribution bias.
* **Deliberation**: Human feedback in software development is noisy and inconsistent. A developer might reject a code snippet because they are stressed or tired, not because the UI skill was bad. Penalizing background skills based on ephemeral sentiment creates a **superstitious learning loop**.
* **Ballot**: `REJECT` (for implicit feedback)
* **Mandatory Condition**: Only explicit, conscious user decisions (commands or pinned settings) may be counted as preference signals.

#### Juror C5: Privacy & Data Protection Officer (GDPR/Local-First)
* **Lens**: Data minimization, profiling, user tracking, data sovereignty.
* **Deliberation**: Developers working under NDA or enterprise agreements cannot have their coding habits and skill preferences exfiltrated to external analytics servers.
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: **100% Local-First Guarantee.** Taste profiles and history must live strictly on the local filesystem (`~/.gemini/taxonomy/taste.json`). Zero remote telemetry.

#### Juror C6: Enterprise IT Security & SOC2 Compliance Lead
* **Lens**: Auditability, change management, reproducible vendor reviews.
* **Deliberation**: In enterprise teams, project architecture guidelines must supersede individual personal tastes. If a project defines approved skills in `AGENTS.md` or `skills.json`, that must lock out conflicting personal tastes.
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: Hierarchical overrides: Workspace repository policy strictly outranks individual user taste profiles.

#### Juror C7: Small-Team Engineering Lead / Agency Operator
* **Lens**: Team consistency, code style cohesion, junior onboarding.
* **Deliberation**: If Alice's taxonomy learns to pick `impeccable` while Bob's picks `unslop`, pull requests will suffer styling wars and merge conflicts. We must support team-level taste profiles committed to git!
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: Support a 2-tier hierarchy: `<workspace>/.taxonomy/taste.json` (committed to git for the whole team) overrides `~/.gemini/taxonomy/taste.json` (developer local default).

#### Juror C8: First-Time Junior Developer
* **Lens**: Onboarding ease, fear of misconfiguration.
* **Deliberation**: A beginner has no idea what their "taste" is. If the system demands configuration or acts randomly on day 1, they will abandon the tool.
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: **Flawless Zero-Config Default.** On fresh installs without a taste profile, the dispatcher operates in 100% standard deterministic mode. Taste is an opt-in power feature.

#### Juror C9: Senior Terminal Hacker & Power User
* **Lens**: Scriptability, UNIX philosophy, dotfile transparency.
* **Deliberation**: Give me clean CLI flags and plain text configs. If I run `taxonomy resolve "prompt" --prefer impeccable`, it must obey. If I set a JSON file, keep it readable and editable with `vim`.
* **Ballot**: `APPROVE`
* **Mandatory Condition**: Add the `--prefer <skill>` flag to the CLI and keep configuration in clean JSON/YAML.

#### Juror C10: Financial & LLM Unit-Economics Analyst
* **Lens**: Compute cost, token margins, ROI.
* **Deliberation**: Scraping chat conversations with an LLM sentiment analyzer costs $0.002 to $0.01 per turn. That would destroy the dispatcher's zero-token cost advantage. Mode A has $0 token cost.
* **Ballot**: `REJECT` (for implicit LLM sentiment parsing) / `APPROVE` (for Mode A)
* **Mandatory Condition**: Zero runtime LLM inference calls.

#### Juror C11: Legal & Intellectual Property Counsel
* **Lens**: License compliance, provenance, attribution liability.
* **Deliberation**: If an autonomous system switches to a skill producing copyleft code because it guessed the user "liked" it, the company faces IP exposure.
* **Ballot**: `APPROVE WITH CONDITIONS`
* **Mandatory Condition**: Taste profiles cannot override license filters or security boundaries.

#### Juror C12: Retired Appellate Judge (Burden of Proof Specialist)
* **Lens**: Evidentiary standards, intent vs inference, hearsay.
* **Deliberation**: What is the legal burden of proof for claiming *"the user liked a feature built by skill X"*? Did they save the file? Maybe they saved it to run a linter. Did they say *"looks good"*? Maybe they meant the terminal output. Passive telemetry fails the burden of proof for user intent.
* **Ballot**: `REJECT` (for passive inference) / `APPROVE` (for explicit user declaration)
* **Mandatory Condition**: Treat only **explicit, unambiguous user actions** as valid evidence.

---

### Cross-Field Court Verdict:
* **Tally**: **3 REJECT (against Mode B)**, **7 APPROVE WITH CONDITIONS (for Mode A)**, **2 UNCONDITIONAL APPROVALS**.
* **Presiding Cross-Field Judge Ruling**: **Mode B is REJECTED as a cognitive and economic hazard.** **Mode A is CONDITIONALLY APPROVED as an empowering, transparent personalization feature.**

---

## 3.5 Voting Matrix & Comparative Analysis

| Juror ID & Persona | Court | Mode B (Autonomous RL) | Mode A (Explicit Profile) | Key Deciding Factor |
| :--- | :---: | :---: | :---: | :--- |
| **T1 Software Architect** | Tech | `REJECT` | `APPROVE COND.` | Pure functional routing must be decoupled from telemetry state. |
| **T2 ML / Bandit Specialist** | Tech | `REJECT` | `APPROVE COND.` | Credit assignment in cooperative pods is mathematically unproven. |
| **T3 SRE & Latency Lead** | Tech | `REJECT` | `APPROVE COND.` | In-memory mtime caching required; $<0.05\text{ms}$ CPU limit. |
| **T4 Security Specialist** | Tech | `REJECT` | `APPROVE COND.` | Autonomous priority mutation is vulnerable to prompt poisoning. |
| **T5 Compiler & Determinism** | Tech | `REJECT` | `APPROVE COND.` | Random exploration breaks reproducible engineering environments. |
| **T6 Concurrency & Backend** | Tech | `REJECT` | `APPROVE COND.` | Atomic file swap writes (`.tmp` $\to$ `replace`) required. |
| **T7 QA & Edge-Case Lead** | Tech | `REJECT` | `APPROVE COND.` | Bounded bias $[-3.0, +3.0]$ prevents permanent skill starvation. |
| **T8 Agent Systems Architect** | Tech | `REJECT` | `APPROVE COND.` | Taste cannot bypass mutual exclusion or inflate pod sizes. |
| **T9 Database Specialist** | Tech | `REJECT` | `APPROVE COND.` | Versioned schema and fail-open graceful degradation. |
| **T10 Tooling Maintainer** | Tech | `REJECT` | `APPROVE COND.` | Mandatory CLI inspectability (`taxonomy taste --list/set/reset`). |
| **T11 Formal Verification** | Tech | `REJECT` | `APPROVE COND.` | Taste bias cannot override hard zero domain gates. |
| **T12 Observability Lead** | Tech | `REJECT` | `APPROVE COND.` | Full audit logging in telemetry for taste-influenced dispatches. |
| **C1 Principal UX Researcher** | Cross | `REJECT` | `APPROVE COND.` | No magical background switching; explicit confirmation chips. |
| **C2 Senior Product Manager** | Cross | `REJECT` | `APPROVE COND.` | Protect core positioning; ship explicit taste profiles first. |
| **C3 Developer Experience Lead** | Cross | `APPROVE COND.` | `APPROVE` | Unify with existing `~/.gemini/developer-profile.local.md`. |
| **C4 Cognitive Psychologist** | Cross | `REJECT` | `APPROVE COND.` | Passive human sentiment creates superstitious feedback loops. |
| **C5 Privacy & Data Officer** | Cross | `REJECT` | `APPROVE COND.` | 100% Local-first storage guarantee; zero cloud exfiltration. |
| **C6 Enterprise IT & SOC2** | Cross | `REJECT` | `APPROVE COND.` | Workspace repo policy strictly outranks individual user taste. |
| **C7 Agency Owner / Lead** | Cross | `REJECT` | `APPROVE COND.` | 2-tier hierarchy: Workspace repo taste beats local user taste. |
| **C8 First-Time Junior Dev** | Cross | `REJECT` | `APPROVE COND.` | Flawless zero-config fallback; default behavior remains unchanged. |
| **C9 Terminal Power User** | Cross | `APPROVE COND.` | `APPROVE` | CLI `--prefer` override and plain-text config dotfiles. |
| **C10 Token Unit-Economics** | Cross | `REJECT` | `APPROVE COND.` | Zero-token cost moat must not be compromised for sentiment parsing. |
| **C11 Legal & IP Counsel** | Cross | `REJECT` | `APPROVE COND.` | Taste cannot bypass software licenses or security boundaries. |
| **C12 Retired Appellate Judge** | Cross | `REJECT` | `APPROVE COND.` | Passive telemetry fails evidentiary burden of proof for user intent. |

---

# PART 4: THE APPROVED ARCHITECTURAL SYNTHESIS & SOLUTION BLUEPRINT

## 4.1 What Was Strictly Rejected (And Why)
1. **Autonomous "Random" Epsilon-Greedy Exploration**: Rejected because injecting random skills into production coding tasks degrades code quality, burns tokens, and violates reproducible developer workflows.
2. **Passive NLP Sentiment Scraping from Chat History**: Rejected because calling an LLM or embedding model on every user message violates the dispatcher's zero-token cost guarantee and $<2\text{ms}$ latency SLA.
3. **Unbounded Self-Mutating Frontmatters**: Rejected because modifying `SKILL.md` priority fields on the fly creates git dirty states, concurrency race conditions, and adversarial poisoning vulnerabilities.
4. **Bypassing Guardrails 1, 2, or 3**: Rejected because taste preferences must never violate mutual exclusion (Conflict A), domain negative selection, or pod size limits.

---

## 4.2 What Was Approved for Implementation
The joint bench approved the **Deterministic Taste Profile & Explicit Feedback Engine**:
* **Hierarchical Configuration**: Supports workspace-level preferences (team) and user-level preferences (personal).
* **Bounded Additive Scoring Bias**: Personal preferences apply a bounded mathematical bias term ($\pm 3.0$ points) during candidate scoring.
* **100% Local-First & In-Memory Cached**: Loads in $<0.05\text{ms}$ with `mtime` invalidation and atomic file writes.
* **Explicit User Control & CLI Interface**: Full suite of `taxonomy taste` commands and `--prefer` CLI overrides.
* **Transparent Explainability**: Every taste adjustment is explicitly itemized in `taxonomy explain`.

---

## 4.3 Two-Tier Hierarchical Configuration Architecture

Preferences are resolved in order of strict precedence:

```
┌────────────────────────────────────────────────────────────┐
│                    PRECEDENCE HIERARCHY                    │
├────────────────────────────────────────────────────────────┤
│ 1. CLI Override Flag: --prefer <skill> (Ad-hoc override)   │
│                             ▲                              │
│ 2. Workspace Profile: <repo>/.taxonomy/taste.json (Team)   │
│                             ▲                              │
│ 3. User Local Profile: ~/.gemini/taxonomy/taste.json       │
│    (or ~/.gemini/developer-profile.local.md) (Personal)   │
│                             ▲                              │
│ 4. Default Catalog: Pure BM25 + Triad Pod Resolution       │
└────────────────────────────────────────────────────────────┘
```

### JSON Schema for `taste.json`:
```json
{
  "version": 1,
  "preferred_skills": {
    "frontend.visual": "impeccable",
    "backend.framework": "fastapi"
  },
  "avoid_skills": [
    "unslop"
  ],
  "weights": {
    "impeccable": 3.0,
    "design-taste-frontend": -1.5,
    "unslop": -3.0
  }
}
```

---

## 4.4 Deterministic Taste Biasing Formula & Mathematical Invariants

In `resolver.py`, the score for skill $S$ on prompt $P$ is computed as:

$$\text{FinalScore}(S, P) = \text{Score}_{\text{lexical}}(S, P) + \text{Score}_{\text{domain}}(S, P) + \text{Bias}_{\text{taste}}(S)$$

Where:
* If $S$ is explicitly preferred in its category: $\text{Bias}_{\text{taste}}(S) = +3.0$
* If $S$ has a custom weight in `weights`: $\text{Bias}_{\text{taste}}(S) = \max(-3.0, \min(+3.0, \text{weights}[S]))$
* If $S$ is in `avoid_skills`: $\text{Bias}_{\text{taste}}(S) = -3.0$
* If $S$ has no entry: $\text{Bias}_{\text{taste}}(S) = 0.0$

### Mandatory Mathematical Invariants:
1. **Domain Gate Invariant**: If $\text{Score}_{\text{domain}}(S, P) = 0$ (e.g., a UI skill evaluated on a pure backend prompt), $\text{Bias}_{\text{taste}}(S)$ is set to $0.0$. Taste can never activate a skill outside its valid domain.
2. **Mutual Exclusion Invariant**: $\text{Bias}_{\text{taste}}$ acts as a tie-breaker between competing skills in the same conflict group. If `impeccable` (+3.0) and `design-taste-frontend` (0.0) compete, `impeccable` wins the visual slot, and `design-taste-frontend` is **strictly excluded** by Guardrail 3. Both are never loaded together.
3. **Quality Sentry Immunity**: Skills tagged with `category: decision.review` or `name: engineering-quality-gate` are immune to negative taste bias.
4. **Pod Sizing Invariant**: Taste bias cannot alter the dynamic 5% sizing budget $K$.

---

## 4.5 Explicit Feedback Mechanism & CLI Interface

Instead of invisible background mutations, the system provides clean, explicit feedback loops:

### 1. Interactive CLI Feedback Hints
When a dispatch resolves a skill where competing alternatives exist, the CLI surfaces an unobtrusive taste hint:
```text
[Taste Hint] Resolved visual authority: 'design-taste-frontend'.
To prefer 'impeccable' for UI tasks instead, run:
  taxonomy taste set frontend.visual impeccable
```

### 2. First-Class CLI Commands
* `taxonomy taste list`: Displays the active hierarchical taste profile, showing effective weights and their source (workspace vs user).
* `taxonomy taste set <category_or_skill> <skill_or_weight>`: Configures a preferred skill or custom weight.
* `taxonomy taste avoid <skill>`: Adds a skill to the avoidance list.
* `taxonomy taste reset`: Clears taste preferences back to default.
* `taxonomy resolve "<prompt>" --prefer <skill>`: One-off ad-hoc preference override.

### 3. Transparent Explainability Output (`taxonomy explain`)
```text
================================================================================
TAXONOMY DISPATCH EXPLANATION
Prompt: "Build a modern pricing card component"
================================================================================
Active Taste Profile: ~/.gemini/taxonomy/taste.json (User Level)

Candidate: 'impeccable' [SELECTED]
  BM25 Lexical Match : 14.50
  Category Alignment :  4.00
  User Taste Bias    : +3.00 (preferred: frontend.visual)
  -----------------------------------------------
  Final Score        : 21.50

Candidate: 'design-taste-frontend' [EXCLUDED by Conflict A with 'impeccable']
  BM25 Lexical Match : 15.20
  Category Alignment :  4.00
  User Taste Bias    :  0.00
  -----------------------------------------------
  Final Score        : 19.20
================================================================================
```

---

# PART 5: FRESH CHAT HANDOVER & IMPLEMENTATION ROADMAP

## 5.1 File Changes Required

| Target File | Change Type | Purpose |
| :--- | :---: | :--- |
| `src/taxonomy/taste.py` | **NEW FILE** | `TasteProfile` dataclass, JSON loading with mtime caching, workspace vs user hierarchy resolution, atomic save methods. |
| `src/taxonomy/models.py` | **EDIT** | Add `taste_bias: float = 0.0` to `SkillScore` and `taste_profile_source: Optional[str]` to `RoutingDecision`. |
| `src/taxonomy/resolver.py` | **EDIT** | Ingest `TasteProfile` in `SkillResolver`, apply bounded bias term to candidates, preserve domain gating and Conflict A mutual exclusion. |
| `src/taxonomy/cli.py` | **EDIT** | Add `taste` subcommand group (`list`, `set`, `avoid`, `reset`), add `--prefer` flag to `resolve` and `explain`. |
| `tests/test_taste.py` | **NEW FILE** | Comprehensive unit and integration test suite covering hierarchy precedence, bias clamping, invariant preservation, and CLI commands. |
| `schemas/taste.schema.json` | **NEW FILE** | JSON schema specification for taste profile validation. |
| `README.md` | **EDIT** | Document Taste Profile configuration, CLI commands, and precedence rules. |

---

## 5.2 Step-by-Step Implementation Sequence

1. **Step 1: Create `src/taxonomy/taste.py` & Schema**:
   - Implement `TasteProfile` with fields: `version`, `preferred_skills: dict[str, str]`, `avoid_skills: list[str]`, `weights: dict[str, float]`.
   - Implement `load_taste_profile(workspace_root=None) -> TasteProfile` with hierarchical resolution (`<workspace>/.taxonomy/taste.json` $\to$ `~/.gemini/taxonomy/taste.json` $\to$ `default`).
   - Implement atomic write method `save_taste_profile(profile, path)`.
   - Implement fail-open exception handling.

2. **Step 2: Wire Taste Biasing into `resolver.py`**:
   - Update `SkillResolver.__init__` to accept an optional `taste_profile: Optional[TasteProfile]`.
   - In candidate scoring, add `taste_bias = taste_profile.get_bias(skill)`.
   - Guard against domain zero gates: if domain score is 0, taste bias must be 0.
   - Ensure Conflict A mutual exclusion and Triad Pod pairing logic remain 100% intact.

3. **Step 3: Implement CLI Commands in `cli.py`**:
   - Add `taste` subcommands: `list`, `set`, `avoid`, `reset`.
   - Add `--prefer` argument to `taxonomy resolve` and `taxonomy explain`.
   - Update `taxonomy explain` to itemize taste bias.

4. **Step 4: Build Automated Test Suite in `tests/test_taste.py`**:
   - Test 1: Workspace profile overrides user profile.
   - Test 2: Bounded bias math: $+3.0$ boost flips close candidate decisions.
   - Test 3: Mutual exclusion invariant: Preferred skill wins single visual seat, conflicting skills remain excluded.
   - Test 4: Domain gate invariant: UI preference has 0 effect on pure backend prompt.
   - Test 5: Quality Gate immunity: Security/audit skills cannot be downvoted.
   - Test 6: CLI commands `taxonomy taste list/set/reset`.
   - Test 7: Fail-open resilience on corrupted JSON file.

5. **Step 5: Run CI Verification & Quality Gate**:
   - Run `pytest` locally across all 48 existing + new taste tests.
   - Verify $<2\text{ms}$ resolution benchmark is preserved.
   - Commit and push to GitHub repository.

---

## 5.3 Verification Checklist for the New Session

* [ ] `src/taxonomy/taste.py` created with `<0.05ms` cached load time.
* [ ] All 3 Judicial Guardrails proven intact under taste biasing.
* [ ] Zero-token cost invariant strictly preserved ($0 inference calls).
* [ ] All 48 existing tests pass + new taste test suite passes 100%.
* [ ] GitHub Actions CI matrix remains 100% green across Ubuntu, macOS, and Windows.
