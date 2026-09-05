# Project: AI Code Review Agent
## Goal
Autonomous GitHub PR reviewer using Groq API — reads diffs, posts inline comments with bugs/security issues/suggestions.

## Current status
- [x] Phase 1: Project structure & setup
- [x] Phase 2: GitHub API client (github_client.py)
- [x] Phase 3: Diff parser & static analysis (parser.py)
- [x] Phase 4: Groq LLM reviewer (reviewer.py)
- [x] Phase 4B: Comment poster (commenter.py)
- [x] Phase 5: Main entry point (main.py)
- [x] Phase 6: GitHub Actions & Dockerfile
- [x] Phase 7: DiffParser enhancements (parser.py extended)
- [x] Phase 8: Multi-language static analysis support
- [x] Phase 9: Core module rewrites (commenter.py, main.py)
- [ ] Phase 10: Local test script (test_local.py)
- [ ] Phase 11: Final polish & retry logic

## Files created so far
- src/main.py - Entry point with multi-language orchestration, env validation, 8-step review flow, exit codes (rewritten this session)
- src/github_client.py - GitHub REST API client with 8 methods (full error handling, returns None on non-200)
- src/parser.py - DiffParser class with parse_file_diff, parse_line_numbers, extract_added_code, truncate_diff, static_analysis methods; build_review_payload helper (multi-language: Python, JS/TS, Java, Go, Ruby, C++)
- src/reviewer.py - Groq-powered code reviewer with review_file, review_pr, generate_pr_summary, merge_static_analysis methods; language-aware prompts
- src/commenter.py - PRCommenter class with format_comment, build_review_batch, post_inline_comments, post_full_review; severity icons, rate limiting, batch review submission (rewritten this session)
- src/test.py - Test file (placeholder, Phase 10 pending)
- .github/workflows/review.yml - GitHub Actions workflow triggered on PR open/update
- Dockerfile - Container build for CI/CD deployment
- requirements.txt - Python dependencies (groq, requests, python-dotenv, pyflakes, astroid) + eslint note
- .env.example - Environment variable template
- .gitignore - Protects sensitive files (.env, __pycache__, etc.)
- CONTEXT.md - Project state documentation (carries context between sessions)

## Key decisions made
- Language: Python 3.11
- LLM: Groq API (qwen/qwen3-32b model)
- GitHub integration: REST API via requests library
- Output format: Inline PR comments + overall summary
- CI/CD: GitHub Actions triggered on PR open/update
- Error handling: All API methods return None on non-200 responses and print error message (no exceptions)
- Session 3: Rewrote github_client.py with complete method set and graceful error handling
- Session 4 Phase 7: DiffParser class extended with 5 new methods plus build_review_payload helper
- Session 4 Phase 8: Multi-language static analysis — uses subprocess to call language-specific linters (pyflakes for Python, ESLint for JS/TS, ruby -wc for Ruby) and pattern-based checks for Java, Go, C++ (no heavy dependencies, graceful fallback if linter not installed)
- Static analysis warnings are included in the LLM review prompt for the model to consider
- Session 5: commenter.py rewritten with PRCommenter class — format_comment() adds severity icons (❌⚠️ℹ️) and type badges ([bug][security][performance]), build_review_batch() converts results to GitHub API format, post_full_review() submits batch inline comments with REQUEST_CHANGES if critical else COMMENT
- Session 5: main.py rewritten with structured 8-step flow, environment variable validation with clear error messages, multi-language file detection display, severity counting, exit code 1 on critical issues (fails CI), comprehensive try/except error handling

## Env vars needed
GROQ_API_KEY, GITHUB_TOKEN, GITHUB_REPO, PR_NUMBER

## Last session ended at
Session 5 - Phase 9 complete: commenter.py and main.py rewritten — commenter.py now has PRCommenter class with format_comment(), build_review_batch(), post_inline_comments(), post_full_review() methods; main.py has full orchestration with env validation, 8-step review flow, multi-language support, severity breakdown, and proper exit codes

## Notes / issues to fix next session
- Phase 10: Create test_local.py for local end-to-end testing without opening a PR (mock GitHub API or use test repo)
- Phase 11: Add retry logic for API calls (network failures, rate limits) — consider tenacity library or exponential backoff
- Consider adding logging instead of print statements for better observability (structlog or Python logging module)
- Verify static_analysis subprocess calls work correctly in GitHub Actions CI environment (ESLint via npx, ruby -wc availability)
- ESLint requires Node.js/npm in CI environment — ensure Node is available in Dockerfile
- Pattern-based checks for Java/Go/C++ are basic — could be enhanced with actual linters if needed (checkstyle, go vet, clang-tidy)
- Line number mapping in post_inline_comments() may need verification — ensure diff line numbers match GitHub's expected format
