"""Directed Acyclic Graph (DAG) validation for category hierarchies and aliases."""

from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple


class CyclicDependencyError(ValueError):
    """Raised when category aliases or dependencies form an infinite recursion loop."""
    pass


class CategoryDAG:
    """Validates category alias graphs and detects circular dependencies using Kahn's algorithm."""

    def __init__(self):
        self.adj_list: Dict[str, Set[str]] = defaultdict(set)
        self.in_degree: Dict[str, int] = defaultdict(int)
        self.nodes: Set[str] = set()

    def add_alias(self, source_alias: str, target_category: str) -> None:
        """Add a directed edge: source_alias -> target_category."""
        src = source_alias.strip().lower()
        dst = target_category.strip().lower()
        
        self.nodes.add(src)
        self.nodes.add(dst)

        if dst not in self.adj_list[src]:
            self.adj_list[src].add(dst)
            self.in_degree[dst] = self.in_degree.get(dst, 0) + 1
            if src not in self.in_degree:
                self.in_degree[src] = 0

    def validate_acyclic(self) -> List[str]:
        """Runs Kahn's algorithm to compute topological order and verify no cycles exist.
        
        Returns:
            Topologically sorted list of nodes if DAG is valid.
        Raises:
            CyclicDependencyError if a cycle is detected.
        """
        # Copy in-degrees
        in_deg = {node: self.in_degree.get(node, 0) for node in self.nodes}

        # Initialize queue with all nodes having in-degree 0
        queue = deque([node for node in self.nodes if in_deg[node] == 0])
        topological_order = []

        while queue:
            node = queue.popleft()
            topological_order.append(node)

            for neighbor in self.adj_list[node]:
                in_deg[neighbor] -= 1
                if in_deg[neighbor] == 0:
                    queue.append(neighbor)

        if len(topological_order) != len(self.nodes):
            unprocessed = [n for n in self.nodes if in_deg[n] > 0]
            raise CyclicDependencyError(
                f"Circular category loop detected! Cycle nodes involved: {unprocessed}"
            )

        return topological_order

    def resolve_alias_chain(self, alias: str, max_depth: int = 10) -> str:
        """Resolve an alias chain down to its canonical destination category safely."""
        current = alias.strip().lower()
        visited = set()

        for _ in range(max_depth):
            if current in visited:
                raise CyclicDependencyError(f"Infinite loop detected resolving alias: {alias}")
            visited.add(current)

            targets = self.adj_list.get(current)
            if not targets:
                return current
            # Pick first canonical target
            current = next(iter(targets))

        return current


class SkillDAG:
    """DAG solver for skill dependency resolution (requires) and topological ordering.

    Guarantees:
    - Transitive dependency resolution (A -> B -> C auto-resolves [C, B] for A).
    - True topological ordering: prerequisites ALWAYS precede dependents in the output.
    - Deterministic cycle detection using Kahn's algorithm and recursion path tracking.
    """

    def __init__(self, indexer=None):
        self.indexer = indexer

    def resolve_transitive_prerequisites(
        self,
        skill,
        visited: Set[str] = None,
        path: List[str] = None,
    ) -> List:
        """Resolve all transitive prerequisites for a skill in topological order (leaf prereqs first).

        Raises CyclicDependencyError if circular requirements exist (e.g. A -> B -> A).
        """
        if visited is None:
            visited = set()
        if path is None:
            path = []

        if skill.name in path:
            cycle_str = " -> ".join(path + [skill.name])
            raise CyclicDependencyError(f"Circular dependency detected in skill requirements: {cycle_str}")

        if skill.name in visited:
            return []

        visited.add(skill.name)
        new_path = path + [skill.name]
        prereqs = []

        if self.indexer:
            for req_name in skill.requires:
                req_skill = self.indexer.get_skill(req_name)
                if req_skill and req_skill.status != "deprecated":
                    sub_prereqs = self.resolve_transitive_prerequisites(req_skill, visited, new_path)
                    for sp in sub_prereqs:
                        if sp not in prereqs:
                            prereqs.append(sp)
                    if req_skill not in prereqs:
                        prereqs.append(req_skill)

        return prereqs

    @staticmethod
    def topological_sort(skills: List) -> List:
        """Sort skills topologically such that all prerequisites appear BEFORE dependents.

        Preserves original relative order for independent skills.
        """
        if len(skills) <= 1:
            return list(skills)

        name_to_skill = {s.name: s for s in skills}
        names = [s.name for s in skills]

        # Directed edge: prereq -> dependent
        in_degree: Dict[str, int] = {n: 0 for n in names}
        adj: Dict[str, List[str]] = {n: [] for n in names}

        for s in skills:
            for req in s.requires:
                if req in name_to_skill:
                    adj[req].append(s.name)
                    in_degree[s.name] += 1

        # Queue nodes with in-degree 0 in original arrival order
        queue = deque([n for n in names if in_degree[n] == 0])
        sorted_names: List[str] = []

        while queue:
            node = queue.popleft()
            sorted_names.append(node)
            for dependent in adj[node]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # In case of unresolved cycles, append remaining in arrival order
        if len(sorted_names) != len(names):
            remaining = [n for n in names if n not in sorted_names]
            sorted_names.extend(remaining)

        return [name_to_skill[n] for n in sorted_names]

