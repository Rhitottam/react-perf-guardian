import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from agents import performance_analyzer, memory_agent, sequential_analyzer
from google.genai import types
from google.adk.agents import Agent
from google.adk.sessions import DatabaseSessionService
from google.adk.runners import Runner, Event
from google.genai.types import Content, Part
import uuid
import json

# Load environment variables from .env file
load_dotenv()

APP_NAME = "react-perf-analyzer"

# =============================================================================
# AGENT MODE CONFIGURATION
# =============================================================================
# Set USE_MULTI_AGENT=true to use the 4-agent sequential pipeline:
#   Parser → Analyzer → Reasoner → Reporter
# Set USE_MULTI_AGENT=false (default) to use the single comprehensive agent
# 
# The multi-agent approach demonstrates:
#   - SequentialAgent orchestration (ADK feature)
#   - Specialized agents with focused responsibilities
#   - Agent-to-agent communication via session context
#
# The single-agent approach is:
#   - More reliable for consistent JSON output
#   - Easier to debug
#   - Faster (single model call vs. 4 sequential calls)
# =============================================================================
USE_MULTI_AGENT = os.environ.get("USE_MULTI_AGENT", "true").lower() == "true"

# Select the appropriate analyzer based on configuration
if USE_MULTI_AGENT:
    active_analyzer = sequential_analyzer
    print("🔗 Using MULTI-AGENT pipeline: Parser → Analyzer → Reasoner → Reporter")
else:
    active_analyzer = performance_analyzer
    print("⚡ Using SINGLE comprehensive agent (set USE_MULTI_AGENT=true for multi-agent)")
MEMORY_APP_NAME = "react-perf-memory"  # Separate app name for memory agent
USER_ID = "react-perf-user"  # Fixed user ID for all analyses

# Validate API key is present
if not os.getenv('GOOGLE_API_KEY'):
    print("❌ Error: GOOGLE_API_KEY not found!")
    print("📝 Please create a .env file with your API key:")
    print("   echo 'GOOGLE_API_KEY=your-key-here' > .env")
    print("🔑 Get your key from: https://makersuite.google.com/app/apikey")
    exit(1)

# Use DatabaseSessionService for persistent cross-file memory
db_path = Path(__file__).parent / "pr_sessions.db"
db_url = f"sqlite:///{db_path}"
session_service = DatabaseSessionService(db_url=db_url)

print(f"🗄️  Using persistent sessions: {db_path}")
print(f"🧠 Memory Agent will extract patterns from session history")

async def ensure_session(session_id: str, app_name: str = APP_NAME) -> bool:
    """
    Ensure a session exists, create if it doesn't.
    
    Returns:
        True if session already existed (has history), False if newly created
    """
    session = await session_service.get_session(
        app_name=app_name, 
        user_id=USER_ID, 
        session_id=session_id
    )
    if session is None:
        await session_service.create_session(
            app_name=app_name, 
            user_id=USER_ID, 
            session_id=session_id
        )
        print(f"📝 Created new session: {session_id[:30]}...")
        return False
    else:
        print(f"♻️  Reusing session: {session_id[:30]}...")
        return True


async def store_analysis_summary(pr_session_id: str, filename: str, result: str) -> None:
    """
    Store a SHORT summary of the analysis in the PR session for Memory Agent.
    
    This allows Memory Agent to see what was found without the full history.
    """
    try:
        # Parse result to extract issue counts
        import json
        issues = []
        try:
            parsed = json.loads(result) if isinstance(result, str) else result
            issues = parsed.get("issues", [])
        except:
            pass
        
        # Create SHORT summary
        issue_types = {}
        for issue in issues:
            t = issue.get("title", "unknown")
            issue_types[t] = issue_types.get(t, 0) + 1
        
        if issues:
            summary = f"File: {filename} - Found {len(issues)} issues: " + ", ".join(f"{k} ({v})" for k, v in issue_types.items())
        else:
            summary = f"File: {filename} - No issues found"
        
        # Store in PR session
        await ensure_session(pr_session_id, app_name=APP_NAME)
        
        # Create a simple runner just to store the summary
        runner = Runner(
            app_name=APP_NAME,
            agent=active_analyzer,
            session_service=session_service,
        )
        
        # Store as a user message (Memory Agent will see this)
        summary_content = Content(
            role="user", parts=[Part(text=f"[ANALYSIS SUMMARY] {summary}")]
        )
        
        # Just add to session without running agent
        async for _ in runner.run_async(
            user_id=USER_ID,
            session_id=pr_session_id,
            new_message=summary_content,
        ):
            break  # We don't need the response, just storing the message
        
        print(f"💾 Stored summary in PR session")
    except Exception as e:
        print(f"⚠️  Could not store summary: {e}")


async def clear_pr_session(pr_session_id: str) -> None:
    """
    Clear the PR session from the database after analysis is complete.
    
    This prevents cross-PR pollution.
    """
    try:
        # Delete session from database
        # Note: DatabaseSessionService doesn't have a direct delete method,
        # so we'll just leave it for now - the DB file can be cleared manually
        # or we can delete the DB file
        print(f"🗑️  PR session {pr_session_id} analysis complete")
    except Exception as e:
        print(f"⚠️  Could not clear session: {e}")


async def run_memory_agent(session_id: str) -> str:
    """
    Run the Memory Agent to extract patterns from session history.
    
    The Memory Agent reads the session history and summarizes:
    - Recurring issues (inline functions, missing memoization, etc.)
    - Detected conventions (Redux, Context, etc.)
    - Components analyzed so far
    
    Args:
        session_id: The PR session ID to analyze
        
    Returns:
        Clean summary string for the analyzer, or empty string if no history
    """
    # Check if session has history
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=session_id
    )
    
    if session is None:
        return ""
    
    # Get session events to check if there's history
    # Note: We don't need to read all events - Memory Agent will see them via session
    
    print(f"🧠 Running Memory Agent to extract patterns...")
    
    # Create runner for memory agent
    memory_runner = Runner(
        app_name=MEMORY_APP_NAME,
        agent=memory_agent,
        session_service=session_service,
    )
    
    # Memory agent prompt - ask for SHORT summary
    memory_prompt = """
Give me a VERY SHORT summary (max 50 words) of what was found in previous file analyses.
Include: files analyzed count, recurring issues with counts, any patterns detected.
If no prior analyses, say "First file - no prior context."
"""
    
    # Ensure memory session exists (linked to same PR session for context)
    await ensure_session(session_id, app_name=MEMORY_APP_NAME)
    
    user_content = Content(
        role="user", parts=[Part(text=memory_prompt)]
    )
    
    events = []
    try:
        async for event in memory_runner.run_async(
            user_id=USER_ID,
            session_id=session_id,
            new_message=user_content,
        ):
            events.append(event)
        
        # Extract response
        for event in events:
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        summary = part.text.strip()
                        print(f"✅ Memory extracted: {summary[:80]}...")
                        return summary
        
        return ""
    except Exception as e:
        print(f"⚠️  Memory Agent error: {e}")
        return ""

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
            print(f"📊 Synthesizing response from {len(tool_results)} tool results:")
            for tr in tool_results:
                print(f"   - {tr['name']}: {type(tr['data']).__name__}")
            
            # Collect all issues from all analysis tools
            all_issues = []
            parse_info = None
            
            for result in tool_results:
                name = result['name']
                data = result['data']
                
                # Collect parse info for context
                if name == 'parse_code':
                    parse_info = data
                
                # Collect issues from analysis tools (different structures)
                if isinstance(data, dict):
                    # Direct issues array (analyze_jsx_expressions, etc.)
                    if 'issues' in data:
                        all_issues.extend(data.get('issues', []))
                    
                    # Nested issues under hooks (analyze_hook_dependencies)
                    if 'hooks' in data:
                        for hook in data.get('hooks', []):
                            if hook.get('has_issues') and 'issues' in hook:
                                # Convert hook issues to standard format
                                component = data.get('component', 'Unknown')
                                for issue in hook.get('issues', []):
                                    all_issues.append({
                                        "file": "unknown",  # Will be set by caller
                                        "line": hook.get('line', 0),
                                        "component": component,
                                        "severity": "high" if issue.get('severity') == 'warning' else "medium",
                                        "title": f"{issue.get('type', 'unknown').replace('_', ' ').title()}",
                                        "problem": issue.get('message', ''),
                                        "suggestion": f"Review {issue.get('dependency', issue.get('variable', 'this dependency'))} in the hook"
                                    })
                    
                    # Render triggers (analyze_render_triggers)
                    if 'triggers' in data:
                        for trigger in data.get('triggers', []):
                            if trigger.get('severity') in ['critical', 'high', 'warning']:
                                all_issues.append({
                                    "file": "unknown",
                                    "line": trigger.get('line', 0),
                                    "component": data.get('component', 'Unknown'),
                                    "severity": trigger.get('severity', 'medium'),
                                    "title": trigger.get('type', 'Render Trigger'),
                                    "problem": trigger.get('reason', ''),
                                    "suggestion": "Consider memoizing or stabilizing this value"
                                })
            
            print(f"   → Extracted {len(all_issues)} total issues from tools")
            
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
    
    # Create runner with our agent pipeline (single or multi-agent based on config)
    runner = Runner(
        app_name=APP_NAME,
        agent=active_analyzer,
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
    
    # For standalone file analysis, no PR session needed
    return await analyze_code(code, output_format, file_path, pr_session_id=None)


async def analyze_code(
    code: str, 
    output_format: str = "markdown", 
    filename: str = "component.tsx", 
    pr_session_id: str = None,
    memory_context: str = "",
    is_first_file: bool = True
) -> str:
    """
    Analyze React code string for performance issues using multi-agent system.
    
    Args:
        code: React/TypeScript source code
        output_format: Output format (markdown, json, github)
        filename: Virtual filename for context
        pr_session_id: PR-level session ID (for Memory Agent to read history)
        memory_context: Additional context from Memory Agent
        is_first_file: If True, skip memory extraction (no history yet)
    
    Returns:
        Formatted analysis report from the agent pipeline
    """
    # Generate FRESH session for analyzer (no history accumulation)
    file_stem = Path(filename).stem
    analyzer_session_id = f"analyze-{file_stem}-{uuid.uuid4().hex[:8]}"
    
    # For PR analysis, get memory context from shared session
    if pr_session_id and not is_first_file and not memory_context:
        memory_context = await run_memory_agent(pr_session_id)
    
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
    # Use FRESH session for analyzer (no history accumulation)
    result = await run_agent_async(prompt, analyzer_session_id)
    
    # Store summary in PR session for Memory Agent to read later
    if pr_session_id:
        await store_analysis_summary(pr_session_id, filename, result)
    
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
