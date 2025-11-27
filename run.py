#!/usr/bin/env python3
"""
MCP Framework - Application Entry Point
Run this file to start the development server
"""
import os
import sys
import socket

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from app import create_app

# Create the application
app = create_app()


def is_port_in_use(port):
    """Check if a port is already in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def find_available_port(preferred_port=5000):
    """Find an available port, starting with the preferred one"""
    ports_to_try = [preferred_port, 5001, 5002, 8000, 8080]
    
    for port in ports_to_try:
        if not is_port_in_use(port):
            return port
    
    return None


if __name__ == '__main__':
    # Get configuration from environment
    host = os.environ.get('HOST', '0.0.0.0')
    preferred_port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'
    
    # Find available port
    port = find_available_port(preferred_port)
    
    if port is None:
        print("\n❌ ERROR: No available ports found!")
        print("   Try closing other applications or specify a different port:")
        print("   PORT=8080 python run.py")
        sys.exit(1)
    
    if port != preferred_port:
        print(f"\n⚠️  Port {preferred_port} is in use (possibly macOS AirPlay).")
        print(f"   Using port {port} instead.\n")
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║              MCP Framework v4.5                              ║
║          Karma Marketing + Media                             ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  🌐 Dashboard: http://localhost:{port:<5}                        ║
║  📡 API:       http://localhost:{port}/api                      ║
║  💚 Health:    http://localhost:{port}/health                   ║
║  🔐 Admin:     http://localhost:{port}/admin                    ║
║                                                              ║
║  Environment: {'development' if debug else 'production':<12}                              ║
║                                                              ║
║  Press Ctrl+C to stop                                        ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    try:
        app.run(host=host, port=port, debug=debug)
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"\n❌ Port {port} is now in use by another process.")
            print("   Try: PORT=8080 python run.py")
        else:
            raise
