"""Curated Community Taste Presets for Skill Taxonomy Dispatcher."""

from typing import Dict, List, Optional


CURATED_PRESETS: Dict[str, dict] = {
    "minimalist-backend": {
        "name": "minimalist-backend",
        "title": "Minimalist Backend & Systems",
        "version": 1,
        "description": "Optimized for CLI, microservices, databases, and APIs with zero frontend noise.",
        "preferred_skills": {
            "backend.api": "backend-architecture",
            "verification.qa": "engineering-quality-gate",
            "orchestration.lead": "development-director",
        },
        "avoid_skills": [
            "design-taste-frontend",
            "unslop",
            "animate",
            "emil-design-eng",
        ],
        "weights": {
            "engineering-quality-gate": 2.5,
            "development-director": 2.0,
        },
    },
    "solidity-auditor": {
        "name": "solidity-auditor",
        "title": "Smart Contract & Web3 Protocol Auditor",
        "version": 1,
        "description": "High-security smart contract, DeFi protocol, and adversarial courtroom jury review.",
        "preferred_skills": {
            "security.blockchain": "smart-contract-auditor",
            "decision.review": "independent-jury",
            "verification.qa": "engineering-quality-gate",
            "orchestration.lead": "development-director",
        },
        "avoid_skills": [
            "design-taste-frontend",
            "unslop",
            "animate",
        ],
        "weights": {
            "smart-contract-auditor": 3.0,
            "independent-jury": 2.5,
            "engineering-quality-gate": 2.0,
        },
    },
    "design-heavy-frontend": {
        "name": "design-heavy-frontend",
        "title": "Design-Heavy Marketing & Showcase",
        "version": 1,
        "description": "Award-level marketing landing pages, smooth transitions, art direction, and micro-interactions.",
        "preferred_skills": {
            "frontend.visual": "design-taste-frontend",
            "ui.animation": "animate",
            "ui.framework": "vercel-react-best-practices",
            "ui.component": "frontend-design",
        },
        "avoid_skills": [],
        "weights": {
            "design-taste-frontend": 3.0,
            "animate": 2.5,
            "vercel-react-best-practices": 2.0,
        },
    },
    "product-saas-builder": {
        "name": "product-saas-builder",
        "title": "B2B SaaS Product & Web Application",
        "version": 1,
        "description": "Production-ready B2B SaaS web applications, dashboards, forms, and design tokens.",
        "preferred_skills": {
            "frontend.visual": "impeccable",
            "ui.framework": "vercel-react-best-practices",
            "verification.qa": "engineering-quality-gate",
            "orchestration.lead": "development-director",
        },
        "avoid_skills": [
            "unslop",
        ],
        "weights": {
            "impeccable": 3.0,
            "vercel-react-best-practices": 2.0,
            "engineering-quality-gate": 2.0,
        },
    },
    "strict-qa-sre": {
        "name": "strict-qa-sre",
        "title": "Strict QA, SRE & Empirical Verification",
        "version": 1,
        "description": "Rigorous empirical test verification, latency SLAs, fuzzing, and courtroom trials.",
        "preferred_skills": {
            "verification.qa": "engineering-quality-gate",
            "decision.review": "independent-jury",
        },
        "avoid_skills": [],
        "weights": {
            "engineering-quality-gate": 3.0,
            "independent-jury": 2.5,
        },
    },
}


def get_preset(name: str) -> Optional[dict]:
    """Retrieve a curated preset by slug name (case-insensitive)."""
    key = name.lower().strip()
    return CURATED_PRESETS.get(key)


def list_presets() -> List[dict]:
    """Return all available curated community presets."""
    return list(CURATED_PRESETS.values())
