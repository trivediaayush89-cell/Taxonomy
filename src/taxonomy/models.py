"""Data models for skill metadata, gating decisions, and resolution results."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class SkillMetadata:
    name: str
    description: str
    category: str
    tags: List[str] = field(default_factory=list)
    status: str = "active"  # "active", "experimental", "deprecated"
    priority: int = 50
    conflicts_with: List[str] = field(default_factory=list)
    requires: List[str] = field(default_factory=list)
    path: Optional[Path] = None
    mtime: float = 0.0
    version: str = "1.0.0"
    content_hash: str = ""
    trust_level: str = "user"  # "builtin", "user", "workspace", "community"
    provenance: Optional[str] = None
    supported_agents: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "tags": self.tags,
            "status": self.status,
            "priority": self.priority,
            "conflicts_with": self.conflicts_with,
            "requires": self.requires,
            "path": str(self.path) if self.path else None,
            "mtime": self.mtime,
            "version": self.version,
            "content_hash": self.content_hash,
            "trust_level": self.trust_level,
            "provenance": self.provenance,
            "supported_agents": self.supported_agents,
            "permissions": self.permissions,
        }

    def to_pointer(self) -> dict:
        """Level 1: Minimal pointer (0-token cost)."""
        return {
            "name": self.name,
            "category": self.category,
            "path": str(self.path) if self.path else None,
        }

    def to_summary(self) -> dict:
        """Level 2: Summary card (~50 tokens)."""
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "tags": self.tags,
            "status": self.status,
            "priority": self.priority,
            "version": self.version,
            "trust_level": self.trust_level,
        }

    def get_full_instructions(self) -> str:
        """Level 3: Full instructions retrieved on demand from SKILL.md."""
        if not self.path:
            return ""
        skill_file = self.path if self.path.name == "SKILL.md" else self.path / "SKILL.md"
        if not skill_file.is_file():
            return ""
        try:
            from taxonomy.security import MAX_SKILL_FILE_BYTES
            if skill_file.stat().st_size > MAX_SKILL_FILE_BYTES:
                return ""
        except Exception:
            return ""
        text = skill_file.read_text(encoding="utf-8")
        from taxonomy.schema import FRONTMATTER_REGEX
        m = FRONTMATTER_REGEX.match(text)
        return text[m.end():].strip() if m else text.strip()


@dataclass
class GateResult:
    should_route: bool
    tier: int  # 0: Casual/Chat, 1: Quick Fix/Question, 2: Feature/Module, 3: Full Project/Arch
    reason: str
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "should_route": self.should_route,
            "tier": self.tier,
            "reason": self.reason,
            "latency_ms": round(self.latency_ms, 3),
        }


@dataclass
class SkillScore:
    skill_name: str
    base_score: float = 0.0
    taste_bias: float = 0.0
    efficacy_bias: float = 0.0
    final_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "skill_name": self.skill_name,
            "base_score": round(self.base_score, 2),
            "taste_bias": round(self.taste_bias, 2),
            "efficacy_bias": round(self.efficacy_bias, 2),
            "final_score": round(self.final_score, 2),
        }


@dataclass
class ResolutionResult:
    gate: GateResult
    selected_skills: List[SkillMetadata] = field(default_factory=list)
    category_scores: Dict[str, float] = field(default_factory=dict)
    total_latency_ms: float = 0.0
    taste_profile_source: Optional[str] = None
    skill_scores: Dict[str, SkillScore] = field(default_factory=dict)
    attribution_id: Optional[str] = None
    confidence: str = "none"  # "high", "medium", "low", "none"
    confidence_score: float = 0.0  # Normalized 0.0 to 1.0 calibrated confidence
    margin: float = 0.0  # Score delta between candidate #1 and runner-up
    abstained: bool = False  # True when dispatcher abstains due to weak confidence or gate bypass
    abstention_reason: Optional[str] = None
    catalog_hash: Optional[str] = None  # Deterministic 16-hex digest of indexed skill catalog
    config_hash: Optional[str] = None  # Deterministic 16-hex digest of active routing config

    def to_dict(self) -> dict:
        return {
            "gate": self.gate.to_dict(),
            "selected_skills": [s.to_dict() for s in self.selected_skills],
            "category_scores": {k: round(v, 2) for k, v in self.category_scores.items()},
            "total_latency_ms": round(self.total_latency_ms, 3),
            "taste_profile_source": self.taste_profile_source,
            "skill_scores": {k: v.to_dict() for k, v in self.skill_scores.items()},
            "attribution_id": self.attribution_id,
            "confidence": self.confidence,
            "confidence_score": round(self.confidence_score, 2),
            "margin": round(self.margin, 2),
            "abstained": self.abstained,
            "abstention_reason": self.abstention_reason,
            "catalog_hash": self.catalog_hash,
            "config_hash": self.config_hash,
        }


# Alias for spec conformity
RoutingDecision = ResolutionResult

