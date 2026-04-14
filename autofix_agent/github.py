from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests


class GitHubError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkflowRunRef:
    run_id: int
    head_sha: str
    head_branch: str | None
    conclusion: str | None


class GitHubClient:
    def __init__(self, token: str, repository: str, api_url: str = "https://api.github.com"):
        self._token = token
        self._repo = repository
        self._api = api_url.rstrip("/")

    @property
    def repository(self) -> str:
        return self._repo

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _url(self, path: str) -> str:
        return f"{self._api}{path}"

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        resp = requests.request(
            method,
            self._url(path),
            headers={**self._headers(), **kwargs.pop("headers", {})},
            timeout=kwargs.pop("timeout", 60),
            **kwargs,
        )
        if resp.status_code >= 400:
            raise GitHubError(
                f"GitHub API error {resp.status_code} for {method} {path}: {resp.text[:2000]}"
            )
        return resp

    def get_workflow_run(self, run_id: int) -> WorkflowRunRef:
        data = self._request("GET", f"/repos/{self._repo}/actions/runs/{run_id}").json()
        return WorkflowRunRef(
            run_id=int(data["id"]),
            head_sha=str(data["head_sha"]),
            head_branch=data.get("head_branch"),
            conclusion=data.get("conclusion"),
        )

    def download_workflow_logs_zip(self, run_id: int) -> bytes:
        resp = self._request("GET", f"/repos/{self._repo}/actions/runs/{run_id}/logs")
        return resp.content

    def rerun_workflow(self, run_id: int) -> None:
        self._request("POST", f"/repos/{self._repo}/actions/runs/{run_id}/rerun")

    def get_workflow_id(self, workflow_file: str) -> int:
        data = self._request("GET", f"/repos/{self._repo}/actions/workflows/{workflow_file}").json()
        return int(data["id"])

    def dispatch_workflow(
        self, workflow_file: str, ref: str, inputs: dict[str, str] | None = None
    ) -> None:
        payload: dict[str, Any] = {"ref": ref}
        if inputs:
            payload["inputs"] = inputs
        self._request(
            "POST",
            f"/repos/{self._repo}/actions/workflows/{workflow_file}/dispatches",
            json=payload,
        )

    def find_latest_run_for_ref(self, workflow_id: int, ref: str) -> WorkflowRunRef | None:
        data = self._request(
            "GET",
            f"/repos/{self._repo}/actions/workflows/{workflow_id}/runs",
            params={"branch": ref, "per_page": 5},
        ).json()
        runs = data.get("workflow_runs", [])
        if not runs:
            return None
        run = runs[0]
        return WorkflowRunRef(
            run_id=int(run["id"]),
            head_sha=str(run["head_sha"]),
            head_branch=run.get("head_branch"),
            conclusion=run.get("conclusion"),
        )

    def wait_for_run_completion(self, run_id: int, timeout_s: int = 1800, poll_s: int = 10) -> WorkflowRunRef:
        start = time.time()
        while True:
            data = self._request("GET", f"/repos/{self._repo}/actions/runs/{run_id}").json()
            status = data.get("status")
            conclusion = data.get("conclusion")
            if status == "completed":
                return WorkflowRunRef(
                    run_id=int(data["id"]),
                    head_sha=str(data["head_sha"]),
                    head_branch=data.get("head_branch"),
                    conclusion=conclusion,
                )
            if time.time() - start > timeout_s:
                raise TimeoutError(f"Timed out waiting for run {run_id} to complete.")
            time.sleep(poll_s)

    def get_ref_sha(self, branch: str) -> str:
        data = self._request("GET", f"/repos/{self._repo}/git/ref/heads/{branch}").json()
        return str(data["object"]["sha"])

    def create_branch(self, branch: str, from_sha: str) -> None:
        self._request(
            "POST",
            f"/repos/{self._repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": from_sha},
        )

    def create_or_reset_branch(self, branch: str, from_sha: str) -> None:
        try:
            self.create_branch(branch, from_sha)
        except GitHubError as e:
            if "Reference already exists" not in str(e):
                raise
            self._request(
                "PATCH",
                f"/repos/{self._repo}/git/refs/heads/{branch}",
                json={"sha": from_sha, "force": True},
            )

    def _create_blob(self, content: str) -> str:
        data = self._request(
            "POST",
            f"/repos/{self._repo}/git/blobs",
            json={"content": content, "encoding": "utf-8"},
        ).json()
        return str(data["sha"])

    def _get_commit_tree_sha(self, commit_sha: str) -> str:
        data = self._request("GET", f"/repos/{self._repo}/git/commits/{commit_sha}").json()
        return str(data["tree"]["sha"])

    def _create_tree(self, base_tree_sha: str, files: dict[str, str]) -> str:
        tree = []
        for path, content in files.items():
            blob_sha = self._create_blob(content)
            tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob_sha})
        data = self._request(
            "POST",
            f"/repos/{self._repo}/git/trees",
            json={"base_tree": base_tree_sha, "tree": tree},
        ).json()
        return str(data["sha"])

    def _create_commit(self, message: str, tree_sha: str, parents: list[str]) -> str:
        data = self._request(
            "POST",
            f"/repos/{self._repo}/git/commits",
            json={"message": message, "tree": tree_sha, "parents": parents},
        ).json()
        return str(data["sha"])

    def commit_files_to_branch(self, branch: str, message: str, files: dict[str, str]) -> str:
        head_sha = self.get_ref_sha(branch)
        base_tree_sha = self._get_commit_tree_sha(head_sha)
        new_tree_sha = self._create_tree(base_tree_sha, files)
        commit_sha = self._create_commit(message=message, tree_sha=new_tree_sha, parents=[head_sha])
        self._request(
            "PATCH",
            f"/repos/{self._repo}/git/refs/heads/{branch}",
            json={"sha": commit_sha, "force": False},
        )
        return commit_sha

    def create_pull_request(
        self, *, title: str, body: str, head: str, base: str, draft: bool = False
    ) -> str:
        data = self._request(
            "POST",
            f"/repos/{self._repo}/pulls",
            json={"title": title, "body": body, "head": head, "base": base, "draft": draft},
        ).json()
        return str(data["html_url"])

    def get_default_branch(self) -> str:
        data = self._request("GET", f"/repos/{self._repo}").json()
        return str(data["default_branch"])

    def get_workflow_run_url(self, run_id: int) -> str:
        return f"https://github.com/{self._repo}/actions/runs/{run_id}"

