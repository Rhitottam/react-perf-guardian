import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from agents import performance_analyzer, memory_agent
from google.genai import types
from google.adk.agents import Agent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner, Event
from google.genai.types import Content, Part
import uuid

# Load environment variables from .env file
load_dotenv()

APP_NAME = "react-perf-analyzer"
USER_ID = "react-perf-user"  # Fixed user ID for all analyses

# Validate API key is present
if not os.getenv('GOOGLE_API_KEY'):
    print("❌ Error: GOOGLE_API_KEY not found!")
    print("📝 Please create a .env file with your API key:")
    print("   echo 'GOOGLE_API_KEY=your-key-here' > .env")
    print("🔑 Get your key from: https://makersuite.google.com/app/apikey")
    exit(1)

# Use InMemorySessionService - each file gets fresh context
# Cross-file memory is handled by ProjectMemory class
session_service = InMemorySessionService()

print(f"🗄️  Using in-memory sessions (fresh context per file)")
print(f"🧠 Cross-file patterns tracked via ProjectMemory")

async def ensure_session(session_id: str) -> None:
    """Create a fresh session for this file analysis."""
    await session_service.create_session(
        app_name=APP_NAME, 
        user_id=USER_ID, 
        session_id=session_id
    )
    print(f"📝 New analysis session: {session_id[:30]}...")

def final_response_from_events(events: list[Event]):
    """Extract final response from event stream."""
    import json
    
    final_response = ""
    final_found = False
    tool_results = []  # Collect tool results as fallback
    
    # Debug: Show event types
    DEBUG = os.environ.get("DEBUG_EVENTS", "").lower() == "true"
    if DEBUG:
        print(f"\n🔍 DEBUG: Processing {len(events)} events:")
    
    for i, event in enumerate(events):
        if DEBUG:
            print(f"  Event {i}: is_final={event.is_final_response()}, author={getattr(event, 'author', 'unknown')}")
        
        if event.content and event.content.parts:
            for part in event.content.parts:
                # Collect text responses
                if hasattr(part, 'text') and part.text:
                    if event.is_final_response():
                        final_response = part.text
                        final_found = True
                        if DEBUG:
                            print(f"    Found final text: {part.text[:80]}...")
                
                # Collect function responses (for fallback)
                if hasattr(part, 'function_response'):
                    resp = part.function_response
                    if hasattr(resp, 'response') and resp.response:
                        tool_results.append({
                            'name': getattr(resp, 'name', 'unknown'),
                            'data': resp.response
                        })
                        if DEBUG:
                            print(f"    Tool response: {getattr(resp, 'name', 'unknown')}")
    
    # If no final text response, synthesize from tool results
    if not final_found or not final_response.strip():
        if tool_results:
            print(f"📊 Synthesizing response from {len(tool_results)} tool results")
            
            # Collect all issues from all analysis tools
            all_issues = []
            parse_info = None
            
            for result in tool_results:
                name = result['name']
                data = result['data']
                
                # Collect parse info for context
                if name == 'parse_code':
                    parse_info = data
                
                # Collect issues from any analysis tool
                if name in ['analyze_jsx_expressions', 'analyze_render_triggers', 
                           'analyze_hook_dependencies', 'analyze_state_relationships',
                           'inspect_component']:
                    if isinstance(data, dict) and 'issues' in data:
                        all_issues.extend(data.get('issues', []))
            
            if all_issues:
                response = {
                    "issues": all_issues,
                    "summary": {
                        "total_issues": len(all_issues),
                        "components_analyzed": parse_info.get('components_found', []) if parse_info else []
                    }
                }
                final_response = json.dumps(response, indent=2)
                print(f"✅ Synthesized JSON with {len(all_issues)} issues")
            else:
                # No issues found - return clean empty result
                components = parse_info.get('components_found', []) if parse_info else []
                response = {
                    "issues": [],
                    "summary": {
                        "total_issues": 0,
                        "components_analyzed": components,
                        "status": "No performance issues detected"
                    }
                }
                final_response = json.dumps(response, indent=2)
                print(f"✅ No issues found in {len(components)} components")
        else:
            print(f"⚠️  Warning: No response or tool results found")
            final_response = json.dumps({
                "issues": [], 
                "summary": {"total_issues": 0, "status": "Analysis incomplete - no tool results"}
            })
    else:
        preview = final_response[:100].replace('\n', ' ')
        print(f"✅ Got response ({len(final_response)} chars): {preview}...")
    
    return final_response

async def run_agent_async(message: str, session_id: str):
    """
    Run the agent pipeline with a specific session ID.
    
    Args:
        message: The prompt/message for the agent
        session_id: Session ID (should be PR-level, e.g., 'pr-owner-repo-123')
    
    Returns:
        Final response text from the agent
    """
    # Ensure session exists
    await ensure_session(session_id)
    
    # Reduced logging - don't print the full prompt with code
    print(f"🔄 Running analysis pipeline (session: {session_id[:20]}...)...")
    
    # Create runner with our agent pipeline
    runner = Runner(
        app_name=APP_NAME,
        agent=performance_analyzer,
        session_service=session_service,
    )
    
    events = []
    user_content = Content(
        role="user", parts=[Part(text=message)]
    )
    
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=user_content,
    ):
        events.append(event)
    
    return final_response_from_events(events)

async def analyze_file(file_path: str, output_format: str = "markdown", session_id: str = None) -> str:
    """
    Analyze a React file for performance issues using multi-agent system.
    
    Args:
        file_path: Path to the React/TypeScript file
        output_format: Output format (markdown, json, github)
        session_id: Optional session ID. If not provided, generates one based on filename.
    
    Returns:
        Formatted analysis report from the agent pipeline
    """
    code = Path(file_path).read_text()
    
    # Generate session ID if not provided (for CLI usage)
    if session_id is None:
        # For standalone file analysis, use filename-based session
        session_id = f"file-{Path(file_path).stem}-{uuid.uuid4().hex[:8]}"
    
    return await analyze_code(code, output_format, file_path, session_id=session_id)


async def analyze_code(
    code: str, 
    output_format: str = "markdown", 
    filename: str = "component.tsx", 
    session_id: str = None,
    memory_context: str = ""
) -> str:
    """
    Analyze React code string for performance issues using multi-agent system.
    
    Args:
        code: React/TypeScript source code
        output_format: Output format (markdown, json, github)
        filename: Virtual filename for context
        session_id: Base session ID (will be made unique per file for clean context)
        memory_context: Additional context from previous analyses (for cross-file insights)
    
    Returns:
        Formatted analysis report from the agent pipeline
    """
    # ALWAYS generate unique session ID per file to ensure fresh context
    # Cross-file memory is passed via memory_context parameter, not session history
    file_stem = Path(filename).stem
    unique_session_id = f"file-{file_stem}-{uuid.uuid4().hex[:8]}"
    
    # Build memory context section if available
    memory_prompt = ""
    if memory_context:
        memory_prompt = f"""

## 🧠 PROJECT MEMORY (Cross-File Context)

You have access to information from previous files analyzed in this PR:
{memory_context}

Use this context to:
- Prioritize recurring issues higher (if you see the same pattern again)
- Provide convention-aware suggestions (e.g., "This project uses Redux, so...")
- Recognize project-wide patterns that need systemic fixes
- Give context about how many times you've seen similar issues
"""
    
    prompt = f"""
Analyze this React code for performance issues and output as {output_format} format.

File: {filename}

```tsx
{code}
```
{memory_prompt}

IMPORTANT: The final output MUST be valid {output_format.upper()} only - no explanations or additional text.

Follow this pipeline:
1. Parser Agent: Parse the code to extract AST data
2. Analyzer Agent: Identify performance issues using the tools
3. Reasoner Agent: Validate issues and create structured issue objects with:
   - file: "{filename}"
   - line: <line_number>
   - component: <component_name>
   - severity: "critical"|"high"|"medium"|"low"
   - title: <brief_title>
   - problem: <description>
   - suggestion: <how_to_fix>
4. Reporter Agent: MUST call format_report() tool with output_format="{output_format}"

Focus on:
- Critical: Inline functions/objects breaking memoization
- High: Unstable hook dependencies
- Medium: Unnecessary re-renders
- Low: Minor optimizations

The final response must be ONLY the formatted {output_format} - no explanations.
"""
    
    # Run agent with unique session ID (fresh context per file)
    result = await run_agent_async(prompt, unique_session_id)
    
    return result


async def analyze_multiple_files(file_paths: list[str], output_format: str = "markdown") -> dict:
    """
    Analyze multiple React files and provide cross-file insights.
    
    Args:
        file_paths: List of file paths to analyze
        output_format: Output format (markdown, json, github)
    
    Returns:
        Dictionary mapping file paths to their analysis results
    """
    results = {}
    
    for file_path in file_paths:
        print(f"Analyzing {file_path}...")
        result = await analyze_file(file_path, output_format)
        results[file_path] = result
    
    return results


# CLI interface
async def main():
    """CLI entry point."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python main.py <file_path> [output_format]")
        print("  output_format: markdown (default), json, github")
        print("\nExample:")
        print("  python main.py ../examples/UserList.tsx markdown")
        sys.exit(1)
    
    file_path = sys.argv[1]
    output_format = sys.argv[2] if len(sys.argv) > 2 else "markdown"
    
    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    
    print(f"🔍 Analyzing {file_path}...")
    print(f"📊 Output format: {output_format}")
    print("=" * 60)
    
    try:
        result = await analyze_file(file_path, output_format)
        print(result)
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
