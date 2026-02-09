"""
Tests for model stylesheet parsing and matching.
"""

from attractor.models import Graph, Node
from attractor.stylesheet import (
    ModelStylesheet,
    Selector,
    apply_stylesheet,
    parse_stylesheet,
)


def test_selector_universal():
    """Test universal selector (*)."""
    selector = Selector("*")
    node = Node(id="test", attrs={})

    assert selector.type == "universal"
    assert selector.matches(node)
    assert selector.specificity() == 0


def test_selector_id():
    """Test ID selector (#node_id)."""
    selector = Selector("#my_node")
    matching_node = Node(id="my_node", attrs={})
    non_matching_node = Node(id="other_node", attrs={})

    assert selector.type == "id"
    assert selector.matches(matching_node)
    assert not selector.matches(non_matching_node)
    assert selector.specificity() == 100


def test_selector_class():
    """Test class selector (.classname)."""
    selector = Selector(".critical")
    matching_node = Node(id="test", attrs={"class": "critical,important"})
    non_matching_node = Node(id="test2", attrs={"class": "normal"})

    assert selector.type == "class"
    assert selector.matches(matching_node)
    assert not selector.matches(non_matching_node)
    assert selector.specificity() == 10


def test_selector_type():
    """Test type selector (typename)."""
    selector = Selector("codergen")
    matching_node = Node(id="test", attrs={"type": "codergen"})
    non_matching_node = Node(id="test2", attrs={"type": "tool"})

    assert selector.type == "type"
    assert selector.matches(matching_node)
    assert not selector.matches(non_matching_node)
    assert selector.specificity() == 1


def test_stylesheet_parsing():
    """Test parsing a simple stylesheet."""
    stylesheet_text = """
    * {
        llm_model: gpt-4;
        reasoning_effort: medium;
    }

    .critical {
        llm_model: gpt-4-turbo;
        reasoning_effort: high;
    }

    #special_node {
        llm_model: claude-3-opus;
        llm_provider: anthropic;
    }
    """

    stylesheet = ModelStylesheet(stylesheet_text)

    assert len(stylesheet.rules) == 3
    assert stylesheet.rules[0].selector == "*"
    assert stylesheet.rules[1].selector == ".critical"
    assert stylesheet.rules[2].selector == "#special_node"


def test_stylesheet_apply_specificity():
    """Test that more specific rules override less specific ones."""
    stylesheet_text = """
    * {
        llm_model: gpt-3.5-turbo;
        reasoning_effort: low;
    }

    .important {
        llm_model: gpt-4;
        reasoning_effort: medium;
    }

    #critical_task {
        llm_model: gpt-4-turbo;
    }
    """

    stylesheet = ModelStylesheet(stylesheet_text)

    # Test node with multiple matching rules
    node = Node(id="critical_task", attrs={"class": "important"})
    config = stylesheet.apply(node)

    # ID selector should win for llm_model
    assert config["llm_model"] == "gpt-4-turbo"
    # Class selector should provide reasoning_effort (not overridden by ID)
    assert config["reasoning_effort"] == "medium"


def test_stylesheet_with_comments():
    """Test stylesheet with comments."""
    stylesheet_text = """
    // Universal defaults
    * {
        llm_model: gpt-4; // Default model
    }

    /* Critical nodes get better models */
    .critical {
        llm_model: claude-3-opus;
    }
    """

    stylesheet = ModelStylesheet(stylesheet_text)

    assert len(stylesheet.rules) == 2


def test_get_model_config():
    """Test getting complete model config for a node."""
    stylesheet_text = """
    * {
        llm_model: gpt-4;
        reasoning_effort: medium;
    }

    .fast {
        llm_model: gpt-3.5-turbo;
        reasoning_effort: low;
    }
    """

    stylesheet = ModelStylesheet(stylesheet_text)

    # Node with explicit attributes
    node = Node(id="test", attrs={
        "class": "fast",
        "llm_provider": "openai"
    })

    config = stylesheet.get_model_config(node)

    assert config["llm_model"] == "gpt-3.5-turbo"  # From stylesheet
    assert config["reasoning_effort"] == "low"     # From stylesheet
    assert config["llm_provider"] == "openai"      # From node attrs


def test_apply_stylesheet_to_graph():
    """Test applying stylesheet to all nodes in a graph."""
    stylesheet_text = """
    * {
        llm_model: gpt-4;
    }

    .critical {
        llm_model: claude-3-opus;
    }
    """

    nodes = {
        "node1": Node(id="node1", attrs={}),
        "node2": Node(id="node2", attrs={"class": "critical"}),
    }

    graph = Graph(
        name="test_graph",
        nodes=nodes,
        edges=[],
        attrs={"model_stylesheet": stylesheet_text}
    )

    configs = apply_stylesheet(graph)

    assert configs["node1"]["llm_model"] == "gpt-4"
    assert configs["node2"]["llm_model"] == "claude-3-opus"


def test_empty_stylesheet():
    """Test handling of empty stylesheet."""
    stylesheet = ModelStylesheet("")
    node = Node(id="test", attrs={})

    config = stylesheet.apply(node)
    assert config == {}


def test_parse_stylesheet_function():
    """Test the convenience parse_stylesheet function."""
    stylesheet_text = """
    * {
        llm_model: gpt-4;
    }
    """

    stylesheet = parse_stylesheet(stylesheet_text)
    assert isinstance(stylesheet, ModelStylesheet)
    assert len(stylesheet.rules) == 1
