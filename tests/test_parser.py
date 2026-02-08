"""
Tests for DOT parser.
"""

import pytest
from attractor.parser import parse_dot_string
from attractor.models import Graph


def test_simple_linear_pipeline():
    """Test parsing a simple linear pipeline."""
    dot = """
    digraph Simple {
        graph [goal="Run tests and report"]
        
        start [shape=Mdiamond, label="Start"]
        exit  [shape=Msquare, label="Exit"]
        
        run_tests [label="Run Tests", prompt="Run the test suite"]
        report    [label="Report", prompt="Summarize results"]
        
        start -> run_tests -> report -> exit
    }
    """
    
    graph = parse_dot_string(dot)
    
    assert graph.name == "Simple"
    assert graph.goal == "Run tests and report"
    assert len(graph.nodes) == 4
    assert "start" in graph.nodes
    assert "exit" in graph.nodes
    assert "run_tests" in graph.nodes
    assert "report" in graph.nodes
    
    # Check edges (chained edges should expand)
    assert len(graph.edges) == 3
    assert graph.edges[0].from_node == "start"
    assert graph.edges[0].to_node == "run_tests"


def test_node_attributes():
    """Test parsing node attributes."""
    dot = """
    digraph Test {
        node1 [label="Node One", shape=box, prompt="Do something", max_retries=3]
    }
    """
    
    graph = parse_dot_string(dot)
    
    node = graph.nodes["node1"]
    assert node.label == "Node One"
    assert node.shape == "box"
    assert node.prompt == "Do something"
    assert node.max_retries == 3


def test_edge_attributes():
    """Test parsing edge attributes."""
    dot = """
    digraph Test {
        a [shape=Mdiamond]
        b [shape=Msquare]
        a -> b [label="Next", condition="outcome=success", weight=10]
    }
    """
    
    graph = parse_dot_string(dot)
    
    edge = graph.edges[0]
    assert edge.label == "Next"
    assert edge.condition == "outcome=success"
    assert edge.weight == 10


def test_comments_stripped():
    """Test that comments are stripped."""
    dot = """
    digraph Test {
        // This is a line comment
        start [shape=Mdiamond]
        /* This is a
           block comment */
        exit [shape=Msquare]
        start -> exit
    }
    """
    
    graph = parse_dot_string(dot)
    
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1


def test_quoted_strings():
    """Test quoted string values."""
    dot = """
    digraph Test {
        node1 [label="Hello World", prompt="Line 1\\nLine 2"]
    }
    """
    
    graph = parse_dot_string(dot)
    
    node = graph.nodes["node1"]
    assert node.label == "Hello World"
    assert node.prompt == "Line 1\nLine 2"


def test_branching_workflow():
    """Test a workflow with conditional branches."""
    dot = """
    digraph Branch {
        graph [goal="Test workflow"]
        
        start [shape=Mdiamond]
        exit  [shape=Msquare]
        plan  [label="Plan"]
        impl  [label="Implement"]
        gate  [shape=diamond, label="Check"]
        
        start -> plan -> impl -> gate
        gate -> exit [label="Pass", condition="outcome=success"]
        gate -> impl [label="Retry", condition="outcome=fail"]
    }
    """
    
    graph = parse_dot_string(dot)
    
    assert len(graph.nodes) == 5
    assert len(graph.edges) == 5
    
    # Check conditional edges
    exit_edges = graph.outgoing_edges("gate")
    assert len(exit_edges) == 2
    
    pass_edge = [e for e in exit_edges if e.label == "Pass"][0]
    assert pass_edge.condition == "outcome=success"
    
    retry_edge = [e for e in exit_edges if e.label == "Retry"][0]
    assert retry_edge.condition == "outcome=fail"
