"""Universal Agent Integration Adapters & Hook Formatting Contracts (ISS-27).

Provides host-independent integration adapters for:
- Claude Code (UserPromptSubmit hook JSON/stdout format)
- Cursor / Windsurf (context prompt and rule injection)
- Model Context Protocol (MCP tools and dynamic prompts)
- OpenAI / Anthropic tool calling definitions
- Google Antigravity & Gemini CLI instruction tags
- Generic JSON / Markdown progressive disclosure contracts
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
from typing import Any, Dict, List, Optional

from taxonomy.models import ResolutionResult, SkillMetadata


@dataclass
class AdapterPayload:
    """Universal dispatch payload container."""

    agent: str
    prompt: str
    resolution: ResolutionResult
    additional_context: str
    raw_payload: Dict[str, Any] = field(default_factory=dict)
    selected_skill_names: List[str] = field(default_factory=list)
    candidate_summaries: List[Dict[str, Any]] = field(default_factory=list)
    instruction_bodies: Dict[str, str] = field(default_factory=dict)
    shadow_mode: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "prompt": self.prompt,
            "selected_skills": self.selected_skill_names,
            "additional_context": self.additional_context,
            "raw_payload": self.raw_payload,
            "candidate_summaries": self.candidate_summaries,
            "instruction_bodies": self.instruction_bodies,
            "shadow_mode": self.shadow_mode,
            "resolution": self.resolution.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def build_progressive_context(
    result: ResolutionResult,
    fallback_candidates: Optional[List[SkillMetadata]] = None,
) -> str:
    """Build progressive disclosure markdown instructions.

    Rules:
    - If gate says don't route and no skills selected: return empty string (0 token tax).
    - If shadow mode: return empty string (non-disruptive, does not alter prompt).
    - For selected skills: retrieve Level-3 full instructions from SKILL.md.
    - For runner-up candidates: inject Level-2 summary cards so the agent has
      recovery awareness if requirements evolve during conversation.
    """
    if result.shadow_mode:
        return ""

    if not result.selected_skills:
        return ""

    sections: List[str] = []

    # Level 3: Full instructions for active selected specialist skills
    for s in result.selected_skills:
        instructions = s.get_full_instructions()
        sec = [
            f"# Active Specialist Skill: {s.name} [{s.category}]",
            f"**Description**: {s.description}",
            f"**Priority**: {s.priority} | **Trust**: {s.trust_level} | **Version**: {s.version}",
        ]
        if s.tags:
            sec.append(f"**Tags**: {', '.join(s.tags)}")
        if instructions:
            sec.append(f"\n## Instructions\n{instructions}")
        sections.append("\n".join(sec))

    # Level 2: Summary cards for alternative / fallback candidates if available
    if fallback_candidates:
        alt_cards: List[str] = []
        sel_names = {sel.name for sel in result.selected_skills}
        for alt in fallback_candidates:
            if alt.name in sel_names or getattr(alt, "status", "active") == "deprecated":
                continue
            card = alt.to_summary()
            alt_cards.append(
                f"- **{card['name']}** [{card['category']}]: {card['description']}"
            )
            if len(alt_cards) >= 3:
                break
        if alt_cards:
            sections.append(
                "## Alternative Available Specialists (Activate on Request)\n" + "\n".join(alt_cards)
            )

    return "\n\n---\n\n".join(sections)


class BaseAgentAdapter(ABC):
    """Abstract base class for all host agent adapters."""

    agent_name: str = "base"
    aliases: List[str] = []

    @abstractmethod
    def build_payload(
        self,
        result: ResolutionResult,
        prompt: str,
        fallback_candidates: Optional[List[SkillMetadata]] = None,
    ) -> AdapterPayload:
        """Transform ResolutionResult into the agent's native payload."""
        pass

    def format_output(self, payload: AdapterPayload, as_json: bool = False) -> str:
        """Format the payload for CLI output or stdout hook consumption."""
        if as_json or payload.raw_payload:
            return json.dumps(payload.raw_payload, indent=2)
        return payload.additional_context


class ClaudeCodeAdapter(BaseAgentAdapter):
    """Adapter for Claude Code CLI hooks (UserPromptSubmit hook contract)."""

    agent_name = "claude"
    aliases = ["claude-code", "claude_code", "claudecode"]

    def build_payload(
        self,
        result: ResolutionResult,
        prompt: str,
        fallback_candidates: Optional[List[SkillMetadata]] = None,
    ) -> AdapterPayload:
        context = build_progressive_context(result, fallback_candidates)
        selected_names = [s.name for s in result.selected_skills]
        shadow_names = [s.name for s in result.shadow_skills]

        # Claude Code UserPromptSubmit hook structure
        raw_payload = {
            "hookSpecificOutput": {
                "additionalContext": context,
                "continue": True,
                "suppressOutput": False,
            },
            "taxonomy": {
                "tier": result.gate.tier,
                "should_route": result.gate.should_route,
                "confidence": result.confidence,
                "confidence_score": round(result.confidence_score, 2),
                "margin": round(result.margin, 2),
                "selected_skills": selected_names,
                "shadow_mode": result.shadow_mode,
                "shadow_skills": shadow_names,
                "attribution_id": result.attribution_id,
                "catalog_hash": result.catalog_hash,
                "config_hash": result.config_hash,
                "total_latency_ms": round(result.total_latency_ms, 3),
            },
        }

        summaries = [s.to_summary() for s in (fallback_candidates or [])]
        bodies = {s.name: s.get_full_instructions() for s in result.selected_skills}

        return AdapterPayload(
            agent=self.agent_name,
            prompt=prompt,
            resolution=result,
            additional_context=context,
            raw_payload=raw_payload,
            selected_skill_names=selected_names,
            candidate_summaries=summaries,
            instruction_bodies=bodies,
            shadow_mode=result.shadow_mode,
        )


class CursorAdapter(BaseAgentAdapter):
    """Adapter for Cursor and Windsurf editors (.cursorrules / context injection)."""

    agent_name = "cursor"
    aliases = ["windsurf", "cursor-editor", "windsurf-editor"]

    def build_payload(
        self,
        result: ResolutionResult,
        prompt: str,
        fallback_candidates: Optional[List[SkillMetadata]] = None,
    ) -> AdapterPayload:
        context = build_progressive_context(result, fallback_candidates)
        selected_names = [s.name for s in result.selected_skills]
        shadow_names = [s.name for s in result.shadow_skills]

        rules = []
        for s in result.selected_skills:
            rules.append(f"Follow conventions from skill '{s.name}' ({s.description})")

        raw_payload = {
            "system_prompt_addition": context,
            "rules": rules,
            "skills_loaded": selected_names,
            "tier": result.gate.tier,
            "confidence": result.confidence,
            "shadow_mode": result.shadow_mode,
            "shadow_skills": shadow_names,
            "catalog_hash": result.catalog_hash,
        }

        summaries = [s.to_summary() for s in (fallback_candidates or [])]
        bodies = {s.name: s.get_full_instructions() for s in result.selected_skills}

        return AdapterPayload(
            agent=self.agent_name,
            prompt=prompt,
            resolution=result,
            additional_context=context,
            raw_payload=raw_payload,
            selected_skill_names=selected_names,
            candidate_summaries=summaries,
            instruction_bodies=bodies,
            shadow_mode=result.shadow_mode,
        )


class MCPAdapter(BaseAgentAdapter):
    """Adapter for Model Context Protocol (MCP) dynamic tool & prompt routers."""

    agent_name = "mcp"
    aliases = ["model-context-protocol", "mcp-server", "mcptools"]

    def build_payload(
        self,
        result: ResolutionResult,
        prompt: str,
        fallback_candidates: Optional[List[SkillMetadata]] = None,
    ) -> AdapterPayload:
        context = build_progressive_context(result, fallback_candidates)
        selected_names = [s.name for s in result.selected_skills]
        shadow_names = [s.name for s in result.shadow_skills]

        tools = []
        prompts = []
        for s in result.selected_skills:
            tools.append({
                "name": s.name.replace("-", "_"),
                "description": s.description,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": f"Action to perform using {s.name}"},
                        "payload": {"type": "string", "description": "Code or prompt snippet"},
                    },
                    "required": ["action"],
                },
            })
            prompts.append({
                "name": f"skill_{s.name.replace('-', '_')}",
                "description": f"Activate {s.name} specialist instructions",
                "arguments": [],
            })

        raw_payload = {
            "tools": tools,
            "prompts": prompts,
            "context": context,
            "meta": {
                "tier": result.gate.tier,
                "confidence": result.confidence,
                "confidence_score": round(result.confidence_score, 2),
                "attribution_id": result.attribution_id,
                "catalog_hash": result.catalog_hash,
                "shadow_mode": result.shadow_mode,
                "shadow_skills": shadow_names,
            },
        }

        summaries = [s.to_summary() for s in (fallback_candidates or [])]
        bodies = {s.name: s.get_full_instructions() for s in result.selected_skills}

        return AdapterPayload(
            agent=self.agent_name,
            prompt=prompt,
            resolution=result,
            additional_context=context,
            raw_payload=raw_payload,
            selected_skill_names=selected_names,
            candidate_summaries=summaries,
            instruction_bodies=bodies,
            shadow_mode=result.shadow_mode,
        )


class OpenAIAdapter(BaseAgentAdapter):
    """Adapter for OpenAI and Anthropic function calling and tool schemas."""

    agent_name = "openai"
    aliases = ["anthropic", "chatgpt", "openai-functions", "anthropic-tools"]

    def build_payload(
        self,
        result: ResolutionResult,
        prompt: str,
        fallback_candidates: Optional[List[SkillMetadata]] = None,
    ) -> AdapterPayload:
        context = build_progressive_context(result, fallback_candidates)
        selected_names = [s.name for s in result.selected_skills]
        shadow_names = [s.name for s in result.shadow_skills]

        tools = []
        for s in result.selected_skills:
            tools.append({
                "type": "function",
                "function": {
                    "name": s.name.replace("-", "_"),
                    "description": s.description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "input": {"type": "string", "description": f"Execution input for {s.name}"}
                        },
                        "required": ["input"],
                    },
                },
            })

        raw_payload = {
            "tools": tools,
            "system_message": {
                "role": "system",
                "content": context if context else "You are an AI engineering assistant.",
            },
            "meta": {
                "tier": result.gate.tier,
                "confidence": result.confidence,
                "shadow_mode": result.shadow_mode,
                "shadow_skills": shadow_names,
                "attribution_id": result.attribution_id,
            },
        }

        summaries = [s.to_summary() for s in (fallback_candidates or [])]
        bodies = {s.name: s.get_full_instructions() for s in result.selected_skills}

        return AdapterPayload(
            agent=self.agent_name,
            prompt=prompt,
            resolution=result,
            additional_context=context,
            raw_payload=raw_payload,
            selected_skill_names=selected_names,
            candidate_summaries=summaries,
            instruction_bodies=bodies,
            shadow_mode=result.shadow_mode,
        )


class AntigravityAdapter(BaseAgentAdapter):
    """Adapter for Google Antigravity & Gemini CLI environment."""

    agent_name = "antigravity"
    aliases = ["agy", "gemini-cli", "gemini"]

    def build_payload(
        self,
        result: ResolutionResult,
        prompt: str,
        fallback_candidates: Optional[List[SkillMetadata]] = None,
    ) -> AdapterPayload:
        context = build_progressive_context(result, fallback_candidates)
        selected_names = [s.name for s in result.selected_skills]
        shadow_names = [s.name for s in result.shadow_skills]

        raw_payload = {
            "framework": "antigravity",
            "tier": result.gate.tier,
            "confidence": result.confidence,
            "confidence_score": round(result.confidence_score, 2),
            "selected_skills": selected_names,
            "shadow_mode": result.shadow_mode,
            "shadow_skills": shadow_names,
            "attribution_id": result.attribution_id,
            "catalog_hash": result.catalog_hash,
            "config_hash": result.config_hash,
            "instructions": context,
        }

        summaries = [s.to_summary() for s in (fallback_candidates or [])]
        bodies = {s.name: s.get_full_instructions() for s in result.selected_skills}

        return AdapterPayload(
            agent=self.agent_name,
            prompt=prompt,
            resolution=result,
            additional_context=context,
            raw_payload=raw_payload,
            selected_skill_names=selected_names,
            candidate_summaries=summaries,
            instruction_bodies=bodies,
            shadow_mode=result.shadow_mode,
        )

    def format_output(self, payload: AdapterPayload, as_json: bool = False) -> str:
        if as_json:
            return json.dumps(payload.raw_payload, indent=2)
        if not payload.additional_context:
            return "(No skills dispatched - gate bypassed or shadow mode active)"
        return (
            "<instructions source=\"taxonomy-dispatcher\">\n"
            + payload.additional_context
            + "\n</instructions>"
        )


class GenericAdapter(BaseAgentAdapter):
    """Standard generic JSON / Markdown progressive disclosure adapter."""

    agent_name = "generic"
    aliases = ["json", "markdown", "default"]

    def build_payload(
        self,
        result: ResolutionResult,
        prompt: str,
        fallback_candidates: Optional[List[SkillMetadata]] = None,
    ) -> AdapterPayload:
        context = build_progressive_context(result, fallback_candidates)
        selected_names = [s.name for s in result.selected_skills]
        shadow_names = [s.name for s in result.shadow_skills]

        summaries = [s.to_summary() for s in (fallback_candidates or [])]
        bodies = {s.name: s.get_full_instructions() for s in result.selected_skills}

        raw_payload = {
            "prompt": prompt,
            "resolution": result.to_dict(),
            "selected_skills": selected_names,
            "shadow_mode": result.shadow_mode,
            "shadow_skills": shadow_names,
            "context": context,
        }

        return AdapterPayload(
            agent=self.agent_name,
            prompt=prompt,
            resolution=result,
            additional_context=context,
            raw_payload=raw_payload,
            selected_skill_names=selected_names,
            candidate_summaries=summaries,
            instruction_bodies=bodies,
            shadow_mode=result.shadow_mode,
        )


_ADAPTER_REGISTRY: Dict[str, BaseAgentAdapter] = {
    "claude": ClaudeCodeAdapter(),
    "cursor": CursorAdapter(),
    "mcp": MCPAdapter(),
    "openai": OpenAIAdapter(),
    "antigravity": AntigravityAdapter(),
    "generic": GenericAdapter(),
}

# Alias mapping
_ALIAS_MAP: Dict[str, str] = {}
for name, adapter in _ADAPTER_REGISTRY.items():
    _ALIAS_MAP[name.lower()] = name
    for alias in adapter.aliases:
        _ALIAS_MAP[alias.lower()] = name


def get_adapter(name: Optional[str] = None) -> BaseAgentAdapter:
    """Retrieve an agent adapter by name or alias (defaults to ClaudeCodeAdapter)."""
    if not name:
        return _ADAPTER_REGISTRY["claude"]
    clean = str(name).strip().lower()
    canonical = _ALIAS_MAP.get(clean)
    if canonical and canonical in _ADAPTER_REGISTRY:
        return _ADAPTER_REGISTRY[canonical]
    # Fallback to generic adapter
    return _ADAPTER_REGISTRY["generic"]


def list_supported_adapters() -> List[str]:
    """Return sorted list of canonical supported adapter names."""
    return sorted(list(_ADAPTER_REGISTRY.keys()))
