"""
Code Reviewer - Uses Groq API to analyze code changes.
Supports multiple programming languages with language-specific review rules.
"""

import os
import re
import json
from typing import Dict, List, Any, Optional
from groq import Groq


class CodeReviewer:
    """Code reviewer powered by Groq API."""

    def __init__(self):
        """Initialize the code reviewer with Groq client."""
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable is required")
        self.client = Groq(api_key=api_key)
        self.model = "qwen/qwen3-32b"

    def _detect_language(self, filename: str) -> str:
        """
        Detect programming language from file extension.

        Args:
            filename: Name of the file

        Returns:
            Language name string
        """
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
        return ext_map.get(ext, "Unknown")

    def _clean_json(self, text: str) -> str:
        """
        Strip markdown code fences from LLM output.

        Args:
            text: Raw text that may contain markdown fences

        Returns:
            Cleaned JSON string
        """
        # Remove ```json ... ``` fences
        text = re.sub(r"```json\s*", "", text, flags=re.IGNORECASE)
        # Remove generic ``` ... ``` fences
        text = re.sub(r"```\s*", "", text)
        # Remove ```code ... ``` fences
        text = re.sub(r"```code\s*", "", text, flags=re.IGNORECASE)
        # Strip whitespace
        return text.strip()

    def review_file(self, file_diff_obj: Dict[str, Any]) -> Dict[str, Any]:
        """
        Review a single file diff using Groq.

        Args:
            file_diff_obj: Parsed file diff from parser.py containing:
                - filename: str
                - language: str (optional, will auto-detect if missing)
                - patch: str
                - status: str (optional)
                - lint_warnings: List[str] (optional)

        Returns:
            Dict with issues, summary, and score. On error returns:
            {"issues": [], "summary": "Review failed", "score": 5}
        """
        filename = file_diff_obj.get("filename", "unknown")
        patch = file_diff_obj.get("patch", "")
        status = file_diff_obj.get("status", "modified")
        lint_warnings = file_diff_obj.get("lint_warnings", [])

        # Use provided language or auto-detect
        language = file_diff_obj.get("language")
        if not language or language == "Unknown":
            language = self._detect_language(filename)

        # Build static analysis section if warnings exist
        static_analysis_section = ""
        if lint_warnings:
            static_analysis_section = "\n\n### Static Analysis Warnings\n"
            for warning in lint_warnings:
                static_analysis_section += f"- {warning}\n"

        system_prompt = """You are an expert code reviewer with deep knowledge across all major programming languages. Analyze the provided code diff and identify issues. You must respond ONLY with a valid JSON object, no markdown fences, no explanation outside the JSON.

Return this exact structure:
{
  "issues": [
    {
      "line": <integer>,
      "severity": "<critical|warning|info>",
      "type": "<bug|security|performance|style|logic|test-coverage>",
      "message": "<short description>",
      "suggestion": "<concrete fix>"
    }
  ],
  "summary": "<2-3 sentence overall assessment>",
  "score": <integer 1-10>
}

For ALL languages check: hardcoded secrets, logic errors, security vulnerabilities, null/nil safety.

Language-specific checks:
- Python: PEP8 compliance, type hints, proper exception handling
- JavaScript/TypeScript: var usage, async/await errors, undefined checks
- Go: error handling, goroutine leaks, defer usage
- SQL: injection vulnerabilities, N+1 query patterns
- Shell: unquoted variables, set -e usage
- Java: null checks, resource leaks, exception handling
- Ruby: nil safety, proper block usage
- C/C++: memory leaks, buffer overflows, pointer safety
- Rust: ownership issues, unwrap usage
- PHP: SQL injection, XSS, proper escaping
- Kotlin/Swift: null safety, optionals handling
- C#: null reference, async/await, IDisposable
- Dart: null safety, async patterns
- HTML/CSS: accessibility, semantic markup
- YAML: syntax errors, indentation

Pay special attention to any Static Analysis Warnings listed above."""

        user_message = f"""## File: {filename}
## Language: {language}
## Status: {status}

## Code Diff:
{patch}
{static_analysis_section}

Review the code changes above and identify all issues."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.1,
                max_tokens=2000,
            )

            response_text = response.choices[0].message.content

            # Clean and parse JSON
            cleaned_text = self._clean_json(response_text)
            review_result = json.loads(cleaned_text)

            # Validate required fields
            if "issues" not in review_result:
                review_result["issues"] = []
            if "summary" not in review_result:
                review_result["summary"] = "Review failed"
            if "score" not in review_result:
                review_result["score"] = 5

            return review_result

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"Error parsing Groq response: {e}")
            return {"issues": [], "summary": "Review failed", "score": 5}
        except Exception as e:
            print(f"Error during review: {e}")
            return {"issues": [], "summary": "Review failed", "score": 5}

    def review_pr(
        self, parsed_files: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Review all files in a parsed PR.

        Args:
            parsed_files: List of parsed file diffs from parser.py

        Returns:
            List of results, each containing:
            - filename: str
            - language: str
            - review: Dict with issues, summary, score
        """
        results = []

        for file_diff in parsed_files:
            # Skip files with no patch (binary files, etc.)
            if not file_diff.get("patch"):
                print(f"  Skipping {file_diff.get('filename', 'unknown')}: no patch")
                continue

            filename = file_diff.get("filename", "unknown")
            language = file_diff.get("language", "Unknown")

            # Auto-detect language if not set
            if not language or language == "Unknown":
                language = self._detect_language(filename)

            review_result = self.review_file(file_diff)

            # Merge any static analysis warnings as info issues
            lint_warnings = file_diff.get("lint_warnings", [])
            if lint_warnings:
                review_result = self.merge_static_analysis(
                    review_result, lint_warnings, filename
                )

            issue_count = len(review_result.get("issues", []))
            score = review_result.get("score", 5)

            print(f"  {filename} ({language}): {issue_count} issues, score={score}")

            results.append({
                "filename": filename,
                "language": language,
                "review": review_result
            })

        return results

    def generate_pr_summary(
        self,
        all_results: List[Dict[str, Any]],
        pr_info: Dict[str, Any]
    ) -> str:
        """
        Generate an overall PR summary using Groq.

        Args:
            all_results: List of file review results from review_pr()
            pr_info: PR metadata (title, description, etc.)

        Returns:
            Markdown-formatted PR summary (max 300 words) with:
            - Overall Quality Score
            - Critical Issues (bullet list)
            - Warnings (bullet list)
            - Final Recommendation: ✅ Approve | 🔄 Request Changes | 💬 Needs Discussion
        """
        pr_title = pr_info.get("title", "Untitled PR")
        pr_description = pr_info.get("body", "No description provided")

        # Build compact file results summary
        files_summary = []
        total_critical = 0
        total_warnings = 0

        for result in all_results:
            filename = result.get("filename", "unknown")
            language = result.get("language", "Unknown")
            review = result.get("review", {})
            issues = review.get("issues", [])
            score = review.get("score", 5)
            summary = review.get("summary", "")

            critical_count = sum(
                1 for i in issues if i.get("severity") == "critical"
            )
            warning_count = sum(
                1 for i in issues if i.get("severity") == "warning"
            )

            total_critical += critical_count
            total_warnings += warning_count

            files_summary.append(
                f"- {filename} ({language}): score={score}/10, "
                f"critical={critical_count}, warnings={warning_count} | {summary}"
            )

        files_text = "\n".join(files_summary) if files_summary else "No files reviewed."

        system_prompt = """You are an expert code reviewer. Generate a concise PR summary in markdown format.

Return ONLY valid markdown, no code blocks around it. Keep it under 300 words.

Structure your response as:
# PR Review Summary

## Overall Quality Score: X/10

## Critical Issues
- List critical issues here (or "None" if no critical issues)

## Warnings
- List warnings here (or "None" if no warnings)

## Final Recommendation
Choose exactly ONE of:
- ✅ Approve
- 🔄 Request Changes
- 💬 Needs Discussion

Base recommendation on: critical issues = Request Changes, only warnings = Needs Discussion, clean = Approve."""

        user_message = f"""## PR: {pr_title}

## Description:
{pr_description}

## File Reviews:
{files_text}

## Totals:
- Critical Issues: {total_critical}
- Total Warnings: {total_warnings}

Generate a concise overall PR summary (max 300 words)."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.2,
                max_tokens=600,
            )

            return response.choices[0].message.content

        except Exception as e:
            print(f"Error generating PR summary: {e}")
            return f"## PR Summary Generation Failed\n\nError: {str(e)}"

    def merge_static_analysis(
        self,
        review_result: Dict[str, Any],
        static_warnings: List[str],
        filename: str = ""
    ) -> Dict[str, Any]:
        """
        Append static analysis warnings as info-severity issues.

        Args:
            review_result: Review result from review_file()
            static_warnings: List of static analysis warning strings
                           Format: "filename:line:message" or just "message"
            filename: Current filename being reviewed

        Returns:
            Updated review result with warnings added as info issues
        """
        if not static_warnings:
            return review_result

        issues = review_result.get("issues", [])

        for warning in static_warnings:
            # Try to parse "filename:line:message" format
            line_number = 1
            message = warning

            # Pattern: something like "path/to/file.py:42:warning message"
            match = re.match(r"^([^:]+):(\d+):(.+)$", warning)
            if match:
                parsed_filename = match.group(1)
                try:
                    line_number = int(match.group(2))
                except ValueError:
                    line_number = 1
                message = match.group(3)
            else:
                # Try simpler "line:message" format
                match = re.match(r"^(\d+):(.+)$", warning)
                if match:
                    try:
                        line_number = int(match.group(1))
                    except ValueError:
                        line_number = 1
                    message = match.group(2)

            issues.append({
                "line": line_number,
                "severity": "info",
                "type": "static_analysis",
                "message": message,
                "suggestion": "Review and fix the static analysis warning above"
            })

        review_result["issues"] = issues
        return review_result
