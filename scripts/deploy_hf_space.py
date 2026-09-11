"""Deploy the whole site to a Hugging Face Space (Docker SDK).

    hf auth login                                                    # once, with a write token
    .venv/Scripts/python.exe scripts/deploy_hf_space.py --dry-run    # list what would upload
    .venv/Scripts/python.exe scripts/deploy_hf_space.py --space mplads-esakshi --public

Uploads exactly what the Dockerfile copies — and nothing else:

* the code (`src/`), the React source (`frontend/`, built inside the image), the Dockerfile
  and its requirement files, and `README_HF.md` as the Space's `README.md` (its YAML header
  tells Hugging Face this is a Docker Space on port 8080);
* the pre-built artifacts the site reads, and the Salesforce CRM mirror.

It never uploads `.env`, `Dataset/`, the OCR model weights, the portal crawl, or the
verification and audit databases, uploaded photographs and documents — those hold records
made on this machine and are created fresh, empty, on the Space.

On the first deploy it sets `MPLADS_JWT_SECRET` as a Space secret (a fresh random value),
so sign-in tokens on the public site cannot be forged with the development default. Files
that were in the Space but are no longer part of the site are removed, so a redeploy
leaves no stale code behind.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

# Hugging Face's Xet transfer client stalls on some networks; the LFS path works everywhere.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

ROOT = Path(__file__).resolve().parents[1]

TOP_LEVEL = ["Dockerfile", ".dockerignore", "requirements-serve.txt", "requirements-ocr.txt",
             "pyproject.toml"]
TREES = ["src", "frontend", "salesforce_export"]
ARTIFACTS = [
    "case_files.json", "works_scored.parquet", "duplicate_pairs.parquet", "archetypes.parquet",
    "stats.json", "temporal.json", "transparency.json", "validation.json",
    "salesforce_case_stages.json",
]
ARTIFACT_TREES = ["models"]
SKIP_PARTS = {"node_modules", "dist", "__pycache__", ".pytest_cache"}


def _tree(base: Path):
    for path in sorted(base.rglob("*")):
        if path.is_file() and not (SKIP_PARTS & set(path.parts)) and path.suffix != ".pyc":
            yield path


def planned_files() -> list[tuple[str, Path]]:
    """(path in the Space, file on disk) for everything the Space needs."""
    files = [("README.md", ROOT / "README_HF.md")]
    files += [(name, ROOT / name) for name in TOP_LEVEL]
    for tree in TREES:
        files += [(p.relative_to(ROOT).as_posix(), p) for p in _tree(ROOT / tree)]
    artifacts = ROOT / "data" / "artifacts"
    files += [(f"data/artifacts/{name}", artifacts / name) for name in ARTIFACTS]
    for tree in ARTIFACT_TREES:
        files += [(p.relative_to(ROOT).as_posix(), p) for p in _tree(artifacts / tree)]
    missing = [str(src) for _, src in files if not src.is_file()]
    if missing:
        raise SystemExit("missing files — run the pipeline first:\n  " + "\n  ".join(missing))
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--space", default="mplads-esakshi",
                        help="Space name, or owner/name (default owner: the signed-in user)")
    visibility = parser.add_mutually_exclusive_group()
    visibility.add_argument("--public", action="store_true", help="anyone can open the Space")
    visibility.add_argument("--private", action="store_true", help="only you can open it")
    parser.add_argument("--dry-run", action="store_true", help="list the files, upload nothing")
    args = parser.parse_args()

    files = planned_files()
    total = sum(src.stat().st_size for _, src in files)
    print(f"{len(files)} files, {total / 1e6:,.1f} MB")
    if args.dry_run:
        for dest, src in files:
            print(f"  {src.stat().st_size / 1e6:8.2f} MB  {dest}")
        return
    if not (args.public or args.private):
        raise SystemExit("choose --public or --private")

    from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi

    api = HfApi()
    user = api.whoami()["name"]
    repo_id = args.space if "/" in args.space else f"{user}/{args.space}"
    first_deploy = not api.repo_exists(repo_id, repo_type="space")

    api.create_repo(repo_id, repo_type="space", space_sdk="docker",
                    private=args.private, exist_ok=True)
    if first_deploy:
        api.add_space_secret(repo_id, "MPLADS_JWT_SECRET", secrets.token_urlsafe(48))
        print("set MPLADS_JWT_SECRET (a fresh random value) as a Space secret")
    elif args.public or args.private:
        api.update_repo_settings(repo_id, repo_type="space", private=args.private)

    wanted = {dest for dest, _ in files}
    stale = [path for path in api.list_repo_files(repo_id, repo_type="space")
             if path not in wanted and path != ".gitattributes"]
    operations = [CommitOperationAdd(path_in_repo=dest, path_or_fileobj=str(src))
                  for dest, src in files]
    operations += [CommitOperationDelete(path_in_repo=path) for path in stale]
    if stale:
        print(f"removing {len(stale)} file(s) no longer part of the site")

    print(f"uploading to https://huggingface.co/spaces/{repo_id} … "
          "(large artifacts go up as LFS; on a slow link this takes a while)")
    api.create_commit(repo_id, repo_type="space", operations=operations,
                      commit_message="Deploy the MPLADS eSAKSHI monitoring site")
    host = repo_id.replace("/", "-").replace("_", "-").lower()
    print(f"done. The Space now builds the image (about 10 minutes).\n"
          f"  page:  https://huggingface.co/spaces/{repo_id}\n"
          f"  site:  https://{host}.hf.space")


if __name__ == "__main__":
    sys.exit(main())
