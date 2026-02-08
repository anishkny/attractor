"""
Validation and linting for Attractor pipelines.
"""

from enum import Enum
from typing import List, Optional, Callable
from dataclasses import dataclass
from .models import Graph


class Severity(Enum):
    """Diagnostic severity levels."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Diagnostic:
    """A validation diagnostic."""
    rule: str
    severity: Severity
    message: str
    node_id: Optional[str] = None
    edge: Optional[tuple] = None
    fix: Optional[str] = None


class LintRule:
    """Base class for lint rules."""
    
    def __init__(self, name: str):
        self.name = name
    
    def apply(self, graph: Graph) -> List[Diagnostic]:
        """Apply the rule to a graph and return diagnostics."""
        raise NotImplementedError


class StartNodeRule(LintRule):
    """Exactly one start node required."""
    
    def __init__(self):
        super().__init__("start_node")
    
    def apply(self, graph: Graph) -> List[Diagnostic]:
        start_nodes = [
            n for n in graph.nodes.values()
            if n.shape == "Mdiamond" or n.id.lower() in ["start", "Start"]
        ]
        
        if len(start_nodes) == 0:
            return [Diagnostic(
                rule=self.name,
                severity=Severity.ERROR,
                message="Pipeline must have exactly one start node (shape=Mdiamond or id='start')"
            )]
        elif len(start_nodes) > 1:
            return [Diagnostic(
                rule=self.name,
                severity=Severity.ERROR,
                message=f"Pipeline has {len(start_nodes)} start nodes, expected 1",
                node_id=", ".join(n.id for n in start_nodes)
            )]
        
        return []


class TerminalNodeRule(LintRule):
    """At least one terminal/exit node required."""
    
    def __init__(self):
        super().__init__("terminal_node")
    
    def apply(self, graph: Graph) -> List[Diagnostic]:
        exit_nodes = [
            n for n in graph.nodes.values()
            if n.shape == "Msquare" or n.id.lower() in ["exit", "end", "done"]
        ]
        
        if len(exit_nodes) == 0:
            return [Diagnostic(
                rule=self.name,
                severity=Severity.ERROR,
                message="Pipeline must have at least one exit node (shape=Msquare)"
            )]
        
        return []


class ReachabilityRule(LintRule):
    """All nodes must be reachable from start."""
    
    def __init__(self):
        super().__init__("reachability")
    
    def apply(self, graph: Graph) -> List[Diagnostic]:
        # Find start node
        start_nodes = [
            n for n in graph.nodes.values()
            if n.shape == "Mdiamond" or n.id.lower() in ["start"]
        ]
        
        if not start_nodes:
            return []  # Start node check handles this
        
        start_node = start_nodes[0]
        
        # BFS from start
        visited = set()
        queue = [start_node.id]
        
        while queue:
            node_id = queue.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)
            
            # Add neighbors
            for edge in graph.outgoing_edges(node_id):
                if edge.to_node not in visited:
                    queue.append(edge.to_node)
        
        # Check for unreachable nodes
        diagnostics = []
        for node_id in graph.nodes:
            if node_id not in visited:
                diagnostics.append(Diagnostic(
                    rule=self.name,
                    severity=Severity.ERROR,
                    message=f"Node '{node_id}' is not reachable from start",
                    node_id=node_id
                ))
        
        return diagnostics


class EdgeTargetExistsRule(LintRule):
    """All edge targets must reference existing nodes."""
    
    def __init__(self):
        super().__init__("edge_target_exists")
    
    def apply(self, graph: Graph) -> List[Diagnostic]:
        diagnostics = []
        
        for edge in graph.edges:
            if edge.from_node not in graph.nodes:
                diagnostics.append(Diagnostic(
                    rule=self.name,
                    severity=Severity.ERROR,
                    message=f"Edge source node '{edge.from_node}' does not exist",
                    edge=(edge.from_node, edge.to_node)
                ))
            
            if edge.to_node not in graph.nodes:
                diagnostics.append(Diagnostic(
                    rule=self.name,
                    severity=Severity.ERROR,
                    message=f"Edge target node '{edge.to_node}' does not exist",
                    edge=(edge.from_node, edge.to_node)
                ))
        
        return diagnostics


class StartNoIncomingRule(LintRule):
    """Start node must have no incoming edges."""
    
    def __init__(self):
        super().__init__("start_no_incoming")
    
    def apply(self, graph: Graph) -> List[Diagnostic]:
        start_nodes = [
            n for n in graph.nodes.values()
            if n.shape == "Mdiamond" or n.id.lower() == "start"
        ]
        
        if not start_nodes:
            return []
        
        start_node = start_nodes[0]
        incoming = graph.incoming_edges(start_node.id)
        
        if incoming:
            return [Diagnostic(
                rule=self.name,
                severity=Severity.ERROR,
                message=f"Start node '{start_node.id}' has {len(incoming)} incoming edges",
                node_id=start_node.id
            )]
        
        return []


class ExitNoOutgoingRule(LintRule):
    """Exit nodes must have no outgoing edges."""
    
    def __init__(self):
        super().__init__("exit_no_outgoing")
    
    def apply(self, graph: Graph) -> List[Diagnostic]:
        exit_nodes = [
            n for n in graph.nodes.values()
            if n.shape == "Msquare"
        ]
        
        diagnostics = []
        
        for exit_node in exit_nodes:
            outgoing = graph.outgoing_edges(exit_node.id)
            if outgoing:
                diagnostics.append(Diagnostic(
                    rule=self.name,
                    severity=Severity.ERROR,
                    message=f"Exit node '{exit_node.id}' has {len(outgoing)} outgoing edges",
                    node_id=exit_node.id
                ))
        
        return diagnostics


class PromptOnLLMNodesRule(LintRule):
    """LLM nodes should have a prompt or label."""
    
    def __init__(self):
        super().__init__("prompt_on_llm_nodes")
    
    def apply(self, graph: Graph) -> List[Diagnostic]:
        diagnostics = []
        
        for node in graph.nodes.values():
            # Codergen nodes (box shape or no explicit type)
            if node.shape == "box" and not node.type:
                if not node.prompt and not node.label:
                    diagnostics.append(Diagnostic(
                        rule=self.name,
                        severity=Severity.WARNING,
                        message=f"LLM node '{node.id}' has no prompt or label",
                        node_id=node.id,
                        fix="Add a 'prompt' or 'label' attribute"
                    ))
        
        return diagnostics


# Built-in rules registry
BUILT_IN_RULES = [
    StartNodeRule(),
    TerminalNodeRule(),
    ReachabilityRule(),
    EdgeTargetExistsRule(),
    StartNoIncomingRule(),
    ExitNoOutgoingRule(),
    PromptOnLLMNodesRule(),
]


def validate(graph: Graph, extra_rules: Optional[List[LintRule]] = None) -> List[Diagnostic]:
    """Validate a graph and return diagnostics."""
    rules = BUILT_IN_RULES.copy()
    if extra_rules:
        rules.extend(extra_rules)
    
    diagnostics = []
    for rule in rules:
        diagnostics.extend(rule.apply(graph))
    
    return diagnostics


def validate_or_raise(graph: Graph, extra_rules: Optional[List[LintRule]] = None) -> List[Diagnostic]:
    """Validate a graph and raise on errors."""
    diagnostics = validate(graph, extra_rules)
    
    errors = [d for d in diagnostics if d.severity == Severity.ERROR]
    if errors:
        error_messages = [f"{d.rule}: {d.message}" for d in errors]
        raise ValueError(f"Validation failed with {len(errors)} errors:\n" + "\n".join(error_messages))
    
    return diagnostics
