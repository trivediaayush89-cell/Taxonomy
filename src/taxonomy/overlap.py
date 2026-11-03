"""Skill overlap, redundancy detection, and case-collision auditing."""

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from taxonomy.indexer import SkillIndexer
from taxonomy.models import SkillMetadata


@dataclass
class OverlapReport:
    skill_a: str
    skill_b: str
    similarity_score: float
    shared_tags: List[str]
    shared_keywords: List[str]
    recommendation: str


class OverlapDetector:
    """Detects high-overlap skills and potential naming collisions."""

    def __init__(self, indexer: SkillIndexer, threshold: float = 0.45):
        self.indexer = indexer
        self.threshold = threshold

    def find_overlaps(self) -> List[OverlapReport]:
        """Scan all indexed skills and find pairs with overlapping descriptions or tags."""
        skills = self.indexer.all_skills
        overlaps: List[OverlapReport] = []

        # Check all unique pairs
        for i in range(len(skills)):
            for j in range(i + 1, len(skills)):
                s1 = skills[i]
                s2 = skills[j]

                # Skip deprecated skills
                if s1.status == "deprecated" or s2.status == "deprecated":
                    continue

                # 1. Tag overlap (Jaccard similarity)
                tags1 = set(t.lower() for t in s1.tags)
                tags2 = set(t.lower() for t in s2.tags)
                shared_tags = sorted(list(tags1.intersection(tags2)))
                union_tags = tags1.union(tags2)
                tag_sim = len(shared_tags) / len(union_tags) if union_tags else 0.0

                # 2. Description keyword overlap
                from taxonomy.resolver import STOP_WORDS, WORD_REGEX, normalize_stem
                words1 = {normalize_stem(w) for w in WORD_REGEX.findall(s1.description.lower()) if len(w) >= 3 and w not in STOP_WORDS}
                words2 = {normalize_stem(w) for w in WORD_REGEX.findall(s2.description.lower()) if len(w) >= 3 and w not in STOP_WORDS}
                shared_words = sorted(list(words1.intersection(words2)))
                union_words = words1.union(words2)
                desc_sim = len(shared_words) / len(union_words) if union_words else 0.0

                # Combined weighted similarity
                combined_score = (tag_sim * 0.6) + (desc_sim * 0.4)

                # Same category gives a boost
                if s1.category == s2.category:
                    combined_score += 0.15

                if combined_score >= self.threshold or (shared_tags and len(shared_tags) >= 3):
                    rec = "Consider merging" if combined_score > 0.65 else "Review differentiation or add conflicts_with"
                    overlaps.append(OverlapReport(
                        skill_a=s1.name,
                        skill_b=s2.name,
                        similarity_score=round(combined_score, 2),
                        shared_tags=shared_tags,
                        shared_keywords=shared_words[:5],
                        recommendation=rec,
                    ))

        overlaps.sort(key=lambda o: o.similarity_score, reverse=True)
        return overlaps

    def find_case_collisions(self) -> List[Tuple[str, str]]:
        """Detect skills that would collide on case-insensitive filesystems (Windows/macOS)."""
        seen: Dict[str, str] = {}
        collisions: List[Tuple[str, str]] = []

        for s in self.indexer.all_skills:
            lower = s.name.lower()
            if lower in seen and seen[lower] != s.name:
                collisions.append((seen[lower], s.name))
            else:
                seen[lower] = s.name

        return collisions
