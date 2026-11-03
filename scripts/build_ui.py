"""Build the self-contained workbench HTML (src/taxonomy/web/index.html).

Portable: every path is resolved relative to this repository, so it runs from any
clone on Windows, macOS, or Linux.

Usage:
    python scripts/build_ui.py                       # writes src/taxonomy/web/index.html
    python scripts/build_ui.py --data my_data.json   # use a different skill data file
    python scripts/build_ui.py --extra-out preview.html  # also write a copy elsewhere
"""

import argparse
import base64
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = REPO_ROOT / "src" / "taxonomy"
FONTS_DIR = PKG_DIR / "web" / "fonts"

parser = argparse.ArgumentParser(description="Build the Skill Taxonomy workbench HTML.")
parser.add_argument("--data", type=Path, default=PKG_DIR / "web_data.json",
                    help="Skill data JSON produced by scripts/export_ui_data.py (default: src/taxonomy/web_data.json)")
parser.add_argument("--out", type=Path, default=PKG_DIR / "web" / "index.html",
                    help="Output HTML path (default: src/taxonomy/web/index.html)")
parser.add_argument("--extra-out", type=Path, action="append", default=[],
                    help="Optional additional output path(s) for a copy of the HTML (repeatable)")
args = parser.parse_args()

if not args.data.exists():
    sys.exit(f"[ERROR] Skill data not found: {args.data}\n"
             f"        Generate it first with: python scripts/export_ui_data.py")

skills_data = json.loads(args.data.read_text(encoding="utf-8"))

# Sanitize any emojis or raw internal prefixes in skill descriptions for clean UI display
for name, s in skills_data.items():
    desc = s.get("description", "")
    # Remove sparkle emoji or non-standard ornaments
    desc = desc.replace("\u2728", "").replace("  ", " ").strip()
    if desc.startswith("tasteskill v2, the anti-slop frontend skill. "):
        desc = desc.replace("tasteskill v2, the anti-slop frontend skill. ", "", 1)
    s["description"] = desc

def _font_b64(filename: str) -> str:
    """Inline a font from src/taxonomy/web/fonts; fall back to system fonts if it's missing."""
    font_path = FONTS_DIR / filename
    if not font_path.exists():
        print(f"[WARN] Font not found ({font_path}); the UI will fall back to system fonts.")
        return ""
    return base64.b64encode(font_path.read_bytes()).decode("ascii")


light_b64 = _font_b64("Satoshi-Light.woff2")
var_b64 = _font_b64("Satoshi-Variable.woff2")

# Universally escape all '<' as '\u003c' so HTML tokenizer never encounters '<script', '</script>', or comments inside the <script> block
json_str = json.dumps(skills_data).replace("<", "\\u003c")

html_content = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Skill Taxonomy & Lifecycle Dispatcher — Command Workbench</title>
  <link rel="preconnect" href="https://api.fontshare.com">
  <link rel="stylesheet" href="https://api.fontshare.com/v2/css?f[]=satoshi@300,400,500,700&display=swap">
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    @font-face {{
      font-family: 'Satoshi';
      src: url('data:font/woff2;base64,{light_b64}') format('woff2');
      font-weight: 300;
      font-style: normal;
      font-display: swap;
    }}
    @font-face {{
      font-family: 'Satoshi';
      src: url('data:font/woff2;base64,{var_b64}') format('woff2');
      font-weight: 300 900;
      font-style: normal;
      font-display: swap;
    }}

    :root {{
      /* Dark Base, #0a0e16 Border Highlight & #0C0D0D Card Surface */
      --app-bg: #070708;
      --card-bg: #0C0D0D;
      --card-bg-hover: #101212;
      --well-bg: #080909;
      --chip-bg: #0C0D0D;
      --chip-active: #131516;
      
      --box-border: #0a0e16;
      --border-line: #12151c;
      --border-line-hover: #1b222c;
      --border-line-focus: #283344;
      
      --text-chrome: #ffffff;
      --text-bright: #f1f5f9;
      --text-steel: #cbd5e1;
      --text-muted: #8694a7;
      --text-dim: #515f73;
    }}

    *, *::before, *::after {{
      font-family: 'Satoshi', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-weight: 300;
      font-variation-settings: 'wght' 300;
      letter-spacing: -0.005em;
    }}

    body {{
      background-color: var(--app-bg);
      color: var(--text-steel);
      min-height: 100vh;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }}

    h1, h2, h3, h4, h5, h6, strong, b, button, input, select, textarea {{
      font-weight: 300 !important;
      font-variation-settings: 'wght' 300 !important;
    }}

    .mono {{
      font-family: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace !important;
      font-weight: 300 !important;
    }}

    .solid-panel {{
      background-color: var(--card-bg);
      border: 1px solid var(--box-border);
      box-shadow: inset 0 0 0 1px rgba(10, 14, 22, 0.95), inset 0 0 6px 1px rgba(10, 14, 22, 0.7);
    }}
    .solid-well {{
      background-color: var(--well-bg);
      border: 1px solid #11141b;
    }}
    .solid-chip {{
      background-color: var(--chip-bg);
      border: 1px solid var(--border-line);
      color: var(--text-steel);
    }}
    .solid-chip:hover {{
      background-color: var(--card-bg-hover);
      border-color: var(--border-line-hover);
      color: var(--text-chrome);
    }}
    .solid-chip.active-preset {{
      background-color: var(--chip-active);
      border-color: #2e3e57;
      color: var(--text-chrome);
    }}
    .solid-input {{
      background-color: var(--well-bg);
      border: 1px solid var(--border-line);
      color: var(--text-bright);
    }}
    .solid-input:focus {{
      border-color: var(--border-line-focus);
      outline: none;
    }}

    ::-webkit-scrollbar {{
      width: 6px;
      height: 6px;
    }}
    ::-webkit-scrollbar-track {{
      background: var(--app-bg);
    }}
    ::-webkit-scrollbar-thumb {{
      background: var(--border-line);
      border-radius: 3px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
      background: var(--border-line-hover);
    }}
  </style>
</head>
<body class="p-4 sm:p-6 lg:p-8 selection:bg-slate-700 selection:text-white">

  <!-- TWO-COLUMN WORKBENCH LAYOUT: LEFT SIDEBAR + RIGHT VIEWPORT -->
  <div class="max-w-[1560px] mx-auto flex flex-col lg:flex-row gap-6 lg:gap-8 items-start">

    <!-- ========================================== -->
    <!-- LEFT SIDEBAR: BRAND, 5-TAB BAR & ROOTS     -->
    <!-- ========================================== -->
    <aside class="w-full lg:w-72 xl:w-[290px] shrink-0 lg:sticky lg:top-8 flex flex-col gap-5">
      
      <div class="solid-panel rounded-2xl p-6 space-y-6">
        
        <!-- Brand Identity -->
        <div class="space-y-3">
          <div class="flex items-center gap-3.5">
            <div class="h-10 w-10 rounded-xl bg-[#101623] border border-[#1e283a] flex items-center justify-center text-slate-100 font-mono text-sm shrink-0">
              ST
            </div>
            <div>
              <h1 class="text-base tracking-tight text-white leading-snug">Skill Taxonomy</h1>
              <div class="text-[11px] font-mono text-slate-400">v0.1.0 &bull; GATED DISPATCHER</div>
            </div>
          </div>
          <p class="text-xs text-slate-400 leading-relaxed">
            Sub-millisecond complexity gating and deterministic conflict-free specialist resolution.
          </p>
        </div>

        <div class="h-px bg-[#18202e] w-full"></div>

        <!-- 5-Tab Navigation Bar -->
        <nav class="space-y-1.5" aria-label="Workspace Views">
          <div class="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2.5 px-1">Views</div>

          <button onclick="switchTab('simulator')" id="tab-btn-simulator" class="tab-btn active w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs sm:text-sm text-white bg-[#121926] border border-[#222e42] transition-all text-left">
            <div class="flex items-center gap-3">
              <svg class="w-4 h-4 text-slate-200 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
              <span>Prompt Triage</span>
            </div>
            <span class="w-1.5 h-1.5 rounded-full bg-slate-300"></span>
          </button>

          <button onclick="switchTab('catalog')" id="tab-btn-catalog" class="tab-btn w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs sm:text-sm text-slate-400 border border-transparent hover:text-white hover:bg-[#111314] transition-all text-left">
            <div class="flex items-center gap-3">
              <svg class="w-4 h-4 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
              <span>Skill Catalog</span>
            </div>
            <span class="text-[10px] font-mono px-2 py-0.5 rounded-md bg-[#0C0D0D] text-slate-400 border border-[#0a0e16]">25</span>
          </button>

          <button onclick="switchTab('matrix')" id="tab-btn-matrix" class="tab-btn w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs sm:text-sm text-slate-400 border border-transparent hover:text-white hover:bg-[#111314] transition-all text-left">
            <div class="flex items-center gap-3">
              <svg class="w-4 h-4 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
              <span>Routing Matrix</span>
            </div>
          </button>

          <button onclick="switchTab('telemetry')" id="tab-btn-telemetry" class="tab-btn w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs sm:text-sm text-slate-400 border border-transparent hover:text-white hover:bg-[#111314] transition-all text-left">
            <div class="flex items-center gap-3">
              <svg class="w-4 h-4 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
              <span>Telemetry & SRE</span>
            </div>
          </button>

          <button onclick="switchTab('doctor')" id="tab-btn-doctor" class="tab-btn w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs sm:text-sm text-slate-400 border border-transparent hover:text-white hover:bg-[#111314] transition-all text-left">
            <div class="flex items-center gap-3">
              <svg class="w-4 h-4 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
              <span>CLI & Diagnostics</span>
            </div>
          </button>
        </nav>

        <div class="h-px bg-[#18202e] w-full"></div>

        <!-- Discovery Roots Precedence Stack (Clickable to jump to filtered Catalog) -->
        <div class="space-y-2">
          <div class="flex items-center justify-between px-1">
            <span class="text-[10px] font-mono uppercase tracking-widest text-slate-500">Discovery Roots</span>
            <span class="text-[10px] font-mono text-slate-500">Precedence</span>
          </div>

          <button onclick="jumpToRoot('config')" class="w-full flex items-center justify-between p-2.5 rounded-xl solid-well hover:border-[#263347] transition-all text-xs text-left">
            <div class="truncate pr-2">
              <div class="text-slate-200 font-mono text-[11px]">1. ~/.gemini/config</div>
              <div class="text-[10px] text-slate-500">Governance & Lead</div>
            </div>
            <span class="px-2 py-0.5 rounded bg-[#0c111a] text-slate-300 border border-[#18202e] font-mono text-[10px] shrink-0">4</span>
          </button>

          <button onclick="jumpToRoot('agents')" class="w-full flex items-center justify-between p-2.5 rounded-xl solid-well hover:border-[#263347] transition-all text-xs text-left">
            <div class="truncate pr-2">
              <div class="text-slate-200 font-mono text-[11px]">2. ~/.agents/skills</div>
              <div class="text-[10px] text-slate-500">UI & Specialist</div>
            </div>
            <span class="px-2 py-0.5 rounded bg-[#0c111a] text-slate-300 border border-[#18202e] font-mono text-[10px] shrink-0">12</span>
          </button>

          <button onclick="jumpToRoot('builtin')" class="w-full flex items-center justify-between p-2.5 rounded-xl solid-well hover:border-[#263347] transition-all text-xs text-left">
            <div class="truncate pr-2">
              <div class="text-slate-200 font-mono text-[11px]">3. builtin/skills</div>
              <div class="text-[10px] text-slate-500">Platform Core</div>
            </div>
            <span class="px-2 py-0.5 rounded bg-[#0c111a] text-slate-300 border border-[#18202e] font-mono text-[10px] shrink-0">9</span>
          </button>
        </div>

        <div class="h-px bg-[#18202e] w-full"></div>

        <!-- Engine Health Summary -->
        <div class="space-y-2">
          <div class="text-[10px] font-mono uppercase tracking-widest text-slate-500 px-1">Engine Telemetry</div>

          <div class="grid grid-cols-2 gap-2 text-xs font-mono">
            <div class="p-2.5 rounded-xl solid-well">
              <div class="text-[10px] text-slate-500">Gate SLA</div>
              <div class="text-slate-200 mt-0.5">0.039 ms</div>
            </div>
            <div class="p-2.5 rounded-xl solid-well">
              <div class="text-[10px] text-slate-500">DAG Graph</div>
              <div class="text-slate-200 mt-0.5">Acyclic</div>
            </div>
            <div class="p-2.5 rounded-xl solid-well">
              <div class="text-[10px] text-slate-500">Active</div>
              <div class="text-slate-200 mt-0.5">25 Skills</div>
            </div>
            <div class="p-2.5 rounded-xl solid-well">
              <div class="text-[10px] text-slate-500">Suppressed</div>
              <div class="text-slate-400 mt-0.5">3 Locked</div>
            </div>
          </div>
        </div>

      </div>

    </aside>

    <!-- ========================================== -->
    <!-- RIGHT CONTENT AREA                         -->
    <!-- ========================================== -->
    <main class="flex-1 min-w-0 w-full space-y-6">

      <!-- Active View Header Bubble -->
      <div class="solid-panel rounded-2xl px-6 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div class="space-y-0.5">
          <div class="text-[10px] font-mono uppercase tracking-widest text-slate-500" id="view-subtitle">Interactive Evaluation & Conflict Resolution</div>
          <h2 id="view-title" class="text-lg tracking-tight text-white">Prompt Triage Simulator</h2>
        </div>
        <div class="flex items-center gap-2.5 text-xs">
          <button onclick="copyCliCommand()" id="copy-cli-btn" class="px-3.5 py-1.5 rounded-xl solid-chip font-mono text-[11px] flex items-center gap-2 transition-all">
            <svg class="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
            <span id="copy-cli-label">Copy CLI Command</span>
          </button>
          <span class="px-3 py-1.5 rounded-xl bg-[#0e1420] text-slate-200 border border-[#202c40] font-mono text-[11px] flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full bg-slate-300"></span>
            25 Indexed
          </span>
        </div>
      </div>

      <!-- ====================================== -->
      <!-- TAB 1: PROMPT TRIAGE SIMULATOR         -->
      <!-- ====================================== -->
      <section id="tab-simulator" class="tab-content block space-y-6">

        <!-- Console Card Bubble -->
        <div class="solid-panel rounded-2xl p-6 space-y-5">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <label for="prompt-input" class="text-xs uppercase tracking-wider text-slate-200 flex items-center gap-2.5">
              <span class="w-1.5 h-1.5 rounded-full bg-slate-300"></span>
              <span>Engineering Prompt Input</span>
            </label>
            <div class="flex items-center gap-2.5 text-xs">
              <span class="text-slate-400">Lifecycle Phase:</span>
              <select id="phase-select" onchange="runSimulation()" class="solid-input rounded-xl px-3.5 py-1.5 text-xs">
                <option value="">All Phases (Unrestricted)</option>
                <option value="architecture">Architecture (Lead & Reviews)</option>
                <option value="implementation">Implementation (UI, Frontend & Backend)</option>
                <option value="verification">Verification (QA & Quality Gate)</option>
                <option value="review">Review (Courtroom Jury & Audit)</option>
              </select>
            </div>
          </div>

          <div class="relative">
            <textarea id="prompt-input" rows="2" oninput="runSimulation()" placeholder="Enter any engineering prompt to evaluate complexity gating, domain signals, and specialist resolution..." class="solid-input w-full rounded-xl p-4 text-sm placeholder:text-slate-600 font-mono leading-relaxed transition-all"></textarea>
          </div>

          <!-- 1-Click Matrix Presets Bubble -->
          <div class="solid-well rounded-xl p-4 space-y-3">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <span class="text-[11px] font-mono text-slate-400 uppercase tracking-wider">Routing Matrix Presets</span>
              <span class="text-[11px] font-mono text-slate-500">Select a scenario to test conflict resolution</span>
            </div>
            <div class="flex flex-wrap gap-2 text-xs" id="preset-buttons-container">
              <button onclick="setPrompt(this, 'Build and design a premium marketing landing page and portfolio showcase with hero section and smooth animations')" class="preset-btn solid-chip active-preset px-3.5 py-2 rounded-xl transition-all">
                Marketing Landing Page
              </button>
              <button onclick="setPrompt(this, 'Build a responsive SaaS analytics dashboard and admin settings web-app with onboarding forms and design tokens')" class="preset-btn solid-chip px-3.5 py-2 rounded-xl transition-all">
                SaaS Dashboard
              </button>
              <button onclick="setPrompt(this, 'Design a technical documentation and blog reading product-ui with clean tokens and accessible layout')" class="preset-btn solid-chip px-3.5 py-2 rounded-xl transition-all">
                Docs & Reading UI
              </button>
              <button onclick="setPrompt(this, 'Unslop and cleanup this vibecoded AI-slop screen with generic-ui purple gradients and restyle its layout')" class="preset-btn solid-chip px-3.5 py-2 rounded-xl transition-all">
                Unslop Cleanup
              </button>
              <button onclick="setPrompt(this, 'Build an isolated-component prototype and single-component card-widget with bespoke visual-identity')" class="preset-btn solid-chip px-3.5 py-2 rounded-xl transition-all">
                Isolated UI Component
              </button>
              <button onclick="setPrompt(this, 'Optimize our React and Next.js SSR suspense waterfall, bundle size, and rerender hooks performance')" class="preset-btn solid-chip px-3.5 py-2 rounded-xl transition-all">
                React & Next.js Perf
              </button>
              <button onclick="setPrompt(this, 'Architect and build a distributed backend REST API and microservice in Python and Rust with Postgres database and pytest verification')" class="preset-btn solid-chip px-3.5 py-2 rounded-xl transition-all">
                Pure Backend API
              </button>
              <button onclick="setPrompt(this, 'Design and audit a Solidity smart-contract settlement protocol with adversarial courtroom jury review and verification')" class="preset-btn solid-chip px-3.5 py-2 rounded-xl transition-all">
                Smart Contract Audit
              </button>
              <button onclick="setPrompt(this, 'Triage this GitHub issue and open a pull-request with full verification and code review')" class="preset-btn solid-chip px-3.5 py-2 rounded-xl transition-all">
                GitHub Issue & PR
              </button>
              <button onclick="setPrompt(this, 'Good morning! How are you doing today?')" class="preset-btn solid-chip px-3.5 py-2 rounded-xl transition-all text-slate-400 border-dashed">
                Casual Greeting (Tier 0)
              </button>
              <button onclick="setPrompt(this, 'Fix the typo on line 42 in index.py')" class="preset-btn solid-chip px-3.5 py-2 rounded-xl transition-all text-slate-400 border-dashed">
                Micro-Fix Typo (Tier 1)
              </button>
            </div>
          </div>
        </div>

        <!-- Simulator Bento Grid: Balanced Left & Right Columns -->
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">

          <!-- Stage 1: Compound Gate & Signal Telemetry Bubble (4 cols) -->
          <div class="xl:col-span-4 solid-panel rounded-2xl p-6 space-y-5">
            <div class="flex items-center justify-between border-b border-[#18202e] pb-3.5">
              <h3 class="text-xs uppercase tracking-wider text-slate-200 flex items-center gap-2">
                <span class="w-1.5 h-1.5 rounded-full bg-slate-300"></span>
                Stage 1: Compound Gate
              </h3>
              <span id="gate-latency-badge" class="px-2.5 py-1 rounded-lg text-xs font-mono solid-well text-slate-300">0.000 ms</span>
            </div>

            <!-- Gate Verdict Box -->
            <div id="gate-verdict-box" class="p-4 rounded-xl solid-well space-y-3.5">
              <div class="flex items-center justify-between">
                <span class="text-xs text-slate-400">Routing Decision</span>
                <span id="gate-status-pill" class="px-3 py-1 text-xs font-mono rounded-lg bg-[#141d2b] text-white border border-[#24334a]">ROUTED</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-xs text-slate-400">Complexity Tier</span>
                <span id="gate-tier-badge" class="px-3 py-1 text-xs font-mono rounded-lg bg-[#0e131d] text-slate-200 border border-[#1b2332]">Tier 2</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-xs text-slate-400">Gate Trigger</span>
                <span id="gate-reason-text" class="text-xs font-mono text-slate-200 bg-[#0C0D0D] px-2.5 py-1 rounded-lg border border-[#0a0e16]">domain_match</span>
              </div>
            </div>

            <!-- Domain Signal Extractor Box -->
            <div class="p-4 rounded-xl solid-well space-y-3">
              <div class="flex items-center justify-between">
                <span class="text-xs text-slate-200">Domain Signal Extraction</span>
                <span id="neg-selection-badge" class="text-[10px] font-mono px-2 py-0.5 rounded bg-[#0c111a] text-slate-400 border border-[#18202e]">UI Allowed</span>
              </div>
              <div class="space-y-2 text-xs">
                <div class="flex items-start justify-between gap-2">
                  <span class="text-slate-400 shrink-0">UI Signals:</span>
                  <span id="ui-signals-list" class="font-mono text-[11px] text-slate-200 text-right">none</span>
                </div>
                <div class="flex items-start justify-between gap-2">
                  <span class="text-slate-400 shrink-0">Backend Signals:</span>
                  <span id="backend-signals-list" class="font-mono text-[11px] text-slate-200 text-right">none</span>
                </div>
              </div>
            </div>

            <!-- Category Affinity Ranking Box -->
            <div class="p-4 rounded-xl solid-well space-y-3">
              <div class="flex items-center justify-between">
                <span class="text-xs text-slate-200">Category Affinity Scores</span>
                <span class="text-[10px] font-mono text-slate-500">Weighted Tag Hits</span>
              </div>
              <div id="category-scores-container" class="space-y-2 text-xs font-mono">
                <!-- Populated dynamically -->
              </div>
            </div>

            <!-- Deterministic Bypass Policy Note -->
            <div class="text-xs text-slate-400 solid-well rounded-xl p-4 space-y-1.5">
              <div class="text-slate-200">Zero-Token Bypass Guarantee</div>
              <p class="leading-relaxed text-[11px]">
                Tier 0 (casual greetings, conceptual questions) and Tier 1 (single-line micro-fixes) bypass skill loading in &lt; 0.04ms, saving ~2,500 context tokens per turn.
              </p>
            </div>
          </div>

          <!-- Stage 2: Specialist Skills Resolved Bubble (8 cols) -->
          <div class="xl:col-span-8 solid-panel rounded-2xl p-6 space-y-5">
            <div class="flex items-center justify-between border-b border-[#18202e] pb-3.5">
              <div class="flex items-center gap-2.5">
                <span class="w-1.5 h-1.5 rounded-full bg-slate-300"></span>
                <h3 class="text-xs uppercase tracking-wider text-slate-200">Stage 2: Specialist Skills Resolved</h3>
                <span id="skill-count-badge" class="px-2.5 py-0.5 text-xs rounded-md bg-[#101520] text-slate-300 border border-[#1e2636] font-mono">0 / max 3</span>
              </div>
              <span id="resolver-latency-badge" class="px-2.5 py-1 rounded-lg text-xs font-mono solid-well text-slate-300">0.000 ms</span>
            </div>

            <!-- Selected Skills Container -->
            <div id="selected-skills-container" class="space-y-3.5">
              <!-- Dynamic cards injected via JS -->
            </div>

            <!-- Conflict Deactivation & Guardrail Log Bubble -->
            <div class="border border-[#18202e] rounded-xl p-4 sm:p-5 solid-well text-xs space-y-3">
              <div class="flex items-center justify-between">
                <div class="text-slate-200 flex items-center gap-2">
                  <svg class="w-4 h-4 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
                  <span>Conflict Resolution & Mutual Exclusion Log</span>
                </div>
                <span id="conflict-count-badge" class="text-[10px] font-mono text-slate-500">Acyclic DAG</span>
              </div>
              <div id="conflict-log-text" class="text-slate-400 space-y-1.5 font-mono text-[11px] leading-relaxed">
                (No conflicting skills detected in this query)
              </div>
            </div>
          </div>

        </div>
      </section>

      <!-- ====================================== -->
      <!-- TAB 2: 25-SKILL CATALOG                -->
      <!-- ====================================== -->
      <section id="tab-catalog" class="tab-content hidden space-y-6">
        <div class="solid-panel rounded-2xl p-5 sm:p-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div class="flex-1 relative">
            <input type="text" id="catalog-search" oninput="renderCatalog()" placeholder="Filter 25 indexed skills by name, category, tag, or description..." class="solid-input w-full rounded-xl pl-11 pr-4 py-2.5 text-xs sm:text-sm text-slate-200 placeholder:text-slate-600 transition-all">
            <svg class="w-4 h-4 text-slate-500 absolute left-4 top-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
          </div>

          <div class="flex flex-wrap items-center gap-2.5 text-xs">
            <select id="catalog-root-filter" onchange="renderCatalog()" class="solid-input rounded-xl px-3.5 py-2.5 text-slate-200">
              <option value="all">All 3 Discovery Roots (25)</option>
              <option value="config">1. ~/.gemini/config/skills (4)</option>
              <option value="agents">2. ~/.agents/skills (12)</option>
              <option value="builtin">3. builtin/skills (9)</option>
            </select>
            <select id="catalog-category-filter" onchange="renderCatalog()" class="solid-input rounded-xl px-3.5 py-2.5 text-slate-200">
              <option value="all">All Categories</option>
            </select>
          </div>
        </div>

        <div id="catalog-grid" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          <!-- Injected via JS -->
        </div>
      </section>

      <!-- ====================================== -->
      <!-- TAB 3: ROUTING MATRIX & CONFLICT RULES -->
      <!-- ====================================== -->
      <section id="tab-matrix" class="tab-content hidden space-y-6">
        <div class="solid-panel rounded-2xl p-6 sm:p-8 space-y-6">
          <div>
            <h2 class="text-sm uppercase tracking-wider text-white">Master Routing Matrix & Conflict Elimination Rules</h2>
            <p class="text-xs text-slate-400 mt-1 leading-relaxed">
              Enforced deterministically by the Taxonomy Resolver according to <code class="text-slate-300 font-mono">skill-routing-matrix.md</code> and <code class="text-slate-300 font-mono">AGENTS.md</code>.
            </p>
          </div>

          <!-- Section 1: Visual Authorities Ring Bubble -->
          <div class="border border-[#18202e] rounded-2xl p-5 sm:p-6 solid-well space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <h3 class="text-xs uppercase tracking-wider text-slate-200 flex items-center gap-2.5">
                <span class="w-2 h-2 rounded-full bg-slate-300"></span>
                Conflict A: Primary Visual Authority Ring (Mutually Exclusive)
              </h3>
              <span class="text-xs px-3 py-0.5 rounded-full bg-[#101724] text-slate-300 border border-[#1e2a3e] font-mono">At most 1 selected</span>
            </div>
            <p class="text-xs text-slate-300 leading-relaxed">
              Prevents competing design systems from writing contradictory state files (<code class="text-slate-300 font-mono">.taste-skill/</code> vs <code class="text-slate-300 font-mono">DESIGN.md</code> vs <code class="text-slate-300 font-mono">MASTER.md</code>):
            </p>
            <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 text-xs">
              <div class="p-4 rounded-xl solid-panel space-y-2">
                <div class="text-slate-100 text-sm">design-taste-frontend</div>
                <div class="text-[11px] text-slate-400 font-mono">Priority: 92 | ui.marketing</div>
                <p class="text-slate-400 leading-relaxed">Owns marketing pages, landing pages, showcases. Locks out impeccable, unslop, frontend-design.</p>
              </div>
              <div class="p-4 rounded-xl solid-panel space-y-2">
                <div class="text-slate-100 text-sm">impeccable</div>
                <div class="text-[11px] text-slate-400 font-mono">Priority: 91 | ui.product</div>
                <p class="text-slate-400 leading-relaxed">Owns SaaS dashboards, app UIs, settings, docs (Operate/Read modes). Locks out design-taste-frontend, unslop.</p>
              </div>
              <div class="p-4 rounded-xl solid-panel space-y-2">
                <div class="text-slate-100 text-sm">unslop</div>
                <div class="text-[11px] text-slate-400 font-mono">Priority: 90 | ui.cleanup</div>
                <p class="text-slate-400 leading-relaxed">Owns restyling vibecoded/AI-slop screens. Fixes spacing & color without bloated design systems.</p>
              </div>
              <div class="p-4 rounded-xl solid-panel space-y-2">
                <div class="text-slate-100 text-sm">frontend-design</div>
                <div class="text-[11px] text-slate-400 font-mono">Priority: 85 | ui.component</div>
                <p class="text-slate-400 leading-relaxed">Owns isolated single components and fast prototypes without multi-file setup overhead.</p>
              </div>
            </div>
          </div>

          <!-- Section 2: Motion Triad Bubble -->
          <div class="border border-[#18202e] rounded-2xl p-5 sm:p-6 solid-well space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <h3 class="text-xs uppercase tracking-wider text-slate-200 flex items-center gap-2.5">
                <span class="w-2 h-2 rounded-full bg-slate-400"></span>
                Conflict D: Emil Kowalski Motion Triad (Mutually Exclusive)
              </h3>
              <span class="text-xs px-3 py-0.5 rounded-full bg-[#101724] text-slate-300 border border-[#1e2a3e] font-mono">Building vs Reviewing</span>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
              <div class="p-4 rounded-xl solid-panel space-y-2">
                <div class="text-slate-200 text-sm">animate</div>
                <div class="text-[11px] text-slate-400 font-mono">Priority: 86 | ui.animation</div>
                <p class="text-slate-400 leading-relaxed">Writes animations from scratch with strict easing & duration tables. Locks out review-animations.</p>
              </div>
              <div class="p-4 rounded-xl solid-panel space-y-2">
                <div class="text-slate-200 text-sm">review-animations</div>
                <div class="text-[11px] text-slate-400 font-mono">Priority: 84 | quality.animation</div>
                <p class="text-slate-400 leading-relaxed">Critiques motion PRs against high craft bar. Does not write new animation implementations.</p>
              </div>
              <div class="p-4 rounded-xl solid-panel space-y-2">
                <div class="text-slate-200 text-sm">emil-design-eng</div>
                <div class="text-[11px] text-slate-400 font-mono">Priority: 83 | ui.polish</div>
                <p class="text-slate-400 leading-relaxed">Unique interaction polish principles (Sonner toast, 3D CSS transforms, velocity math).</p>
              </div>
            </div>
          </div>

          <!-- Section 3: Domain Negative Selection Bubble -->
          <div class="border border-[#18202e] rounded-2xl p-5 sm:p-6 solid-well space-y-3">
            <h3 class="text-xs uppercase tracking-wider text-slate-200 flex items-center gap-2.5">
              <span class="w-2 h-2 rounded-full bg-slate-300"></span>
              Domain Negative Selection (Backend & Smart Contract Isolation)
            </h3>
            <p class="text-xs text-slate-300 leading-relaxed">
              When a prompt specifies a pure backend API, database, CLI tool, or smart contract protocol with zero UI signals, the Resolver automatically locks out all 9 UI/frontend/motion specialist skills, ensuring pure focus on <code class="text-slate-200 font-mono">development-director</code>, <code class="text-slate-200 font-mono">engineering-quality-gate</code>, and <code class="text-slate-200 font-mono">independent-jury</code>.
            </p>
          </div>

          <!-- Section 4: Suppressed Exclusions Bubble -->
          <div class="border border-[#18202e] rounded-2xl p-5 sm:p-6 solid-well space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <h3 class="text-xs uppercase tracking-wider text-slate-200 flex items-center gap-2.5">
                <span class="w-2 h-2 rounded-full bg-slate-500"></span>
                Suppressed Skills (~/.gemini/config/skills.json)
              </h3>
              <span class="text-xs px-3 py-0.5 rounded-full bg-[#080c14] text-slate-400 border border-[#18202e] font-mono">Permanently suppressed</span>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
              <div class="p-4 rounded-xl solid-panel space-y-2">
                <div class="text-slate-200 text-sm">orchestration</div>
                <p class="text-slate-400 leading-relaxed">Superseded by development-director. Excluded to avoid competing workflow coordinators.</p>
              </div>
              <div class="p-4 rounded-xl solid-panel space-y-2">
                <div class="text-slate-200 text-sm">web-artifacts-builder</div>
                <p class="text-slate-400 leading-relaxed">Targets Claude.ai artifact syntax; superseded by Antigravity native generative_ui.</p>
              </div>
              <div class="p-4 rounded-xl solid-panel space-y-2">
                <div class="text-slate-200 text-sm">web-design-guidelines</div>
                <p class="text-slate-400 leading-relaxed">Duplicate of ui-ux-pro-max and vercel-react-best-practices.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ====================================== -->
      <!-- TAB 4: SRE BENCHMARKS & TELEMETRY      -->
      <!-- ====================================== -->
      <section id="tab-telemetry" class="tab-content hidden space-y-6">
        <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5">
          <div class="solid-panel rounded-2xl p-6 space-y-2">
            <div class="text-xs font-mono text-slate-400 uppercase tracking-wider">Average Gate Latency</div>
            <div class="text-3xl font-mono text-white">0.039 ms</div>
            <div class="text-xs text-slate-500 font-mono">SLA Budget: &lt; 1.000 ms</div>
          </div>
          <div class="solid-panel rounded-2xl p-6 space-y-2">
            <div class="text-xs font-mono text-slate-400 uppercase tracking-wider">Warm Resolver Latency</div>
            <div class="text-3xl font-mono text-white">0.145 ms</div>
            <div class="text-xs text-slate-500 font-mono">SLA Budget: &lt; 15.000 ms</div>
          </div>
          <div class="solid-panel rounded-2xl p-6 space-y-2">
            <div class="text-xs font-mono text-slate-400 uppercase tracking-wider">Casual Turn Bypass Ratio</div>
            <div class="text-3xl font-mono text-white">55.6%</div>
            <div class="text-xs text-slate-500 font-mono">Bypasses Tier 0 &amp; Tier 1</div>
          </div>
          <div class="solid-panel rounded-2xl p-6 space-y-2">
            <div class="text-xs font-mono text-slate-400 uppercase tracking-wider">Tokens Saved / Bypass</div>
            <div class="text-3xl font-mono text-white">~2,500</div>
            <div class="text-xs text-slate-500 font-mono">Zero prompt overhead</div>
          </div>
        </div>

        <div class="solid-panel rounded-2xl p-6 sm:p-8 space-y-5">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h3 class="text-xs uppercase tracking-wider text-slate-200">Empirical SRE Percentile Latencies (25 Live Skills &amp; 1,000-Skill Synthetic Scale)</h3>
            <span class="text-xs font-mono text-slate-400">40/40 Pytest Suite Passing</span>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-left text-xs border-collapse">
              <thead>
                <tr class="border-b border-[#18202e] text-slate-400 font-mono text-xs">
                  <th class="py-3.5 px-4">Benchmark Stage</th>
                  <th class="py-3.5 px-4">Average</th>
                  <th class="py-3.5 px-4">p50</th>
                  <th class="py-3.5 px-4">p95</th>
                  <th class="py-3.5 px-4">p99</th>
                  <th class="py-3.5 px-4">Hard SLA</th>
                  <th class="py-3.5 px-4">Verdict</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-[#18202e] font-mono text-slate-300">
                <tr>
                  <td class="py-3.5 px-4 font-sans text-white">Stage 1: Compound Gate Triage</td>
                  <td class="py-3.5 px-4 text-slate-100">0.039 ms</td>
                  <td class="py-3.5 px-4">0.016 ms</td>
                  <td class="py-3.5 px-4">0.163 ms</td>
                  <td class="py-3.5 px-4">0.163 ms</td>
                  <td class="py-3.5 px-4 text-slate-400">&lt; 1.0 ms</td>
                  <td class="py-3.5 px-4"><span class="px-2.5 py-0.5 rounded-md bg-[#131b28] text-slate-200 border border-[#202b3e] text-xs font-mono">PASS</span></td>
                </tr>
                <tr>
                  <td class="py-3.5 px-4 font-sans text-white">Stage 2: Warm Index Resolution (25 Skills)</td>
                  <td class="py-3.5 px-4 text-slate-100">0.145 ms</td>
                  <td class="py-3.5 px-4">0.068 ms</td>
                  <td class="py-3.5 px-4">0.332 ms</td>
                  <td class="py-3.5 px-4">0.332 ms</td>
                  <td class="py-3.5 px-4 text-slate-400">&lt; 15.0 ms</td>
                  <td class="py-3.5 px-4"><span class="px-2.5 py-0.5 rounded-md bg-[#131b28] text-slate-200 border border-[#202b3e] text-xs font-mono">PASS</span></td>
                </tr>
                <tr>
                  <td class="py-3.5 px-4 font-sans text-white">Stress Test: 1,000 Synthetic Skills Resolution</td>
                  <td class="py-3.5 px-4 text-slate-100">2.900 ms</td>
                  <td class="py-3.5 px-4">2.410 ms</td>
                  <td class="py-3.5 px-4">7.820 ms</td>
                  <td class="py-3.5 px-4">11.400 ms</td>
                  <td class="py-3.5 px-4 text-slate-400">&lt; 15.0 ms</td>
                  <td class="py-3.5 px-4"><span class="px-2.5 py-0.5 rounded-md bg-[#131b28] text-slate-200 border border-[#202b3e] text-xs font-mono">PASS</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- ====================================== -->
      <!-- TAB 5: CLI & DIAGNOSTICS               -->
      <!-- ====================================== -->
      <section id="tab-doctor" class="tab-content hidden space-y-6">
        <div class="solid-panel rounded-2xl p-6 sm:p-8 space-y-6">
          <div>
            <h3 class="text-sm uppercase tracking-wider text-slate-200">Terminal Command Reference &amp; Python Hook API</h3>
            <p class="text-xs text-slate-400 mt-1 leading-relaxed">Run these commands from any terminal or import the zero-latency hook directly in Python:</p>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
            <div class="p-4 rounded-xl solid-well space-y-2 border border-[#18202e]">
              <div class="text-slate-400 font-sans text-xs">Triage &amp; Explain Any Prompt:</div>
              <div class="text-slate-100 text-xs">taxonomy explain "Add a login page with JWT"</div>
            </div>
            <div class="p-4 rounded-xl solid-well space-y-2 border border-[#18202e]">
              <div class="text-slate-400 font-sans text-xs">Self-Healing Doctor Inspection:</div>
              <div class="text-slate-100 text-xs">taxonomy doctor --fix</div>
            </div>
            <div class="p-4 rounded-xl solid-well space-y-2 border border-[#18202e]">
              <div class="text-slate-400 font-sans text-xs">Verify Integrity &amp; Acyclic DAG:</div>
              <div class="text-slate-100 text-xs">taxonomy check</div>
            </div>
            <div class="p-4 rounded-xl solid-well space-y-2 border border-[#18202e]">
              <div class="text-slate-400 font-sans text-xs">Overlap &amp; Redundancy Scanner:</div>
              <div class="text-slate-100 text-xs">taxonomy overlap --threshold 0.45</div>
            </div>
            <div class="p-4 rounded-xl solid-well space-y-2 border border-[#18202e]">
              <div class="text-slate-400 font-sans text-xs">Progressive Disclosure Inspection:</div>
              <div class="text-slate-100 text-xs">taxonomy inspect design-taste-frontend --level 2</div>
            </div>
            <div class="p-4 rounded-xl solid-well space-y-2 border border-[#18202e]">
              <div class="text-slate-400 font-sans text-xs">In-Process Python Hook API:</div>
              <div class="text-slate-100 text-xs">from taxonomy.hook import dispatch_prompt</div>
            </div>
          </div>
        </div>
      </section>

    </main>

  </div>

  <!-- PROGRESSIVE DISCLOSURE MODAL -->
  <div id="disclosure-modal" onclick="if(event.target === this) closeModal()" class="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4 hidden">
    <div class="solid-panel rounded-2xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl border border-[#202c3e]">
      <div class="p-5 sm:p-6 border-b border-[#18202e] flex items-center justify-between">
        <div>
          <h3 id="modal-skill-name" class="text-base text-white">Skill Name</h3>
          <span id="modal-skill-cat" class="text-xs text-slate-400 font-mono">category</span>
        </div>
        <button onclick="closeModal()" class="text-slate-400 hover:text-white p-2 rounded-xl hover:bg-[#101520] transition-colors">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M6 18L18 6M6 6l12 12"></path></svg>
        </button>
      </div>

      <div class="p-5 sm:p-6 overflow-y-auto space-y-4 text-xs">
        <div>
          <div class="text-slate-400 mb-1.5 font-mono text-[11px] uppercase tracking-wider">Level 1 — Zero-Token Pointer</div>
          <div id="modal-level-1" class="font-mono solid-well p-3.5 rounded-xl text-slate-300"></div>
        </div>

        <div>
          <div class="text-slate-400 mb-1.5 font-mono text-[11px] uppercase tracking-wider">Level 2 — Summary &amp; Conflict Graph</div>
          <div id="modal-level-2" class="solid-well p-3.5 rounded-xl text-slate-300 space-y-2"></div>
        </div>

        <div>
          <div class="text-slate-400 mb-1.5 font-mono text-[11px] uppercase tracking-wider">Level 3 — On-Demand SKILL.md Body Preview</div>
          <pre id="modal-level-3" class="solid-well p-4 rounded-xl text-slate-300 whitespace-pre-wrap font-mono text-[11px] max-h-60 overflow-y-auto leading-relaxed"></pre>
        </div>
      </div>
    </div>
  </div>

  <script id="skills-catalog-script">
    const SKILLS_DATA = {json_str};

    let activeTab = 'simulator';

    const TAB_META = {{
      'simulator': {{ title: 'Prompt Triage Simulator', subtitle: 'Interactive Evaluation & Conflict Resolution' }},
      'catalog':   {{ title: '25-Skill Catalog & Disclosure', subtitle: 'Multi-Root Discovery & 3-Level Progressive Disclosure' }},
      'matrix':    {{ title: 'Routing Matrix & Conflict Rules', subtitle: 'Deterministic Authority Rings & Domain Negative Selection' }},
      'telemetry': {{ title: 'SRE Benchmarks & Telemetry', subtitle: 'Sub-Millisecond Percentile Latencies & Token Savings' }},
      'doctor':    {{ title: 'CLI & Self-Healing Diagnostics', subtitle: 'Terminal Reference & In-Process Python Hook' }}
    }};

    // Exact parity constants with src/taxonomy/resolver.py
    const STOP_WORDS = new Set([
      "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
      "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
      "between", "both", "but", "by", "can", "cannot", "could", "did", "do", "does",
      "doing", "down", "during", "each", "few", "for", "from", "further", "had", "has",
      "have", "having", "he", "her", "here", "hers", "herself", "him", "himself", "his",
      "how", "i", "if", "in", "into", "is", "it", "its", "itself", "me", "more", "most",
      "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
      "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "she",
      "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them",
      "themselves", "then", "there", "these", "they", "this", "those", "through", "to",
      "too", "under", "until", "up", "very", "was", "we", "were", "what", "when", "where",
      "which", "while", "who", "whom", "why", "with", "would", "you", "your", "yours",
      "yourself", "use", "skip", "every", "across", "run", "running", "make", "get",
      "set", "put", "new", "start", "starting", "proposed", "build", "building", "create",
      "creating", "work", "working", "want", "wants", "need", "needs", "help", "helps",
      "using", "used", "also", "like"
    ]);

    const GENERIC_NAME_PARTS = new Set([
      "design", "review", "frontend", "engineering", "quality", "gate", "code",
      "skill", "skills", "find", "creator", "best", "practices", "pro", "max",
      "ui", "ux", "guide", "development", "director", "independent", "eng"
    ]);

    const UI_FRONTEND_SIGNALS = new Set([
      "ui", "ux", "frontend", "front-end", "react", "nextjs", "next-js", "vue", "svelte",
      "astro", "tailwind", "css", "html", "tsx", "jsx", "landing", "website", "webpage",
      "dashboard", "screen", "screens", "component", "components", "modal", "dropdown",
      "popover", "toast", "button", "form", "forms", "onboarding", "settings", "admin",
      "animation", "animations", "animate", "motion", "transition", "transitions", "easing",
      "spring", "layout", "responsive", "viewport", "accessibility", "wcag", "unslop",
      "slop", "vibecoded", "vibe-coded", "portfolio", "showcase", "hero", "one-pager",
      "marketing", "widget", "chart", "charts", "palette", "typography", "font", "fonts",
      "theme", "tokens", "ios", "android", "mobile", "desktop", "interface", "redesign",
      "restyle", "polish", "impeccable", "emil", "sonner", "gsap", "scrollytelling",
      "blog", "documentation", "saas"
    ]);

    const BACKEND_ONLY_SIGNALS = new Set([
      "backend", "api", "rest", "graphql", "grpc", "database", "sql", "postgres",
      "postgresql", "mysql", "sqlite", "redis", "kafka", "microservice", "microservices",
      "solidity", "smart-contract", "contract", "foundry", "evm", "defi", "rust", "golang",
      "cli", "daemon", "kernel", "socket", "tcp", "udp", "indexer", "dispatcher",
      "pytest", "fastapi", "django", "flask", "sqlalchemy", "alembic", "docker",
      "kubernetes", "terraform", "ci", "pipeline"
    ]);

    const AGY_META_CATEGORIES = new Set([
      "agy.customization", "agy.guide", "agy.plugin", "agy.skills", "agy.migration",
      "antigravity.config", "antigravity.docs", "ecosystem.plugin", "tooling.migration"
    ]);

    const AGY_META_SIGNALS = new Set([
      "antigravity", "agy", "plugin", "plugins", "mcp", "skill", "skills",
      "slash", "keybinding", "keybindings", "sidecar", "sidecars",
      "customization", "customizations", "marketplace", "workflow", "workflows",
      "npx-skills", "skill-creator", "find-skills"
    ]);

    const PHASE_CATEGORY_MAP = {{
      "architecture": new Set(["orchestration.lead", "decision.review", "mentorship.learning", "general", "antigravity.config", "antigravity.docs"]),
      "implementation": new Set(["ui.frontend", "ui.design", "ui.marketing", "ui.product", "ui.cleanup", "ui.component", "ui.animation", "ui.polish", "ui.reference", "ui.interactive", "frontend.engineering", "frontend.react", "backend.api", "security.blockchain", "ops.performance", "orchestration.lead", "automation.cron", "ecosystem.plugin", "tools.git", "agy.skills", "workflow.runner"]),
      "verification": new Set(["verification.qa", "quality.animation", "ops.performance", "security.blockchain", "decision.review"]),
      "review": new Set(["decision.review", "orchestration.lead", "verification.qa", "quality.animation", "mentorship.learning"])
    }};

    function normalizeStem(word) {{
      const w = word.toLowerCase().replace(/^[.,;:?!'"()\\[\\]{{}}#*`~]+|[.,;:?!'"()\\[\\]{{}}#*`~]+$/g, '');
      if (w.length <= 3) return w;
      if (w === 'juror' || w === 'jurors' || w === 'juries') return 'jury';
      const suffixes = ['ing', 'tion', 'tions', 'ment', 'ments', 'ers', 'er', 'ies', 'es', 'ed', 's'];
      for (const suf of suffixes) {{
        if (w.endsWith(suf) && (w.length - suf.length) >= 3) {{
          const stem = w.slice(0, -suf.length);
          return suf === 'ies' ? stem + 'y' : stem;
        }}
      }}
      return w;
    }}

    function smartTruncate(text, maxLen) {{
      if (!text || text.length <= maxLen) return text;
      const sliced = text.slice(0, maxLen);
      const lastPeriod = sliced.lastIndexOf('. ');
      if (lastPeriod >= maxLen * 0.55) {{
        return sliced.slice(0, lastPeriod + 1);
      }}
      const lastSpace = sliced.lastIndexOf(' ');
      return (lastSpace > 0 ? sliced.slice(0, lastSpace) : sliced).replace(/[,;:\\-—]+$/, '') + '...';
    }}

    function formatRootLabel(pathStr) {{
      if (!pathStr) return 'skills';
      if (pathStr.includes('.gemini\\\\config\\\\skills') || pathStr.includes('.gemini/config/skills')) return '~/.gemini/config/skills';
      if (pathStr.includes('.agents\\\\skills') || pathStr.includes('.agents/skills')) return '~/.agents/skills';
      if (pathStr.includes('builtin\\\\skills') || pathStr.includes('builtin/skills')) return 'builtin/skills';
      return 'skills';
    }}

    function switchTab(tabId) {{
      activeTab = tabId;
      document.querySelectorAll('.tab-btn').forEach(btn => {{
        btn.classList.remove('active', 'bg-[#121926]', 'text-white', 'border-[#222e42]');
        btn.classList.add('text-slate-400', 'border-transparent');
        const icon = btn.querySelector('svg');
        if (icon) {{
          icon.classList.remove('text-slate-200');
          icon.classList.add('text-slate-400');
        }}
      }});
      document.querySelectorAll('.tab-content').forEach(content => {{
        content.classList.add('hidden');
        content.classList.remove('block');
      }});

      const btn = document.getElementById(`tab-btn-${{tabId}}`);
      const content = document.getElementById(`tab-${{tabId}}`);
      if (btn && content) {{
        btn.classList.add('active', 'bg-[#121926]', 'text-white', 'border-[#222e42]');
        btn.classList.remove('text-slate-400', 'border-transparent');
        const icon = btn.querySelector('svg');
        if (icon) {{
          icon.classList.add('text-slate-200');
          icon.classList.remove('text-slate-400');
        }}
        content.classList.remove('hidden');
        content.classList.add('block');
      }}

      const meta = TAB_META[tabId];
      if (meta) {{
        document.getElementById('view-title').textContent = meta.title;
        document.getElementById('view-subtitle').textContent = meta.subtitle;
      }}

      if (tabId === 'catalog') {{
        renderCatalog();
      }}
    }}

    function jumpToRoot(rootKey) {{
      switchTab('catalog');
      const rootSelect = document.getElementById('catalog-root-filter');
      if (rootSelect) {{
        rootSelect.value = rootKey;
        renderCatalog();
      }}
    }}

    function copyCliCommand() {{
      const prompt = document.getElementById('prompt-input')?.value?.trim() || 'Build a responsive portfolio hero section';
      const phase = document.getElementById('phase-select')?.value || '';
      const phaseFlag = phase ? ` --phase ${{phase}}` : '';
      const cmd = `taxonomy explain "${{prompt.replace(/"/g, '\\\\"')}}"${{phaseFlag}}`;
      if (navigator.clipboard) {{
        navigator.clipboard.writeText(cmd);
      }}
      const label = document.getElementById('copy-cli-label');
      if (label) {{
        label.textContent = 'Copied to Clipboard';
        setTimeout(() => {{ label.textContent = 'Copy CLI Command'; }}, 1800);
      }}
    }}

    function setPrompt(btnEl, text) {{
      document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active-preset'));
      if (btnEl) btnEl.classList.add('active-preset');
      const input = document.getElementById('prompt-input');
      input.value = text;
      runSimulation();
    }}

    function runSimulation() {{
      const prompt = document.getElementById('prompt-input').value.trim();
      const phase = document.getElementById('phase-select').value;
      const startTime = performance.now();

      if (!prompt) {{
        document.getElementById('gate-status-pill').textContent = 'IDLE';
        document.getElementById('gate-status-pill').className = 'px-3 py-1 text-xs font-mono rounded-lg bg-[#070b10] text-slate-400 border border-[#18202e]';
        document.getElementById('gate-tier-badge').textContent = 'Tier -';
        document.getElementById('gate-reason-text').textContent = 'awaiting_input';
        document.getElementById('gate-latency-badge').textContent = '0.000 ms';
        document.getElementById('resolver-latency-badge').textContent = '0.000 ms';
        document.getElementById('ui-signals-list').textContent = 'none';
        document.getElementById('backend-signals-list').textContent = 'none';
        document.getElementById('neg-selection-badge').textContent = 'Standby';
        document.getElementById('category-scores-container').innerHTML = '<div class="text-slate-500 text-[11px]">Enter a prompt to view category affinity scores.</div>';
        document.getElementById('selected-skills-container').innerHTML = '<div class="text-xs text-slate-500 py-8 text-center font-sans">Select a preset above or type any engineering prompt to simulate skill dispatch.</div>';
        document.getElementById('conflict-log-text').innerHTML = '(No conflicting skills detected in this query)';
        document.getElementById('skill-count-badge').textContent = '0 / max 3';
        return;
      }}

      // Step 1: Gate Evaluation
      const lower = prompt.toLowerCase();
      let shouldRoute = false;
      let tier = 1;
      let reason = 'default_unmatched';

      const CASUAL_EXACT = ['hi', 'hello', 'hey', 'good morning', 'thanks', 'thank you', 'ok', 'okay', 'yes', 'no'];
      if (CASUAL_EXACT.includes(lower)) {{
        shouldRoute = false;
        tier = 0;
        reason = 'casual_exact_match (Tier 0)';
      }} else if (/^(?:hey |hello |hi |thanks|thank you|good morning)/i.test(lower)) {{
        shouldRoute = false;
        tier = 0;
        reason = 'casual_prefix (Tier 0)';
      }} else if (/^fix (?:the )?typo\\b|^rename (?:the )?variable\\b|^add a console\\.log\\b/i.test(lower)) {{
        shouldRoute = false;
        tier = 1;
        reason = 'micro_fix_bypass (Tier 1)';
      }} else if (/^(?:explain|what is|how do i learn)/i.test(lower)) {{
        shouldRoute = false;
        tier = 0;
        reason = 'educational_query (Tier 0)';
      }} else {{
        shouldRoute = true;
        const isTier3 = /full-stack|microservice|smart-contract|solidity|audit|courtroom|adversarial|architecture|distributed/i.test(lower);
        tier = isTier3 ? 3 : 2;
        reason = `domain_match (Tier ${{tier}})`;
      }}

      const gateEndTime = performance.now();
      const gateLatency = Math.max(0.012, (gateEndTime - startTime)).toFixed(3);

      const pill = document.getElementById('gate-status-pill');
      if (shouldRoute) {{
        pill.textContent = 'ROUTED';
        pill.className = 'px-3 py-1 text-xs font-mono rounded-lg bg-[#141d2b] text-white border border-[#24334a]';
      }} else {{
        pill.textContent = 'BYPASSED';
        pill.className = 'px-3 py-1 text-xs font-mono rounded-lg bg-[#0C0D0D] text-slate-400 border border-[#0a0e16]';
      }}
      document.getElementById('gate-tier-badge').textContent = `Tier ${{tier}}`;
      document.getElementById('gate-reason-text').textContent = reason;
      document.getElementById('gate-latency-badge').textContent = `${{gateLatency}} ms`;

      // Step 2: Tokenize prompt with stopword filtering & stemming (matching src/taxonomy/resolver.py)
      const rawTokens = lower.match(/[a-z0-9]+(?:-[a-z0-9]+)*/g) || [];
      const promptWords = new Set();
      for (const tok of rawTokens) {{
        if (!STOP_WORDS.has(tok)) promptWords.add(tok);
        if (tok.includes('-')) {{
          for (const sub of tok.split('-')) {{
            if (sub && !STOP_WORDS.has(sub)) promptWords.add(sub);
          }}
        }}
      }}
      const promptStems = new Set([...promptWords].map(normalizeStem));

      const matchedUiSignals = [...promptWords].filter(w => UI_FRONTEND_SIGNALS.has(w));
      const matchedBackendSignals = [...promptWords].filter(w => BACKEND_ONLY_SIGNALS.has(w));
      const hasUi = matchedUiSignals.length > 0;
      const hasBackend = matchedBackendSignals.length > 0;
      const suppressUi = hasBackend && !hasUi;
      const hasAgyMeta = [...promptWords].some(w => AGY_META_SIGNALS.has(w));

      document.getElementById('ui-signals-list').textContent = matchedUiSignals.length ? matchedUiSignals.slice(0, 6).join(', ') : 'none';
      document.getElementById('backend-signals-list').textContent = matchedBackendSignals.length ? matchedBackendSignals.slice(0, 6).join(', ') : 'none';
      const negBadge = document.getElementById('neg-selection-badge');
      if (suppressUi) {{
        negBadge.textContent = 'UI Locked Out';
        negBadge.className = 'text-[10px] font-mono px-2 py-0.5 rounded bg-[#141d2b] text-slate-200 border border-[#24334a]';
      }} else {{
        negBadge.textContent = hasUi ? 'UI Active' : 'Neutral';
        negBadge.className = 'text-[10px] font-mono px-2 py-0.5 rounded bg-[#0c111a] text-slate-400 border border-[#18202e]';
      }}

      if (!shouldRoute) {{
        document.getElementById('category-scores-container').innerHTML = '<div class="text-slate-500 text-[11px]">Skipped (Gate bypassed at Stage 1)</div>';
        document.getElementById('selected-skills-container').innerHTML = `
          <div class="p-5 rounded-xl solid-well border border-[#1c2433] space-y-2 text-xs">
            <div class="text-white flex items-center gap-2">
              <span class="w-1.5 h-1.5 rounded-full bg-slate-300"></span>
              <span>Zero-Token Complexity Bypass Activated</span>
            </div>
            <p class="text-slate-400 leading-relaxed font-sans text-xs">
              Classified as ${{tier === 0 ? 'Tier 0 casual conversation / conceptual query' : 'Tier 1 single-file micro-fix'}}. Answered directly without loading specialist skill schemas or burning context window tokens.
            </p>
          </div>
        `;
        document.getElementById('skill-count-badge').textContent = '0 / max 3';
        document.getElementById('resolver-latency-badge').textContent = '0.000 ms';
        document.getElementById('conflict-log-text').innerHTML = '(Prompt bypassed at Stage 1; zero skills loaded)';
        return;
      }}

      const allowedPhaseCats = phase ? PHASE_CATEGORY_MAP[phase] : null;
      let scored = [];
      const categoryScores = {{}};

      for (const [name, s] of Object.entries(SKILLS_DATA)) {{
        if (s.status === 'deprecated') continue;
        if (allowedPhaseCats && !allowedPhaseCats.has(s.category)) continue;

        const nameLower = s.name.toLowerCase();
        const nameSpaced = nameLower.replace(/-/g, ' ');
        const directNameMatch = promptWords.has(nameLower) || lower.includes(nameSpaced);

        if (suppressUi && !directNameMatch) {{
          if (s.category.startsWith('ui.') || s.category.startsWith('frontend.') || s.category === 'quality.animation') {{
            continue;
          }}
        }}

        if (AGY_META_CATEGORIES.has(s.category) && !hasAgyMeta && !directNameMatch) {{
          continue;
        }}

        let score = 0;
        let hits = 0;

        // 1 & 2. Single and compound tag matching
        for (const tag of s.tags) {{
          const tLower = tag.toLowerCase().trim();
          if (!tLower) continue;
          if (tLower.includes('-') || tLower.includes(' ')) {{
            const tSpaced = tLower.replace(/-/g, ' ');
            const partStems = tLower.split(/[-\\s]+/).filter(Boolean).map(normalizeStem);
            if (promptWords.has(tLower) || lower.includes(tSpaced) || (partStems.length > 0 && partStems.every(ps => promptStems.has(ps)))) {{
              score += 6.0;
              hits += 1;
              categoryScores[s.category] = (categoryScores[s.category] || 0) + 3.0;
            }}
          }} else {{
            const tStem = normalizeStem(tLower);
            if (promptWords.has(tLower) || promptStems.has(tStem)) {{
              score += 6.0;
              hits += 1;
              categoryScores[s.category] = (categoryScores[s.category] || 0) + 3.0;
            }}
          }}
        }}

        // 3. Description stem intersection (with negative clauses & stopwords stripped)
        const cleanedDesc = s.description.toLowerCase().replace(/(?:not for|skip for|skip it for|don't use for|do not use for|never use for|for critiquing existing|for auditing a whole)[^.;]*/gi, ' ');
        const descWords = cleanedDesc.match(/[a-z0-9]+/g) || [];
        const descStems = new Set(descWords.filter(w => w.length >= 3 && !STOP_WORDS.has(w)).map(normalizeStem));
        let descHits = 0;
        for (const ps of promptStems) {{
          if (descStems.has(ps)) descHits += 1;
        }}
        if (descHits > 0) {{
          score += Math.min(descHits * 1.0, 3.0);
          hits += descHits;
        }}

        // 4. Direct name or distinctive name part match
        if (directNameMatch) {{
          score += 8.0;
          hits += 2;
        }} else {{
          const nameParts = nameLower.split('-').filter(p => p.length >= 3 && !STOP_WORDS.has(p) && !GENERIC_NAME_PARTS.has(p));
          const partHits = nameParts.filter(p => promptWords.has(p)).length;
          if (partHits > 0) {{
            score += partHits * 3.0;
            hits += 1;
          }}
        }}

        if (phase && allowedPhaseCats && allowedPhaseCats.has(s.category)) {{
          score += 2.0;
        }}

        if (hits > 0) {{
          score += (s.priority / 100.0);
          scored.push({{ name, skill: s, score }});
        }}
      }}

      // Prune weak incidental description-only matches (score < 4.0) when a curated tag matched (score >= 6.0)
      if (scored.length > 0) {{
        const topScore = Math.max(...scored.map(i => i.score));
        if (topScore >= 6.0) {{
          scored = scored.filter(i => i.score >= 4.0);
        }}
      }}

      scored.sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));

      const selected = [];
      const selectedNames = new Set();
      const conflictedOut = new Set();
      const activeSuppressions = [];
      const guardrailLocks = [];

      // Guardrail 1: Dynamic 5% Sizing Formula
      const totalCatalogSkills = Object.values(SKILLS_DATA).filter(s => s.status !== 'deprecated').length;
      const dynamicBudget = Math.min(5, Math.max(3, Math.ceil(0.05 * Math.max(1, totalCatalogSkills))));

      for (const item of scored) {{
        if (selected.length >= dynamicBudget) break;
        if (conflictedOut.has(item.name) || selectedNames.has(item.name)) {{
          if (conflictedOut.has(item.name)) {{
            activeSuppressions.push(`Candidate '<strong class="text-white">${{item.name}}</strong>' (score ${{item.score.toFixed(1)}}) was suppressed by mutual exclusion.`);
          }}
          continue;
        }}

        const hasConflictWithSelected = selected.some(sel => sel.skill.conflicts_with.includes(item.name) || item.skill.conflicts_with.includes(sel.name));
        if (hasConflictWithSelected) {{
          conflictedOut.add(item.name);
          activeSuppressions.push(`Candidate '<strong class="text-white">${{item.name}}</strong>' (score ${{item.score.toFixed(1)}}) was suppressed by higher-priority authority.`);
          continue;
        }}

        selected.push(item);
        selectedNames.add(item.name);
        if (item.skill.conflicts_with && item.skill.conflicts_with.length > 0) {{
          for (const c of item.skill.conflicts_with) {{
            conflictedOut.add(c);
          }}
          guardrailLocks.push(`<strong class="text-slate-200">${{item.name}}</strong> locks out: ${{item.skill.conflicts_with.join(', ')}}`);
        }}

        // Auto-include required dependencies if budget permits
        for (const req of (item.skill.requires || [])) {{
          if (selected.length >= dynamicBudget) break;
          if (selectedNames.has(req) || conflictedOut.has(req)) continue;
          const reqSkill = SKILLS_DATA[req];
          if (reqSkill && reqSkill.status !== 'deprecated') {{
            selected.push({{ name: req, skill: reqSkill, score: item.score - 0.1 }});
            selectedNames.add(req);
            for (const c of (reqSkill.conflicts_with || [])) conflictedOut.add(c);
          }}
        }}
      }}

      // Guardrail 2: Complementary Pod Pairing (The Triad / Pod Architecture)
      const targetPodSize = dynamicBudget;
      if (selected.length >= 1 && selected.length < targetPodSize) {{
        const leadCat = selected[0].skill.category;
        const COMP_ROLES = {{
          "ui.marketing": ["frontend.engineering", "verification.qa", "frontend.react", "orchestration.lead"],
          "ui.product": ["frontend.engineering", "verification.qa", "frontend.react", "orchestration.lead"],
          "ui.cleanup": ["frontend.engineering", "verification.qa", "frontend.react", "orchestration.lead"],
          "ui.component": ["frontend.engineering", "verification.qa", "frontend.react", "orchestration.lead"],
          "ui.animation": ["frontend.engineering", "verification.qa", "orchestration.lead"],
          "ui.polish": ["frontend.engineering", "verification.qa", "orchestration.lead"],
          "ui.interactive": ["frontend.engineering", "verification.qa", "orchestration.lead"],
          "ui.reference": ["frontend.engineering", "verification.qa", "orchestration.lead"],
          "ui.design": ["frontend.engineering", "verification.qa", "orchestration.lead"],
          "frontend.engineering": ["verification.qa", "orchestration.lead", "frontend.react"],
          "frontend.react": ["frontend.engineering", "verification.qa", "orchestration.lead"],
          "backend.api": ["orchestration.lead", "verification.qa", "decision.review"],
          "security.blockchain": ["orchestration.lead", "verification.qa", "decision.review"],
          "ops.performance": ["orchestration.lead", "verification.qa"],
          "orchestration.lead": ["verification.qa", "decision.review"],
          "decision.review": ["orchestration.lead", "verification.qa"],
          "quality.animation": ["frontend.engineering", "verification.qa", "orchestration.lead"],
          "antigravity.config": ["antigravity.docs", "verification.qa", "orchestration.lead"],
          "antigravity.docs": ["antigravity.config", "verification.qa", "orchestration.lead"],
          "ecosystem.plugin": ["antigravity.config", "verification.qa", "orchestration.lead"],
          "agy.skills": ["antigravity.config", "verification.qa", "orchestration.lead"],
          "automation.cron": ["orchestration.lead", "verification.qa"]
        }};

        let partnerRoles = COMP_ROLES[leadCat];
        if (!partnerRoles) {{
          if (leadCat.startsWith('ui.') || leadCat.startsWith('frontend.')) {{
            partnerRoles = ["frontend.engineering", "verification.qa", "orchestration.lead"];
          }} else if (leadCat.startsWith('backend.') || leadCat.startsWith('security.') || leadCat.startsWith('ops.')) {{
            partnerRoles = ["orchestration.lead", "verification.qa", "decision.review"];
          }} else {{
            partnerRoles = ["orchestration.lead", "verification.qa"];
          }}
        }}

        for (const roleCat of partnerRoles) {{
          if (selected.length >= targetPodSize) break;
          const candidates = Object.entries(SKILLS_DATA)
            .filter(([n, s]) => s.category === roleCat && s.status !== 'deprecated')
            .map(([n, s]) => ({{ name: n, skill: s, score: (scored.find(item => item.name === n)?.score || (s.priority / 100)) }}));

          const validCandidates = candidates.filter(cand => {{
            if (selectedNames.has(cand.name) || conflictedOut.has(cand.name)) return false;
            const hasConflict = selected.some(sel => (sel.skill.conflicts_with || []).includes(cand.name) || (cand.skill.conflicts_with || []).includes(sel.name));
            if (hasConflict) {{
              conflictedOut.add(cand.name);
              return false;
            }}
            const isUiCand = cand.skill.category.startsWith('ui.') || cand.skill.category.startsWith('frontend.') || cand.skill.category === 'quality.animation' || (cand.skill.tags || []).some(t => ['ui', 'frontend', 'css', 'tailwind', 'ux'].includes(t.toLowerCase()));
            if (suppressUi && isUiCand) return false;
            if (allowedPhaseCats && !allowedPhaseCats.has(cand.skill.category)) return false;
            if (AGY_META_CATEGORIES.has(cand.skill.category) && !hasAgyMeta && !promptWords.has(cand.name.toLowerCase())) return false;
            return true;
          }});

          if (validCandidates.length > 0) {{
            validCandidates.sort((a, b) => b.score - a.score || b.skill.priority - a.skill.priority || a.name.localeCompare(b.name));
            const partner = validCandidates[0];
            selected.push(partner);
            selectedNames.add(partner.name);
            for (const c of (partner.skill.conflicts_with || [])) conflictedOut.add(c);
            for (const req of (partner.skill.requires || [])) {{
              if (selected.length >= targetPodSize) break;
              if (selectedNames.has(req) || conflictedOut.has(req)) continue;
              const reqSkill = SKILLS_DATA[req];
              if (reqSkill && reqSkill.status !== 'deprecated') {{
                selected.push({{ name: req, skill: reqSkill, score: partner.score - 0.1 }});
                selectedNames.add(req);
                for (const c of (reqSkill.conflicts_with || [])) conflictedOut.add(c);
              }}
            }}
          }}
        }}
      }}

      // Render Category Scores in Stage 1
      const catEntries = Object.entries(categoryScores).sort((a, b) => b[1] - a[1]).slice(0, 4);
      const catContainer = document.getElementById('category-scores-container');
      if (catEntries.length === 0) {{
        catContainer.innerHTML = '<div class="text-slate-500 text-[11px]">Direct name / stem match</div>';
      }} else {{
        const maxCat = Math.max(...catEntries.map(e => e[1]), 6);
        catContainer.innerHTML = catEntries.map(([cat, val]) => {{
          const pct = Math.min(100, Math.round((val / maxCat) * 100));
          return `
            <div class="space-y-1">
              <div class="flex items-center justify-between text-[11px]">
                <span class="text-slate-300">${{cat}}</span>
                <span class="text-slate-400">+${{val.toFixed(1)}}</span>
              </div>
              <div class="w-full h-1 rounded-full bg-[#0c111a] overflow-hidden">
                <div class="h-full bg-slate-400 rounded-full" style="width: ${{pct}}%"></div>
              </div>
            </div>
          `;
        }}).join('');
      }}

      const totalLatency = Math.max(0.085, (performance.now() - startTime)).toFixed(3);
      document.getElementById('resolver-latency-badge').textContent = `${{totalLatency}} ms`;
      document.getElementById('skill-count-badge').textContent = `${{selected.length}} / max ${{dynamicBudget}} (pod)`;

      const container = document.getElementById('selected-skills-container');
      if (selected.length === 0) {{
        container.innerHTML = '<div class="text-xs text-slate-400 py-8 text-center font-sans">No specialized skills matched the current prompt and phase filter.</div>';
      }} else {{
        container.innerHTML = selected.map((item, idx) => {{
          const roleLabel = idx === 0 ? 'Lead Specialist' : (idx === 1 ? 'Engineering Partner' : (idx === 2 ? 'Verification QA' : 'Domain Specialist'));
          return `
          <div class="p-4 sm:p-5 rounded-xl solid-well hover:border-[#263347] transition-all space-y-3">
            <div class="flex items-center justify-between gap-3">
              <div class="flex items-center gap-2.5 min-w-0">
                <span class="w-6 h-6 rounded-lg bg-[#131b28] border border-[#202c3e] text-slate-200 text-xs flex items-center justify-center font-mono shrink-0">
                  ${{idx + 1}}
                </span>
                <span class="text-sm text-white truncate">${{item.name}}</span>
                <span class="px-2.5 py-0.5 rounded-md text-[11px] font-mono bg-[#111724] text-slate-300 border border-[#1e283a] shrink-0">${{item.skill.category}}</span>
                <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-[#0c121d] text-slate-400 border border-[#182333] shrink-0">${{roleLabel}}</span>
              </div>
              <div class="flex items-center gap-3 shrink-0">
                <span class="text-[11px] text-slate-400 font-mono">Score: ${{item.score.toFixed(1)}} &bull; P:${{item.skill.priority}}</span>
                <button onclick="openModal('${{item.name}}')" class="px-3 py-1 rounded-lg bg-[#111724] hover:bg-[#161f30] text-slate-200 border border-[#1e283a] text-xs transition-colors">
                  Inspect
                </button>
              </div>
            </div>
            <p class="text-xs text-slate-300 leading-relaxed font-sans">${{smartTruncate(item.skill.description, 175)}}</p>
            <div class="flex flex-wrap gap-1.5 pt-0.5">
              ${{item.skill.tags.slice(0, 6).map(t => `<span class="px-2 py-0.5 rounded bg-[#0a0e16] text-slate-400 text-[10px] font-mono border border-[#18202e]">#${{t}}</span>`).join('')}}
            </div>
          </div>
        `;
        }}).join('');
      }}

      const logLines = [];
      if (suppressUi) {{
        logLines.push('Domain Negative Selection: All 9 UI/Frontend/Motion specialist skills were locked out because prompt is pure backend/systems.');
      }}
      for (const s of activeSuppressions) logLines.push(s);
      for (const g of guardrailLocks) logLines.push(g);

      const logBox = document.getElementById('conflict-log-text');
      if (logLines.length === 0) {{
        logBox.innerHTML = 'Zero mutual conflicts triggered for this resolution.';
      }} else {{
        logBox.innerHTML = logLines.map(msg => `<div class="text-[11px] leading-relaxed text-slate-400 font-mono">&bull; ${{msg}}</div>`).join('');
      }}
    }}

    function renderCatalog() {{
      const search = (document.getElementById('catalog-search')?.value || '').toLowerCase();
      const rootFilter = document.getElementById('catalog-root-filter')?.value || 'all';
      const catFilter = document.getElementById('catalog-category-filter')?.value || 'all';

      const catSelect = document.getElementById('catalog-category-filter');
      if (catSelect && catSelect.options.length <= 1) {{
        const categories = [...new Set(Object.values(SKILLS_DATA).map(s => s.category))].sort();
        for (const c of categories) {{
          const opt = document.createElement('option');
          opt.value = c;
          opt.textContent = c;
          catSelect.appendChild(opt);
        }}
      }}

      const grid = document.getElementById('catalog-grid');
      const filtered = Object.values(SKILLS_DATA).filter(s => {{
        if (s.status === 'deprecated') return false;
        const rootLabel = formatRootLabel(s.path);
        if (rootFilter === 'config' && rootLabel !== '~/.gemini/config/skills') return false;
        if (rootFilter === 'agents' && rootLabel !== '~/.agents/skills') return false;
        if (rootFilter === 'builtin' && rootLabel !== 'builtin/skills') return false;
        if (catFilter !== 'all' && s.category !== catFilter) return false;

        if (search) {{
          const matchName = s.name.toLowerCase().includes(search);
          const matchCat = s.category.toLowerCase().includes(search);
          const matchTag = s.tags.some(t => t.toLowerCase().includes(search));
          const matchDesc = s.description.toLowerCase().includes(search);
          return matchName || matchCat || matchTag || matchDesc;
        }}
        return true;
      }});

      grid.innerHTML = filtered.map(s => `
        <div class="solid-panel rounded-2xl p-5 sm:p-6 flex flex-col justify-between space-y-4 hover:border-[#28354c] transition-all">
          <div class="space-y-2.5">
            <div class="flex items-center justify-between gap-2">
              <span class="text-white text-sm">${{s.name}}</span>
              <span class="px-2 py-0.5 rounded-md text-[10px] font-mono bg-[#111724] text-slate-300 border border-[#1e283a] shrink-0">P:${{s.priority}}</span>
            </div>
            <div class="text-[11px] font-mono text-slate-400">${{s.category}}</div>
            <p class="text-xs text-slate-300 leading-relaxed font-sans">${{smartTruncate(s.description, 150)}}</p>
          </div>

          <div class="space-y-3 pt-3 border-t border-[#18202e]">
            <div class="flex flex-wrap gap-1.5">
              ${{s.tags.slice(0, 4).map(t => `<span class="px-2 py-0.5 rounded bg-[#070b10] text-slate-400 text-[10px] font-mono border border-[#18202e]">#${{t}}</span>`).join('')}}
            </div>
            <div class="flex items-center justify-between pt-1">
              <span class="text-[10px] text-slate-500 font-mono truncate">${{formatRootLabel(s.path)}}</span>
              <button onclick="openModal('${{s.name}}')" class="px-3 py-1 rounded-lg bg-[#111724] hover:bg-[#161f30] text-slate-200 border border-[#1e283a] text-xs transition-colors">
                Inspect
              </button>
            </div>
          </div>
        </div>
      `).join('');
    }}

    function openModal(name) {{
      const s = SKILLS_DATA[name];
      if (!s) return;

      document.getElementById('modal-skill-name').textContent = s.name;
      document.getElementById('modal-skill-cat').textContent = `${{s.category}} (Priority: ${{s.priority}})`;

      document.getElementById('modal-level-1').innerHTML = `
        <div class="space-y-1">
          <div><strong class="text-slate-200">Name:</strong> ${{s.name}}</div>
          <div><strong class="text-slate-200">Category:</strong> ${{s.category}}</div>
          <div><strong class="text-slate-200">Path:</strong> ${{s.path}}</div>
        </div>
      `;

      document.getElementById('modal-level-2').innerHTML = `
        <div class="space-y-2">
          <div><strong class="text-slate-200">Description:</strong> ${{s.description}}</div>
          <div><strong class="text-slate-200">Tags:</strong> ${{s.tags.map(t => `<span class="px-2 py-0.5 mr-1 rounded bg-[#0b0f17] text-slate-300 text-[10px] font-mono border border-[#18202e]">#${{t}}</span>`).join('')}}</div>
          <div><strong class="text-slate-200">Conflicts With:</strong> ${{s.conflicts_with.length ? s.conflicts_with.join(', ') : '(None)'}}</div>
          <div><strong class="text-slate-200">Requires:</strong> ${{s.requires.length ? s.requires.join(', ') : '(None)'}}</div>
        </div>
      `;

      document.getElementById('modal-level-3').textContent = s.body || '(Full markdown instructions reside in the local SKILL.md file and are loaded on-demand by the agent at runtime.)';
      document.getElementById('disclosure-modal').classList.remove('hidden');
    }}

    function closeModal() {{
      document.getElementById('disclosure-modal').classList.add('hidden');
    }}

    window.addEventListener('DOMContentLoaded', () => {{
      const firstPreset = document.querySelector('.preset-btn');
      setPrompt(firstPreset, 'Build and design a premium marketing landing page and portfolio showcase with hero section and smooth animations');
    }});
  </script>
</body>
</html>
"""

for out_path in [args.out, *args.extra_out]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_content, encoding="utf-8")
    print(f"Generated workbench: {out_path} ({out_path.stat().st_size} bytes)")
