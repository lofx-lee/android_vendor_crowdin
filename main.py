import asyncio
import os
from base64 import b64decode
from pathlib import Path
from types import CoroutineType

import yaml
from httpx import AsyncClient

GITHUB_TOKEN = os.environ["X_GITHUB_TOKEN"]


async def main():
    with open("repos.yaml", "r") as f:
        r = yaml.safe_load(f.read())

    default_branch = r.get("default_branch")
    repos: list[dict] = r.get("repos", [])

    tasks: list[CoroutineType] = []
    meta: list[dict] = []

    async with AsyncClient(
        base_url="https://api.github.com/repos",
        headers={
            "Accept": "application/vnd.github.object",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {GITHUB_TOKEN}",
        },
        timeout=30,
    ) as client:
        for repo in repos:
            branch = repo.get("branch", default_branch)
            params = {"ref": branch} if branch else {}
            for m in repo.get("files", []):
                tasks.append(client.get(f"{repo['name']}/contents/{m}", params=params))
                meta.append(
                    {
                        "repo_name": repo["name"],
                        "repo_path": repo["path"],
                        "file_path": m,
                        "branch": branch,
                        "translate_attributes": repo.get("translate_attributes", True),
                    }
                )
        results = await asyncio.gather(*tasks)

    files = []

    for m, res in zip(meta, results):
        if res.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch {m['file_path']} from {m['repo_name']} (branch: {m['branch']}): "
                f"HTTP {res.status_code} - {res.text}"
            )

        content = res.json()["content"]
        decoded = b64decode(content)

        p: Path = Path("source") / m["repo_path"] / m["file_path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(decoded)

        entry: dict[str, str | int] = {
            "source": f"/source/{m['repo_path']}/{m['file_path']}",
            "translation": f"/overlay/{m['repo_path']}/{m['file_path'].replace('values', 'values-%android_code%')}",
        }
        if not m.get("translate_attributes"):
            entry["translate_attributes"] = 0

        files.append(entry)

    Path("crowdin.yml").write_text(
        yaml.safe_dump({"preserve_hierarchy": True, "files": files}, sort_keys=False)
    )


if __name__ == "__main__":
    asyncio.run(main())
