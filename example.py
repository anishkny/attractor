"""
Example usage of the Attractor pattern.

This script demonstrates how to use the Attractor with custom
authentication and routing handlers.
"""

from attractor import Attractor, Connection, AuthResult
import socket
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def example_auth_handler(connection: Connection) -> AuthResult:
    """
    Example authentication handler.
    
    This demonstrates how to implement custom authentication logic.
    In a real system, you would check tokens, certificates, or other credentials.
    """
    logger.info(f"Authenticating connection from {connection.source_addr}")
    
    # Example: Allow only localhost connections
    if connection.source_addr[0] in ["127.0.0.1", "::1"]:
        logger.info("Connection from localhost - ALLOWED")
        return AuthResult.ALLOWED
    
    # Example: Check for specific destinations
    if connection.destination.endswith(".example.com"):
        logger.info(f"Connection to {connection.destination} - ALLOWED")
        return AuthResult.ALLOWED
    
    logger.warning(f"Connection denied for {connection.source_addr} -> {connection.destination}")
    return AuthResult.DENIED


def example_route_handler(connection: Connection, client_socket: socket.socket, initial_data: bytes):
    """
    Example routing handler.
    
    This demonstrates how to implement custom routing logic.
    In a real system, you would forward to actual backend services.
    """
    logger.info(f"Routing connection from {connection.source_addr} to {connection.destination}")
    
    # Example: Different responses based on destination
    if "api" in connection.destination.lower():
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: 38\r\n"
            b"\r\n"
            b'{"status": "ok", "service": "api"}\n'
        )
    else:
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/html\r\n"
            b"Content-Length: 130\r\n"
            b"\r\n"
            b"<html><head><title>Attractor</title></head>"
            b"<body><h1>Welcome</h1><p>Routed through Attractor</p></body></html>\n"
        )
    
    try:
        client_socket.send(response)
        logger.info(f"Response sent to {connection.source_addr}")
    except Exception as e:
        logger.error(f"Error sending response: {e}")


def main():
    """Main function to run the example"""
    logger.info("Starting Attractor example...")
    
    # Create Attractor with custom handlers
    attractor = Attractor(
        host="127.0.0.1",
        port=8080,
        auth_handler=example_auth_handler,
        route_handler=example_route_handler
    )
    
    logger.info("Attractor configured with custom handlers")
    logger.info("Try connecting with: curl http://localhost:8080/")
    logger.info("Press Ctrl+C to stop")
    
    try:
        attractor.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        attractor.stop()
    
    logger.info("Attractor stopped")


if __name__ == "__main__":
    main()
