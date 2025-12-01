import subprocess
import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel


class ParseResult(BaseModel):
    success: bool
    components: list
    imports: list
    exports: list
    errors: list
    metadata: dict


def parse_react_code(
    code: str,
    filename: str = "component.tsx",
    parser_path: Optional[Path] = None
) -> ParseResult:
    """
    Call the Node.js AST parser and return structured data.

    Args:
        code: React/TypeScript source code
        filename: Virtual filename for the parser
        parser_path: Path to the parser CLI (defaults to ../parser/dist/cli.js)

    Returns:
        ParseResult with component information
    """
    if parser_path is None:
        parser_path = Path(__file__).parent.parent / "parser" / "dist" / "cli.js"

    try:
        result = subprocess.run(
            ["node", str(parser_path)],
            input=code,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            error_msg = result.stderr or "Parser exited with non-zero code"
            return ParseResult(
                success=False,
                components=[],
                imports=[],
                exports=[],
                errors=[{"message": error_msg}],
                metadata={}
            )

        # Check if stdout is empty
        if not result.stdout or result.stdout.strip() == "":
            return ParseResult(
                success=False,
                components=[],
                imports=[],
                exports=[],
                errors=[{"message": "Parser returned empty output"}],
                metadata={}
            )

        # Try to parse JSON
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            return ParseResult(
                success=False,
                components=[],
                imports=[],
                exports=[],
                errors=[{
                    "message": f"Invalid JSON from parser: {str(e)}",
                    "output_preview": result.stdout[:200]
                }],
                metadata={}
            )

        return ParseResult(**data)
    
    except subprocess.TimeoutExpired:
        return ParseResult(
            success=False,
            components=[],
            imports=[],
            exports=[],
            errors=[{"message": "Parser timeout (file may be too large or complex)"}],
            metadata={}
        )
    except Exception as e:
        return ParseResult(
            success=False,
            components=[],
            imports=[],
            exports=[],
            errors=[{"message": f"Parser error: {str(e)}"}],
            metadata={}
        )


# Singleton to hold parsed AST data for tool access
class AstContext:
    _instance = None
    _data: Optional[ParseResult] = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_data(self, data: ParseResult):
        self._data = data

    def get_data(self) -> Optional[ParseResult]:
        return self._data

    def get_component(self, name: str) -> Optional[dict]:
        if not self._data:
            return None
        for comp in self._data.components:
            if comp.get("name") == name:
                return comp
        return None

    def get_all_component_names(self) -> list[str]:
        if not self._data:
            return []
        return [c.get("name") for c in self._data.components]
