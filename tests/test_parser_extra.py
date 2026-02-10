"""
Additional tests for DOT parser edge cases.
"""

import pytest

from attractor.parser import DotParser, parse_dot_string


def test_parse_edge_defaults_subgraph_and_misc():
    dot = """
    digraph Test {
        graph [goal=true]
        node [shape=box]
        edge [weight=2, label="L"]

        subgraph cluster_0 {
            a;
            b;
            a -> b [weight=-1.5];
        }

        123; // invalid statement should be skipped
        stray = "value";
        node1 [label="Hello\\qWorld"]
        node2;
        node1 -> node2;
    }
    """

    graph = parse_dot_string(dot)

    assert graph.attrs["goal"] is True
    assert graph.nodes["node1"].label == "HelloqWorld"

    sub_edge = next(e for e in graph.edges if e.from_node == "a" and e.to_node == "b")
    assert sub_edge.attrs["weight"] == -1.5

    last_edge = graph.edges[-1]
    assert last_edge.label == "L"
    assert last_edge.weight == 2


def test_parse_value_empty_string():
    dot = """
    digraph Test {
        node1 [label=]
    }
    """

    graph = parse_dot_string(dot)
    assert graph.nodes["node1"].attrs["label"] == ""


def test_parse_identifier_and_peek_char_at_end():
    parser = DotParser("1")
    assert parser.parse_identifier() == ""
    parser.pos = len(parser.content)
    assert parser.peek_char() == ""


def test_attr_block_missing_equals_raises():
    parser = DotParser("[foo]")
    with pytest.raises(ValueError, match="Expected '='"):
        parser.parse_attr_block()


def test_consume_keyword_with_longer_identifier_fails():
    parser = DotParser("digraphy {}")
    assert not parser.consume_keyword("digraph")
    with pytest.raises(ValueError, match="Expected 'digraph'"):
        parser.parse()

def test_parse_missing_opening_brace():
    """Test parsing fails when opening brace is missing."""
    parser = DotParser("digraph Test")
    with pytest.raises(ValueError, match=r"Expected '\{' after digraph name"):
        parser.parse()


def test_parse_missing_brace_after_subgraph():
    """Test parsing fails when subgraph opening brace is missing."""
    dot = """
    digraph Test {
        subgraph cluster_0
    }
    """
    with pytest.raises(ValueError, match=r"Expected '\{' after subgraph"):
        parse_dot_string(dot)


def test_parse_string_with_escape_sequences():
    """Test parsing strings with various escape sequences."""
    dot = r"""
    digraph Test {
        node1 [label="Line 1\nLine 2\tTabbed", attrs="Quoted: \"hello\""]
        node2 [text="Backslash: \\"]
    }
    """

    graph = parse_dot_string(dot)
    assert "Line 1\nLine 2\tTabbed" in graph.nodes["node1"].label
    assert 'Quoted: "hello"' in graph.nodes["node1"].attrs["attrs"]
    assert "Backslash: \\" in graph.nodes["node2"].attrs["text"]


def test_parse_negative_numbers():
    """Test parsing negative integer and float values."""
    dot = """
    digraph Test {
        node1 [weight=-5, score=-3.14]
    }
    """

    graph = parse_dot_string(dot)
    assert graph.nodes["node1"].attrs["weight"] == -5
    assert graph.nodes["node1"].attrs["score"] == pytest.approx(-3.14)


def test_parse_float_without_integer_part():
    """Test parsing float with negative sign and decimal."""
    dot = """
    digraph Test {
        node1 [value=-.5]
    }
    """

    graph = parse_dot_string(dot)
    # Parser handles -.5 correctly
    assert graph.nodes["node1"].attrs["value"] == pytest.approx(-0.5)


def test_parse_edge_with_multiple_nodes():
    """Test parsing edge with multiple nodes in chain."""
    dot = """
    digraph Test {
        a -> b -> c -> d [label="Multi"]
    }
    """

    graph = parse_dot_string(dot)
    assert len(graph.edges) == 3
    assert graph.edges[0].from_node == "a"
    assert graph.edges[0].to_node == "b"
    assert graph.edges[1].from_node == "b"
    assert graph.edges[1].to_node == "c"
    assert graph.edges[2].from_node == "c"
    assert graph.edges[2].to_node == "d"
    # All edges should have the same attributes
    assert all(e.label == "Multi" for e in graph.edges)


def test_parse_edge_with_no_attributes():
    """Test parsing edge without attribute block."""
    dot = """
    digraph Test {
        a -> b
    }
    """

    graph = parse_dot_string(dot)
    edge = graph.edges[0]
    assert edge.from_node == "a"
    assert edge.to_node == "b"
    assert edge.attrs == {}


def test_parse_attr_block_with_commas():
    """Test parsing attribute block with optional commas."""
    dot = """
    digraph Test {
        node1 [label="A", shape=box, bg="red"]
        node2 [label="B" shape=circle]
    }
    """

    graph = parse_dot_string(dot)
    assert graph.nodes["node1"].label == "A"
    assert graph.nodes["node1"].shape == "box"
    assert graph.nodes["node1"].attrs["bg"] == "red"
    assert graph.nodes["node2"].label == "B"
    assert graph.nodes["node2"].shape == "circle"


def test_parse_boolean_values():
    """Test parsing boolean true and false values."""
    dot = """
    digraph Test {
        node1 [required=true, optional=false]
    }
    """

    graph = parse_dot_string(dot)
    assert graph.nodes["node1"].attrs["required"] is True
    assert graph.nodes["node1"].attrs["optional"] is False


def test_parse_bare_identifier_values():
    """Test parsing bare identifiers as values."""
    dot = """
    digraph Test {
        node1 [shape=diamond, status=blue, enum_val=CONSTANT]
    }
    """

    graph = parse_dot_string(dot)
    assert graph.nodes["node1"].shape == "diamond"
    assert graph.nodes["node1"].attrs["status"] == "blue"
    assert graph.nodes["node1"].attrs["enum_val"] == "CONSTANT"


def test_parse_graph_level_attributes():
    """Test parsing graph-level attributes."""
    dot = """
    digraph Test {
        graph [rankdir=LR, label="My Graph"]
        node [shape=box]
    }
    """

    graph = parse_dot_string(dot)
    assert graph.attrs["rankdir"] == "LR"
    assert graph.attrs["label"] == "My Graph"


def test_skip_whitespace_and_empty_statements():
    """Test parser skips whitespace and empty statements."""
    dot = """
    digraph Test {


        node1;

        ;
        node1 -> node2;


    }
    """

    graph = parse_dot_string(dot)
    assert "node1" in graph.nodes
    assert "node2" in graph.nodes
    assert len(graph.edges) == 1