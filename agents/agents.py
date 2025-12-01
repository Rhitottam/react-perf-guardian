from google.genai import types
from google.adk.agents import Agent, SequentialAgent
from google.adk.tools import FunctionTool
from tools import (
    inspect_component, list_components, trace_prop,
    analyze_render_triggers, analyze_hook_dependencies,
    analyze_state_relationships, analyze_jsx_expressions
)
from google.adk.models.google_llm import Gemini
from google.genai import types
from parser_bridge import parse_react_code, AstContext
from utils import retry_config

# Tool for parser agent
def parse_code(code: str, filename: str = "component.tsx") -> dict:
    """
    Parse React/TypeScript code and extract AST information.
    
    Args:
        code: The source code to parse
        filename: Virtual filename (affects TypeScript/JSX handling)
    
    Returns:
        Parsed component information
    """
    result = parse_react_code(code, filename)
    
    # Store in context for other tools
    AstContext.get_instance().set_data(result)
    
    return {
        "success": result.success,
        "components_found": [c.get("name") for c in result.components],
        "total_components": len(result.components),
        "errors": result.errors,
        "metadata": result.metadata
    }


# Agent 1: Parser Agent
parser_agent = Agent(
    name="parser",
    model=Gemini(
        model="gemini-2.5-flash-lite",
        retry_options=retry_config
    ),
    description="Parses React/TypeScript code into structured AST data",
    tools=[FunctionTool(parse_code)],
    instruction="""
You are the first agent in a React performance analysis pipeline.
Your job is to parse the provided React code.

When you receive code:
1. Call the parse_code tool with the code
2. Report what components were found
3. Note any parsing errors

Pass the parsing results to the next agent. Keep your response concise.
""",
)


# Agent 2: Analyzer Agent
analyzer_agent = Agent(
    name="analyzer",
    model=Gemini(
        model="gemini-2.5-flash-lite",
        retry_options=retry_config
    ),
    description="Analyzes React components for performance patterns and issues",
    tools=[
        FunctionTool(inspect_component),
        FunctionTool(list_components),
        FunctionTool(trace_prop),
        FunctionTool(analyze_render_triggers),
        FunctionTool(analyze_hook_dependencies),
        FunctionTool(analyze_state_relationships),
        FunctionTool(analyze_jsx_expressions),
    ],
    instruction="""
You are a React performance analysis expert. You receive parsed AST data 
and must identify performance issues using the available tools.

## Analysis Strategy

1. **Start with overview**: Use list_components to see all components

2. **For each component, investigate systematically:**

   a) **Render triggers** (use analyze_render_triggers)
      - Is it re-rendering due to unstable props?
      - Would memoization help?
   
   b) **Hook health** (use analyze_hook_dependencies)
      - Are dependency arrays correct?
      - Are any deps unstable?
   
   c) **State design** (use analyze_state_relationships)
      - Is there derived state?
      - States that should be consolidated?
   
   d) **JSX patterns** (use analyze_jsx_expressions)
      - Only flag inline expressions if they break memoization
      - Assess severity based on context

3. **For prop drilling concerns**: Use trace_prop to follow flow

## Output Format

Return structured JSON:

```json
{
  "issues": [
    {
      "id": "unique-id",
      "type": "issue-type",
      "component": "ComponentName",
      "line": 42,
      "description": "Clear explanation",
      "evidence": {},
      "severity": "critical|warning|suggestion",
      "confidence": "high|medium|low"
    }
  ],
  "component_health": {
    "ComponentName": "good|needs-attention|problematic"
  }
}
```

## Guidelines

- **Avoid false positives**: Only flag issues with evidence
- **Context matters**: Inline function is fine if child isn't memoized
- **Be specific**: Include line numbers and concrete details
""",
)


# Agent 3: Reasoner Agent  
reasoner_agent = Agent(
    name="reasoner",
    model=Gemini(
        model="gemini-2.5-flash-lite",
        retry_options=retry_config
    ),  # Use thinking model for reasoning
    description="Evaluates issues, filters false positives, and suggests fixes",
    instruction="""
You receive a list of potential performance issues from the analyzer.
Your job is to apply expert judgment to filter and enhance the findings.

## For each issue:

1. **Validate**: Is this actually a problem in context?
   - Missing useCallback isn't an issue if callback isn't passed to memoized children
   - Inline objects are fine if child doesn't use React.memo
   - Consider if the "fix" adds more complexity than the problem warrants

2. **Assess severity**:
   - **Critical**: Will cause noticeable perf issues (N+1 re-renders, broken memoization)
   - **Warning**: Could cause issues at scale, worth addressing
   - **Suggestion**: Cleaner code, marginal performance benefit

3. **Provide actionable fix**:
   - Include specific code changes
   - Explain the "why" - what runtime behavior does this cause?
   - Note any tradeoffs

4. **Assign confidence**:
   - **High**: Clear evidence from AST analysis
   - **Medium**: Likely issue but depends on runtime behavior
   - **Low**: Potential issue, worth reviewing

## Output Format

CRITICAL: Each issue MUST include file, line, component, severity, title, problem, and suggestion.

```json
{
  "issues": [
    {
      "file": "path/to/file.tsx",
      "line": 42,
      "component": "ComponentName",
      "severity": "critical|high|medium|low",
      "confidence": "high|medium|low",
      "title": "Brief description (e.g., 'Inline function breaks memoization')",
      "problem": "Detailed explanation of why this is an issue",
      "suggestion": "Specific fix with code example",
      "runtime_impact": "What happens at runtime because of this",
      "code_before": "// Original problematic code",
      "code_after": "// Fixed code"
    }
  ],
  "summary": {
    "critical_count": 0,
    "high_count": 0,
    "medium_count": 0,
    "low_count": 0,
    "files_analyzed": 1,
    "components_analyzed": ["ComponentName"],
    "overall_health": "good|needs-work|problematic"
  }
}
```

Filter aggressively. Developers hate false positives.
""",
)


# Agent 4: Reporter Agent
# Note: Simplified tools without complex type annotations to avoid API schema issues
def format_report(report_data: str, output_format: str) -> str:
    """
    Format the analysis report in the requested format.
    
    Args:
        report_data: JSON string containing issues and summary
        output_format: One of 'markdown', 'json', 'github'
    
    Returns:
        Formatted report string
    """
    import json
    
    try:
        data = json.loads(report_data)
        issues = data.get("issues", [])
        summary = data.get("summary", {})
    except:
        issues = []
        summary = {}
    
    if output_format == "markdown":
        lines = ["# React Performance Analysis Report", ""]
        
        # Group by severity
        critical = [i for i in issues if i.get("severity") == "critical"]
        high = [i for i in issues if i.get("severity") == "high"]
        medium = [i for i in issues if i.get("severity") == "medium"]
        low = [i for i in issues if i.get("severity") == "low"]
        
        lines.extend([
            "## Summary",
            f"- 🚨 {len(critical)} critical issues",
            f"- ⚠️  {len(high)} high-priority issues",
            f"- 💡 {len(medium)} medium-priority issues",
            f"- ℹ️  {len(low)} low-priority suggestions",
            ""
        ])
        
        # Helper to format issue
        def format_issue(issue):
            file = issue.get("file", "unknown")
            line = issue.get("line", "?")
            component = issue.get("component", "Unknown")
            title = issue.get("title", "Performance Issue")
            problem = issue.get("problem", "")
            suggestion = issue.get("suggestion", "")
            impact = issue.get("runtime_impact", "")
            code_before = issue.get("code_before", "")
            code_after = issue.get("code_after", "")
            
            result = [
                f"### `{file}:{line}` - {component}",
                f"**{title}**",
                "",
                f"**Problem:** {problem}",
                ""
            ]
            
            if impact:
                result.extend([f"**Runtime Impact:** {impact}", ""])
            
            result.extend([f"**Suggestion:**", f"{suggestion}", ""])
            
            if code_before or code_after:
                result.append("**Example:**")
                result.append("```tsx")
                if code_before:
                    result.append(f"// Before:\n{code_before}")
                    result.append("")
                if code_after:
                    result.append(f"// After:\n{code_after}")
                result.append("```")
                result.append("")
            
            return result
        
        if critical:
            lines.extend(["## 🚨 Critical Issues", ""])
            for issue in critical:
                lines.extend(format_issue(issue))
        
        if high:
            lines.extend(["## ⚠️  High-Priority Issues", ""])
            for issue in high:
                lines.extend(format_issue(issue))
        
        if medium:
            lines.extend(["## 💡 Medium-Priority Issues", ""])
            for issue in medium:
                lines.extend(format_issue(issue))
        
        if low:
            lines.extend(["## ℹ️  Low-Priority Suggestions", ""])
            for issue in low:
                lines.extend(format_issue(issue))
        
        return "\n".join(lines)
    
    elif output_format == "github":
        lines = [
            "## React Performance Analysis",
            "",
            f"Found {len(issues)} potential performance issues:",
            ""
        ]
        
        for issue in issues[:10]:  # Limit to 10 comments
            lines.append(
                f"- **{issue.get('component')}** ({issue.get('type')}): "
                f"{issue.get('description')}"
            )
        
        if len(issues) > 10:
            lines.append(f"\n... and {len(issues) - 10} more issues (see detailed report)")
        
        return "\n".join(lines)
    
    else:  # json
        return json.dumps({"issues": issues, "summary": summary}, indent=2)


reporter_agent = Agent(
    name="reporter",
    model=Gemini(
        model="gemini-2.5-flash-lite",
        retry_options=retry_config
    ),
    description="Formats analysis results for the target audience",
    tools=[
        FunctionTool(format_report),
    ],
    instruction="""
You MUST call the format_report tool with the analysis results.

## CRITICAL: You must ALWAYS call format_report() tool

DO NOT write any explanation or conversational text.
DO NOT say "passing to next agent" or describe what you're doing.
ONLY call the format_report() tool with the data.

## Your Task

1. Take the validated issues and summary from the reasoner agent
2. Create a JSON string with this EXACT structure:
   {"issues": [...], "summary": {...}}
3. Call format_report(report_data=<json_string>, output_format=<format>)
4. Return ONLY the tool's output - no additional text

## Example

If you receive issues like:
[{
  "file": "Button.tsx",
  "line": 42,
  "severity": "high",
  "title": "Inline function breaks memo",
  "problem": "...",
  "suggestion": "..."
}]

You MUST call:
format_report(
  report_data='{"issues": [...], "summary": {...}}',
  output_format="json"
)

DO NOT add any text before or after the tool call.

### Markdown Format (Default):

```markdown
# React Performance Analysis Report

## Summary
- X critical issues
- Y warnings  
- Z suggestions

## Critical Issues

### [Component: Line] Brief title
**Problem**: What's wrong
**Impact**: Runtime behavior
**Fix**: 
```jsx
// code
```

## Warnings
...

## Suggestions
...
```

Keep it actionable and scannable.
""",
)


# Main orchestrator - Sequential multi-agent system
performance_analyzer = SequentialAgent(
    name="react_performance_analyzer",
    description="Analyzes React code for performance issues using multi-agent pipeline",
    sub_agents=[parser_agent, analyzer_agent, reasoner_agent, reporter_agent],
)
