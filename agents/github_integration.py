"""
GitHub PR Integration for React Performance Analyzer

Fetches changed files from a PR and posts review comments.
"""

import os
import json
import asyncio
import re
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv
import subprocess

# Load .env file if it exists (silently ignore if not)
try:
    load_dotenv()
except:
    pass


def parse_pr_url(url: str) -> Tuple[str, int]:
    """
    Parse a GitHub PR URL to extract repository and PR number.
    
    Supported formats:
    - https://github.com/owner/repo/pull/123
    - https://github.com/owner/repo/pull/123/files
    - https://github.com/owner/repo/pull/123#issuecomment-xxx
    - github.com/owner/repo/pull/123
    
    Args:
        url: GitHub PR URL
        
    Returns:
        Tuple of (repository, pr_number) where repository is "owner/repo"
        
    Raises:
        ValueError: If URL format is invalid
    """
    # Pattern to match GitHub PR URLs
    pattern = r'(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+)/pull/(\d+)'
    
    match = re.search(pattern, url)
    if not match:
        raise ValueError(
            f"Invalid GitHub PR URL: {url}\n"
            "Expected format: https://github.com/owner/repo/pull/123"
        )
    
    owner, repo, pr_number = match.groups()
    repository = f"{owner}/{repo}"
    
    return repository, int(pr_number)

class GitHubPRAnalyzer:
    """Analyzes React files changed in a GitHub PR"""
    
    def __init__(self, github_token: Optional[str] = None, repo: Optional[str] = None):
        """
        Initialize GitHub PR Analyzer
        
        Args:
            github_token: GitHub personal access token (optional, falls back to env)
            repo: Repository in format 'owner/repo' (optional, falls back to env)
        """
        self.token = github_token or os.getenv('GITHUB_TOKEN')
        self.repo = repo or os.getenv('GITHUB_REPOSITORY')
        
        if not self.token:
            raise ValueError(
                "GitHub token required. Set GITHUB_TOKEN env var or pass github_token argument"
            )
        
        if not self.repo:
            raise ValueError(
                "Repository required. Set GITHUB_REPOSITORY env var (format: owner/repo) "
                "or pass repo argument"
            )
    
    def get_changed_files(self, pr_number: int) -> List[Dict[str, str]]:
        """
        Fetch list of changed files in a PR
        
        Args:
            pr_number: Pull request number
            
        Returns:
            List of dicts with 'filename', 'status', 'patch'
        """
        import requests
        
        url = f"https://api.github.com/repos/{self.repo}/pulls/{pr_number}/files"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        files = response.json()
        
        # Filter for React/TS files only
        react_extensions = {'.tsx', '.ts', '.jsx', '.js'}
        react_files = [
            f for f in files 
            if Path(f['filename']).suffix in react_extensions
            and f['status'] in ['added', 'modified']
        ]
        
        print(f"📁 Found {len(files)} changed files, {len(react_files)} are React/TS files")
        
        return react_files
    
    def fetch_file_content(self, filepath: str, ref: str = "HEAD", contents_url: str = None) -> str:
        """
        Fetch file content from GitHub
        
        Args:
            filepath: Path to file in repo
            ref: Git ref (branch, commit, etc.)
            contents_url: GitHub API contents URL (preferred for PR files)
            
        Returns:
            File content as string
        """
        import requests
        
        # Prefer contents_url if provided (reliable API endpoint for PR files)
        if contents_url:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github.v3.raw"  # Get raw content directly
            }
            response = requests.get(contents_url, headers=headers)
            response.raise_for_status()
            return response.text
        
        # Fallback to constructing contents URL manually
        url = f"https://api.github.com/repos/{self.repo}/contents/{filepath}?ref={ref}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3.raw"
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        return response.text
    
    async def analyze_pr_file(self, filename: str, content: str, session_id: str, is_first_file: bool = True) -> Dict:
        """
        Analyze a single file using the React Performance Analyzer
        
        Args:
            filename: Name of the file
            content: File content
            session_id: Session ID for this PR analysis (shared across all files)
            is_first_file: If True, skip Memory Agent (no history yet)
            
        Returns:
            Analysis results with issues
        """
        from main import analyze_code
        
        print(f"  🔍 Analyzing {filename}...")
        
        try:
            # Run analysis with FRESH session for analyzer
            # Memory Agent reads from PR session, but analyzer gets clean context
            result = await analyze_code(
                content, 
                output_format="json", 
                filename=filename,
                pr_session_id=session_id,  # ← PR session for Memory Agent
                memory_context="",  # ← Memory Agent provides this
                is_first_file=is_first_file  # ← Skip memory for first file
            )
            
            # Debug: Show what we got
            if os.getenv('DEBUG_ANALYSIS'):
                print(f"  [DEBUG] Raw response type: {type(result)}")
                print(f"  [DEBUG] Raw response length: {len(result) if isinstance(result, str) else 'N/A'}")
                print(f"  [DEBUG] First 500 chars: {result[:500] if isinstance(result, str) else result}")
            
            # Check if result is empty
            if not result or (isinstance(result, str) and result.strip() == ""):
                print(f"  ❌ Empty result for {filename}")
                return {
                    "filename": filename,
                    "success": False,
                    "error": "Empty analysis result (file may be too large or complex)"
                }
            
            # Check if result is an error message from the agent
            if isinstance(result, str):
                error_indicators = ["I'm sorry", "error", "failed", "cannot parse", "unable to"]
                if any(indicator.lower() in result.lower()[:100] for indicator in error_indicators):
                    if not result.strip().startswith('{'):
                        print(f"  ⚠️  Agent reported error: {result[:100]}...")
                        return {
                            "filename": filename,
                            "success": True,
                            "issues": [],
                            "summary": {"warning": "Agent reported parsing error"},
                            "error": result[:200]
                        }
            
            # Parse JSON result
            if isinstance(result, str):
                try:
                    # Strip markdown code fences if present
                    cleaned_result = result.strip()
                    
                    # Handle various markdown fence formats
                    if '```' in cleaned_result:
                        # Method 1: JSON on same line as fence (```json {...} ```)
                        fence_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', cleaned_result)
                        if fence_match:
                            cleaned_result = fence_match.group(1)
                        else:
                            # Method 2: Multi-line fence (```json\n{...}\n```)
                            lines = cleaned_result.split('\n')
                            if lines[0].startswith('```'):
                                lines = lines[1:]
                            if lines and lines[-1].strip() == '```':
                                lines = lines[:-1]
                            cleaned_result = '\n'.join(lines)
                    
                    result = json.loads(cleaned_result)
                    print(f"  ✅ Parsed response successfully")
                except json.JSONDecodeError as e:
                    print(f"  ⚠️  Agent returned text instead of JSON, attempting extraction...")
                    
                    # Try to find JSON embedded in the text
                    json_match = re.search(r'\{[\s\S]*"issues"[\s\S]*\}', result)
                    if json_match:
                        try:
                            result = json.loads(json_match.group(0))
                            print(f"  ✅ Extracted JSON successfully")
                        except:
                            print(f"  ❌ Could not extract valid JSON")
                            print(f"     First 200 chars: {result[:200]}")
                            # Return empty result instead of failing
                            return {
                                "filename": filename,
                                "success": True,
                                "issues": [],
                                "summary": {"warning": "Agent returned text instead of JSON, no issues detected"},
                                "error": "Agent output was not JSON"
                            }
                    else:
                        print(f"  ⚠️  No JSON found in response, returning empty result")
                        print(f"     Response: {result[:300]}")
                        # Return empty result
                        return {
                            "filename": filename,
                            "success": True,
                            "issues": [],
                            "summary": {"warning": "Could not parse agent output"},
                            "error": "No JSON in response"
                        }
            
            issues = result.get("issues", [])
            print(f"  📊 Found {len(issues)} potential issues")
            
            # Memory Agent handles cross-file insights via session history
            # Issues are stored in the session automatically
            
            return {
                "filename": filename,
                "success": True,
                "issues": issues,
                "summary": result.get("summary", {})
            }
        except Exception as e:
            print(f"  ❌ Error analyzing {filename}: {str(e)}")
            import traceback
            print(f"     Traceback: {traceback.format_exc()[:200]}")
            return {
                "filename": filename,
                "success": False,
                "error": str(e)
            }
    
    async def analyze_pr(self, pr_number: int) -> Dict:
        """
        Analyze all React files in a PR using DatabaseSessionService + Memory Agent.
        
        The Memory Agent reads session history to extract patterns for cross-file insights.
        
        Args:
            pr_number: Pull request number
            
        Returns:
            Combined analysis results with project-wide insights
        """
        print(f"\n🚀 Analyzing PR #{pr_number} in {self.repo}")
        print("=" * 60)
        
        # Create ONE session ID for entire PR analysis
        # All files share this session - Memory Agent reads history between files
        session_id = f"pr-{self.repo.replace('/', '-')}-{pr_number}"
        print(f"📝 Session ID: {session_id}")
        print("🧠 Memory Agent will extract patterns from session history")
        
        # Get changed files
        changed_files = self.get_changed_files(pr_number)
        
        if not changed_files:
            print("✅ No React/TypeScript files changed in this PR")
            return {
                "pr_number": pr_number,
                "files_analyzed": 0,
                "results": []
            }
        
        # Analyze each file with shared session
        results = []
        all_issues = []
        
        for i, file_info in enumerate(changed_files):
            filename = file_info['filename']
            contents_url = file_info.get('contents_url')
            is_first_file = (i == 0)  # Only first file skips Memory Agent
            
            # Fetch file content
            try:
                content = self.fetch_file_content(filename, ref=f"pull/{pr_number}/head", contents_url=contents_url)
            except Exception as e:
                print(f"  ❌ Could not fetch {filename}: {str(e)}")
                continue
            
            # Analyze file with shared session ID
            # Memory Agent runs automatically for subsequent files
            analysis = await self.analyze_pr_file(
                filename, 
                content, 
                session_id=session_id, 
                is_first_file=is_first_file
            )
            results.append(analysis)
            
            # Collect issues for summary
            if analysis.get("success") and analysis.get("issues"):
                all_issues.extend(analysis["issues"])
        
        # Combine results
        total_issues = len(all_issues)
        
        # Count issue types for project insights
        issue_types = {}
        for issue in all_issues:
            issue_type = issue.get("title", "unknown")
            issue_types[issue_type] = issue_types.get(issue_type, 0) + 1
        
        print("=" * 60)
        print(f"✅ Analysis complete: {len(results)} files, {total_issues} issues found")
        
        # Show recurring issues
        recurring = {k: v for k, v in issue_types.items() if v >= 2}
        if recurring:
            print(f"⚠️  Recurring issues: {', '.join(f'{k} ({v}x)' for k, v in recurring.items())}")
        
        # Clear the database file to prevent cross-PR pollution
        self._cleanup_session_db()
        
        return {
            "pr_number": pr_number,
            "files_analyzed": len(results),
            "results": results,
            "total_issues": total_issues,
            "recurring_issues": recurring,
            "issue_breakdown": issue_types,
            "session_id": session_id
        }
    
    def _cleanup_session_db(self):
        """Clean up the session database after PR analysis."""
        import os
        from pathlib import Path
        db_path = Path(__file__).parent / "pr_sessions.db"
        try:
            if db_path.exists():
                os.remove(db_path)
                print(f"🗑️  Cleared session database")
        except Exception as e:
            print(f"⚠️  Could not clear session DB: {e}")
    
    def post_review_comment(
        self, 
        pr_number: int, 
        filepath: str, 
        line: int, 
        body: str,
        commit_id: Optional[str] = None
    ) -> Dict:
        """
        Post an inline review comment on a specific line
        
        Args:
            pr_number: Pull request number
            filepath: Path to file in repo
            line: Line number for comment
            body: Comment text
            commit_id: Specific commit SHA (optional, uses PR head if not provided)
            
        Returns:
            API response
        """
        import requests
        
        # Get PR details to find latest commit if not provided
        if not commit_id:
            pr_url = f"https://api.github.com/repos/{self.repo}/pulls/{pr_number}"
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github.v3+json"
            }
            pr_response = requests.get(pr_url, headers=headers)
            pr_response.raise_for_status()
            commit_id = pr_response.json()['head']['sha']
        
        url = f"https://api.github.com/repos/{self.repo}/pulls/{pr_number}/comments"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        data = {
            "body": body,
            "commit_id": commit_id,
            "path": filepath,
            "line": line,
            "side": "RIGHT"  # Comment on the new version
        }
        
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        return response.json()
    
    def create_review(
        self, 
        pr_number: int, 
        comments: List[Dict],
        event: str = "COMMENT",
        body: Optional[str] = None
    ) -> Dict:
        """
        Create a comprehensive PR review with multiple comments
        
        Args:
            pr_number: Pull request number
            comments: List of review comments, each with:
                - path: File path
                - line: Line number
                - body: Comment text
            event: Review event type - "APPROVE", "REQUEST_CHANGES", or "COMMENT"
            body: Overall review summary (optional)
            
        Returns:
            API response
        """
        import requests
        
        # Get PR head commit
        pr_url = f"https://api.github.com/repos/{self.repo}/pulls/{pr_number}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        pr_response = requests.get(pr_url, headers=headers)
        pr_response.raise_for_status()
        commit_id = pr_response.json()['head']['sha']
        
        url = f"https://api.github.com/repos/{self.repo}/pulls/{pr_number}/reviews"
        
        # Format comments for review API
        formatted_comments = [
            {
                "path": c["path"],
                "line": c["line"],
                "body": c["body"],
                "side": "RIGHT"
            }
            for c in comments
        ]
        
        data = {
            "commit_id": commit_id,
            "body": body or "",
            "event": event,
            "comments": formatted_comments
        }
        
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        return response.json()
    
    async def analyze_and_review(
        self, 
        pr_number: int,
        severity_threshold: str = "medium",
        auto_approve: bool = False
    ) -> Dict:
        """
        Analyze PR and post review with inline comments
        
        Args:
            pr_number: Pull request number
            severity_threshold: Minimum severity to report ("low", "medium", "high", "critical")
            auto_approve: If True, approve PRs with no critical issues
            
        Returns:
            Review results
        """
        print(f"\n🎯 Analyzing and reviewing PR #{pr_number}")
        print(f"   Severity threshold: {severity_threshold}")
        print(f"   Auto-approve: {auto_approve}")
        print("=" * 60)
        
        # Analyze PR
        analysis = await self.analyze_pr(pr_number)
        
        if analysis["files_analyzed"] == 0:
            print("✅ No files to analyze, skipping review")
            return analysis
        
        # Filter issues by severity
        severity_levels = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        threshold_level = severity_levels.get(severity_threshold, 1)
        
        review_comments = []
        critical_count = 0
        high_count = 0
        
        for result in analysis["results"]:
            if not result.get("success"):
                continue
            
            filepath = result["filename"]
            
            for issue in result.get("issues", []):
                severity = issue.get("severity", "low")
                issue_level = severity_levels.get(severity, 0)
                
                # Track critical/high issues
                if severity == "critical":
                    critical_count += 1
                elif severity == "high":
                    high_count += 1
                
                # Skip if below threshold
                if issue_level < threshold_level:
                    continue
                
                # Format comment
                line = issue.get("line", 1)
                title = issue.get("title", "Performance Issue")
                problem = issue.get("problem", "")
                suggestion = issue.get("suggestion", "")
                
                severity_emoji = {
                    "critical": "🚨",
                    "high": "⚠️",
                    "medium": "💡",
                    "low": "ℹ️"
                }.get(severity, "📝")
                
                comment_body = f"""
{severity_emoji} **{title}** ({severity.upper()})

**Problem:**
{problem}

**Suggestion:**
{suggestion}

---
*React Performance Analyzer*
"""
                
                review_comments.append({
                    "path": filepath,
                    "line": line,
                    "body": comment_body.strip()
                })
        
        # Build memory insights section
        memory_section = ""
        recurring_warning = analysis.get("recurring_warning")
        conventions = analysis.get("detected_conventions", {})
        
        if recurring_warning or conventions:
            memory_section = "\n\n---\n\n### 🧠 Project-Wide Insights\n\n"
            
            if recurring_warning:
                memory_section += f"**⚠️ Recurring Pattern Detected:**\n{recurring_warning}\n\n"
                memory_section += "Consider implementing a project-wide solution:\n"
                memory_section += "- Add ESLint rules (e.g., `react-perf/jsx-no-new-function-as-prop`)\n"
                memory_section += "- Create utility hooks (e.g., `useStableCallback`)\n"
                memory_section += "- Team training on React.memo patterns\n\n"
            
            if conventions:
                memory_section += "**Detected Conventions:**\n"
                for key, value in conventions.items():
                    memory_section += f"- {key.replace('_', ' ').title()}: `{value}`\n"
        
        # Determine review event
        if critical_count > 0:
            event = "REQUEST_CHANGES"
            review_summary = f"""
## 🚨 React Performance Review

**Critical issues found: {critical_count}**

This PR has {critical_count} critical performance issue(s) that should be addressed.

**Summary:**
- 🚨 Critical: {critical_count}
- ⚠️ High: {high_count}
- 💡 Total issues: {len(review_comments)}

Please review the inline comments for details.
{memory_section}
"""
        elif high_count > 0 and not auto_approve:
            event = "COMMENT"
            review_summary = f"""
## ⚠️ React Performance Review

**High-priority issues found: {high_count}**

**Summary:**
- ⚠️ High: {high_count}
- 💡 Total issues: {len(review_comments)}

Consider addressing these before merging.
{memory_section}
"""
        elif len(review_comments) > 0:
            event = "APPROVE" if auto_approve else "COMMENT"
            review_summary = f"""
## 💡 React Performance Review

**Minor issues found: {len(review_comments)}**

These are suggestions that may improve performance. Not blocking.
{memory_section}
"""
        else:
            event = "APPROVE" if auto_approve else "COMMENT"
            review_summary = f"""
## ✅ React Performance Review

No performance issues detected! Great work! 🎉
{memory_section}
"""
        
        # Post review
        if review_comments:
            print(f"\n📝 Posting review with {len(review_comments)} comments...")
            print(f"   Event: {event}")
            
            try:
                review_response = self.create_review(
                    pr_number=pr_number,
                    comments=review_comments,
                    event=event,
                    body=review_summary
                )
                
                print(f"✅ Review posted successfully!")
                print(f"   Review ID: {review_response.get('id')}")
                
                return {
                    **analysis,
                    "review_posted": True,
                    "review_id": review_response.get("id"),
                    "review_event": event,
                    "comments_posted": len(review_comments)
                }
            except Exception as e:
                print(f"❌ Error posting review: {str(e)}")
                return {
                    **analysis,
                    "review_posted": False,
                    "error": str(e)
                }
        else:
            print("✅ No issues to report")
            return {
                **analysis,
                "review_posted": False,
                "reason": "no_issues"
            }


async def main():
    """CLI entry point for manual PR analysis"""
    import sys
    
    if len(sys.argv) < 2:
        print("""
Usage: python github_integration.py <pr_number_or_url> [options]

Arguments:
  pr_number_or_url      Either:
                        - PR number (e.g., 123)
                        - Full PR URL (e.g., https://github.com/owner/repo/pull/123)

Options:
  --severity <level>    Minimum severity to report (low|medium|high|critical)
                        Default: medium
  --auto-approve        Approve PRs with no critical issues
  --analyze-only        Only analyze, don't post review
  
Environment Variables:
  GITHUB_TOKEN          GitHub personal access token (required)
  GITHUB_REPOSITORY     Repository in format 'owner/repo' (required if using PR number)
  
Examples:
  # Using PR number (requires GITHUB_REPOSITORY env var)
  export GITHUB_TOKEN="ghp_xxxxx"
  export GITHUB_REPOSITORY="owner/repo"
  python github_integration.py 123 --severity high
  
  # Using PR URL (repository auto-detected from URL)
  export GITHUB_TOKEN="ghp_xxxxx"
  python github_integration.py https://github.com/owner/repo/pull/123 --severity high
  
  # Dry run with URL
  python github_integration.py https://github.com/owner/repo/pull/123 --analyze-only
""")
        sys.exit(1)
    
    pr_input = sys.argv[1]
    severity = "medium"
    auto_approve = False
    analyze_only = False
    
    # Parse options
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--severity" and i + 1 < len(sys.argv):
            severity = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--auto-approve":
            auto_approve = True
            i += 1
        elif sys.argv[i] == "--analyze-only":
            analyze_only = True
            i += 1
        else:
            i += 1
    
    # Determine if input is a URL or PR number
    repository = None
    pr_number = None
    
    if pr_input.startswith('http') or 'github.com' in pr_input:
        # Parse URL
        try:
            repository, pr_number = parse_pr_url(pr_input)
            print(f"📋 Parsed PR URL:")
            print(f"   Repository: {repository}")
            print(f"   PR Number: {pr_number}")
            print()
        except ValueError as e:
            print(f"❌ Error: {str(e)}")
            sys.exit(1)
    else:
        # Treat as PR number
        try:
            pr_number = int(pr_input)
        except ValueError:
            print(f"❌ Error: Invalid input '{pr_input}'")
            print("   Expected either a PR number or a GitHub PR URL")
            sys.exit(1)
    
    # Create analyzer (with repository if parsed from URL)
    try:
        analyzer = GitHubPRAnalyzer(repo=repository)
    except ValueError as e:
        print(f"❌ Error: {str(e)}")
        sys.exit(1)
    
    if analyze_only:
        # Just analyze, don't post
        result = await analyzer.analyze_pr(pr_number)
        print("\n📊 Analysis Results:")
        print(json.dumps(result, indent=2))
    else:
        # Analyze and post review
        result = await analyzer.analyze_and_review(
            pr_number=pr_number,
            severity_threshold=severity,
            auto_approve=auto_approve
        )
        print("\n📊 Final Results:")
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())

