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
