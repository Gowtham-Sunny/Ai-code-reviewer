"""
GitHub Client - Handles interactions with the GitHub API.
"""

import requests
from typing import Dict, List, Any, Optional


class GitHubClient:
    """Client for interacting with the GitHub API."""

    def __init__(self, token: str, repo: str):
        """
        Initialize the GitHub client.

        Args:
            token: GitHub personal access token
            repo: Repository in format 'owner/repo'
        """
        self.token = token
        self.owner, self.repo_name = repo.split("/")
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def _get(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Make a GET request to the GitHub API."""
        url = f"{self.base_url}{endpoint}"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 401:
            # Fallback to unauthenticated request for public repositories if token is invalid/expired
            headers_no_auth = {k: v for k, v in self.headers.items() if k != "Authorization"}
            response = requests.get(url, headers=headers_no_auth)
        if response.status_code != 200:
            print(f"GitHub API GET error: {response.status_code} - {response.text}")
            return None
        return response.json()

    def _post(self, endpoint: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Make a POST request to the GitHub API."""
        import json
        url = f"{self.base_url}{endpoint}"
        # Use json.dumps with ensure_ascii=False to preserve emojis/Unicode
        json_data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        post_headers = {
            "Authorization": self.headers["Authorization"],
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json; charset=utf-8",
        }
        response = requests.post(url, headers=post_headers, data=json_data)
        # GitHub returns 201 Created for successful POST requests
        if response.status_code not in [200, 201]:
            print(f"GitHub API POST error: {response.status_code} - {response.text}")
            return None
        return response.json()

    def get_pr_files(self, pr_number: int) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch files changed in a pull request.

        Args:
            pr_number: The pull request number

        Returns:
            List of changed files with metadata (filename, status, additions, deletions, patch)
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}/files"
        return self._get(endpoint)

    def get_pr_info(self, pr_number: int) -> Optional[Dict[str, Any]]:
        """
        Fetch pull request information.

        Args:
            pr_number: The pull request number

        Returns:
            Dict with title, body, head commit SHA, and base branch
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}"
        data = self._get(endpoint)
        if data is None:
            return None
        return {
            "title": data.get("title"),
            "body": data.get("body"),
            "head_sha": data.get("head", {}).get("sha"),
            "base_branch": data.get("base", {}).get("ref"),
        }

    def get_pr_commits(self, pr_number: int) -> Optional[str]:
        """
        Fetch commits in a pull request and return the latest commit SHA.

        Args:
            pr_number: The pull request number

        Returns:
            Latest commit SHA
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}/commits"
        commits = self._get(endpoint)
        if commits is None or len(commits) == 0:
            return None
        return commits[-1].get("sha")

    def post_review_comment(
        self, pr_number: int, commit_sha: str, path: str, line: int, body: str
    ) -> Optional[Dict[str, Any]]:
        """
        Post an inline review comment on a specific file line.

        Args:
            pr_number: The pull request number
            commit_sha: The commit SHA to comment on
            path: File path
            line: Line number
            body: Comment body

        Returns:
            Created comment data
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}/comments"
        data = {
            "body": body,
            "commit_id": commit_sha,
            "path": path,
            "line": line,
            "side": "RIGHT",
        }
        return self._post(endpoint, data)

    def post_pr_summary(self, pr_number: int, body: str) -> Optional[Dict[str, Any]]:
        """
        Post an overall summary comment on the PR.

        Args:
            pr_number: The pull request number
            body: Summary comment body

        Returns:
            Created comment data
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/issues/{pr_number}/comments"
        data = {"body": body}
        return self._post(endpoint, data)

    def create_review(
        self,
        pr_number: int,
        commit_sha: str,
        comments: List[Dict[str, Any]],
        action: str = "COMMENT",
    ) -> Optional[Dict[str, Any]]:
        """
        Create a pull request review with inline comments.

        Args:
            pr_number: The pull request number
            commit_sha: The commit SHA for the review
            comments: List of comment dicts with path, line, body
            action: Review action (COMMENT, APPROVE, REQUEST_CHANGES)

        Returns:
            Created review data
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}/reviews"
        data = {
            "commit_id": commit_sha,
            "event": action,
            "comments": comments,
        }
        return self._post(endpoint, data)

    def get_file_content(self, path: str, ref: str = "HEAD") -> Optional[str]:
        """
        Fetch raw file content for AST parsing.

        Args:
            path: File path in the repository
            ref: Git reference (branch, tag, or SHA)

        Returns:
            Raw file content as string
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/contents/{path}"
        url = f"{self.base_url}{endpoint}"
        params = {"ref": ref}
        response = requests.get(url, headers=self.headers, params=params)
        if response.status_code != 200:
            print(f"GitHub API GET file error: {response.status_code} - {response.text}")
            return None
        data = response.json()
        return data.get("content", "")
