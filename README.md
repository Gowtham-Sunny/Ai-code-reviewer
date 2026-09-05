# AI Code Reviewer

An autonomous GitHub PR code review agent powered by Groq LLM that automatically reviews GitHub pull requests and posts inline comments with bug detection, security issues, and suggestions.

## Features

- Automatically fetches PR diffs from GitHub
- Uses Groq API (Qwen 3 32B) to analyze code changes
- Posts inline comments on PRs with suggestions and feedback
- Multi-language support: Python, JavaScript, TypeScript, Java, Go, Ruby, C++
- Runs static analysis before LLM review
- Runs as a GitHub Action or standalone Docker container

## Setup

### Option 1: GitHub Actions (Recommended)

1. **Fork/clone the repo** to your GitHub account

2. **Add GROQ_API_KEY to GitHub repo Secrets:**
   - Go to your repo Settings → Secrets → Actions
   - Click "New repository secret"
   - Name: `GROQ_API_KEY`
   - Value: Your Groq API key (get one at https://console.groq.com)
   - The `GITHUB_TOKEN` is automatic (provided by GitHub Actions)

3. **Open any PR** — the agent runs automatically on:
   - PR opened
   - New commits pushed to PR
   - PR reopened

### Option 2: Local Testing

1. **Copy `.env.example` to `.env`:**
   ```bash
   cp .env.example .env
   ```

2. **Fill in your credentials:**
   ```
   GROQ_API_KEY=your_groq_api_key_here
   GITHUB_TOKEN=your_github_token_here
   GITHUB_REPO=owner/repo
   PR_NUMBER=123
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the reviewer:**
   ```bash
   python src/main.py
   ```

### Option 3: Docker

```bash
docker build -t ai-code-reviewer .
docker run -e GROQ_API_KEY=your_key -e GITHUB_TOKEN=your_token -e GITHUB_REPO=owner/repo -e PR_NUMBER=123 ai-code-reviewer
```

## Configuration

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Your Groq API key (required) |
| `GITHUB_TOKEN` | GitHub token with repo scope (auto-provided in Actions) |
| `GITHUB_REPO` | Repository in format `owner/repo` |
| `PR_NUMBER` | Pull request number to review |

## Supported Languages

- Python (pyflakes static analysis)
- JavaScript/TypeScript (ESLint static analysis)
- Ruby (ruby -wc syntax check)
- Java (pattern-based checks)
- Go (pattern-based checks)
- C++ (pattern-based checks)

## License

MIT
