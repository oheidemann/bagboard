#!/usr/bin/env python3
"""Builds a BagBoard release and puts it on GitHub, where installed copies find it.

    python3 dev/release.py 1.0.1 "What changed, in a sentence."
    python3 dev/release.py --build-only [version]     only writes dist/BagBoard.zip and dist/version.json

A release: VERSION is set, committed, tagged v<version> and pushed; then the zip (a folder "BagBoard" with the
program, nothing from data/) and version.json ({"version", "file", "sha256", "notes"}) are attached to a GitHub
release marked as the latest. starter.py on other computers reads exactly those two files.
Needs git and the GitHub command line tool (gh), logged in.
"""
import hashlib
import json
import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import starter      # the list of parts and the version rules are the starter's

DIST = os.path.join(ROOT, "dist")
SKIP = ("__pycache__", ".DS_Store")


def run(*args):
    return subprocess.run(args, cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def files():
    for part in starter.PARTS:
        path = os.path.join(ROOT, part)
        if os.path.isfile(path):
            yield part
        for folder, dirs, names in os.walk(path):
            dirs[:] = sorted(d for d in dirs if d not in SKIP)
            for name in sorted(names):
                if name not in SKIP and not name.endswith((".tmp", ".pyc")):
                    yield os.path.relpath(os.path.join(folder, name), ROOT)


def build(version, notes=""):
    os.makedirs(DIST, exist_ok=True)
    name = os.path.join(DIST, "BagBoard.zip")
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files():
            info = zipfile.ZipInfo.from_file(os.path.join(ROOT, path), "BagBoard/" + path.replace(os.sep, "/"))
            runs = path in ("Start BagBoard.command", "starter.py") or path.endswith("bagboard_server.py")
            info.external_attr = (0o100755 if runs else 0o100644) << 16         # the starter must stay double-clickable
            info.compress_type = zipfile.ZIP_DEFLATED
            data = version.encode() + b"\n" if path == "VERSION" else open(os.path.join(ROOT, path), "rb").read()
            archive.writestr(info, data)
    with open(name, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(os.path.join(DIST, "version.json"), "w", encoding="utf-8") as f:
        json.dump({"version": version, "file": "BagBoard.zip", "sha256": digest, "notes": notes}, f, indent=1)
    return name, os.path.join(DIST, "version.json")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--build-only":
        version = args[1] if len(args) > 1 else starter.installed_version()
        print("\n".join(build(version)))
        return
    if len(args) < 1 or not starter.as_numbers(args[0]):
        sys.exit(__doc__)
    version, notes = args[0], " ".join(args[1:])
    current = starter.installed_version()
    released = run("git", "tag", "--list", "v" + version)
    if released or (run("git", "tag", "--list", "v*") and not starter.is_newer(version, current)):
        sys.exit("Version %s is not newer than %s." % (version, current))
    if run("git", "status", "--porcelain"):
        sys.exit("There are changes that are not committed. Commit them first, so that the release is what is in git.")
    with open(os.path.join(ROOT, "VERSION"), "w", encoding="utf-8") as f:
        f.write(version + "\n")
    if run("git", "status", "--porcelain"):
        run("git", "commit", "-am", "Release " + version)
    run("git", "tag", "v" + version)
    run("git", "push", "origin", "HEAD", "--tags")
    zip_file, info_file = build(version, notes)
    print(run("gh", "release", "create", "v" + version, zip_file, info_file, "--latest",
              "--title", "BagBoard " + version, "--notes", notes or "BagBoard " + version))
    print("Released %s. Installed copies pick it up at their next start, or within six hours while running." % version)


if __name__ == "__main__":
    main()
