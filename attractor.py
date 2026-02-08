"""
Attractor - A component for intercepting, authenticating, and routing network traffic.

This implementation provides the core functionality of an Attractor pattern as used in
zero-trust network architectures and access management systems.
"""

import logging
import socket
import threading
from typing import Dict, Optional, Callable, Tuple, Any
from dataclasses import dataclass
from enum import Enum


class AuthResult(Enum):
    """Authentication result states"""
    ALLOWED = "allowed"
    DENIED = "denied"
    PENDING = "pending"


@dataclass
class Connection:
    """Represents an incoming connection"""
    source_addr: Tuple[str, int]
    destination: str
    protocol: str
    metadata: Dict[str, Any]


class Attractor:
    """
    Attractor - Intercepts network traffic and manages authentication/routing.
    
    The Attractor acts as an intelligent proxy that:
    1. Attracts/intercepts incoming connections
    2. Authenticates the source
    3. Authorizes access to the destination
    4. Routes traffic to the appropriate backend
    5. Provides observability and logging
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        auth_handler: Optional[Callable] = None,
        route_handler: Optional[Callable] = None
    ):
        """
        Initialize the Attractor.
        
        Args:
            host: Host address to bind to
            port: Port to listen on
            auth_handler: Custom authentication handler
            route_handler: Custom routing handler
        """
        self.host = host
        self.port = port
        self.auth_handler = auth_handler or self._default_auth_handler
        self.route_handler = route_handler or self._default_route_handler
        self.running = False
        self.connections: Dict[str, Connection] = {}
        self.logger = logging.getLogger(__name__)
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def start(self):
        """Start the Attractor service"""
        self.running = True
        self.logger.info(f"Starting Attractor on {self.host}:{self.port}")
        
        try:
            # Create socket and bind
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            self.socket.settimeout(1.0)  # Allow checking self.running periodically
            
            self.logger.info(f"Attractor listening on {self.host}:{self.port}")
            
            # Accept connections
            while self.running:
                try:
                    client_socket, client_addr = self.socket.accept()
                    self.logger.info(f"Accepted connection from {client_addr}")
                    
                    # Handle connection in a separate thread
                    thread = threading.Thread(
                        target=self._handle_connection,
                        args=(client_socket, client_addr)
                    )
                    thread.daemon = True
                    thread.start()
                    
                except socket.timeout:
                    continue  # Check if still running
                except Exception as e:
                    if self.running:
                        self.logger.error(f"Error accepting connection: {e}")
                    
        except Exception as e:
            self.logger.error(f"Failed to start Attractor: {e}")
            raise
        finally:
            self.socket.close()
            self.logger.info("Attractor stopped")
    
    def stop(self):
        """Stop the Attractor service"""
        self.logger.info("Stopping Attractor...")
        self.running = False
    
    def _handle_connection(self, client_socket: socket.socket, client_addr: Tuple[str, int]):
        """
        Handle an incoming connection.
        
        Args:
            client_socket: Client socket
            client_addr: Client address
        """
        try:
            # Create connection object
            connection = Connection(
                source_addr=client_addr,
                destination="",  # Will be determined from request
                protocol="tcp",
                metadata={}
            )
            
            # Receive initial data
            data = client_socket.recv(1024)
            if not data:
                self.logger.warning(f"No data received from {client_addr}")
                client_socket.close()
                return
            
            # Parse destination from data (simplified)
            connection.destination = self._parse_destination(data)
            
            # Authenticate
            auth_result = self.authenticate(connection)
            
            if auth_result == AuthResult.ALLOWED:
                self.logger.info(f"Authentication successful for {client_addr}")
                
                # Route the connection
                self.route(connection, client_socket, data)
            else:
                self.logger.warning(f"Authentication failed for {client_addr}")
                response = b"HTTP/1.1 403 Forbidden\r\nContent-Length: 13\r\n\r\nAccess Denied"
                client_socket.send(response)
                
        except Exception as e:
            self.logger.error(f"Error handling connection from {client_addr}: {e}")
        finally:
            client_socket.close()
    
    def authenticate(self, connection: Connection) -> AuthResult:
        """
        Authenticate a connection.
        
        Args:
            connection: Connection to authenticate
            
        Returns:
            Authentication result
        """
        self.logger.info(f"Authenticating connection from {connection.source_addr}")
        return self.auth_handler(connection)
    
    def route(self, connection: Connection, client_socket: socket.socket, initial_data: bytes):
        """
        Route an authenticated connection to its destination.
        
        Args:
            connection: Authenticated connection
            client_socket: Client socket
            initial_data: Initial data received from client
        """
        self.logger.info(f"Routing connection from {connection.source_addr} to {connection.destination}")
        self.route_handler(connection, client_socket, initial_data)
    
    def _default_auth_handler(self, connection: Connection) -> AuthResult:
        """
        Default authentication handler - allows all connections.
        
        Args:
            connection: Connection to authenticate
            
        Returns:
            Authentication result
        """
        # In a real implementation, this would check credentials, tokens, etc.
        self.logger.debug(f"Using default auth handler for {connection.source_addr}")
        return AuthResult.ALLOWED
    
    def _default_route_handler(
        self,
        connection: Connection,
        client_socket: socket.socket,
        initial_data: bytes
    ):
        """
        Default routing handler - sends a simple response.
        
        Args:
            connection: Connection to route
            client_socket: Client socket
            initial_data: Initial data from client
        """
        # In a real implementation, this would forward to actual backends
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Length: 45\r\n"
            b"\r\n"
            b"Connection routed through Attractor service.\n"
        )
        client_socket.send(response)
    
    def _parse_destination(self, data: bytes) -> str:
        """
        Parse destination from request data.
        
        Args:
            data: Request data
            
        Returns:
            Destination address
        """
        # Simple HTTP HOST header parsing
        try:
            lines = data.decode('utf-8', errors='ignore').split('\r\n')
            for line in lines:
                if line.lower().startswith('host:'):
                    return line.split(':', 1)[1].strip()
        except Exception as e:
            self.logger.debug(f"Error parsing destination: {e}")
        
        return "unknown"
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the Attractor.
        
        Returns:
            Dictionary with statistics
        """
        return {
            "running": self.running,
            "host": self.host,
            "port": self.port,
            "active_connections": len(self.connections)
        }


if __name__ == "__main__":
    # Example usage
    attractor = Attractor(host="127.0.0.1", port=8080)
    
    try:
        attractor.start()
    except KeyboardInterrupt:
        attractor.stop()
