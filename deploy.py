#!/usr/bin/env python
"""
Listoria Deployment Script
A simple script to help with deployment tasks
"""

import os
import subprocess
import sys
from pathlib import Path

def check_python_version():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} detected")
    return True

def install_dependencies():
    """Install required dependencies"""
    print("📦 Installing dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install dependencies")
        return False

def check_env_file():
    """Check if .env file exists and has basic configuration"""
    env_path = Path(".env")
    if not env_path.exists():
        print("❌ .env file not found")
        return False
    
    with open(env_path, 'r') as f:
        content = f.read()
        
    if "FLASK_SECRET_KEY=" not in content:
        print("❌ FLASK_SECRET_KEY not found in .env")
        return False
        
    print("✅ .env file found with basic configuration")
    return True

def create_database():
    """Initialize the database"""
    print("🗄️ Initializing database...")
    try:
        # Import here to avoid import errors before dependencies are installed
        from app import create_db_table
        create_db_table()
        print("✅ Database initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        return False

def run_app():
    """Run the Flask application"""
    print("🚀 Starting Listoria...")
    try:
        subprocess.check_call([sys.executable, "app.py"])
    except KeyboardInterrupt:
        print("\n👋 Listoria stopped")
    except subprocess.CalledProcessError:
        print("❌ Failed to start application")

def main():
    """Main deployment function"""
    print("🎯 Listoria Deployment Script")
    print("=" * 40)
    
    # Check Python version
    if not check_python_version():
        return
    
    # Install dependencies
    if not install_dependencies():
        return
    
    # Check environment file
    if not check_env_file():
        print("💡 Please create and configure your .env file")
        print("📝 See .env for required variables")
        return
    
    # Initialize database
    if not create_database():
        return
    
    print("\n🎉 Deployment completed successfully!")
    print("🌐 Your Listoria app is ready to run")
    print("\n🚀 To start the app, run: python app.py")
    print("📱 Access it at: http://localhost:5000")
    
    # Ask if user wants to start the app
    start_now = input("\n❓ Start the app now? (y/n): ").lower().strip()
    if start_now in ['y', 'yes']:
        run_app()

if __name__ == "__main__":
    main()