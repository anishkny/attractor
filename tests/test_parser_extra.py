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
