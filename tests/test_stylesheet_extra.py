"""
Additional tests for stylesheet edge cases.
"""

from attractor.models import Node
from attractor.stylesheet import ModelStylesheet, Selector


def test_selector_unknown_type_fallbacks():
    selector = Selector("*")
    selector.type = "unknown"
    node = Node(id="node", attrs={})

    assert selector.matches(node) is False
    assert selector.specificity() == 0


def test_get_model_config_with_all_attrs():
    stylesheet = ModelStylesheet(
        """
        * {
            llm_model: gpt-4;
            llm_provider: openai;
            reasoning_effort: high;
        }
        """
    )

    node = Node(
        id="task",
        attrs={
            "llm_model": "gpt-3.5",
            "llm_provider": "anthropic",
            "reasoning_effort": "low",
        },
    )

    config = stylesheet.get_model_config(node)

    assert config["llm_model"] == "gpt-4"
    assert config["llm_provider"] == "openai"
    assert config["reasoning_effort"] == "high"
