"""
Model stylesheet parsing and matching for Attractor.

Implements a CSS-like stylesheet for configuring LLM model and provider
settings on a per-node basis using selectors.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List

from .models import Graph, Node


@dataclass
class StyleRule:
    """A single style rule with selector and properties."""

    selector: str
    properties: Dict[str, Any]
    specificity: int  # Higher specificity wins


class Selector:
    """Selector for matching nodes."""

    def __init__(self, selector_str: str):
        self.selector = selector_str.strip()
        self.type = self._determine_type()

    def _determine_type(self) -> str:
        """Determine selector type (universal, id, class, or type)."""
        if self.selector == "*":
            return "universal"
        elif self.selector.startswith("#"):
            return "id"
        elif self.selector.startswith("."):
            return "class"
        else:
            return "type"

    def matches(self, node: Node) -> bool:
        """Check if this selector matches the given node."""
        if self.type == "universal":
            return True
        elif self.type == "id":
            return node.id == self.selector[1:]
        elif self.type == "class":
            class_name = self.selector[1:]
            node_classes = node.attrs.get("class", "").split(",")
            node_classes = [c.strip() for c in node_classes if c.strip()]
            return class_name in node_classes
        elif self.type == "type":
            node_type = node.attrs.get("type", "")
            return node_type == self.selector
        return False

    def specificity(self) -> int:
        """Calculate specificity (higher is more specific)."""
        if self.type == "universal":
            return 0
        elif self.type == "type":
            return 1
        elif self.type == "class":
            return 10
        elif self.type == "id":
            return 100
        return 0


class ModelStylesheet:
    """Parser and matcher for model stylesheets."""

    def __init__(self, stylesheet: str = ""):
        self.rules: List[StyleRule] = []
        if stylesheet:
            self.parse(stylesheet)

    def parse(self, stylesheet: str):
        """Parse a CSS-like stylesheet string."""
        # Remove comments (both // and /* */ style)
        stylesheet = re.sub(r"//.*?$", "", stylesheet, flags=re.MULTILINE)
        stylesheet = re.sub(r"/\*.*?\*/", "", stylesheet, flags=re.DOTALL)

        # Split into rules
        rule_pattern = r"([^{]+)\{([^}]+)\}"
        matches = re.finditer(rule_pattern, stylesheet)

        for match in matches:
            selector_str = match.group(1).strip()
            properties_str = match.group(2).strip()

            # Parse properties
            properties = {}
            for line in properties_str.split(";"):
                line = line.strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip().strip("\"'")
                    properties[key] = value

            # Create rule
            selector = Selector(selector_str)
            rule = StyleRule(
                selector=selector_str,
                properties=properties,
                specificity=selector.specificity(),
            )
            self.rules.append(rule)

    def apply(self, node: Node) -> Dict[str, Any]:
        """Apply stylesheet rules to a node and return computed properties."""
        computed = {}

        # Sort rules by specificity (lowest to highest)
        sorted_rules = sorted(self.rules, key=lambda r: r.specificity)

        # Apply matching rules in order (later rules override)
        for rule in sorted_rules:
            selector = Selector(rule.selector)
            if selector.matches(node):
                computed.update(rule.properties)

        return computed

    def get_model_config(self, node: Node) -> Dict[str, Any]:
        """
        Get model configuration for a node.

        Returns:
            Dictionary with keys like 'llm_model', 'llm_provider', 'reasoning_effort'
        """
        # Start with node's explicit attributes
        config = {}
        if "llm_model" in node.attrs:
            config["llm_model"] = node.attrs["llm_model"]
        if "llm_provider" in node.attrs:
            config["llm_provider"] = node.attrs["llm_provider"]
        if "reasoning_effort" in node.attrs:
            config["reasoning_effort"] = node.attrs["reasoning_effort"]

        # Apply stylesheet (may override)
        stylesheet_props = self.apply(node)
        config.update(stylesheet_props)

        return config


def parse_stylesheet(stylesheet_str: str) -> ModelStylesheet:
    """Parse a model stylesheet string."""
    return ModelStylesheet(stylesheet_str)


def apply_stylesheet(graph: Graph) -> Dict[str, Dict[str, Any]]:
    """
    Apply graph's model stylesheet to all nodes.

    Returns:
        Dictionary mapping node_id -> computed properties
    """
    stylesheet = ModelStylesheet(graph.model_stylesheet)

    result = {}
    for node_id, node in graph.nodes.items():
        result[node_id] = stylesheet.get_model_config(node)

    return result
