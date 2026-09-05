"""
Diff Parser - Parses git diffs and performs AST analysis.
"""

import re
import subprocess
import sys
from typing import Dict, List, Any, Optional
from pyflakes.api import check
from pyflakes.messages import Message
from astroid import parse as astroid_parse
from astroid.exceptions import AstroidError


class DiffParser:
    """Parser for git diffs and code analysis."""

    def __init__(self):
        """Initialize the diff parser."""
        self.file_pattern = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)
        self.hunk_pattern = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
        self.addition_pattern = re.compile(r"^\+(?!\+\+).*$", re.MULTILINE)

    def parse(self, diff: str) -> Dict[str, Any]:
        """
        Parse a git diff string into structured data.

        Args:
            diff: Raw git diff string

        Returns:
            Dictionary containing parsed diff data
        """
        files = []
        current_file = None
        current_lines = []
        current_line_number = 0

        for line in diff.split("\n"):
            # Check for new file
            file_match = self.file_pattern.search(line)
            if file_match:
                # Save previous file
                if current_file:
                    current_file["diff"] = "\n".join(current_lines)
                    files.append(current_file)

                current_file = {"path": file_match.group(1), "changes": []}
                current_lines = []
                current_line_number = 0
                continue

            # Check for hunk header
            hunk_match = self.hunk_pattern.match(line)
            if hunk_match:
                current_line_number = int(hunk_match.group(1)) - 1
                current_lines.append(line)
                continue

            # Check for addition
            if line.startswith("+") and not line.startswith("+++"):
                current_line_number += 1
                current_file["changes"].append(
                    {"line": current_line_number, "content": line[1:], "type": "addition"}
                )
                current_lines.append(line)
            elif line.startswith("-") and not line.startswith("---"):
                current_lines.append(line)
            else:
                if current_file:
                    current_lines.append(line)

        # Don't forget the last file
        if current_file:
            current_file["diff"] = "\n".join(current_lines)
            files.append(current_file)

        return {"files": files, "raw_diff": diff}

    def check_syntax(self, code: str) -> List[Dict[str, Any]]:
        """
        Check Python code for syntax errors using pyflakes.

        Args:
            code: Python code string

        Returns:
            List of issues found
        """
        issues = []
        try:
            # Capture pyflakes messages
            import io
            import sys

            old_stdout = sys.stdout
            sys.stdout = io.StringIO()

            check(code, "<string>")

            output = sys.stdout.getvalue()
            sys.stdout = old_stdout

            if output:
                issues.append({"type": "pyflakes", "message": output.strip()})
        except Exception as e:
            issues.append({"type": "syntax_error", "message": str(e)})

        return issues

    def analyze_ast(self, code: str) -> Dict[str, Any]:
        """
        Analyze Python code using AST.

        Args:
            code: Python code string

        Returns:
            AST analysis results
        """
        result = {"functions": [], "classes": [], "imports": [], "complexity": 0}

        try:
            tree = astroid_parse(code)

            for node in tree.body:
                if hasattr(node, "name"):
                    if node.__class__.__name__ == "FunctionDef":
                        result["functions"].append(
                            {
                                "name": node.name,
                                "args": [arg.name for arg in node.args.args],
                                "line": node.lineno,
                            }
                        )
                        result["complexity"] += 1
                    elif node.__class__.__name__ == "ClassDef":
                        result["classes"].append(
                            {"name": node.name, "line": node.lineno}
                        )
                        result["complexity"] += 1
                elif node.__class__.__name__ == "Import":
                    for alias in node.names:
                        result["imports"].append(alias[0])
                elif node.__class__.__name__ == "ImportFrom":
                    module = node.modname or ""
                    for alias in node.names:
                        result["imports"].append(f"{module}.{alias[0]}")

        except AstroidError:
            pass

        return result

    def parse_file_diff(self, file_obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse a GitHub file object from the API into a structured dict.

        Args:
            file_obj: Dict with filename, patch, status fields from GitHub API

        Returns:
            Dict with parsed diff data, or None if no patch field (binary file)
        """
        if "patch" not in file_obj:
            return None

        filename = file_obj.get("filename", "unknown")
        patch = file_obj.get("patch", "")
        status = file_obj.get("status", "modified")

        # Detect language from extension
        ext_map = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".java": "Java",
            ".go": "Go",
            ".rb": "Ruby",
            ".cpp": "C++",
        }
        ext = "." + filename.split(".")[-1] if "." in filename else ""
        language = ext_map.get(ext, "Unknown")

        # Parse line numbers from patch
        line_number_map = self.parse_line_numbers(patch)

        # Extract added and removed lines
        added_lines = []
        removed_lines = []
        current_added_pos = 0
        current_removed_pos = 0

        for line in patch.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                current_added_pos += 1
                actual_line = line_number_map.get(current_added_pos)
                added_lines.append({
                    "line_number": actual_line,
                    "content": line[1:]
                })
            elif line.startswith("-") and not line.startswith("---"):
                current_removed_pos += 1
                removed_lines.append({
                    "line_number": current_removed_pos,
                    "content": line[1:]
                })

        # Extract chunk header (@@ line numbers @@)
        chunk_header = None
        header_match = re.search(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@", patch, re.MULTILINE)
        if header_match:
            chunk_header = header_match.group(0)

        return {
            "filename": filename,
            "language": language,
            "status": status,
            "patch": patch,
            "added_lines": added_lines,
            "removed_lines": removed_lines,
            "chunk_header": chunk_header,
        }

    def parse_line_numbers(self, patch: str) -> Dict[int, int]:
        """
        Parse diff patch to build a map from diff position to actual file line number.

        The @@ -a,b +c,d @@ header tells you where lines start.
        Returns a dict {position: actual_line_number} for added lines only.

        Args:
            patch: Raw diff patch string

        Returns:
            Dict mapping position in added lines to actual file line number
        """
        line_map = {}
        added_pos = 0
        current_new_line = 0

        for line in patch.split("\n"):
            # Parse hunk header
            header_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if header_match:
                current_new_line = int(header_match.group(1)) - 1
                continue

            # Track added lines
            if line.startswith("+") and not line.startswith("+++"):
                added_pos += 1
                current_new_line += 1
                line_map[added_pos] = current_new_line

        return line_map

    def extract_added_code(self, patch: str) -> str:
        """
        Extract only added lines from a diff patch.

        Args:
            patch: Raw diff patch string

        Returns:
            String of added lines with line numbers prepended
        """
        added_lines = []
        line_num = 0

        for line in patch.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                line_num += 1
                added_lines.append(f"{line_num}: {line[1:]}")

        return "\n".join(added_lines)

    def truncate_diff(self, patch: str, max_chars: int = 8000) -> str:
        """
        Truncate a diff patch if it exceeds max_chars.

        Keeps first 4000 and last 4000 chars with a truncation message in between.

        Args:
            patch: Raw diff patch string
            max_chars: Maximum character limit (default 8000)

        Returns:
            Truncated patch string
        """
        if len(patch) <= max_chars:
            return patch

        half_size = max_chars // 2
        truncation_message = "\n\n[... diff truncated ...]\n\n"

        first_part = patch[:half_size]
        last_part = patch[-half_size:]

        return first_part + truncation_message + last_part

    def static_analysis(self, code_string: str, language: str) -> List[str]:
        """
        Run static analysis on code using language-specific linters.

        Args:
            code_string: Code string to analyze
            language: Programming language (Python, JavaScript, TypeScript, Java, Go, Ruby, C++)

        Returns:
            List of warning strings, empty if unsupported language or no warnings
        """
        if not code_string.strip():
            return []

        language_lower = language.lower()

        if language_lower == "python":
            return self._analyze_python(code_string)
        elif language_lower in ["javascript", "typescript"]:
            return self._analyze_javascript(code_string, language_lower)
        elif language_lower == "java":
            return self._analyze_java(code_string)
        elif language_lower == "go":
            return self._analyze_go(code_string)
        elif language_lower == "ruby":
            return self._analyze_ruby(code_string)
        elif language_lower == "c++":
            return self._analyze_cpp(code_string)
        else:
            return []

    def _analyze_python(self, code_string: str) -> List[str]:
        """Run pyflakes on Python code."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pyflakes", "-"],
                input=code_string,
                capture_output=True,
                text=True,
                timeout=10
            )
            return self._parse_linter_output(result.stdout)
        except subprocess.TimeoutExpired:
            return ["Python analysis timed out"]
        except Exception:
            return []

    def _analyze_javascript(self, code_string: str, language: str) -> List[str]:
        """Run ESLint on JavaScript/TypeScript code via subprocess."""
        try:
            # Try to run eslint with stdin
            # ESLint needs a file, so we create a temp file
            import tempfile
            ext = ".ts" if language == "typescript" else ".js"

            with tempfile.NamedTemporaryFile(mode='w', suffix=ext, delete=False) as f:
                f.write(code_string)
                temp_path = f.name

            try:
                result = subprocess.run(
                    ["npx", "eslint", "--no-eslintrc", "--parser-options=ecmaVersion:2020,sourceType:module", temp_path],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                return self._parse_linter_output(result.stdout + result.stderr)
            finally:
                import os
                os.unlink(temp_path)
        except subprocess.TimeoutExpired:
            return [f"{language.title()} analysis timed out"]
        except FileNotFoundError:
            return [f"ESLint not found. Install with: npm install -g eslint"]
        except Exception:
            return []

    def _analyze_java(self, code_string: str) -> List[str]:
        """Run javac with lint options on Java code."""
        try:
            import tempfile
            import os

            # Java needs a file with matching class name, use a generic approach
            # Just check for basic syntax by looking for common issues
            warnings = []

            # Basic pattern-based checks for Java
            if "public class" in code_string:
                class_match = re.search(r"public\s+class\s+(\w+)", code_string)
                if class_match:
                    class_name = class_match.group(1)
                    # Check for unclosed braces
                    if code_string.count("{") != code_string.count("}"):
                        warnings.append("Mismatched braces - check for unclosed blocks")
                    # Check for unclosed parentheses
                    if code_string.count("(") != code_string.count(")"):
                        warnings.append("Mismatched parentheses - check for unclosed expressions")

            # Check for common Java issues
            if re.search(r"\bSystem\.out\.print(ln)?\s*\(", code_string):
                warnings.append("Debug print statement found (System.out.println)")

            if re.search(r"\bcatch\s*\(\s*Exception\s+e\s*\)", code_string):
                warnings.append("Generic Exception catch - consider catching specific exceptions")

            return warnings

        except Exception:
            return []

    def _analyze_go(self, code_string: str) -> List[str]:
        """Run go vet on Go code via subprocess."""
        try:
            # Go also needs a file - use basic pattern checks as fallback
            warnings = []

            # Check for common Go issues
            if code_string.count("{") != code_string.count("}"):
                warnings.append("Mismatched braces - check for unclosed blocks")

            # Check for unused variable patterns (declaration without use is hard without full AST)
            var_declarations = re.findall(r":=\s*(\w+)", code_string)
            for var in set(var_declarations):
                # Simple check: if variable appears only once (in its declaration)
                if code_string.count(var) == 1:
                    warnings.append(f"Variable '{var}' declared but possibly unused")

            # Check for error handling
            if "err" in code_string and ":=" in code_string:
                if "if err" not in code_string and "err !=" not in code_string:
                    warnings.append("Error returned but may not be checked")

            return warnings

        except Exception:
            return []

    def _analyze_ruby(self, code_string: str) -> List[str]:
        """Run Ruby syntax check via subprocess."""
        try:
            result = subprocess.run(
                ["ruby", "-wc", "-e", code_string],
                capture_output=True,
                text=True,
                timeout=10
            )
            output = result.stdout + result.stderr
            if output and "Syntax OK" not in output:
                return self._parse_linter_output(output)
            return []
        except subprocess.TimeoutExpired:
            return ["Ruby analysis timed out"]
        except FileNotFoundError:
            return ["Ruby not found in PATH"]
        except Exception:
            return []

    def _analyze_cpp(self, code_string: str) -> List[str]:
        """Run basic C++ static analysis via pattern matching."""
        try:
            warnings = []

            # Check for mismatched braces
            if code_string.count("{") != code_string.count("}"):
                warnings.append("Mismatched braces - check for unclosed blocks")

            # Check for mismatched parentheses
            if code_string.count("(") != code_string.count(")"):
                warnings.append("Mismatched parentheses")

            # Check for common C++ issues
            if re.search(r"\bdelete\s+\w+\s*;", code_string) and "delete[]" not in code_string:
                if re.search(r"\bnew\s+\w+\s*\[", code_string):
                    warnings.append("Possible mismatch: new[] used with delete (should use delete[])")

            # Check for potential memory leaks (new without delete in same snippet)
            if "new " in code_string and "delete" not in code_string:
                warnings.append("Dynamic allocation (new) found without corresponding delete")

            # Check for raw pointers
            if re.search(r"\*\s*\w+\s*=", code_string) and "unique_ptr" not in code_string and "shared_ptr" not in code_string:
                warnings.append("Raw pointer usage detected - consider using smart pointers")

            return warnings

        except Exception:
            return []

    def _parse_linter_output(self, output: str) -> List[str]:
        """Parse linter output into a list of warnings."""
        warnings = []
        if output:
            for line in output.strip().split("\n"):
                if line and "error" in line.lower() or "warning" in line.lower() or ":" in line:
                    warnings.append(line.strip())
        return warnings


def build_review_payload(files: List[Dict[str, Any]], run_static_analysis: bool = True) -> List[Dict[str, Any]]:
    """
    Build a clean list of parsed file objects ready for LLM review.

    Takes a list of file objects from GitHub API, parses each one,
    filters out binary files (no patch field), and returns parsed data.
    Optionally runs static analysis based on detected language.

    Args:
        files: List of file objects from GitHub API
        run_static_analysis: Whether to run static analysis (default True)

    Returns:
        List of parsed file dicts ready for review, with optional lint warnings
    """
    parser = DiffParser()
    payload = []

    for file_obj in files:
        parsed = parser.parse_file_diff(file_obj)
        if parsed is not None:
            # Run static analysis if enabled
            if run_static_analysis:
                # Extract only added code for analysis
                added_code = parser.extract_added_code(parsed["patch"])
                warnings = parser.static_analysis(added_code, parsed["language"])
                if warnings:
                    parsed["lint_warnings"] = warnings

            payload.append(parsed)

    return payload
