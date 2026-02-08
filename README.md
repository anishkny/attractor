# Attractor

An implementation of the Attractor pattern for intercepting, authenticating, and routing network traffic. This is commonly used in zero-trust network architectures and access management systems.

## Overview

The Attractor acts as an intelligent proxy that:

1. **Attracts/Intercepts** - Captures incoming network connections
2. **Authenticates** - Verifies the identity of the connection source
3. **Authorizes** - Determines if access should be granted
4. **Routes** - Forwards authenticated traffic to appropriate backends
5. **Observes** - Provides logging and visibility into all traffic

## Features

- **Flexible Authentication**: Pluggable authentication handlers
- **Custom Routing**: Configurable routing logic
- **Multi-threaded**: Handles multiple concurrent connections
- **Observable**: Built-in logging and statistics
- **Extensible**: Easy to customize for specific use cases

## Installation

No external dependencies required. Just Python 3.7+.

```bash
# Clone the repository
git clone https://github.com/anishkny/test.git
cd test

# Run the tests
python test_attractor.py
```

## Usage

### Basic Usage

```python
from attractor import Attractor

# Create an Attractor instance
attractor = Attractor(host="0.0.0.0", port=8080)

# Start the service
try:
    attractor.start()
except KeyboardInterrupt:
    attractor.stop()
```

### Custom Authentication

```python
from attractor import Attractor, Connection, AuthResult

def custom_auth_handler(connection: Connection) -> AuthResult:
    """Custom authentication logic"""
    # Check if source is from trusted network
    if connection.source_addr[0].startswith("192.168."):
        return AuthResult.ALLOWED
    return AuthResult.DENIED

attractor = Attractor(
    host="0.0.0.0",
    port=8080,
    auth_handler=custom_auth_handler
)
attractor.start()
```

### Custom Routing

```python
from attractor import Attractor, Connection
import socket

def custom_route_handler(connection: Connection, client_socket: socket.socket, initial_data: bytes):
    """Custom routing logic"""
    # Forward to backend based on destination
    if "api" in connection.destination:
        backend_host = "api-server.local"
        backend_port = 8000
    else:
        backend_host = "web-server.local"
        backend_port = 80
    
    # Connect to backend and forward traffic
    backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    backend.connect((backend_host, backend_port))
    backend.send(initial_data)
    
    # Relay data between client and backend
    # ... (implementation details)

attractor = Attractor(
    host="0.0.0.0",
    port=8080,
    route_handler=custom_route_handler
)
attractor.start()
```

### Getting Statistics

```python
attractor = Attractor(host="127.0.0.1", port=8080)

# Get current statistics
stats = attractor.get_stats()
print(f"Running: {stats['running']}")
print(f"Active connections: {stats['active_connections']}")
```

## Architecture

```
┌─────────┐      ┌───────────┐      ┌─────────┐
│ Client  │─────▶│ Attractor │─────▶│ Backend │
└─────────┘      └───────────┘      └─────────┘
                      │
                      │ 1. Intercept
                      │ 2. Authenticate
                      │ 3. Authorize
                      │ 4. Route
                      │ 5. Log
                      ▼
                 ┌─────────┐
                 │  Logs   │
                 └─────────┘
```

## Testing

Run the unit tests:

```bash
python test_attractor.py
```

Run a simple test with curl:

```bash
# In one terminal, start the Attractor
python attractor.py

# In another terminal, test with curl
curl http://localhost:8080/
```

## Configuration

The Attractor can be configured with:

- `host`: Host address to bind to (default: "0.0.0.0")
- `port`: Port to listen on (default: 8080)
- `auth_handler`: Custom authentication function
- `route_handler`: Custom routing function

## Use Cases

1. **Zero-Trust Networks**: Verify every connection before allowing access
2. **API Gateway**: Route and authenticate API requests
3. **Access Proxy**: Control access to internal services
4. **Traffic Inspection**: Monitor and log all network traffic
5. **Load Balancing**: Distribute traffic across multiple backends

## Security Considerations

- The default authentication handler **allows all connections** and should be replaced with proper authentication in production
- Always use TLS/SSL for production deployments
- Implement rate limiting to prevent abuse
- Use strong authentication mechanisms (tokens, certificates, etc.)
- Keep logs secure and monitor for suspicious activity

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

## License

MIT License - See LICENSE file for details
