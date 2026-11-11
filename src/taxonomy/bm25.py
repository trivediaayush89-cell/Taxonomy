"""Okapi BM25 and BM25F multi-field scoring engine with smoothed Robertson-Spärck Jones IDF.

Provides mathematically grounded lexical relevance scoring across skill catalogs:
- Field-weighted term frequencies (BM25F) for name, curated tags, and description.
- Document length normalization per field to prevent verbose descriptions from dominating.
- Robertson-Spärck Jones IDF with smoothing floor to ensure positive weights on small and large catalogs.
- High-speed inverted index traversal for sub-millisecond querying across 1,000+ skills.
"""

from collections import defaultdict
from dataclasses import dataclass, field
import math
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from taxonomy.models import SkillMetadata

# Stop words consistent with resolver
STOP_WORDS = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "did", "do", "does", "doing", "don't", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers",
    "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it",
    "its", "itself", "let's", "me", "more", "most", "my", "myself", "no", "nor",
    "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours",
    "ourselves", "out", "over", "own", "same", "she", "should", "so", "some", "such",
    "than", "that", "the", "their", "theirs", "them", "themselves", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "we", "were", "what", "when", "where", "which", "while", "who",
    "whom", "why", "with", "won't", "would", "you", "your", "yours", "yourself",
    "use", "when", "skip", "before", "after", "any", "every", "across",
    "run", "running", "make", "get", "set", "put", "new", "start", "starting", "proposed",
    "build", "building", "create", "creating", "work", "working", "want", "wants",
    "need", "needs", "help", "helps", "using", "used", "also", "like", "other",
})

GENERIC_NAME_PARTS = frozenset({
    "design", "review", "frontend", "engineering", "quality", "gate", "code",
    "skill", "skills", "find", "creator", "best", "practices", "pro", "max",
    "ui", "ux", "guide", "development", "director", "independent", "eng",
    "settings", "agent", "tool", "tools", "helper", "util", "utils",
})


@dataclass
class BM25Params:
    """Configurable hyperparameters for field-weighted BM25F."""

    k1: float = 1.2
    w_name: float = 3.5
    w_tags: float = 3.0
    w_desc: float = 1.0
    b_name: float = 0.0
    b_tags: float = 0.25
    b_desc: float = 0.75
    idf_smoothing: float = 0.5
    exact_name_boost: float = 8.0
    compound_tag_boost: float = 3.0


@dataclass
class BM25Document:
    """Internal token representation and field statistics for a single skill."""

    name: str
    category: str
    mtime: float
    name_lower: str
    name_spaced: str
    name_parts: Set[str]
    compound_tags: List[Tuple[str, str, Tuple[str, ...]]]
    single_tags: List[Tuple[str, str]]
    tf_name: Dict[str, int]
    tf_tags: Dict[str, int]
    tf_desc: Dict[str, int]
    len_name: int
    len_tags: int
    len_desc: int


class BM25Index:
    """In-memory BM25 / BM25F inverted index with smoothed Robertson-Spärck Jones IDF."""

    def __init__(self, params: Optional[BM25Params] = None):
        self.params = params or BM25Params()
        self.documents: Dict[str, BM25Document] = {}
        self.doc_freq: Dict[str, int] = defaultdict(int)
        self.idf_cache: Dict[str, float] = {}
        self.avg_len_name: float = 1.0
        self.avg_len_tags: float = 1.0
        self.avg_len_desc: float = 1.0
        self.total_docs: int = 0
        # Inverted index: term -> list of (skill_name, tf_name, tf_tags, tf_desc)
        self.inverted_index: Dict[str, List[Tuple[str, int, int, int]]] = defaultdict(list)
        # Precomputed BM25F term score postings: term -> list of (skill_name, precomputed_term_score)
        self.score_postings: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        # Fast lookup indices for exact names, name parts, and compound tags
        self.exact_name_map: Dict[str, str] = {}
        self.name_first_word_postings: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        self.name_part_postings: Dict[str, List[str]] = defaultdict(list)
        self.compound_tag_postings: Dict[str, List[Tuple[str, str, str, Tuple[str, ...]]]] = defaultdict(list)
        self._catalog_fingerprint: Optional[object] = None

    def build(
        self,
        skills: Iterable[SkillMetadata],
        force: bool = False,
        catalog_hash: Optional[str] = None,
    ) -> None:
        """Build or refresh the BM25 inverted index from a collection of skills."""
        if not force and catalog_hash and self._catalog_fingerprint == catalog_hash and self.total_docs > 0:
            return  # Fast O(1) cache hit

        active_skills = [s for s in skills if s.status != "deprecated"]
        fingerprint: object = catalog_hash or tuple(
            sorted((s.name, s.mtime, s.priority, len(s.description), tuple(s.tags)) for s in active_skills)
        )

        if not force and self._catalog_fingerprint == fingerprint and self.total_docs > 0:
            return  # Cache hit, catalog unchanged

        from taxonomy.resolver import (
            NEGATIVE_CLAUSE_REGEX,
            WORD_REGEX,
            normalize_stem,
            tokenize_code_aware,
        )

        docs: Dict[str, BM25Document] = {}
        doc_freq: Dict[str, int] = defaultdict(int)
        inverted: Dict[str, List[Tuple[str, int, int, int]]] = defaultdict(list)

        sum_len_name = 0
        sum_len_tags = 0
        sum_len_desc = 0

        for skill in active_skills:
            # 1. Name tokens
            name_lower = skill.name.lower()
            name_spaced = name_lower.replace("-", " ")
            raw_parts = [
                p for p in name_lower.split("-")
                if len(p) >= 3 and p not in STOP_WORDS
            ]
            name_raw_parts = [normalize_stem(p) for p in raw_parts]
            distinctive_name_parts = {
                p for p in raw_parts
                if p not in GENERIC_NAME_PARTS and normalize_stem(p) not in GENERIC_NAME_PARTS
            }

            tf_name: Dict[str, int] = defaultdict(int)
            for p in name_raw_parts:
                tf_name[p] += 1

            # 2. Tag tokens (single & compound)
            single_tags: List[Tuple[str, str]] = []
            compound_tags: List[Tuple[str, str, Tuple[str, ...]]] = []
            tf_tags: Dict[str, int] = defaultdict(int)

            for tag in skill.tags:
                tag_lower = tag.lower().strip()
                if not tag_lower:
                    continue
                if "-" in tag_lower or " " in tag_lower:
                    tag_spaced = tag_lower.replace("-", " ")
                    parts = tuple(normalize_stem(p) for p in re_split_words(tag_lower) if p)
                    compound_tags.append((tag_lower, tag_spaced, parts))
                    for part in parts:
                        if len(part) >= 3 and part not in STOP_WORDS:
                            tf_tags[part] += 1
                else:
                    tag_stem = normalize_stem(tag_lower)
                    single_tags.append((tag_lower, tag_stem))
                    if len(tag_stem) >= 3 and tag_stem not in STOP_WORDS:
                        tf_tags[tag_stem] += 1

            # 3. Description tokens (with code-aware identifier & framework splitting)
            cleaned_desc = NEGATIVE_CLAUSE_REGEX.sub(" ", skill.description)
            _, desc_code_stems = tokenize_code_aware(cleaned_desc)
            desc_words = WORD_REGEX.findall(cleaned_desc.lower())
            desc_stems = [
                normalize_stem(w)
                for w in desc_words
                if len(w) >= 3 and w not in STOP_WORDS
            ]
            existing_desc_stems = set(desc_stems)
            for cs in desc_code_stems:
                if len(cs) >= 3 and cs not in STOP_WORDS and cs not in existing_desc_stems:
                    desc_stems.append(cs)

            tf_desc: Dict[str, int] = defaultdict(int)
            for w in desc_stems:
                tf_desc[w] += 1

            len_name = max(1, sum(tf_name.values()))
            len_tags = max(1, sum(tf_tags.values()))
            len_desc = max(1, sum(tf_desc.values()))

            sum_len_name += len_name
            sum_len_tags += len_tags
            sum_len_desc += len_desc

            doc = BM25Document(
                name=skill.name,
                category=skill.category,
                mtime=skill.mtime,
                name_lower=name_lower,
                name_spaced=name_spaced,
                name_parts=distinctive_name_parts,
                compound_tags=compound_tags,
                single_tags=single_tags,
                tf_name=dict(tf_name),
                tf_tags=dict(tf_tags),
                tf_desc=dict(tf_desc),
                len_name=len_name,
                len_tags=len_tags,
                len_desc=len_desc,
            )
            docs[skill.name] = doc

            # Register document frequencies and postings
            unique_terms = set(tf_name.keys()) | set(tf_tags.keys()) | set(tf_desc.keys())
            for t in unique_terms:
                doc_freq[t] += 1
                inverted[t].append((
                    skill.name,
                    tf_name.get(t, 0),
                    tf_tags.get(t, 0),
                    tf_desc.get(t, 0),
                ))

        n_docs = len(docs)
        self.total_docs = n_docs
        self.documents = docs
        self.doc_freq = doc_freq
        self.inverted_index = inverted
        self.avg_len_name = max(1.0, sum_len_name / max(1, n_docs))
        self.avg_len_tags = max(1.0, sum_len_tags / max(1, n_docs))
        self.avg_len_desc = max(1.0, sum_len_desc / max(1, n_docs))

        # Precompute smoothed IDF for all terms in catalog
        idf: Dict[str, float] = {}
        for t, df in doc_freq.items():
            # Smoothed Robertson-Spärck Jones IDF
            numerator = n_docs - df + 0.5
            denominator = df + 0.5
            val = math.log(1.0 + max(0.0, numerator / denominator))
            idf[t] = round(val + self.params.idf_smoothing, 4)

        self.idf_cache = idf

        # Precompute BM25F saturated term scores per posting for O(1) query-time lookup
        p = self.params
        k1 = p.k1
        score_postings: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        for t, postings in inverted.items():
            term_idf = idf[t]
            post_list: List[Tuple[str, float]] = []
            for skill_name, fn, ft, fd in postings:
                doc = docs[skill_name]
                norm_name = 1.0 - p.b_name + (p.b_name * (doc.len_name / self.avg_len_name))
                norm_tags = 1.0 - p.b_tags + (p.b_tags * (doc.len_tags / self.avg_len_tags))
                norm_desc = 1.0 - p.b_desc + (p.b_desc * (doc.len_desc / self.avg_len_desc))
                tf_tilde = (
                    (p.w_name * (fn / max(0.1, norm_name)))
                    + (p.w_tags * (ft / max(0.1, norm_tags)))
                    + (p.w_desc * (fd / max(0.1, norm_desc)))
                )
                if tf_tilde > 0.0:
                    term_score = term_idf * ((tf_tilde * (k1 + 1.0)) / (tf_tilde + k1))
                    post_list.append((skill_name, term_score))
            if post_list:
                score_postings[t] = post_list

        self.score_postings = score_postings

        # Build fast lookup tables for Step 2 (exact name, name parts, compound tags)
        exact_name_map: Dict[str, str] = {}
        name_first_word_postings: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        name_part_postings: Dict[str, List[str]] = defaultdict(list)
        compound_tag_postings: Dict[str, List[Tuple[str, str, str, Tuple[str, ...]]]] = defaultdict(list)

        for skill_name, doc in docs.items():
            exact_name_map[doc.name_lower] = skill_name
            first_word = doc.name_spaced.split(" ", 1)[0]
            if first_word:
                name_first_word_postings[first_word].append((skill_name, doc.name_spaced))
            for part in doc.name_parts:
                name_part_postings[part].append(skill_name)
            for tag_lower, tag_spaced, part_stems in doc.compound_tags:
                if part_stems:
                    compound_tag_postings[part_stems[0]].append((skill_name, tag_lower, tag_spaced, part_stems))

        self.exact_name_map = exact_name_map
        self.name_first_word_postings = name_first_word_postings
        self.name_part_postings = name_part_postings
        self.compound_tag_postings = compound_tag_postings
        self._catalog_fingerprint = fingerprint

    def get_idf(self, term: str) -> float:
        """Return cached IDF for a term, or default floor for unseen terms."""
        if term in self.idf_cache:
            return self.idf_cache[term]
        # For unseen query term
        n_docs = max(1, self.total_docs)
        val = math.log(1.0 + (n_docs + 0.5) / 0.5)
        return round(val + self.params.idf_smoothing, 4)

    def score_query(
        self,
        prompt_words: Set[str],
        prompt_stems: Set[str],
        lower_prompt: str,
    ) -> Tuple[Dict[str, float], Dict[str, int]]:
        """Compute field-weighted BM25F scores for all matching candidate skills.

        Returns:
            (scores_dict, relevance_hits_dict)
        """
        scores: Dict[str, float] = defaultdict(float)
        hits: Dict[str, int] = defaultdict(int)

        if not self.documents:
            return {}, {}

        p = self.params
        k1 = p.k1

        # 1. Inverted index BM25 term scoring (using precomputed BM25F postings)
        for term in prompt_stems:
            postings = self.score_postings.get(term)
            if not postings:
                continue
            for skill_name, term_score in postings:
                scores[skill_name] += term_score
                hits[skill_name] += 1

        # 2. Exact name & compound tag boosts (O(|Q|) inverted lookup instead of O(N_docs))
        exact_matched_skills: Set[str] = set()
        for w in prompt_words:
            exact_skill = self.exact_name_map.get(w)
            if exact_skill:
                exact_matched_skills.add(exact_skill)
            spaced_candidates = self.name_first_word_postings.get(w)
            if spaced_candidates:
                for skill_name, name_spaced in spaced_candidates:
                    if skill_name not in exact_matched_skills and name_spaced in lower_prompt:
                        exact_matched_skills.add(skill_name)

        for skill_name in exact_matched_skills:
            scores[skill_name] += p.exact_name_boost
            hits[skill_name] += 2

        for w in prompt_words:
            part_skills = self.name_part_postings.get(w)
            if part_skills:
                for skill_name in part_skills:
                    if skill_name not in exact_matched_skills:
                        scores[skill_name] += 2.5
                        hits[skill_name] += 1

        for stem in prompt_stems:
            comp_list = self.compound_tag_postings.get(stem)
            if comp_list:
                for skill_name, tag_lower, tag_spaced, part_stems in comp_list:
                    if (
                        tag_lower in prompt_words
                        or tag_spaced in lower_prompt
                        or all(ps in prompt_stems for ps in part_stems)
                    ):
                        scores[skill_name] += p.compound_tag_boost
                        hits[skill_name] += 1

        return dict(scores), dict(hits)


def re_split_words(text: str) -> List[str]:
    """Helper to split compound tags on spaces or hyphens."""
    import re
    return [p for p in re.split(r"[-\s]+", text) if p]
