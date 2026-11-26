#!/usr/bin/env python3
"""Starts BagBoard. Before that it brings this folder up to date with the newest release.

A release is two files on the project's GitHub page: version.json ({"version", "file", "sha256"}) and the zip
it names. The zip holds a folder "BagBoard" with the program. Updating replaces the program's parts in this
folder and nothing else: data/ (notes, settings, recipe list) is never touched.

No update is made in a development copy (a folder with .git) or with BAGBOARD_NO_UPDATE set. Without a
connection, or when anything goes wrong, the version that is here starts as it is.

Python 3.9 or newer, standard library only.
"""
import hashlib
import io
import json
import os
import shutil
import sys
import urllib.request
import zipfile

REPO = "oheidemann/bagboard"
RELEASES = os.environ.get("BAGBOARD_UPDATE_URL") or "https://github.com/%s/releases/latest/download/" % REPO
HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = ("addon", "server", "web", "starter.py", "Start BagBoard.command", "README.md", "VERSION")      # the program
WORK = os.path.join(HERE, ".update")
MAX_ZIP = 20_000_000


def installed_version():
    try:
        with open(os.path.join(HERE, "VERSION"), "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def is_dev():
    return os.path.exists(os.path.join(HERE, ".git")) or bool(os.environ.get("BAGBOARD_NO_UPDATE"))


def as_numbers(version):
    try:
        return tuple(int(part) for part in version.split("."))
    except (ValueError, AttributeError):
        return ()


def is_newer(candidate, current):
    return bool(as_numbers(candidate)) and as_numbers(candidate) > as_numbers(current)


def fetch(name, limit):
    request = urllib.request.Request(RELEASES + name, headers={"User-Agent": "BagBoard-starter"})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(name + " is larger than expected")
    return data


def newest():
    """The newest release: {"version", "file", "sha256"}."""
    info = json.loads(fetch("version.json", 100_000).decode("utf-8"))
    if not (isinstance(info, dict) and as_numbers(info.get("version")) and isinstance(info.get("sha256"), str)
            and isinstance(info.get("file"), str) and os.path.basename(info["file"]) == info["file"]):
        raise ValueError("version.json is not as expected")
    return info


def unpack(data, target):
    """Unpacks the zip's folder "BagBoard" into target. Refuses names that point outside of it."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            parts = member.filename.split("/")
            if parts[0] != "BagBoard" or ".." in parts or member.filename.startswith("/") or "\\" in member.filename:
                raise ValueError("unexpected name in the download: " + member.filename)
            if member.is_dir() or len(parts) < 2 or not parts[-1]:
                continue
            path = os.path.join(target, *parts[1:])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with archive.open(member) as source, open(path, "wb") as out:
                shutil.copyfileobj(source, out)
            mode = (member.external_attr >> 16) & 0o777
            os.chmod(path, mode | 0o600 if mode else 0o644)


def update(info):
    """Downloads the release and swaps the program's parts. On any failure this folder is as it was."""
    data = fetch(info["file"], MAX_ZIP)
    if hashlib.sha256(data).hexdigest() != info["sha256"].lower():
        raise ValueError("the download is damaged (checksum differs)")
    shutil.rmtree(WORK, ignore_errors=True)
    new, old = os.path.join(WORK, "new"), os.path.join(WORK, "old")
    os.makedirs(new)
    os.makedirs(old)
    unpack(data, new)
    with open(os.path.join(new, "VERSION"), "r", encoding="utf-8") as f:
        if f.read().strip() != info["version"]:
            raise ValueError("the download is not version " + info["version"])
    if not os.path.isfile(os.path.join(new, "server", "bagboard_server.py")):
        raise ValueError("the download is incomplete")
    moved = []
    try:
        for part in PARTS:
            ours, theirs = os.path.join(HERE, part), os.path.join(new, part)
            if not os.path.exists(theirs):
                continue
            had = os.path.exists(ours)
            if had:
                os.rename(ours, os.path.join(old, part))
            moved.append((part, had))
            os.rename(theirs, ours)
    except OSError:
        for part, had in reversed(moved):           # put everything back
            ours = os.path.join(HERE, part)
            if os.path.exists(ours):
                shutil.rmtree(ours) if os.path.isdir(ours) else os.remove(ours)
            if had:
                os.rename(os.path.join(old, part), ours)
        raise
    finally:
        shutil.rmtree(WORK, ignore_errors=True)


def bring_up_to_date():
    """Returns the version that was replaced, or "" when nothing changed."""
    if is_dev():
        return ""
    before = installed_version()
    try:
        info = newest()
        if not is_newer(info["version"], before):
            return ""
        print("Updating BagBoard from %s to %s ..." % (before or "?", info["version"]))
        update(info)
        return before or "?"
    except Exception as error:      # no connection, GitHub away, a damaged download: start what is here
        print("No update this time (%s). Starting the version that is here." % error)
        shutil.rmtree(WORK, ignore_errors=True)
        return ""


def main():
    before = bring_up_to_date()
    if before:
        os.environ["BAGBOARD_UPDATED_FROM"] = before
    else:
        os.environ.pop("BAGBOARD_UPDATED_FROM", None)
    helper = os.path.join(HERE, "server", "bagboard_server.py")
    os.execv(sys.executable, [sys.executable, helper] + sys.argv[1:])


if __name__ == "__main__":
    main()
