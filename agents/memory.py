from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class ProjectMemory:
    """Tracks information across multiple analysis runs."""

    # Files we've analyzed
    analyzed_files: dict[str, dict] = field(default_factory=dict)

    # Patterns we've seen
    recurring_issues: dict[str, int] = field(default_factory=dict)  # issue_type -> count

    # Project conventions detected
    conventions: dict[str, str] = field(default_factory=dict)

    # Component relationships across files
    component_graph: dict[str, list[str]] = field(default_factory=dict)

    def record_analysis(self, file_path: str, issues: list[dict]):
        """Record issues from an analysis run."""
        self.analyzed_files[file_path] = {
            "issues": issues,
            "timestamp": datetime.now().isoformat(),
        }

        # Track recurring issues
        for issue in issues:
            issue_type = issue.get("type", "unknown")
            self.recurring_issues[issue_type] = self.recurring_issues.get(issue_type, 0) + 1

    def detect_conventions(self, components: list[dict]):
        """Detect project conventions from analyzed components."""
        # Check for consistent patterns
        memo_usage = sum(1 for c in components if c.get("isMemoized"))
        if memo_usage > len(components) * 0.7:
            self.conventions["memoization"] = "heavy"

        # Check state management patterns
        has_context = any(
            any(h.get("type") == "useContext" for h in c.get("hooks", []))
            for c in components
        )
        has_redux = any(
            any(h.get("type") in ["useSelector", "useDispatch"] for h in c.get("hooks", []))
            for c in components
        )

        if has_redux:
            self.conventions["state_management"] = "redux"
        elif has_context:
            self.conventions["state_management"] = "context"

    def get_recurring_issue_warning(self) -> Optional[str]:
        """Generate warning for recurring issues."""
        frequent = [
            (issue, count)
            for issue, count in self.recurring_issues.items()
            if count >= 3
        ]

        if frequent:
            issues_str = ", ".join(f"{issue} ({count}x)" for issue, count in frequent)
            return f"Recurring issues across files: {issues_str}. Consider project-wide lint rules."

        return None

    def get_analysis_summary(self) -> dict:
        """Get overall analysis summary."""
        return {
            "files_analyzed": len(self.analyzed_files),
            "total_issues_found": sum(len(f.get("issues", [])) for f in self.analyzed_files.values()),
            "recurring_issues": self.recurring_issues,
            "detected_conventions": self.conventions,
            "component_graph": self.component_graph,
            "warning": self.get_recurring_issue_warning()
        }
