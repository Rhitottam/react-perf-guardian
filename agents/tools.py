from typing import Optional
from parser_bridge import AstContext

# Get shared context
ctx = AstContext.get_instance()


def inspect_component(component_name: str) -> dict:
    """
    Returns detailed information about a specific React component.

    Args:
        component_name: Name of the component to inspect (e.g., "UserCard")

    Returns:
        Component details including props, state, hooks, children,
        memoization status, and JSX expressions
    """
    component = ctx.get_component(component_name)
    if not component:
        return {"error": f"Component '{component_name}' not found"}
    return component


def list_components() -> dict:
    """
    Returns a list of all components found in the parsed code.

    Returns:
        List of component names with basic metadata
    """
    data = ctx.get_data()
    if not data:
        return {"error": "No code has been parsed yet"}

    return {
        "components": [
            {
                "name": c.get("name"),
                "isMemoized": c.get("isMemoized"),
                "propsCount": len(c.get("props", [])),
                "hooksCount": len(c.get("hooks", [])),
                "childrenCount": len(c.get("children", []))
            }
            for c in data.components
        ],
        "total": len(data.components)
    }


def trace_prop(prop_name: str, start_component: str) -> dict:
    """
    Traces how a prop flows through the component tree.

    Args:
        prop_name: The prop to trace (e.g., "onClick", "user")
        start_component: Component where the prop originates

    Returns:
        Flow path showing where prop is passed, transformed, and consumed
    """
    component = ctx.get_component(start_component)
    if not component:
        return {"error": f"Component '{start_component}' not found"}

    # Find the prop
    prop = None
    for p in component.get("props", []):
        if p.get("name") == prop_name:
            prop = p
            break

    if not prop:
        return {"error": f"Prop '{prop_name}' not found in '{start_component}'"}

    # Build flow path
    flow = {
        "origin": start_component,
        "prop_name": prop_name,
        "path": [],
        "terminal_usages": [],
        "pass_through_components": []
    }

    # Track through children
    for child_pass in prop.get("passedToChildren", []):
        child_name = child_pass.get("childComponent")
        child = ctx.get_component(child_name)

        flow["path"].append({
            "component": child_name,
            "received_as": child_pass.get("asPropName"),
            "transformed": child_pass.get("transformed"),
            "child_is_memoized": child.get("isMemoized") if child else False
        })

        # Check if child uses it or just passes through
        if child:
            child_prop = None
            for cp in child.get("props", []):
                if cp.get("name") == child_pass.get("asPropName"):
                    child_prop = cp
                    break

            if child_prop:
                if child_prop.get("usedInRender"):
                    flow["terminal_usages"].append({
                        "component": child_name,
                        "usage": "render"
                    })
                elif child_prop.get("usedInHooks"):
                    flow["terminal_usages"].append({
                        "component": child_name,
                        "usage": "hooks",
                        "hooks": child_prop.get("usedInHooks")
                    })
                else:
                    flow["pass_through_components"].append(child_name)

    flow["depth"] = len(flow["path"])
    return flow


def analyze_render_triggers(component_name: str) -> dict:
    """
    Identifies what causes a component to re-render.

    Args:
        component_name: Component to analyze

    Returns:
        All possible render triggers with stability assessment
    """
    component = ctx.get_component(component_name)
    if not component:
        return {"error": f"Component '{component_name}' not found"}

    triggers = []

    # Props as triggers
    for prop in component.get("props", []):
        triggers.append({
            "type": "prop",
            "name": prop.get("name"),
            "actually_used": prop.get("usedInRender") or bool(prop.get("usedInHooks")),
            "stability": "depends_on_parent"
        })

    # State as triggers
    for state in component.get("state", []):
        triggers.append({
            "type": "state",
            "name": state.get("name"),
            "actually_used": True,
            "stability": "changes_on_set"
        })

    # Context subscriptions
    for hook in component.get("hooks", []):
        if hook.get("type") == "useContext":
            triggers.append({
                "type": "context",
                "name": hook.get("returnValue", "unknown"),
                "actually_used": True,
                "stability": "depends_on_provider"
            })

    # Parent renders (if not memoized)
    if not component.get("isMemoized"):
        triggers.append({
            "type": "parent_render",
            "mitigated": False,
            "suggestion": "Consider React.memo if props are stable"
        })

    return {
        "component": component_name,
        "is_memoized": component.get("isMemoized"),
        "triggers": triggers,
        "unnecessary_renders_possible": any(
            t.get("type") == "prop" and not t.get("actually_used")
            for t in triggers
        )
    }


def analyze_hook_dependencies(component_name: str, hook_index: Optional[int] = None) -> dict:
    """
    Analyzes hook dependency arrays for stability issues.

    Args:
        component_name: Component containing the hooks
        hook_index: Specific hook index to analyze (optional)

    Returns:
        Dependency analysis including stability and missing deps
    """
    component = ctx.get_component(component_name)
    if not component:
        return {"error": f"Component '{component_name}' not found"}

    hooks = component.get("hooks", [])
    if hook_index is not None:
        if hook_index >= len(hooks):
            return {"error": f"Hook index {hook_index} out of range"}
        hooks = [hooks[hook_index]]

    # Filter to hooks with dependency arrays
    dep_hooks = ["useEffect", "useLayoutEffect", "useMemo", "useCallback"]

    results = []
    for i, hook in enumerate(hooks):
        if hook.get("type") not in dep_hooks:
            continue

        deps = hook.get("dependencies")
        body_refs = hook.get("bodyReferences", [])

        analysis = {
            "hook_type": hook.get("type"),
            "line": hook.get("line"),
            "index": i,
            "dependencies": deps,
            "body_references": body_refs,
            "issues": []
        }

        if deps is None:
            # No dependency array - runs every render
            analysis["issues"].append({
                "type": "missing_dependency_array",
                "severity": "warning",
                "message": "Hook has no dependency array, will run every render"
            })
        elif deps == []:
            # Empty array - runs once
            if body_refs:
                analysis["issues"].append({
                    "type": "stale_closure_risk",
                    "severity": "critical",
                    "message": f"Empty deps but references: {body_refs}. May have stale values.",
                    "referenced_variables": body_refs
                })
        else:
            # Check stability of each dep
            for dep in deps:
                if not dep.get("isStable"):
                    analysis["issues"].append({
                        "type": "unstable_dependency",
                        "severity": "warning",
                        "dependency": dep.get("name"),
                        "reason": dep.get("stabilityReason"),
                        "message": f"'{dep.get('name')}' recreates every render, causing hook to re-run"
                    })

            # Check for missing deps
            declared_names = {d.get("name") for d in deps}
            for ref in body_refs:
                if ref not in declared_names:
                    # Could be a missing dep (simplified check)
                    analysis["issues"].append({
                        "type": "potentially_missing_dependency",
                        "severity": "info",
                        "variable": ref,
                        "message": f"'{ref}' is used but not in dependencies"
                    })

        analysis["has_issues"] = len(analysis["issues"]) > 0
        results.append(analysis)

    return {
        "component": component_name,
        "hooks_analyzed": len(results),
        "hooks": results,
        "total_issues": sum(len(h["issues"]) for h in results)
    }


def analyze_state_relationships(component_name: str) -> dict:
    """
    Identifies relationships between state variables.

    Args:
        component_name: Component to analyze

    Returns:
        State relationships and consolidation opportunities
    """
    component = ctx.get_component(component_name)
    if not component:
        return {"error": f"Component '{component_name}' not found"}

    state_vars = component.get("state", [])
    relationships = []

    # This would need more sophisticated analysis in the parser
    # For now, return basic structure

    return {
        "component": component_name,
        "state_count": len(state_vars),
        "state_variables": [
            {
                "name": s.get("name"),
                "setter": s.get("setter"),
                "type": s.get("type"),
                "usage_count": len(s.get("usageLocations", []))
            }
            for s in state_vars
        ],
        "relationships": relationships,
        "suggestions": []
    }


def analyze_jsx_expressions(component_name: str) -> dict:
    """
    Analyzes inline expressions in JSX for render performance issues.

    Args:
        component_name: Component to analyze

    Returns:
        JSX expressions that may cause unnecessary re-renders
    """
    component = ctx.get_component(component_name)
    if not component:
        return {"error": f"Component '{component_name}' not found"}

    expressions = component.get("jsxExpressions", [])

    issues = []
    for expr in expressions:
        severity = "low"

        # High severity if passed to memoized component
        if expr.get("isComponentMemoized"):
            severity = "high"
        # Medium if it's a function (could affect child hooks)
        elif expr.get("type") == "inline_function":
            severity = "medium"

        issues.append({
            "type": expr.get("type"),
            "line": expr.get("line"),
            "prop_name": expr.get("propName"),
            "passed_to": expr.get("passedToComponent"),
            "child_memoized": expr.get("isComponentMemoized"),
            "severity": severity,
            "captured_variables": expr.get("capturedVariables", []),
            "source_preview": expr.get("sourceText", "")[:80]
        })

    return {
        "component": component_name,
        "issues": issues,
        "total_issues": len(issues),
        "high_severity_count": len([i for i in issues if i["severity"] == "high"]),
        "medium_severity_count": len([i for i in issues if i["severity"] == "medium"])
    }
