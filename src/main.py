"""
AI Code Reviewer - Entry Point

Autonomous GitHub PR code review agent powered by Groq LLM.
Supports multiple programming languages with language-specific static analysis.
"""

import os
import sys
import io

# Set UTF-8 encoding for Windows console to support emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

from github_client import GitHubClient
from reviewer import CodeReviewer
from parser import DiffParser, build_review_payload
from commenter import PRCommenter


def main():
    """Main entry point for the AI code reviewer."""

    # =========================================================================
    # STEP 1: Load and validate environment variables
    # =========================================================================
    load_dotenv()

    required_vars = {
        "GROQ_API_KEY": "Groq API key for LLM inference",
        "GITHUB_TOKEN": "GitHub personal access token for API access",
        "GITHUB_REPO": "Repository in format 'owner/repo'",
        "PR_NUMBER": "Pull request number to review",
    }

    missing_vars = []
    for var, description in required_vars.items():
        value = os.getenv(var)
        if not value:
            missing_vars.append(f"{var} ({description})")

    if missing_vars:
        print("=" * 60)
        print("ERROR: Missing required environment variables")
        print("=" * 60)
        print("The following environment variables must be set:")
        print()
        for var_info in missing_vars:
            print(f"  - {var_info}")
        print()
        print("Set these in your .env file or as shell environment variables.")
        print("=" * 60)
        sys.exit(1)

    # Load validated environment variables
    github_token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")
    pr_number = int(os.getenv("PR_NUMBER"))
    groq_api_key = os.getenv("GROQ_API_KEY")

    # =========================================================================
    # STEP 2: Initialize components
    # =========================================================================
    print("=" * 60)
    print(f"Starting AI Code Review for PR #{pr_number} on {repo}")
    print("=" * 60)

    try:
        print("\n[1/8] Initializing components...")
        github_client = GitHubClient(github_token, repo)
        diff_parser = DiffParser()
        reviewer = CodeReviewer()
        commenter = PRCommenter(github_client)
        print("      Components initialized successfully")

        # =========================================================================
        # STEP 3: Fetch PR data
        # =========================================================================
        print("\n[2/8] Fetching PR data from GitHub...")

        pr_info = github_client.get_pr_info(pr_number)
        if pr_info is None:
            print(f"ERROR: Failed to fetch PR #{pr_number} info")
            print("Check that the PR exists and your GITHUB_TOKEN has read access")
            sys.exit(1)

        print(f"      PR Title: {pr_info.get('title', 'Untitled')}")
        print(f"      Base Branch: {pr_info.get('base_branch', 'unknown')}")

        files = github_client.get_pr_files(pr_number)
        if files is None:
            print(f"ERROR: Failed to fetch files for PR #{pr_number}")
            sys.exit(1)

        print(f"      Files Changed: {len(files)}")

        commit_sha = github_client.get_pr_commits(pr_number)
        if commit_sha is None:
            print(f"ERROR: Failed to fetch commits for PR #{pr_number}")
            sys.exit(1)

        print(f"      Latest Commit: {commit_sha[:8]}...")

        # =========================================================================
        # STEP 4: Parse files and run static analysis
        # =========================================================================
        print("\n[3/8] Parsing files and running static analysis...")
        print("      (Multi-language: Python, JS/TS, Java, Go, Ruby, C++)")

        files_with_analysis = build_review_payload(files, run_static_analysis=True)

        if not files_with_analysis:
            print("      No parseable files found (may be binary files only)")
            print("\n" + "=" * 60)
            print("Review complete. 0 files reviewed, 0 issues found")
            print("=" * 60)
            sys.exit(0)

        print(f"\n      Files to review ({len(files_with_analysis)}):")
        for file_data in files_with_analysis:
            filename = file_data.get("filename", "unknown")
            language = file_data.get("language", "Unknown")
            has_warnings = len(file_data.get("lint_warnings", [])) > 0
            warning_note = f" ({len(file_data.get('lint_warnings', []))} static warnings)" if has_warnings else ""
            print(f"        - {filename} [{language}]{warning_note}")

        # =========================================================================
        # STEP 5: Run LLM review on all files
        # =========================================================================
        print("\n[4/8] Running AI code review with Groq LLM...")

        all_results = reviewer.review_pr(files_with_analysis)

        if not all_results:
            print("      No files were reviewed")
            print("\n" + "=" * 60)
            print("Review complete. 0 files reviewed, 0 issues found")
            print("=" * 60)
            sys.exit(0)

        # =========================================================================
        # STEP 6: Generate PR summary
        # =========================================================================
        print("\n[5/8] Generating overall PR summary...")

        summary_text = reviewer.generate_pr_summary(all_results, pr_info)

        # =========================================================================
        # STEP 7: Prepare results for posting
        # =========================================================================
        print("\n[6/8] Preparing review results for GitHub...")

        # Transform reviewer results into commenter format
        review_results = []
        total_issues = 0
        critical_count = 0
        warning_count = 0
        info_count = 0

        for result in all_results:
            filename = result.get("filename", "unknown")
            language = result.get("language", "Unknown")
            review = result.get("review", {})
            issues = review.get("issues", [])
            file_summary = review.get("summary", "")
            score = review.get("score", 5)

            # Count by severity
            for issue in issues:
                severity = issue.get("severity", "info")
                total_issues += 1
                if severity == "critical":
                    critical_count += 1
                elif severity == "warning":
                    warning_count += 1
                else:
                    info_count += 1

            review_results.append({
                "filename": filename,
                "language": language,
                "issues": issues,
                "summary": file_summary,
                "score": score,
            })

        print(f"      Total issues found: {total_issues}")
        print(f"        - Critical: {critical_count}")
        print(f"        - Warnings: {warning_count}")
        print(f"        - Info: {info_count}")

        # =========================================================================
        # STEP 8: Post review to GitHub
        # =========================================================================
        print("\n[7/8] Posting review to GitHub PR...")

        report = commenter.post_full_review(
            pr_number=pr_number,
            commit_sha=commit_sha,
            all_results=review_results,
            summary_text=summary_text,
        )

        if report.get("review_submitted"):
            print(f"      Review submitted with {report.get('inline_comments_posted', 0)} inline comments")
        else:
            print("      WARNING: Review submission failed (check GITHUB_TOKEN permissions)")

        if report.get("summary_posted"):
            print("      Summary comment posted")
        else:
            print("      WARNING: Summary submission failed (check GITHUB_TOKEN permissions)")

        if not report.get("summary_posted") or not report.get("review_submitted"):
            print("\n" + "=" * 60)
            print("GENERATED PR SUMMARY & REVIEW FINDINGS (LOCAL OUTPUT)")
            print("=" * 60)
            print(summary_text)
            print("\n" + "-" * 60)
            print("DETAILED INLINE ISSUES DETECTED:")
            print("-" * 60)
            for res in review_results:
                fname = res.get("filename")
                for issue in res.get("issues", []):
                    line = issue.get("line")
                    sev = issue.get("severity", "info").upper()
                    msg = issue.get("message")
                    sug = issue.get("suggestion", "")
                    print(f"\n  [{sev}] {fname}:{line}")
                    print(f"    Message:    {msg}")
                    if sug:
                        print(f"    Suggestion: {sug}")
            print("=" * 60)

        # =========================================================================
        # STEP 9: Final report and exit code
        # =========================================================================
        print("\n" + "=" * 60)
        print("REVIEW COMPLETE")
        print("=" * 60)
        print(f"Files Reviewed:     {report.get('total_files_reviewed', 0)}")
        print(f"Total Issues:       {total_issues}")
        print(f"  - Critical:       {critical_count}")
        print(f"  - Warnings:       {warning_count}")
        print(f"  - Info:           {info_count}")
        print(f"Review Action:      {report.get('review_action', 'UNKNOWN')}")
        print("=" * 60)

        # Exit with code 1 if critical issues found (fails CI check)
        if critical_count > 0:
            print(f"\nExiting with code 1 due to {critical_count} critical issue(s)")
            sys.exit(1)
        else:
            print("\nExiting with code 0 (no critical issues)")
            sys.exit(0)

    except SystemExit:
        raise
    except Exception as e:
        print("\n" + "=" * 60)
        print("FATAL ERROR")
        print("=" * 60)
        print(f"An unexpected error occurred: {type(e).__name__}")
        print(f"Details: {str(e)}")
        print()
        print("Check the following:")
        print("  - GROQ_API_KEY is valid and has quota remaining")
        print("  - GITHUB_TOKEN has appropriate permissions")
        print("  - Network connectivity to GitHub and Groq APIs")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
