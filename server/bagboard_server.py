#!/usr/bin/env python3
"""BagBoard helper: serves the BagBoard page and the addon's saved file on this computer only.

Start it with "Start BagBoard.command" (double-click), which runs starter.py: that updates an installed copy
to the newest release and then runs this file. In a development copy:  python3 server/bagboard_server.py
Then open http://localhost:8787
Your decisions and remarks are stored in data/bagboard-notes.json in the project folder.

The helper also installs the addon: from the page, or with --install. --uninstall removes it again
(add --purge to remove the game's saved scan data too).

The game folder is /Applications/World of Warcraft/_forever_ unless the page's Settings (stored in
data/bagboard-config.json) or BAGBOARD_WOW_DIR say otherwise. BAGBOARD_WOW_DIR wins.
"""
import csv
import glob
import hashlib
import io
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("BAGBOARD_PORT") or 8787)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))                 # the project folder
STARTER = os.path.join(ROOT, "starter.py")
UPDATE_EVERY = int(os.environ.get("BAGBOARD_UPDATE_EVERY") or 6 * 3600)            # seconds between looks for a newer release
UPDATED_FROM = os.environ.get("BAGBOARD_UPDATED_FROM") or ""                       # set by the starter after an update
STARTED = int(time.time())
GAME_DEFAULT = "/Applications/World of Warcraft/_forever_"
SOURCE = os.path.join(ROOT, "addon", "BagBoard")                                   # the addon's files in this project
PAGE = os.path.join(ROOT, "web", "board.html")
DATA = os.path.join(ROOT, "data")
NOTES = os.path.join(DATA, "bagboard-notes.json")
CONFIG = os.path.join(DATA, "bagboard-config.json")    # locations chosen on the page
# Set by apply_config():
GAME = ""           # the game folder
ADDON_DIR = ""      # the installed addon
NOTES_LUA = ""      # read by the addon at login and /reload
SAVED_FILE = ""     # the addon's data file if one was chosen, otherwise it is looked up in the game folder
MAX_NOTES_BYTES = 2_000_000
NOTES_LOCK = threading.Lock()       # one notes change at a time
NOTE_FIELDS = ("d", "r", "t")       # decision, remark, twink to send to
DECISIONS = ("keep", "forever", "auction", "toss", "twink")
INGAME = os.path.join(DATA, "bagboard-ingame.json")     # per character, the time of the newest in-game decision taken over
INGAME_LOCK = threading.Lock()
INGAME_SEEN = None                  # the saved file that was last looked through: (name, modification time)

# Recipe list: every profession recipe of the game, with its materials and skill numbers. It comes from the
# game client's own tables, which wago.tools offers to tools as CSV downloads (see https://wago.tools/llms.txt).
WAGO = "https://wago.tools"
WAGO_PRODUCT = "wowf"               # WoW: Forever
RECIPE_LOCALE = "deDE"              # language of the recipe and profession names, same as the game client here
RECIPE_ENGLISH = "enUS"             # the English names are kept as well ("en", "skillsEn")
RECIPE_CACHE = os.path.join(DATA, "recipe-cache.json")
RECIPE_CHECK = 7 * 86400            # ask once a week whether there is a newer game build
RECIPE_FORMAT = 3                   # raise this when the cache file's layout changes, to build it again
RECIPE_RETRY = 3600                 # after a failed download
USER_AGENT = "BagBoard-helper"
ALLOWED_HOSTS = {"localhost:%d" % PORT, "127.0.0.1:%d" % PORT}


def app_version():
    try:
        with open(os.path.join(ROOT, "VERSION"), "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def watch_for_updates():
    """While BagBoard keeps running: looks for a newer release now and then and, if there is one, starts over
    through the starter, which installs it. The page reloads itself when it sees the new version."""
    sys.path.insert(0, ROOT)
    try:
        import starter
    except ImportError:
        return
    if starter.is_dev():
        return
    while True:
        time.sleep(UPDATE_EVERY)
        try:
            if not starter.is_newer(starter.newest()["version"], app_version()):
                continue
        except Exception:       # no connection: look again later
            continue
        print("A newer BagBoard is available. Starting over to install it.")
        args = [a for a in sys.argv[1:] if a != "--no-browser"] + ["--no-browser"]      # the page is open already
        os.execv(sys.executable, [sys.executable, STARTER] + args)


def load_config():
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config if isinstance(config, dict) else {}
    except (OSError, ValueError):
        return {}


def apply_config():
    global GAME, ADDON_DIR, NOTES_LUA, SAVED_FILE
    config = load_config()
    GAME = os.environ.get("BAGBOARD_WOW_DIR") or str(config.get("gameDir") or "") or GAME_DEFAULT
    ADDON_DIR = os.path.join(GAME, "Interface", "AddOns", "BagBoard")
    NOTES_LUA = os.path.join(ADDON_DIR, "Notes.lua")
    SAVED_FILE = str(config.get("savedFile") or "")


def settings_state():
    return {"gameDir": GAME, "gameDirFromEnv": bool(os.environ.get("BAGBOARD_WOW_DIR")), "savedFile": SAVED_FILE,
            "reading": saved_file() or "", "addonDir": ADDON_DIR, "addon": addon_state()}


def clean_path(value):
    """A full path without a trailing slash, or "" for "not set". Raises ValueError otherwise."""
    if not isinstance(value, str):
        raise ValueError("A location must be text.")
    value = os.path.expanduser(value.strip())
    if value and not os.path.isabs(value):
        raise ValueError("Give the full path, starting with / or ~.")
    return os.path.normpath(value) if value else ""


def save_settings(new):
    """Stores the locations chosen on the page and switches to them. Raises ValueError on bad input."""
    if not isinstance(new, dict):
        raise ValueError("Settings must be an object.")
    game, saved = clean_path(new.get("gameDir", "")), clean_path(new.get("savedFile", ""))
    if saved and os.path.basename(saved) != "BagBoard.lua":
        raise ValueError("The data file must be named BagBoard.lua.")    # the helper hands this file to the page
    config = load_config()
    config["savedFile"] = saved
    if not os.environ.get("BAGBOARD_WOW_DIR"):
        config["gameDir"] = "" if game == GAME_DEFAULT else game
    os.makedirs(DATA, exist_ok=True)
    temp = CONFIG + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=1)
    os.replace(temp, CONFIG)
    apply_config()
    with NOTES_LOCK:
        write_lua(load_notes())     # the addon in the chosen game folder, if it is installed there


def saved_file():
    """The chosen data file, or the newest BagBoard.lua of any account. None when there is none."""
    if SAVED_FILE:
        return SAVED_FILE if os.path.isfile(SAVED_FILE) else None
    found = glob.glob(os.path.join(GAME, "WTF", "Account", "*", "SavedVariables", "BagBoard.lua"))
    return max(found, key=os.path.getmtime) if found else None


GENERATED = ("Notes.lua", "Build.lua")


def addon_build(files=None):
    """A short fingerprint of this project's addon files. It is written into Build.lua at install time, the
    addon stores it with every scan, and the page compares the two."""
    files = addon_files(SOURCE) if files is None else files
    digest = hashlib.sha1()
    for name in sorted(files):
        digest.update(name.encode("utf-8") + b"\0" + files[name] + b"\0")
    return digest.hexdigest()[:10] if files else ""


def addon_version():
    """The readable version from the addon's manifest."""
    for line in addon_files(SOURCE).get("BagBoard.toc", b"").decode("utf-8", "replace").splitlines():
        if line.lower().startswith("## version:"):
            return line.split(":", 1)[1].strip()
    return ""


def addon_files(folder):
    """Name -> content of the addon's own files in a folder. Notes.lua and Build.lua are generated at
    install time, so they do not count."""
    files = {}
    try:
        names = os.listdir(folder)
    except OSError:
        return files
    for name in names:
        path = os.path.join(folder, name)
        if name.startswith(".") or name in GENERATED or not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                files[name] = f.read()
        except OSError:
            pass
    return files


def addon_state():
    """"installed", "outdated" (the game's copy differs from this project's addon), "missing",
    or "nogame" when the game's AddOns folder is not there."""
    if os.path.isfile(os.path.join(ADDON_DIR, "BagBoard.toc")):
        ours = addon_files(SOURCE)
        # Without our own manifest there is nothing sound to compare with, and nothing to install.
        if "BagBoard.toc" not in ours:
            return "installed"
        stamp = os.path.join(ADDON_DIR, "Build.lua")        # listed in the manifest, so it must be there
        return "installed" if ours == addon_files(ADDON_DIR) and os.path.isfile(stamp) else "outdated"
    return "missing" if os.path.isdir(os.path.dirname(ADDON_DIR)) else "nogame"


ADDON_LOCK = threading.Lock()
ADDON_UPDATED = None        # the last automatic update: {"at", "ok", "restart", "error"}
ADDON_RETRY = 60            # seconds before a failed update is tried again


def update_addon():
    """Brings an installed addon up to date with this project. A first install is never done here: the page
    asks for that. Returns the record of the last update, or None."""
    global ADDON_UPDATED
    with ADDON_LOCK:
        last = ADDON_UPDATED
        if last and not last["ok"] and time.time() - last["at"] < ADDON_RETRY:
            return last
        if addon_state() != "outdated":
            return last
        ours, theirs = addon_files(SOURCE), addon_files(ADDON_DIR)
        # The game reads the manifest and the list of files only when it starts.
        restart = (ours.get("BagBoard.toc") != theirs.get("BagBoard.toc") or set(ours) != set(theirs)
                   or not os.path.isfile(os.path.join(ADDON_DIR, "Build.lua")))
        ok, message = install_addon()
        ADDON_UPDATED = {"at": int(time.time()), "ok": ok, "restart": restart, "error": "" if ok else message}
        return ADDON_UPDATED


def install_addon():
    """Clean install: the addon folder only ever holds what comes from this project, plus Notes.lua.

    Returns (ok, message)."""
    addons = os.path.dirname(ADDON_DIR)
    if not os.path.isdir(addons):
        return False, "No AddOns folder at: " + addons
    try:
        # Rescue notes from an old install that kept them inside the addon folder.
        old_notes = os.path.join(ADDON_DIR, "bagboard-notes.json")
        if os.path.isfile(old_notes) and not os.path.exists(NOTES):
            os.makedirs(DATA, exist_ok=True)
            shutil.copy2(old_notes, NOTES)
        # Build the new folder beside the old one and swap, so that a failed copy leaves the old install.
        fresh = ADDON_DIR + ".new"
        shutil.rmtree(fresh, ignore_errors=True)
        os.makedirs(fresh)
        for name in sorted(os.listdir(SOURCE)):
            if not name.startswith(".") and os.path.isfile(os.path.join(SOURCE, name)):
                shutil.copy2(os.path.join(SOURCE, name), os.path.join(fresh, name))
        with open(os.path.join(fresh, "Build.lua"), "w", encoding="utf-8") as f:
            f.write("-- Written by the BagBoard helper at install time. Do not edit.\n"
                    "BagBoardBuild = %s\n" % lua_string(addon_build(addon_files(fresh))))
        if os.path.isdir(ADDON_DIR):
            shutil.rmtree(ADDON_DIR)
        os.rename(fresh, ADDON_DIR)
        with NOTES_LOCK:
            write_lua(load_notes())
    except OSError as e:
        return False, "Install failed: %s" % e
    return True, "BagBoard installed in: " + ADDON_DIR


def uninstall_addon(purge):
    """Removes the installed addon, and with purge the game's saved scan data. The notes in data/ stay."""
    if os.path.isdir(ADDON_DIR):
        shutil.rmtree(ADDON_DIR)
        print("Removed: " + ADDON_DIR)
    else:
        print("BagBoard is not installed in: " + GAME)
    if not purge:
        print("Saved scan data was kept. Use --uninstall --purge to remove it too.")
        return
    pattern = os.path.join(GAME, "WTF", "Account", "*", "SavedVariables", "BagBoard.lua")
    found = glob.glob(pattern) + glob.glob(pattern + ".bak")
    for name in found:
        os.remove(name)
        print("Removed: " + name)
    if not found:
        print("No saved scan data found.")


def lua_string(text):
    text = "".join(ch if ch >= " " else " " for ch in str(text))[:300]
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_lua(notes):
    """Writes the notes into the installed addon so the game can show them in item tooltips.

    Returns False when the addon is not installed."""
    if not os.path.isdir(ADDON_DIR):
        return False
    lines = ["-- Written by the BagBoard helper. Edit your notes on the BagBoard page, not here.",
             "BagBoardNotes = {", "  chars = {"]
    for char, bucket in sorted(notes.get("chars", {}).items()):
        if not isinstance(bucket, dict):
            continue
        lines.append("    [%s] = {" % lua_string(char))
        for key, note in sorted(bucket.items()):
            if not (key.isascii() and key.isdigit() and isinstance(note, dict)):
                continue
            fields = []
            if note.get("d"):
                fields.append("d = " + lua_string(note["d"]))
            if note.get("r"):
                fields.append("r = " + lua_string(note["r"]))
            if note.get("t") and note.get("d") == "twink":
                fields.append("t = " + lua_string(note["t"]))
            if fields:
                lines.append("      [%d] = { %s }," % (int(key), ", ".join(fields)))
        lines.append("    },")
    lines += ["  },", "  applied = {     -- decisions changed in game up to this time are in the notes above"]
    for char, at in sorted(ingame_applied().items()):
        lines.append("    [%s] = %d," % (lua_string(char), at))
    lines += ["  },", "}"]
    temp = NOTES_LUA + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(temp, NOTES_LUA)
    return True


LUA_TOKEN = re.compile(r'''\s+|--[^\n]*|"((?:[^"\\]|\\.)*)"|(-?(?:0x[0-9a-fA-F]+|\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+))|([A-Za-z_]\w*)|([{}\[\]=,;])''', re.S)
LUA_ESCAPE = re.compile(r"\\(\d{1,3}|.)", re.S)


def lua_text(raw):
    """The text of a Lua string literal. The game writes UTF-8; a numeric escape is one byte of it."""
    out, pos = bytearray(), 0
    for escape in LUA_ESCAPE.finditer(raw):
        out += raw[pos:escape.start()].encode("utf-8")
        code = escape.group(1)
        out += bytes([int(code) & 255]) if code.isdigit() else {"n": "\n", "r": "\r", "t": "\t"}.get(code, code).encode("utf-8")
        pos = escape.end()
    return (out + raw[pos:].encode("utf-8")).decode("utf-8", "replace")


def parse_saved(text):
    """Reads a SavedVariables file: {variable: value}. Lua tables become dicts, list entries get the keys 1, 2, ...
    Raises ValueError on anything it does not understand."""
    tokens, pos = [], 0
    while pos < len(text):
        m = LUA_TOKEN.match(text, pos)
        if not m:
            raise ValueError("unexpected text at %d" % pos)
        pos = m.end()
        if m.group(1) is not None:
            tokens.append(("s", lua_text(m.group(1))))
        elif m.group(2) is not None:
            number = m.group(2)
            tokens.append(("n", int(number, 0) if re.fullmatch(r"-?(0x[0-9a-fA-F]+|\d+)", number) else float(number)))
        elif m.group(3) is not None:
            tokens.append(("w", m.group(3)))
        elif m.group(4) is not None:
            tokens.append(("p", m.group(4)))
    at = 0

    def take(kind=None, value=None):
        nonlocal at
        if at >= len(tokens) or (kind and tokens[at][0] != kind) or (value is not None and tokens[at][1] != value):
            raise ValueError("unexpected token %d" % at)
        at += 1
        return tokens[at - 1][1]

    def value():
        nonlocal at
        kind, tok = tokens[at] if at < len(tokens) else (None, None)
        if kind in ("s", "n"):
            return take()
        if kind == "w" and tok in ("true", "false", "nil"):
            take()
            return {"true": True, "false": False, "nil": None}[tok]
        take("p", "{")
        table, index = {}, 1
        while tokens[at] != ("p", "}"):
            if tokens[at] == ("p", "["):
                take()
                key = value()
                take("p", "]")
                take("p", "=")
                table[key] = value()
            elif tokens[at][0] == "w" and tokens[at + 1] == ("p", "="):
                key = take()
                take()
                table[key] = value()
            else:
                table[index] = value()
                index += 1
            if tokens[at][0] == "p" and tokens[at][1] in ",;":
                take()
        take("p", "}")
        return table

    found = {}
    try:
        while at < len(tokens):
            name = take("w")
            take("p", "=")
            found[name] = value()
    except IndexError:
        raise ValueError("the file ends early")
    return found


def ingame_applied():
    try:
        with open(INGAME, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: int(v) for k, v in data.items() if isinstance(k, str) and isinstance(v, (int, float))}
    except (OSError, ValueError, AttributeError):
        return {}


def take_ingame_edits(force=False):
    """Decisions changed in game arrive in the addon's saved file (BagBoardDB.edits[character][item id] =
    {d, at}). This puts the ones not seen before into the notes, once per change of that file, and remembers
    per character the newest one, which Notes.lua passes on so that the addon can drop them.
    Returns the number of decisions taken over."""
    global INGAME_SEEN
    with INGAME_LOCK:
        name = saved_file()
        if not name:
            return 0
        stamp = (name, os.path.getmtime(name))
        if stamp == INGAME_SEEN and not force:
            return 0
        try:
            with open(name, "r", encoding="utf-8", errors="replace") as f:
                edits = (parse_saved(f.read()).get("BagBoardDB") or {}).get("edits")
        except (OSError, ValueError, AttributeError) as error:
            print("Could not read in-game decisions from %s: %s" % (name, error))
            INGAME_SEEN = stamp
            return 0
        INGAME_SEEN = stamp
        applied, changes = ingame_applied(), []
        newest = dict(applied)
        for char, bucket in (edits.items() if isinstance(edits, dict) else []):
            if not (isinstance(char, str) and 0 < len(char) <= 100 and isinstance(bucket, dict)):
                continue
            for item, edit in bucket.items():
                at, d = (edit.get("at"), edit.get("d")) if isinstance(edit, dict) else (None, None)
                if not (isinstance(item, int) and item > 0 and isinstance(at, (int, float)) and at > applied.get(char, 0)
                        and (d == "" or d in DECISIONS)):
                    continue
                change = {"char": char, "id": str(item), "d": d}
                if d != "twink":
                    change["t"] = ""        # the character to send it to belongs to "twink" only
                changes.append((at, change))
                newest[char] = max(newest.get(char, 0), int(at))
        if not changes:
            return 0
        changes.sort(key=lambda pair: pair[0])
        # The time goes to disk first: write_lua() inside merge_notes() reads it for Notes.lua.
        os.makedirs(DATA, exist_ok=True)
        with open(INGAME + ".tmp", "w", encoding="utf-8") as f:
            json.dump(newest, f, ensure_ascii=False, indent=1)
        os.replace(INGAME + ".tmp", INGAME)
        try:
            merge_notes([change for _, change in changes])
        except (OSError, ValueError) as error:
            with open(INGAME + ".tmp", "w", encoding="utf-8") as f:
                json.dump(applied, f, ensure_ascii=False, indent=1)
            os.replace(INGAME + ".tmp", INGAME)       # not taken over after all: try again at the next change
            print("Could not put in-game decisions into the notes: %s" % error)
            return 0
        return len(changes)


def empty_notes():
    return {"version": 2, "chars": {}, "legacy": {}}


def read_notes():
    """The notes as {"version": 2, "chars": {character: {item id: note}}, "legacy": {item id: note}}.

    A note is {"d": decision, "r": remark, "t": character to send it to, for the decision "twink"}. "legacy" holds notes from before they were per character;
    the page hands them to the characters that carry the item. A missing file is empty, a damaged one
    raises ValueError."""
    try:
        with open(NOTES, "r", encoding="utf-8") as f:
            notes = json.load(f)
    except FileNotFoundError:
        return empty_notes()
    if not isinstance(notes, dict):
        raise ValueError("the notes file does not hold an object")
    if notes.get("version") != 2:
        return {"version": 2, "chars": {}, "legacy": notes}     # the old format: {item id: note}
    for part in ("chars", "legacy"):
        if not isinstance(notes.setdefault(part, {}), dict):
            raise ValueError("the notes file is damaged")
    if any(not isinstance(bucket, dict) for bucket in notes["chars"].values()):
        raise ValueError("the notes file is damaged")
    return notes


def load_notes():
    try:
        return read_notes()
    except (OSError, ValueError):
        return empty_notes()


def check_changes(changes):
    """Raises ValueError unless this is a list of changes to single notes.

    A change is {"char": character or None for a legacy note, "id": item id, and "d", "r", "t" or "remove"}."""
    if not isinstance(changes, list):
        raise ValueError("changes must be a list")
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError("a change must be an object")
        item, char = change.get("id"), change.get("char")
        if not (isinstance(item, str) and item.isascii() and item.isdigit()):
            raise ValueError("item ids must be numbers")
        if char is not None and not (isinstance(char, str) and 0 < len(char) <= 100):
            raise ValueError("bad character name")
        if any(not isinstance(change.get(f, ""), str) for f in NOTE_FIELDS):
            raise ValueError("d, r and t must be text")


def merge_notes(changes):
    """Applies changes to the notes file and the addon, in order. All other notes stay as they are.

    A change sets the fields it names; an empty text removes the field, "remove" removes the note.
    Returns the notes after the change and the file's modification time."""
    with NOTES_LOCK:
        notes = read_notes()        # raises on a damaged file, so that it is never written over
        backup = os.path.splitext(NOTES)[0] + ".v1.json"
        if notes["legacy"] and not notes["chars"] and os.path.exists(NOTES) and not os.path.exists(backup):
            shutil.copy2(NOTES, backup)         # keep the notes as they were before they became per character
        for change in changes:
            char, item = change.get("char"), change["id"]
            bucket = notes["legacy"] if char is None else notes["chars"].setdefault(char, {})
            old = bucket.get(item)
            note = dict(old) if isinstance(old, dict) and not change.get("remove") else {}
            for field in NOTE_FIELDS:
                if field in change and not change.get("remove"):
                    note[field] = change[field]
                if not note.get(field):
                    note.pop(field, None)
            if note.get("d") or note.get("r"):
                bucket[item] = note
            else:
                bucket.pop(item, None)
            if char is not None and not bucket:
                del notes["chars"][char]
        os.makedirs(DATA, exist_ok=True)
        temp = NOTES + ".tmp"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=1)
        os.replace(temp, NOTES)
        mtime = os.path.getmtime(NOTES)
        write_lua(notes)
    return notes, mtime


def notes_mtime():
    try:
        return os.path.getmtime(NOTES)
    except OSError:
        return 0


def wago(path):
    request = urllib.request.Request(WAGO + path, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read().decode("utf-8-sig", errors="replace")


def wago_table(name, version, locale=None):
    text = wago("/db2/%s/csv?version=%s%s" % (name, version, "&locale=" + locale if locale else ""))
    return csv.DictReader(io.StringIO(text))


def build_recipes(version):
    """Downloads six client tables once and turns them into: item id -> the recipes that use it.
    Each recipe also names the item it makes, so that the page can follow an item one step further."""
    # Categories 11 and 9 are the professions and secondary skills; class spells with reagents are left out.
    lines = {int(r["ID"]): (r["DisplayName_lang"], int(r["ParentSkillLineID"] or 0))
             for r in wago_table("SkillLine", version, RECIPE_LOCALE)
             if r["CategoryID"] in ("9", "11") and "[DNT]" not in r["DisplayName_lang"]}
    reagents = {}
    for r in wago_table("SpellReagents", version):
        used = [(int(r["Reagent_%d" % i]), int(r["ReagentCount_%d" % i])) for i in range(8)]
        reagents[int(r["SpellID"])] = [(item, count) for item, count in used if item > 0]
    abilities = list(wago_table("SkillLineAbility", version))
    wanted = {int(r["Spell"]) for r in abilities if reagents.get(int(r["Spell"]))}
    names = {int(r["ID"]): r["Name_lang"] for r in wago_table("SpellName", version, RECIPE_LOCALE) if int(r["ID"]) in wanted}
    english = {int(r["ID"]): r["Name_lang"] for r in wago_table("SpellName", version, RECIPE_ENGLISH) if int(r["ID"]) in wanted}
    lines_en = {int(r["ID"]): r["DisplayName_lang"] for r in wago_table("SkillLine", version, RECIPE_ENGLISH)}
    makes = {}                              # spell -> the item it creates (spell effect 24)
    for r in wago_table("SpellEffect", version):
        spell, item = int(r["SpellID"]), int(r["EffectItemType"] or 0)
        if spell in wanted and r["Effect"] == "24" and item > 0:
            makes.setdefault(spell, item)
    items, skills, skills_en, seen = {}, {}, {}, set()
    for r in abilities:
        spell, line = int(r["Spell"]), int(r["SkillLine"])
        if spell not in wanted or line not in lines:
            continue
        if lines[line][1] in lines:
            line = lines[line][1]           # a sub-line of a profession counts as the profession
        if (spell, line) in seen:
            continue
        seen.add((spell, line))
        skills[str(line)] = lines[line][0]
        skills_en[str(line)] = lines_en.get(line) or lines[line][0]
        recipe = {"id": spell, "name": names.get(spell) or english.get(spell) or "Spell %d" % spell,
                  "en": english.get(spell) or "", "skill": line,
                  "yellow": int(r["TrivialSkillLineRankLow"]),      # the tables do not say at which skill it is learned
                  "grey": int(r["TrivialSkillLineRankHigh"])}
        if spell in makes:
            recipe["makes"] = makes[spell]
        for item, count in reagents[spell]:
            items.setdefault(str(item), []).append(dict(recipe, qty=count))
    if not items:
        raise ValueError("the tables contain no recipes")
    # Names of the made items that are materials themselves; only those can lead on to another recipe.
    onward = {item for item in makes.values() if str(item) in items}
    made = {str(r["ID"]): r["Display_lang"] for r in wago_table("ItemSparse", version, RECIPE_LOCALE)
            if int(r["ID"]) in onward and r["Display_lang"]}
    now = int(time.time())
    return {"format": RECIPE_FORMAT, "made": made, "version": version, "product": WAGO_PRODUCT, "locale": RECIPE_LOCALE, "source": WAGO,
            "fetched": now, "checked": now, "recipes": len(seen), "skills": skills, "skillsEn": skills_en, "items": items}


class Recipes:
    """The recipe list, kept in data/recipe-cache.json and downloaded again only for a new game build."""

    def __init__(self):
        self.lock = threading.Lock()
        self.error = None
        self.loading = False
        try:
            with open(RECIPE_CACHE, "r", encoding="utf-8") as f:
                self.cache = json.load(f)
            if not isinstance(self.cache.get("items"), dict) or self.cache.get("format") != RECIPE_FORMAT:
                self.cache = {}
        except (OSError, ValueError, AttributeError):
            self.cache = {}
        threading.Thread(target=self.work, daemon=True).start()

    def lookup(self, ids):
        with self.lock:
            cache = self.cache
            items = {str(i): {"recipes": cache["items"].get(str(i), [])} for i in ids} if cache else {}
            # One step further: what the recipes make, where that is a material of other recipes.
            made = {}
            for i in ids if cache else []:
                for r in items[str(i)]["recipes"]:
                    m = str(r.get("makes") or "")
                    if m and m != str(i) and m not in made and m in cache["items"]:
                        made[m] = {"name": cache.get("made", {}).get(m) or r["name"], "recipes": cache["items"][m]}
            return {"items": items, "made": made, "pending": 1 if self.loading and not cache else 0, "error": self.error,
                    "skills": cache.get("skills", {}), "skillsEn": cache.get("skillsEn", {}), "version": cache.get("version"), "count": cache.get("recipes", 0)}

    def save(self):
        os.makedirs(DATA, exist_ok=True)
        temp = RECIPE_CACHE + ".tmp"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False)
        os.replace(temp, RECIPE_CACHE)

    def update(self):
        """One short question for the newest build; the tables are only downloaded when it is a new one."""
        version = json.loads(wago("/api/builds/%s/latest" % WAGO_PRODUCT))["version"]
        if not isinstance(version, str) or not version.replace(".", "").isdigit():
            raise ValueError("unexpected build number")
        fresh = build_recipes(version) if version != self.cache.get("version") else dict(self.cache, checked=int(time.time()))
        with self.lock:
            self.cache = fresh
            self.save()

    def work(self):
        while True:
            wait = RECIPE_CHECK - (time.time() - self.cache.get("checked", 0))
            if wait > 0:
                time.sleep(min(wait, 3600))
                continue
            with self.lock:
                self.loading = True
            try:
                self.update()
                error = None
            except Exception as e:      # the thread must survive anything a download can throw
                error = "Recipe list not updated: %s" % e
            with self.lock:
                self.loading, self.error = False, error
            if error:
                time.sleep(RECIPE_RETRY)


RECIPES = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, body, kind="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def local_only(self):
        # Refuse requests that another website could trigger in the browser.
        if self.headers.get("Host") not in ALLOWED_HOSTS:
            self.send(403, '{"error":"forbidden"}')
            return False
        origin = self.headers.get("Origin")
        if origin and origin.replace("http://", "") not in ALLOWED_HOSTS:
            self.send(403, '{"error":"forbidden"}')
            return False
        return True

    def do_GET(self):
        if not self.local_only():
            return
        path = self.path.split("?")[0]
        if path in ("/", "/board.html"):
            with open(PAGE, "rb") as f:
                self.send(200, f.read(), "text/html; charset=utf-8")
        elif path == "/mtime":
            name = saved_file()
            updated = update_addon()        # a newer BagBoard brings its addon along
            take_ingame_edits()             # decisions changed in game, after a /reload or logout
            self.send(200, json.dumps({"mtime": os.path.getmtime(name) if name else 0, "notes": notes_mtime(),
                                       "addon": addon_state(), "addonDir": ADDON_DIR, "addonUpdated": updated,
                                       "addonBuild": addon_build(), "addonVersion": addon_version(),
                                       "app": {"version": app_version(), "updatedFrom": UPDATED_FROM, "started": STARTED}}))
        elif path == "/settings":
            self.send(200, json.dumps(settings_state()))
        elif path == "/data":
            name = saved_file()
            if not name:
                self.send(200, json.dumps({"mtime": 0, "text": ""}))
                return
            with open(name, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            self.send(200, json.dumps({"mtime": os.path.getmtime(name), "text": text}))
        elif path == "/uses":
            query = self.path.partition("?")[2]
            raw = next((part[4:] for part in query.split("&") if part.startswith("ids=")), "")
            ids = [int(x) for x in raw.split(",") if x.isdigit()][:2000]
            self.send(200, json.dumps(RECIPES.lookup(ids) if RECIPES else {"items": {}, "pending": 0, "error": None}))
        elif path == "/notes":
            try:
                self.send(200, json.dumps(read_notes(), ensure_ascii=False))
            except (OSError, ValueError) as e:
                self.send(500, json.dumps({"error": "Notes not readable: %s" % e}))
        else:
            self.send(404, '{"error":"not found"}')

    def do_POST(self):
        if not self.local_only():
            return
        if self.path != "/install":
            self.send(404, '{"error":"not found"}')
            return
        if not self.headers.get("Origin"):      # only the page's own button, never a plain link or form
            self.send(403, '{"error":"forbidden"}')
            return
        ok, output = install_addon()
        self.send(200 if ok else 500, json.dumps({"ok": ok, "output": output}))

    def do_PUT(self):
        if not self.local_only():
            return
        if self.path != "/settings":
            self.send(404, '{"error":"not found"}')
            return
        if not self.headers.get("Origin"):
            self.send(403, '{"error":"forbidden"}')
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 10000:
                raise ValueError("Bad size.")
            save_settings(json.loads(self.rfile.read(length).decode("utf-8")))
        except ValueError as e:
            self.send(400, json.dumps({"error": str(e)}))
            return
        except OSError as e:
            self.send(500, json.dumps({"error": "Settings not saved: %s" % e}))
            return
        self.send(200, json.dumps(settings_state()))

    def do_PATCH(self):
        # Changes single notes of single characters. There is no request that replaces all notes: a page that was
        # opened earlier holds an older copy and would undo what was saved since.
        if not self.local_only():
            return
        if self.path != "/notes":
            self.send(404, '{"error":"not found"}')
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_NOTES_BYTES:
            self.send(400, '{"error":"bad size"}')
            return
        try:
            changes = json.loads(self.rfile.read(length).decode("utf-8"))
            check_changes(changes)
        except ValueError:
            self.send(400, '{"error":"not valid notes"}')
            return
        try:
            notes, mtime = merge_notes(changes)
        except (OSError, ValueError) as e:
            self.send(500, json.dumps({"error": "Notes not saved: %s" % e}))
            return
        self.send(200, json.dumps({"ok": True, "notes": notes, "mtime": mtime}))


def main():
    apply_config()
    if "--install" in sys.argv:
        ok, message = install_addon()
        print(message)
        if ok:
            print("Restart WoW Forever if this is a new install, otherwise /reload is enough.")
        sys.exit(0 if ok else 1)
    if "--uninstall" in sys.argv:
        uninstall_addon("--purge" in sys.argv)
        return
    if "--write-notes" in sys.argv:
        print("Notes written to the addon." if write_lua(load_notes()) else "Addon is not installed, notes not written.")
        return
    url = "http://localhost:%d" % PORT
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print("BagBoard is already running. Opening the page.")
        webbrowser.open(url)
        return
    global RECIPES
    RECIPES = Recipes()
    threading.Thread(target=watch_for_updates, daemon=True).start()
    updated = update_addon()
    taken = take_ingame_edits()
    installed = write_lua(load_notes())
    print("BagBoard %s is running at %s" % (app_version(), url)
          + (" (updated from %s)" % UPDATED_FROM if UPDATED_FROM else ""))
    if updated:
        print("The addon in the game was updated. " + ("Restart WoW Forever." if updated["restart"] else "Type /reload in game.")
              if updated["ok"] else "The addon in the game could not be updated: " + updated["error"])
    if taken:
        print("%d decisions changed in game were put into the notes." % taken)
    if not installed:
        print("The addon is not installed in " + GAME + ". The page offers to install it.")
    print("Saved file: " + (saved_file() or "not written yet. In game: /bb sync"))
    print("Leave this window open. Close it to stop BagBoard.")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
