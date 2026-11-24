#!/usr/bin/env python3
"""Prepare a clean, standalone GitHub-ready repository for StreetVulkan WASM/WebGPU.

Copies source code, shaders, tools, docs, tests, GitHub workflows, WebAssembly/WebGPU
client assets, and curated showcase models (strictly < 95 MB per file) into a
standalone git repository (default: <repo_root>/street_vulkan_wasm_repo).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_TARGET = Path(__file__).resolve().parent.parent / "street_vulkan_wasm_repo"
DEFAULT_MAX_FILE_MB = 95.0

COPY_DIRS = (
    "src",
    "include",
    "shaders",
    "tools",
    "docs",
    "tests",
    ".github",
    "web",
)

COPY_ROOT_FILES = (
    ".gitignore",
    "Makefile",
    "Makefile.wasm",
    "README.md",
)

SHOWCASE_MODEL_FILES = (
    "models/texture_atlas_16x16.png",
    "models/traffic_signals.json",
    "models/rolcar_aguascalientes.json",
    "models/utility_poles_rolcar.json",
    "models/sectors/sector_0_0.glb",
    "models/sectors/chunks_0_0.json",
)

# Lightweight test/CI assets (< 4 MB total) so `make test` and ISO 25023 CI pass cleanly
OPTIONAL_TEST_MODEL_FILES = (
    "models/road_network.bin",
    "models/test.obj",
)
OPTIONAL_TEST_MODEL_DIRS = (
    "models/cars",
    "models/peds",
)

SKIP_DIR_NAMES = {"__pycache__", ".git", "build", "logs", "captures"}
SKIP_EXTENSIONS = {".pyc", ".pyo", ".o", ".so", ".a", ".spv", ".out", ".exe"}
SKIP_FILE_NAMES = {".env", ".DS_Store", "Thumbs.db"}

ROOT_INDEX_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="refresh" content="0; url=./web/index.html" />
  <title>StreetVulkan Web — Aguascalientes WebAssembly + WebGPU</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #0a101d;
      color: #e6f0ff;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }
    a { color: #38bdf8; }
  </style>
  <script>
    window.location.replace('./web/index.html' + window.location.search + window.location.hash);
  </script>
</head>
<body>
  <p>Iniciando StreetVulkan WebAssembly + WebGPU... <a href="./web/index.html">Abrir cliente</a></p>
</body>
</html>
"""

PUBLISH_GITHUB_SH = """#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: GitHub CLI (gh) is not installed. See https://cli.github.com/" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is not authenticated. Launching interactive login..."
  gh auth login
fi

if git remote get-url origin >/dev/null 2>&1; then
  echo "Remote 'origin' already configured; pushing main branch..."
  git push -u origin main
else
  gh repo create streetvulkan-wasm --public --source=. --remote=origin --push
fi

echo "Published! Check Settings -> Pages in your GitHub repository for the live URL."
"""


def _should_skip_file(rel_path: Path) -> bool:
    if rel_path.name in SKIP_FILE_NAMES:
        return True
    if rel_path.suffix.lower() in SKIP_EXTENSIONS:
        return True
    if any(part in SKIP_DIR_NAMES for part in rel_path.parts):
        return True
    return False


def _copy_tree_filtered(src_dir: Path, dst_dir: Path) -> int:
    """Copy a directory tree while filtering out compiled/cache artifacts."""
    if not src_dir.is_dir():
        raise FileNotFoundError(f"Missing required directory: {src_dir}")
    copied = 0
    for root, dirnames, filenames in os.walk(src_dir):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIR_NAMES)
        root_path = Path(root)
        rel_root = root_path.relative_to(src_dir)
        for fname in sorted(filenames):
            src_file = root_path / fname
            rel_file = rel_root / fname
            if _should_skip_file(rel_file):
                continue
            dst_file = dst_dir / rel_file
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied += 1
    return copied


def _write_curated_sectors_manifest(src_manifest: Path, dst_manifest: Path, max_file_mb: float) -> dict:
    """Write a curated models/sectors.json containing only sector (0, 0)."""
    if not src_manifest.is_file():
        raise FileNotFoundError(f"Missing sector manifest: {src_manifest}")
    with src_manifest.open("r", encoding="utf-8") as f:
        data = json.load(f)

    sector_0_0 = [
        s for s in data.get("sectors", [])
        if s.get("mx") == 0 and s.get("mz") == 0
    ]
    if not sector_0_0:
        raise RuntimeError("Sector (0, 0) not found in models/sectors.json")

    curated = {
        "macro_size": data.get("macro_size", 1024.0),
        "chunk_size": data.get("chunk_size", 128.0),
        "sector_count": len(sector_0_0),
        "total_verts": sum(int(s.get("vert_count", 0)) for s in sector_0_0),
        "max_allowed_file_mb": min(float(data.get("max_allowed_file_mb", max_file_mb)), max_file_mb),
        "sectors": sector_0_0,
    }
    dst_manifest.parent.mkdir(parents=True, exist_ok=True)
    with dst_manifest.open("w", encoding="utf-8") as f:
        json.dump(curated, f, separators=(",", ":"))
    return curated


def _prepare_gitignore(src_gitignore: Path, dst_gitignore: Path) -> None:
    """Copy .gitignore, strip parent showcase-dir rule, and allow lightweight test.obj."""
    lines = src_gitignore.read_text(encoding="utf-8").splitlines()
    filtered_lines = [
        ln for ln in lines
        if ln.strip() not in ("/street_vulkan_wasm_repo/", "# Repositorio showcase standalone generado para GitHub/Pages")
    ]
    text = "\n".join(filtered_lines).rstrip() + "\n"
    if "!models/test.obj" not in text:
        text += "\n# Track lightweight unit-test OBJ fixture in showcase repo\n!models/test.obj\n"
    dst_gitignore.write_text(text, encoding="utf-8")


def _clean_target_preserving_git(target: Path) -> None:
    """Clean existing target directory contents while preserving .git if present."""
    target.mkdir(parents=True, exist_ok=True)
    for item in target.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()


def verify_size_limit(target: Path, max_file_mb: float) -> tuple[int, int, Path | None, int]:
    """Verify every non-.git file in target is strictly smaller than max_file_mb."""
    limit_bytes = int(max_file_mb * 1024 * 1024)
    file_count = 0
    total_bytes = 0
    largest_path: Path | None = None
    largest_bytes = -1
    oversized: list[tuple[Path, int]] = []

    for root, dirnames, filenames in os.walk(target):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fname in filenames:
            p = Path(root) / fname
            sz = p.stat().st_size
            file_count += 1
            total_bytes += sz
            if sz > largest_bytes:
                largest_bytes = sz
                largest_path = p
            if sz >= limit_bytes:
                oversized.append((p, sz))

    if oversized:
        details = ", ".join(f"{p} ({sz / (1024 * 1024):.2f} MiB)" for p, sz in oversized)
        raise RuntimeError(f"Files exceed {max_file_mb} MiB limit: {details}")

    return file_count, total_bytes, largest_path, largest_bytes


def prepare_repo(
    source: Path,
    target: Path,
    max_file_mb: float = DEFAULT_MAX_FILE_MB,
    init_git: bool = True,
    commit: bool = False,
) -> dict:
    """Build the clean, self-contained StreetVulkan WASM/WebGPU GitHub repository."""
    source = source.resolve()
    target = target.resolve()
    if source == target:
        raise ValueError("Source and target directories must be different")

    _clean_target_preserving_git(target)

    copied_files = 0
    for dirname in COPY_DIRS:
        copied_files += _copy_tree_filtered(source / dirname, target / dirname)

    for rel in COPY_ROOT_FILES:
        src_file = source / rel
        if not src_file.is_file():
            raise FileNotFoundError(f"Missing required root file: {src_file}")
        dst_file = target / rel
        if rel == ".gitignore":
            _prepare_gitignore(src_file, dst_file)
        else:
            shutil.copy2(src_file, dst_file)
        copied_files += 1

    # Ensure WASM binary is freshly built from WAT inside target repo as well
    wat_file = target / "web" / "street_vulkan_core.wat"
    wasm_file = target / "web" / "street_vulkan_core.wasm"
    compiler_script = target / "tools" / "compile_wat_to_wasm.py"
    if wat_file.is_file() and compiler_script.is_file():
        subprocess.run(
            [sys.executable, str(compiler_script), str(wat_file), str(wasm_file)],
            cwd=str(target),
            check=True,
        )

    for rel in SHOWCASE_MODEL_FILES:
        src_file = source / rel
        if not src_file.is_file():
            raise FileNotFoundError(f"Missing required showcase model: {src_file}")
        dst_file = target / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        copied_files += 1

    for rel in OPTIONAL_TEST_MODEL_FILES:
        src_file = source / rel
        if src_file.is_file():
            dst_file = target / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied_files += 1

    for rel_dir in OPTIONAL_TEST_MODEL_DIRS:
        src_dir = source / rel_dir
        if src_dir.is_dir():
            copied_files += _copy_tree_filtered(src_dir, target / rel_dir)

    curated_manifest = _write_curated_sectors_manifest(
        source / "models" / "sectors.json",
        target / "models" / "sectors.json",
        max_file_mb=max_file_mb,
    )

    (target / "index.html").write_text(ROOT_INDEX_HTML, encoding="utf-8")

    publish_path = target / "publish_github.sh"
    publish_path.write_text(PUBLISH_GITHUB_SH, encoding="utf-8")
    os.chmod(publish_path, 0o755)

    file_count, total_bytes, largest_path, largest_bytes = verify_size_limit(target, max_file_mb)

    if init_git and not (target / ".git").exists():
        subprocess.run(["git", "init", "-b", "main"], cwd=str(target), check=True)

    if commit:
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=StreetVulkan CI",
                "-c",
                "user.email=ci@streetvulkan.local",
                "commit",
                "-m",
                "Initial StreetVulkan WASM + WebGPU/WebGL2 showcase",
            ],
            cwd=str(target),
            check=True,
        )

    return {
        "target": str(target),
        "file_count": file_count,
        "total_mb": total_bytes / (1024 * 1024),
        "largest_file": str(largest_path.relative_to(target)) if largest_path else "",
        "largest_mb": largest_bytes / (1024 * 1024),
        "sector_count": curated_manifest["sector_count"],
        "total_verts": curated_manifest["total_verts"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare standalone GitHub WASM/WebGPU repository for StreetVulkan.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Source StreetVulkan workspace root",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET,
        help="Target standalone repository directory",
    )
    parser.add_argument(
        "--max-file-mb",
        type=float,
        default=DEFAULT_MAX_FILE_MB,
        help="Maximum allowed single file size in MiB (default: 95.0)",
    )
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="Do not initialize git repository in target",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Stage and commit all files in target git repository",
    )
    args = parser.parse_args(argv)

    summary = prepare_repo(
        source=args.source,
        target=args.target,
        max_file_mb=args.max_file_mb,
        init_git=not args.no_git,
        commit=args.commit,
    )
    print(
        f"[prepare_github_wasm_repo] Prepared {summary['target']} | "
        f"files={summary['file_count']} | total={summary['total_mb']:.2f} MiB | "
        f"largest={summary['largest_file']} ({summary['largest_mb']:.2f} MiB) | "
        f"sectors={summary['sector_count']} (verts={summary['total_verts']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
