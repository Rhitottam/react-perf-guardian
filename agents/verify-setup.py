#!/usr/bin/env python3
"""
Verify Python setup for React Performance Agent
"""

import sys
import os

def check_import(module_name, import_statement):
    """Check if a module can be imported"""
    try:
        exec(import_statement)
        print(f"✅ {module_name}")
        return True
    except ImportError as e:
        print(f"❌ {module_name}: {e}")
        return False

def main():
    print("🔍 Verifying Python Setup for React Performance Agent")
    print("=" * 60)
    print()

    all_ok = True

    # Check Python version
    print("📋 Python Version:")
    version = sys.version_info
    print(f"   Python {version.major}.{version.minor}.{version.micro}")
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print("   ⚠️  Warning: Python 3.9+ recommended")
        all_ok = False
    else:
        print("   ✅ Version OK")
    print()

    # Check imports
    print("📦 Checking Required Packages:")
    imports = [
        ("Google ADK - Agent", "from google.adk.agents import Agent, SequentialAgent"),
        ("Google ADK - Tools", "from google.adk.tools import FunctionTool"),
        ("Google ADK - Sessions", "from google.adk.sessions import InMemorySessionService"),
        ("Google ADK - Runner", "from google.adk.runners import Runner"),
        ("Google GenAI", "from google.genai import types"),
        ("Pydantic", "import pydantic"),
        ("Python Dotenv", "from dotenv import load_dotenv"),
    ]

    for name, statement in imports:
        if not check_import(name, statement):
            all_ok = False
    print()

    # Check local modules
    print("📁 Checking Local Modules:")
    local_modules = [
        ("parser_bridge", "from parser_bridge import parse_react_code, AstContext"),
        ("tools", "from tools import list_components, inspect_component"),
        ("agents", "from agents import performance_analyzer"),
        ("memory", "from memory import ProjectMemory"),
    ]

    for name, statement in local_modules:
        if not check_import(name, statement):
            all_ok = False
    print()

    # Check .env file
    print("🔑 Checking .env File and API Key:")
    if os.path.exists('.env'):
        print("   ✅ .env file found")
        # Load .env
        try:
            from dotenv import load_dotenv
            load_dotenv()
            print("   ✅ python-dotenv installed")
        except ImportError:
            print("   ⚠️  python-dotenv not installed")
            print("   Install with: pip install python-dotenv")
            all_ok = False
    else:
        print("   ⚠️  .env file not found")
        print("   Create with: echo 'GOOGLE_API_KEY=your-key' > .env")
    
    api_key = os.environ.get('GOOGLE_API_KEY')
    if api_key:
        print(f"   ✅ GOOGLE_API_KEY is set ({len(api_key)} characters)")
    else:
        print("   ⚠️  GOOGLE_API_KEY not loaded")
        print("   Get a key from: https://makersuite.google.com/app/apikey")
        print("   Add to .env file: GOOGLE_API_KEY=your-key-here")
        all_ok = False
    print()

    # Check parser
    print("🏗️  Checking Parser:")
    parser_path = "../parser/dist/cli.js"
    if os.path.exists(parser_path):
        print(f"   ✅ Parser found at {parser_path}")
    else:
        print(f"   ❌ Parser not found at {parser_path}")
        print("   Build it with: cd ../parser && npm run build")
        all_ok = False
    print()

    # Check example files
    print("📄 Checking Example Files:")
    example_files = [
        "../examples/UserList.tsx",
        "../examples/UserCard.tsx"
    ]
    for example_file in example_files:
        if os.path.exists(example_file):
            print(f"   ✅ {example_file}")
        else:
            print(f"   ❌ {example_file} not found")
    print()

    # Final verdict
    print("=" * 60)
    if all_ok:
        print("🎉 All checks passed! Setup is complete.")
        print()
        print("🚀 Ready to run:")
        print("   python main.py ../examples/UserList.tsx")
    else:
        print("⚠️  Some checks failed. Please review the errors above.")
        print()
        print("💡 Quick fixes:")
        print("   - Install packages: pip install -r requirements.txt")
        print("   - Install Google ADK: pip install google-adk")
        print("   - Set API key: export GOOGLE_API_KEY='your-key'")
        print("   - Build parser: cd ../parser && npm run build")
    print("=" * 60)

    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())

