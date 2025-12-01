import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from agents import performance_analyzer
from google.genai import types
from google.adk.agents import Agent
from google.adk.sessions import InMemorySessionService, BaseSessionService
from google.adk.runners import InMemoryRunner, Runner, Event
from google.genai.types import Content, Part
import uuid

# Load environment variables from .env file
load_dotenv()

APP_NAME = "react-perf-analyzer"
USER_ID = "user-" + str(uuid.uuid4())
SESSION_ID = "session-" + str(uuid.uuid4())
# Validate API key is present
if not os.getenv('GOOGLE_API_KEY'):
    print("❌ Error: GOOGLE_API_KEY not found!")
    print("📝 Please create a .env file with your API key:")
    print("   echo 'GOOGLE_API_KEY=your-key-here' > .env")
    print("🔑 Get your key from: https://makersuite.google.com/app/apikey")
    exit(1)

# session_service = InMemorySessionService()

def get_runner_with_session (agent: Agent):
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session_service = runner.session_service
    return (runner, session_service)

async def create_session (session_service: BaseSessionService):
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )
    if session is None:
        session = await session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )
    return session
def final_response_from_events(events: list[Event]):
    final_response = ""
    final_found = False
    
    for event in events:
        if event.is_final_response() and event.content and event.content.parts:
            final_response = event.content.parts[0].text
            final_found = True
            break
    
    if not final_found:
        print(f"⚠️  Warning: No final response found in {len(events)} events")
        # Try to collect any text from events
        for event in events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        final_response += part.text + "\n"
    else:
        # Log response type for debugging
        if final_response:
            preview = final_response[:100].replace('\n', ' ')
            print(f"✅ Got response ({len(final_response)} chars): {preview}...")
    
    return final_response

async def run_agent_async (message: str, runner: Runner):
    # Reduced logging - don't print the full prompt with code
    print(f"🔄 Running analysis pipeline...")
    events = []
    user_content = Content(
        role="user", parts=[Part(text=message)]
    )
    async for event in runner.run_async(
        user_id = USER_ID,
        session_id = SESSION_ID,
        new_message=user_content,
    ):
        events.append(event)
    return final_response_from_events(events)

async def analyze_file(file_path: str, output_format: str = "markdown") -> str:
    """
    Analyze a React file for performance issues using multi-agent system.
    
    Args:
        file_path: Path to the React/TypeScript file
        output_format: Output format (markdown, json, github)
    
    Returns:
        Formatted analysis report from the agent pipeline
    """
    code = Path(file_path).read_text()
    return await analyze_code(code, output_format, file_path)


async def analyze_code(code: str, output_format: str = "markdown", filename: str = "component.tsx") -> str:
    """
    Analyze React code string for performance issues using multi-agent system.
    
    Args:
        code: React/TypeScript source code
        output_format: Output format (markdown, json, github)
        filename: Virtual filename for context
    
    Returns:
        Formatted analysis report from the agent pipeline
    """
    # runner = Runner(
    #     app_name=APP_NAME,
    #     agent=performance_analyzer,
    #     session_service=session_service,
    # )
    
    # session = await session_service.create_session(
    #     app_name=APP_NAME,
    #     user_id="user",
    #     session_id=SESSION_ID,
    # )
    
    runner, session_service = get_runner_with_session(performance_analyzer)
    session = await create_session(session_service)
    
    prompt = f"""
Analyze this React code for performance issues and output as {output_format} format.

File: {filename}

```tsx
{code}
```

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
    
    # result = await runner.run(
    #     prompt,
    #     session_id=session.id,
    # )
    
    result = await run_agent_async(prompt, runner)
    
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
