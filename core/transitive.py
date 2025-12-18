"""
Transitive inference engine for active learning.

Infers matches from graph of past decisions without LLM calls.
If A~B with high confidence and B~C with high confidence, infers A~C.
"""

from collections import deque
from dataclasses import dataclass, field


@dataclass
class TransitiveInference:
    """
    Infer matches from graph of past decisions.

    If A~B with confidence 0.95 and B~C with confidence 0.9,
    infers A~C with confidence 0.95 * 0.9 = 0.855

    Graph is per-user (stores actual item relationships).
    """

    min_confidence: float = 0.75
    max_path_length: int = 3
    # Graph: item_id -> {neighbor_id: (is_match, confidence)}
    graph: dict[str, dict[str, tuple[bool, float]]] = field(default_factory=dict)

    def add_edge(
        self,
        item_a: str,
        item_b: str,
        is_match: bool,
        confidence: float,
    ) -> None:
        """Add a decision edge to the graph."""
        if item_a not in self.graph:
            self.graph[item_a] = {}
        if item_b not in self.graph:
            self.graph[item_b] = {}

        self.graph[item_a][item_b] = (is_match, confidence)
        self.graph[item_b][item_a] = (is_match, confidence)

    def infer(
        self,
        item_a: str,
        item_b: str,
    ) -> tuple[bool, float] | None:
        """
        Try to infer match between item_a and item_b.

        Uses BFS to find path with highest confidence.
        Returns None if no inference possible.
        """
        if item_a not in self.graph or item_b not in self.graph:
            return None

        # Direct edge?
        if item_b in self.graph.get(item_a, {}):
            return self.graph[item_a][item_b]

        # BFS with confidence propagation
        # Queue: (current_node, path_confidence, is_match_chain, path_length)
        queue: deque[tuple[str, float, bool, int]] = deque([(item_a, 1.0, True, 0)])
        visited = {item_a}
        best_result: tuple[bool, float] | None = None

        while queue:
            current, path_conf, is_match_chain, path_len = queue.popleft()

            if path_len >= self.max_path_length:
                continue

            for neighbor, (edge_match, edge_conf) in self.graph.get(current, {}).items():
                if neighbor in visited:
                    continue

                # Propagate confidence
                new_conf = path_conf * edge_conf

                # Chain of matches = match, any non-match breaks chain
                new_is_match = is_match_chain and edge_match

                if neighbor == item_b:
                    # Found path to target
                    if new_conf >= self.min_confidence:
                        # Keep best result
                        if best_result is None or new_conf > best_result[1]:
                            best_result = (new_is_match, new_conf)
                    continue

                if new_conf >= self.min_confidence:
                    visited.add(neighbor)
                    queue.append((neighbor, new_conf, new_is_match, path_len + 1))

        return best_result

    def get_component(self, item_id: str) -> set[str]:
        """Get all items transitively connected to item_id as matches."""
        if item_id not in self.graph:
            return {item_id}

        component: set[str] = set()
        stack = [item_id]

        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)

            for neighbor, (is_match, conf) in self.graph.get(current, {}).items():
                if is_match and conf >= self.min_confidence:
                    stack.append(neighbor)

        return component

    def clear(self) -> None:
        """Clear the graph."""
        self.graph.clear()

    def __len__(self) -> int:
        """Number of nodes in graph."""
        return len(self.graph)
