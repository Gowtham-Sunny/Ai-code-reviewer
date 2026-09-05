"""
PR Commenter - Posts review results to GitHub PRs with inline and summary comments.
"""

import time
from typing import Dict, List, Any, Tuple
from github_client import GitHubClient


class PRCommenter:
    """Handles posting code review results on GitHub pull requests."""

    # Severity indicators
    SEVERITY_ICONS = {
        "critical": "❌",
        "warning": "⚠️",
        "info": "ℹ️",
    }

    # Issue type badges
    TYPE_BADGES = {
        "bug": "bug",
        "security": "security",
        "performance": "performance",
        "style": "style",
        "maintainability": "maintainability",
        "best-practice": "best-practice",
    }

    def __init__(self, github_client: GitHubClient):
        """
        Initialize the PR commenter.

        Args:
            github_client: GitHubClient instance
        """
        self.github_client = github_client

    def format_comment(self, issue: Dict[str, Any]) -> str:
        """
        Format a single issue dict into a clean GitHub comment string.

        Args:
            issue: Dict with keys: severity, type, message, suggestion

        Returns:
            Formatted comment string
        """
        severity = issue.get("severity", "info").lower()
        issue_type = issue.get("type", "issue").lower()
        message = issue.get("message", "")
        suggestion = issue.get("suggestion", "")

        # Get icon for severity
        icon = self.SEVERITY_ICONS.get(severity, "ℹ️")

        # Get badge for issue type
        badge = self.TYPE_BADGES.get(issue_type, issue_type)

        # Build the comment
        lines = [
            f"{icon} **[{severity.upper()}] {issue_type.replace('-', ' ').title()}**",
            "",
            message,
        ]

        if suggestion:
            lines.append("")
            lines.append(f"> Suggestion: {suggestion}")

        return "\n".join(lines)

    def build_review_batch(
        self, all_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Convert all review results into GitHub review API format.

        Args:
            all_results: List of {filename, issues, summary, score} dicts

        Returns:
            List of {path, line, body} dicts for GitHub API
        """
        batch = []

        for result in all_results:
            filename = result.get("filename", "")
            issues = result.get("issues", [])

            for issue in issues:
                line = issue.get("line")

                # Skip issues without valid line numbers
                if line is None or line <= 0:
                    continue

                comment_body = self.format_comment(issue)

                batch.append({
                    "path": filename,
                    "line": line,
                    "body": comment_body,
                })

        return batch

    def post_inline_comments(
        self,
        pr_number: int,
        commit_sha: str,
        filename: str,
        issues: List[Dict[str, Any]],
        line_map: Dict[int, int] = None,
    ) -> int:
        """
        Post inline comments for issues on specific lines.

        Args:
            pr_number: The pull request number
            commit_sha: The commit SHA to comment on
            filename: The file path
            issues: List of issue dicts with line numbers
            line_map: Optional mapping of diff line to actual file line

        Returns:
            Number of comments successfully posted
        """
        posted_count = 0

        for issue in issues:
            line = issue.get("line")

            # Skip if line number is invalid
            if line is None or line <= 0:
                continue

            # Apply line mapping if provided
            if line_map and line in line_map:
                actual_line = line_map[line]
            else:
                actual_line = line

            # Skip if mapped line is still invalid
            if actual_line <= 0:
                continue

            comment_body = self.format_comment(issue)

            try:
                result = self.github_client.post_review_comment(
                    pr_number=pr_number,
                    commit_sha=commit_sha,
                    path=filename,
                    line=actual_line,
                    body=comment_body,
                )

                if result:
                    posted_count += 1
            except Exception as e:
                print(f"Failed to post inline comment on {filename}:{actual_line}: {e}")

            # Rate limiting delay
            time.sleep(0.5)

        return posted_count

    def post_full_review(
        self,
        pr_number: int,
        commit_sha: str,
        all_results: List[Dict[str, Any]],
        summary_text: str,
    ) -> Dict[str, Any]:
        """
        Post a complete code review with inline comments and summary.

        Args:
            pr_number: The pull request number
            commit_sha: The commit SHA for the review
            all_results: List of {filename, issues, summary, score} dicts
            summary_text: Overall review summary markdown

        Returns:
            Report dict with totals and breakdown
        """
        # Collect statistics
        total_files = len(all_results)
        total_issues = 0
        severity_breakdown = {"critical": 0, "warning": 0, "info": 0}
        has_critical = False

        for result in all_results:
            issues = result.get("issues", [])
            total_issues += len(issues)

            for issue in issues:
                severity = issue.get("severity", "info").lower()
                if severity in severity_breakdown:
                    severity_breakdown[severity] += 1
                if severity == "critical":
                    has_critical = True

        # Determine review action
        # Note: GitHub blocks REQUEST_CHANGES on your own PR, so we use COMMENT
        # and indicate severity in the summary instead
        action = "COMMENT"

        # Build the batch of inline comments
        inline_batch = self.build_review_batch(all_results)

        # Submit the review with inline comments
        review_result = None
        if inline_batch:
            try:
                review_result = self.github_client.create_review(
                    pr_number=pr_number,
                    commit_sha=commit_sha,
                    comments=inline_batch,
                    action=action,
                )
                if review_result:
                    print(f"Review submitted with {len(inline_batch)} inline comments")
                else:
                    # Fallback to individual inline comments if batch posting failed (e.g. 422 unresolvable line)
                    print("      Batch review failed; falling back to individual inline comment posting...")
                    posted_count = 0
                    for res in all_results:
                        fname = res.get("filename", "")
                        issues = res.get("issues", [])
                        if fname and issues:
                            posted_count += self.post_inline_comments(
                                pr_number=pr_number,
                                commit_sha=commit_sha,
                                filename=fname,
                                issues=issues,
                            )
                    print(f"      Fallback inline comments posted: {posted_count}")
                    review_result = {"posted_count": posted_count}
            except Exception as e:
                print(f"Failed to create review: {e}")
                review_result = None

        # Post the summary comment
        summary_result = None
        try:
            summary_result = self.github_client.post_pr_summary(
                pr_number=pr_number,
                body=summary_text,
            )
            if summary_result:
                print(f"Summary comment posted")
        except Exception as e:
            print(f"Failed to post summary: {e}")
            summary_result = None

        # Build the report
        report = {
            "total_files_reviewed": total_files,
            "total_issues_found": total_issues,
            "severity_breakdown": severity_breakdown,
            "inline_comments_posted": len(inline_batch),
            "review_action": action,
            "review_submitted": review_result is not None,
            "summary_posted": summary_result is not None,
        }

        return report
