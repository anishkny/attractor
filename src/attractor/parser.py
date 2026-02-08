"""
DOT parser for Attractor pipelines.

Parses a strict subset of the Graphviz DOT language.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from .models import Graph, Node, Edge


def parse_dot(filepath: str) -> Graph:
    """Parse a DOT file and return a Graph."""
    with open(filepath, 'r') as f:
        content = f.read()
    return parse_dot_string(content)


def parse_dot_string(content: str) -> Graph:
    """Parse DOT content string and return a Graph."""
    # Strip comments
    content = strip_comments(content)
    
    # Parse the digraph
    parser = DotParser(content)
    return parser.parse()


def strip_comments(content: str) -> str:
    """Remove // and /* */ comments from DOT content."""
    # Remove /* */ block comments
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    # Remove // line comments
    content = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)
    return content


class DotParser:
    """Parser for DOT syntax."""
    
    def __init__(self, content: str):
        self.content = content
        self.pos = 0
        self.graph_attrs: Dict[str, Any] = {}
        self.node_defaults: Dict[str, Any] = {}
        self.edge_defaults: Dict[str, Any] = {}
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self.graph_name = ""
    
    def parse(self) -> Graph:
        """Parse the DOT content and return a Graph."""
        self.skip_whitespace()
        
        # Expect 'digraph'
        if not self.consume_keyword('digraph'):
            raise ValueError("Expected 'digraph' at start")
        
        self.skip_whitespace()
        
        # Parse graph name (optional but typically present)
        self.graph_name = self.parse_identifier()
        
        self.skip_whitespace()
        
        # Expect '{'
        if not self.consume_char('{'):
            raise ValueError("Expected '{' after digraph name")
        
        # Parse statements
        while True:
            self.skip_whitespace()
            
            if self.peek_char() == '}':
                self.consume_char('}')
                break
            
            self.parse_statement()
        
        # Create graph
        graph = Graph(
            name=self.graph_name,
            nodes=self.nodes,
            edges=self.edges,
            attrs=self.graph_attrs
        )
        
        return graph
    
    def parse_statement(self):
        """Parse a statement (graph attr, node def, edge, etc.)."""
        self.skip_whitespace()
        
        # Check for keywords
        if self.peek_word() == 'graph':
            self.parse_graph_attrs()
        elif self.peek_word() == 'node':
            self.parse_node_defaults()
        elif self.peek_word() == 'edge':
            self.parse_edge_defaults()
        elif self.peek_word() == 'subgraph':
            self.parse_subgraph()
        else:
            # Could be node def, edge, or graph attr assignment
            # Try to parse identifier
            start_pos = self.pos
            identifier = self.parse_identifier()
            
            if not identifier:
                # Skip empty lines
                self.skip_until_semicolon()
                return
            
            self.skip_whitespace()
            
            # Check what follows
            next_char = self.peek_char()
            
            if next_char == '-':
                # It's an edge
                self.pos = start_pos
                self.parse_edge()
            elif next_char == '=':
                # It's a graph-level attribute
                self.consume_char('=')
                self.skip_whitespace()
                value = self.parse_value()
                self.graph_attrs[identifier] = value
                self.consume_optional_semicolon()
            elif next_char == '[':
                # It's a node definition
                attrs = self.parse_attr_block()
                # Apply defaults
                node_attrs = {**self.node_defaults, **attrs}
                self.nodes[identifier] = Node(id=identifier, attrs=node_attrs)
                self.consume_optional_semicolon()
            else:
                # Node with no attributes
                node_attrs = {**self.node_defaults}
                self.nodes[identifier] = Node(id=identifier, attrs=node_attrs)
                self.consume_optional_semicolon()
    
    def parse_graph_attrs(self):
        """Parse 'graph [...]'."""
        self.consume_keyword('graph')
        self.skip_whitespace()
        attrs = self.parse_attr_block()
        self.graph_attrs.update(attrs)
        self.consume_optional_semicolon()
    
    def parse_node_defaults(self):
        """Parse 'node [...]'."""
        self.consume_keyword('node')
        self.skip_whitespace()
        attrs = self.parse_attr_block()
        self.node_defaults.update(attrs)
        self.consume_optional_semicolon()
    
    def parse_edge_defaults(self):
        """Parse 'edge [...]'."""
        self.consume_keyword('edge')
        self.skip_whitespace()
        attrs = self.parse_attr_block()
        self.edge_defaults.update(attrs)
        self.consume_optional_semicolon()
    
    def parse_subgraph(self):
        """Parse subgraph (flatten contents)."""
        self.consume_keyword('subgraph')
        self.skip_whitespace()
        
        # Optional subgraph name
        if self.peek_char() not in ['{', '']:
            self.parse_identifier()  # Skip name
            self.skip_whitespace()
        
        if not self.consume_char('{'):
            raise ValueError("Expected '{' after subgraph")
        
        # Parse statements inside subgraph
        while True:
            self.skip_whitespace()
            
            if self.peek_char() == '}':
                self.consume_char('}')
                break
            
            self.parse_statement()
    
    def parse_edge(self):
        """Parse edge statement: A -> B -> C [attrs]."""
        # Parse first node
        from_node = self.parse_identifier()
        
        # Collect all nodes in the chain
        chain = [from_node]
        
        while True:
            self.skip_whitespace()
            
            if not self.consume_operator('->'):
                break
            
            self.skip_whitespace()
            to_node = self.parse_identifier()
            chain.append(to_node)
        
        # Parse optional attributes
        self.skip_whitespace()
        if self.peek_char() == '[':
            attrs = self.parse_attr_block()
        else:
            attrs = {}
        
        # Apply defaults
        edge_attrs = {**self.edge_defaults, **attrs}
        
        # Create edges for each pair in the chain
        for i in range(len(chain) - 1):
            # Ensure nodes exist
            if chain[i] not in self.nodes:
                self.nodes[chain[i]] = Node(id=chain[i], attrs={**self.node_defaults})
            if chain[i+1] not in self.nodes:
                self.nodes[chain[i+1]] = Node(id=chain[i+1], attrs={**self.node_defaults})
            
            self.edges.append(Edge(
                from_node=chain[i],
                to_node=chain[i+1],
                attrs=edge_attrs.copy()
            ))
        
        self.consume_optional_semicolon()
    
    def parse_attr_block(self) -> Dict[str, Any]:
        """Parse [key=value, key=value, ...]."""
        if not self.consume_char('['):
            return {}
        
        attrs = {}
        
        while True:
            self.skip_whitespace()
            
            if self.peek_char() == ']':
                self.consume_char(']')
                break
            
            # Parse key
            key = self.parse_identifier()
            if not key:
                break
            
            self.skip_whitespace()
            
            if not self.consume_char('='):
                raise ValueError(f"Expected '=' after attribute key '{key}'")
            
            self.skip_whitespace()
            
            # Parse value
            value = self.parse_value()
            attrs[key] = value
            
            self.skip_whitespace()
            
            # Optional comma
            self.consume_char(',')
            
            self.skip_whitespace()
        
        return attrs
    
    def parse_value(self) -> Any:
        """Parse a value (string, int, float, bool, duration)."""
        self.skip_whitespace()
        
        ch = self.peek_char()
        
        if ch == '"':
            return self.parse_string()
        elif ch == '-' or ch.isdigit():
            return self.parse_number()
        elif ch.isalpha():
            word = self.parse_identifier()
            if word == 'true':
                return True
            elif word == 'false':
                return False
            else:
                # Could be a duration or bare identifier
                return word
        else:
            return ""
    
    def parse_string(self) -> str:
        """Parse a quoted string with escape sequences."""
        if not self.consume_char('"'):
            raise ValueError("Expected '\"' at start of string")
        
        result = []
        
        while self.pos < len(self.content):
            ch = self.content[self.pos]
            
            if ch == '"':
                self.pos += 1
                break
            elif ch == '\\' and self.pos + 1 < len(self.content):
                # Escape sequence
                self.pos += 1
                next_ch = self.content[self.pos]
                if next_ch == 'n':
                    result.append('\n')
                elif next_ch == 't':
                    result.append('\t')
                elif next_ch == '\\':
                    result.append('\\')
                elif next_ch == '"':
                    result.append('"')
                else:
                    result.append(next_ch)
                self.pos += 1
            else:
                result.append(ch)
                self.pos += 1
        
        return ''.join(result)
    
    def parse_number(self) -> Any:
        """Parse integer or float."""
        start_pos = self.pos
        
        # Optional negative sign
        if self.peek_char() == '-':
            self.pos += 1
        
        # Parse digits
        while self.pos < len(self.content) and self.content[self.pos].isdigit():
            self.pos += 1
        
        # Check for decimal point
        if self.pos < len(self.content) and self.content[self.pos] == '.':
            self.pos += 1
            while self.pos < len(self.content) and self.content[self.pos].isdigit():
                self.pos += 1
            return float(self.content[start_pos:self.pos])
        else:
            return int(self.content[start_pos:self.pos])
    
    def parse_identifier(self) -> str:
        """Parse an identifier [A-Za-z_][A-Za-z0-9_]*."""
        self.skip_whitespace()
        
        if self.pos >= len(self.content):
            return ""
        
        ch = self.content[self.pos]
        if not (ch.isalpha() or ch == '_'):
            return ""
        
        start_pos = self.pos
        self.pos += 1
        
        while self.pos < len(self.content):
            ch = self.content[self.pos]
            if ch.isalnum() or ch == '_':
                self.pos += 1
            else:
                break
        
        return self.content[start_pos:self.pos]
    
    def peek_char(self) -> str:
        """Peek at the current character without consuming."""
        if self.pos < len(self.content):
            return self.content[self.pos]
        return ''
    
    def peek_word(self) -> str:
        """Peek at the next word without consuming."""
        start_pos = self.pos
        word = self.parse_identifier()
        self.pos = start_pos
        return word
    
    def consume_char(self, ch: str) -> bool:
        """Consume a specific character."""
        self.skip_whitespace()
        if self.pos < len(self.content) and self.content[self.pos] == ch:
            self.pos += 1
            return True
        return False
    
    def consume_keyword(self, keyword: str) -> bool:
        """Consume a specific keyword."""
        self.skip_whitespace()
        if self.content[self.pos:self.pos+len(keyword)] == keyword:
            # Make sure it's not part of a longer identifier
            if self.pos + len(keyword) < len(self.content):
                next_ch = self.content[self.pos + len(keyword)]
                if next_ch.isalnum() or next_ch == '_':
                    return False
            self.pos += len(keyword)
            return True
        return False
    
    def consume_operator(self, op: str) -> bool:
        """Consume an operator like '->'."""
        self.skip_whitespace()
        if self.content[self.pos:self.pos+len(op)] == op:
            self.pos += len(op)
            return True
        return False
    
    def consume_optional_semicolon(self):
        """Consume an optional semicolon."""
        self.skip_whitespace()
        self.consume_char(';')
    
    def skip_whitespace(self):
        """Skip whitespace characters."""
        while self.pos < len(self.content) and self.content[self.pos].isspace():
            self.pos += 1
    
    def skip_until_semicolon(self):
        """Skip until semicolon or newline."""
        while self.pos < len(self.content):
            ch = self.content[self.pos]
            if ch == ';' or ch == '\n':
                self.pos += 1
                break
            self.pos += 1
