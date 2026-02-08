"""
Unit tests for the Attractor module.
"""

import unittest
import socket
import threading
import time
from attractor import Attractor, Connection, AuthResult


class TestAttractor(unittest.TestCase):
    """Test cases for Attractor class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_port = 8888
        self.attractor = Attractor(host="127.0.0.1", port=self.test_port)
    
    def tearDown(self):
        """Clean up after tests"""
        if self.attractor.running:
            self.attractor.stop()
            time.sleep(0.5)  # Give time to stop
    
    def test_initialization(self):
        """Test Attractor initialization"""
        self.assertEqual(self.attractor.host, "127.0.0.1")
        self.assertEqual(self.attractor.port, self.test_port)
        self.assertFalse(self.attractor.running)
    
    def test_authentication_default(self):
        """Test default authentication handler"""
        connection = Connection(
            source_addr=("127.0.0.1", 12345),
            destination="example.com",
            protocol="tcp",
            metadata={}
        )
        result = self.attractor.authenticate(connection)
        self.assertEqual(result, AuthResult.ALLOWED)
    
    def test_custom_auth_handler(self):
        """Test custom authentication handler"""
        def custom_auth(conn):
            if conn.source_addr[0] == "127.0.0.1":
                return AuthResult.ALLOWED
            return AuthResult.DENIED
        
        attractor = Attractor(
            host="127.0.0.1",
            port=self.test_port + 1,
            auth_handler=custom_auth
        )
        
        connection = Connection(
            source_addr=("127.0.0.1", 12345),
            destination="example.com",
            protocol="tcp",
            metadata={}
        )
        result = attractor.authenticate(connection)
        self.assertEqual(result, AuthResult.ALLOWED)
        
        connection2 = Connection(
            source_addr=("192.168.1.1", 12345),
            destination="example.com",
            protocol="tcp",
            metadata={}
        )
        result2 = attractor.authenticate(connection2)
        self.assertEqual(result2, AuthResult.DENIED)
    
    def test_get_stats(self):
        """Test statistics retrieval"""
        stats = self.attractor.get_stats()
        self.assertIn("running", stats)
        self.assertIn("host", stats)
        self.assertIn("port", stats)
        self.assertIn("active_connections", stats)
        self.assertEqual(stats["host"], "127.0.0.1")
        self.assertEqual(stats["port"], self.test_port)
    
    def test_start_stop(self):
        """Test starting and stopping the Attractor"""
        # Start in a thread
        thread = threading.Thread(target=self.attractor.start)
        thread.daemon = True
        thread.start()
        
        # Wait for startup
        time.sleep(0.5)
        self.assertTrue(self.attractor.running)
        
        # Stop
        self.attractor.stop()
        time.sleep(0.5)
        self.assertFalse(self.attractor.running)
    
    def test_connection_handling(self):
        """Test handling a real connection"""
        # Start attractor in a thread
        thread = threading.Thread(target=self.attractor.start)
        thread.daemon = True
        thread.start()
        
        # Wait for startup
        time.sleep(0.5)
        
        # Make a test connection
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(2.0)
            client.connect(("127.0.0.1", self.test_port))
            
            # Send a simple HTTP request
            request = b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
            client.send(request)
            
            # Receive response
            response = client.recv(1024)
            self.assertIn(b"200 OK", response)
            self.assertIn(b"Attractor", response)
            
            client.close()
        except Exception as e:
            self.fail(f"Connection test failed: {e}")
        finally:
            self.attractor.stop()
    
    def test_parse_destination(self):
        """Test destination parsing from HTTP request"""
        data = b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
        destination = self.attractor._parse_destination(data)
        self.assertEqual(destination, "example.com")
        
        data2 = b"GET / HTTP/1.1\r\nHost: test.local:8080\r\n\r\n"
        destination2 = self.attractor._parse_destination(data2)
        self.assertIn("test.local", destination2)


class TestConnection(unittest.TestCase):
    """Test cases for Connection dataclass"""
    
    def test_connection_creation(self):
        """Test creating a Connection object"""
        conn = Connection(
            source_addr=("127.0.0.1", 12345),
            destination="example.com",
            protocol="tcp",
            metadata={"user": "test"}
        )
        
        self.assertEqual(conn.source_addr, ("127.0.0.1", 12345))
        self.assertEqual(conn.destination, "example.com")
        self.assertEqual(conn.protocol, "tcp")
        self.assertEqual(conn.metadata["user"], "test")


class TestAuthResult(unittest.TestCase):
    """Test cases for AuthResult enum"""
    
    def test_auth_result_values(self):
        """Test AuthResult enum values"""
        self.assertEqual(AuthResult.ALLOWED.value, "allowed")
        self.assertEqual(AuthResult.DENIED.value, "denied")
        self.assertEqual(AuthResult.PENDING.value, "pending")


if __name__ == "__main__":
    unittest.main()
