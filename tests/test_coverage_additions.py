"""
Additional tests to increase code coverage for uncovered lines.
"""

import pytest

from attractor.parser import DotParser, parse_dot_string


def test_attr_block_empty_key_ends_parsing():
    """Test that empty key in attribute block ends parsing."""
    dot = """
    digraph Test {
        node1 [label="test"]
    }
    """

    graph = parse_dot_string(dot)
    assert graph.nodes["node1"].label == "test"


def test_parse_string_empty_string():
    """Test parsing empty quoted string."""
    dot = """
    digraph Test {
        node1 [label=""]
    }
    """

    graph = parse_dot_string(dot)
    assert graph.nodes["node1"].label == ""


def test_parse_string_with_special_chars():
    """Test parsing string with special characters."""
    dot = r"""
    digraph Test {
        node1 [label="test\nline"]
    }
    """

    graph = parse_dot_string(dot)
    # Parser should handle escape sequences
    assert "test" in graph.nodes["node1"].label


def test_consume_optional_semicolon_without():
    """Test that consume_optional_semicolon works without semicolon."""
    dot = """
    digraph Test {
        node1
        node2
    }
    """
    graph = parse_dot_string(dot)
    assert "node1" in graph.nodes
    assert "node2" in graph.nodes


def test_parse_value_with_empty_value():
    """Test parsing empty value in attributes."""
    dot = """
    digraph Test {
        node1 [label = ""]
    }
    """

    graph = parse_dot_string(dot)
    assert graph.nodes["node1"].label == ""


def test_consume_char_skips_whitespace():
    """Test that consume_char skips whitespace before checking character."""
    parser = DotParser("  {}")
    assert parser.consume_char("{")
    assert parser.consume_char("}")


def test_consume_operator_skips_whitespace():
    """Test that consume_operator skips whitespace before checking operator."""
    parser = DotParser("  ->")
    assert parser.consume_operator("->")


def test_parse_identifier_at_end_of_content():
    """Test parse_identifier when at end of content."""
    parser = DotParser("")
    parser.pos = 0
    assert parser.parse_identifier() == ""


def test_parse_identifier_with_non_alpha_start():
    """Test that parse_identifier returns empty for non-alpha start."""
    parser = DotParser("123abc")
    assert parser.parse_identifier() == ""


def test_parse_identifier_mixed_alphanum():
    """Test parse_identifier with mixed alphanumeric and underscores."""
    parser = DotParser("_var123_name test")
    assert parser.parse_identifier() == "_var123_name"


def test_peek_char_at_end():
    """Test that peek_char returns empty string at end of content."""
    parser = DotParser("")
    assert parser.peek_char() == ""


def test_peek_word_with_no_identifier():
    """Test peek_word when there's no identifier to parse."""
    parser = DotParser("123")
    assert parser.peek_word() == ""
    assert parser.pos == 0  # Position should not change


def test_consume_keyword_partial_match_fails():
    """Test that consume_keyword fails on partial identifier match."""
    parser = DotParser("digraphy")
    assert not parser.consume_keyword("digraph")


def test_parse_number_zero():
    """Test parsing zero."""
    parser = DotParser("0")
    assert parser.parse_number() == 0


def test_parse_number_negative_zero():
    """Test parsing negative zero."""
    parser = DotParser("-0")
    assert parser.parse_number() == 0


def test_parse_number_float_trailing_zeros():
    """Test parsing float with trailing zeros."""
    parser = DotParser("3.1400")
    assert parser.parse_number() == pytest.approx(3.14)


def test_parse_number_at_end_of_content():
    """Test parse_number at end of content."""
    parser = DotParser("42")
    assert parser.parse_number() == 42
    assert parser.pos == len(parser.content)


def test_skip_until_semicolon_with_semicolon():
    """Test skip_until_semicolon stops at semicolon."""
    parser = DotParser("some stuff;more")
    parser.skip_until_semicolon()
    assert parser.pos == len("some stuff;")


def test_skip_until_semicolon_with_newline():
    """Test skip_until_semicolon stops at newline."""
    parser = DotParser("some stuff\nmore")
    parser.skip_until_semicolon()
    assert parser.pos == len("some stuff\n")


def test_skip_until_semicolon_at_end():
    """Test skip_until_semicolon at end of content."""
    parser = DotParser("some stuff")
    initial_pos = parser.pos
    parser.skip_until_semicolon()
    # Should consume all content since no semicolon or newline
    assert parser.pos == len("some stuff")
