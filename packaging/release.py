"""Publish a FoxLogin release: bump the version everywhere, commit, tag and push.

    python3 packaging/release.py 1.0.5          # explicit version
    python3 packaging/release.py patch          # 1.0.4 -> 1.0.5 (also: minor, major)
    python3 packaging/release.py 1.0.5 --dry-run   # only show what would change
    python3 packaging/release.py 1.0.4 --retag  # tag exists but its CI run failed: move it
    python3 packaging/release.py --check 1.0.5  # exit 1 unless every file says 1.0.5

Steps:
  1. write the version into every file in FILES (app/core.py, both packaging shells, lock files)
  2. commit "Release X.Y.Z" on main
  3. tag vX.Y.Z and push main + the tag; CI then builds and publishes the GitHub Release

Refuses to run off main, with unrelated uncommitted changes, or when the tag already exists
(unless --retag, which only makes sense while no GitHub Release exists for it yet).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V = r"\d+\.\d+\.\d+"

# file -> patterns; group 1 is kept, the version follows it. Each must match exactly once.
FILES = {
    "app/core.py": [rf'(^VERSION = "){V}'],
    "packaging/pywebview/foxlogin.spec": [rf'("FOXLOGIN_VERSION", "){V}'],
    "packaging/pywebview/windows/foxlogin.iss": [rf'(#define AppVersion "){V}'],
    "packaging/tauri/package.json": [rf'(^  "version": "){V}'],
    "packaging/tauri/package-lock.json": [rf'(^  "version": "){V}',
                                          rf'(^    "": \{{\n      "name": "[^"]+",\n      "version": "){V}'],
    "packaging/tauri/src-tauri/Cargo.toml": [rf'(^\[package\]\nname = "foxlogin"\nversion = "){V}'],
    "packaging/tauri/src-tauri/Cargo.lock": [rf'(^name = "foxlogin"\nversion = "){V}'],
    "packaging/tauri/src-tauri/tauri.conf.json": [rf'(^  "version": "){V}'],
}


def git(*args, check=True) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r.stdout.strip()


def current_version() -> str:
    m = re.search(rf'^VERSION = "({V})"', (ROOT / "app/core.py").read_text(encoding="utf-8"), re.M)
    return m.group(1)


def resolve(arg: str) -> str:
    if re.fullmatch(V, arg):
        return arg
    major, minor, patch = map(int, current_version().split("."))
    bumped = {"major": (major + 1, 0, 0), "minor": (major, minor + 1, 0),
              "patch": (major, minor, patch + 1)}.get(arg)
    if not bumped:
        sys.exit(f"not a version or patch/minor/major: {arg}")
    return "%d.%d.%d" % bumped


def versions_in_files() -> dict[str, list[str]]:
    found = {}
    for rel, patterns in FILES.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        found[rel] = [m.group(0)[len(m.group(1)):] for p in patterns
                      for m in re.finditer(p, text, re.M)]
    return found


def write_version(version: str, dry_run: bool):
    for rel, patterns in FILES.items():
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        for p in patterns:
            text, n = re.subn(p, lambda m: m.group(1) + version, text, flags=re.M)
            if n != 1:
                sys.exit(f"{rel}: expected one version match for {p!r}, found {n}")
        if not dry_run:
            path.write_text(text, encoding="utf-8")


def check(version: str) -> bool:
    ok = True
    for rel, found in versions_in_files().items():
        if found != [version] * len(FILES[rel]):
            print(f"  {rel}: {found or 'no version found'} (want {version})")
            ok = False
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version", help="X.Y.Z, or patch / minor / major")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen, change nothing")
    ap.add_argument("--retag", action="store_true", help="move an existing tag (its build failed, no Release yet)")
    ap.add_argument("--no-push", action="store_true", help="commit and tag locally only")
    ap.add_argument("--check", action="store_true", help="only verify every file has this version")
    args = ap.parse_args()

    if args.check:
        ok = check(args.version)
        print(f"all files at {args.version}" if ok else "version mismatch")
        sys.exit(0 if ok else 1)

    version = resolve(args.version)
    tag = f"v{version}"
    print(f"release {current_version()} -> {version} ({tag})")

    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch != "main":
        sys.exit(f"on branch {branch}; releases are cut from main")
    dirty = {line[3:] for line in git("status", "--porcelain", "--untracked-files=no").splitlines()}
    if dirty - set(FILES):
        sys.exit("uncommitted changes outside the version files:\n  " + "\n  ".join(sorted(dirty - set(FILES))))
    if not args.dry_run:
        git("fetch", "--quiet", "origin", "main", "--tags", "--force")
    if git("rev-list", "--count", "HEAD..origin/main") != "0":
        sys.exit("origin/main has commits you don't have; pull first")
    tag_exists = bool(git("tag", "--list", tag))
    if tag_exists and not args.retag:
        sys.exit(f"{tag} already exists. If its CI run failed and no Release was published, "
                 f"run again with --retag")

    write_version(version, args.dry_run)
    if args.dry_run:
        print("dry run: files would be updated:\n  " + "\n  ".join(FILES))
        return
    if not check(version):
        sys.exit("version files disagree after writing; nothing committed")

    git("add", *FILES)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
        git("commit", "--quiet", "-m", f"Release {version}")
    else:
        print("version files already committed at this version")
    if tag_exists:
        git("tag", "--delete", tag)
    git("tag", "-a", tag, "-m", f"Release {version}")
    print(f"committed and tagged {tag} at {git('rev-parse', '--short', 'HEAD')}")

    if args.no_push:
        print(f"not pushed; when ready: git push origin main && git push origin {tag}")
        return
    git("push", "--quiet", "origin", "main")
    if tag_exists:
        git("push", "--quiet", "origin", f":refs/tags/{tag}", check=False)
    git("push", "--quiet", "origin", tag)
    print(f"pushed main and {tag}; CI is building the release:")
    print("  gh run watch $(gh run list --branch " + tag + " --limit 1 --json databaseId -q '.[0].databaseId')")


if __name__ == "__main__":
    main()
