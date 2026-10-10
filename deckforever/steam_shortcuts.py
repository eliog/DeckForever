#!/usr/bin/env python3
"""
Manage non-Steam shortcuts and their Proton (compat tool) mapping on a Steam Deck.

Pure standard library. Edits:
  <steam>/userdata/<steamid3>/config/shortcuts.vdf   (binary VDF)
  <steam>/config/config.vdf                          (text VDF, CompatToolMapping block)

Steam must be closed while this runs; the caller is responsible for that.

Usage:
  steam_shortcuts.py add    --name NAME --exe PATH --startdir DIR [--launch-options OPTS]
                            [--compat-tool GE-ProtonX-Y] [--icon PATH] [--tag TAG]
  steam_shortcuts.py remove --name NAME
  steam_shortcuts.py list
  steam_shortcuts.py dedupe        remove later entries that repeat an earlier name + exe
  steam_shortcuts.py prune [--missing-under DIR]   drop dead shortcuts, stale Proton mappings, orphan art
  steam_shortcuts.py appid  --name NAME --exe PATH
  steam_shortcuts.py info
"""
import argparse
import json
import os
import re
import shutil
import struct
import sys
import time
import zlib

# ----------------------------------------------------------------------------
# Steam paths
# ----------------------------------------------------------------------------

class SteamNotFound(RuntimeError):
    """Steam is not installed or nobody has logged in yet (a normal error, not SystemExit)."""


def steam_root():
    env = os.environ.get("STEAM_ROOT")
    candidates = [env] if env else []
    home = os.path.expanduser("~")
    candidates += [
        os.path.join(home, ".steam", "root"),
        os.path.join(home, ".local", "share", "Steam"),
        os.path.join(home, ".steam", "steam"),
    ]
    for c in candidates:
        if c and os.path.isdir(os.path.join(c, "userdata")):
            return os.path.realpath(c)
    raise SteamNotFound("Could not find the Steam install folder (no userdata dir).")


def _parse_loginusers(path):
    """Return list of (steamid64, dict) from loginusers.vdf (text VDF, 2 levels)."""
    users = []
    if not os.path.isfile(path):
        return users
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    for m in re.finditer(r'"(\d{17})"\s*\{(.*?)\}', text, re.S):
        sid, body = m.group(1), m.group(2)
        kv = dict(re.findall(r'"([^"]+)"\s+"([^"]*)"', body))
        users.append((sid, kv))
    return users


def steamid3(root):
    env = os.environ.get("STEAM_USER_ID3")
    if env:
        return env
    userdata = os.path.join(root, "userdata")
    ids = [d for d in os.listdir(userdata) if d.isdigit() and d != "0"]
    if not ids:
        raise SteamNotFound("No Steam user has logged in on this device yet.")
    if len(ids) == 1:
        return ids[0]
    # Several accounts: prefer the most recent login.
    for sid64, kv in _parse_loginusers(os.path.join(root, "config", "loginusers.vdf")):
        if kv.get("MostRecent") == "1":
            id3 = str(int(sid64) - 76561197960265728)
            if id3 in ids:
                return id3
    # Fall back to the most recently modified userdata dir.
    ids.sort(key=lambda d: os.path.getmtime(os.path.join(userdata, d)), reverse=True)
    return ids[0]


def shortcuts_path(root, id3):
    return os.path.join(root, "userdata", id3, "config", "shortcuts.vdf")


def config_path(root):
    return os.path.join(root, "config", "config.vdf")


def compat_tool_installed(root, name):
    for base in (os.path.join(root, "compatibilitytools.d"),
                 os.path.expanduser("~/.steam/root/compatibilitytools.d")):
        if os.path.isfile(os.path.join(base, name, "proton")):
            return True
    return False


# ----------------------------------------------------------------------------
# Binary VDF (shortcuts.vdf)
# ----------------------------------------------------------------------------

T_MAP, T_STR, T_INT, T_END = 0x00, 0x01, 0x02, 0x08


def _read_cstr(buf, pos):
    end = buf.index(b"\x00", pos)
    return buf[pos:end].decode("utf-8", errors="replace"), end + 1


def _parse_map(buf, pos):
    out = {}
    while True:
        t = buf[pos]
        pos += 1
        if t == T_END:
            return out, pos
        key, pos = _read_cstr(buf, pos)
        if t == T_MAP:
            out[key], pos = _parse_map(buf, pos)
        elif t == T_STR:
            out[key], pos = _read_cstr(buf, pos)
        elif t == T_INT:
            out[key] = struct.unpack_from("<I", buf, pos)[0]
            pos += 4
        else:
            raise ValueError(f"Unknown binary VDF type 0x{t:02x} at offset {pos - 1}")


def binary_loads(buf):
    data, _ = _parse_map(buf, 0)
    return data


def _dump_map(d):
    out = bytearray()
    for key, val in d.items():
        k = key.encode("utf-8") + b"\x00"
        if isinstance(val, dict):
            out += bytes([T_MAP]) + k + _dump_map(val)
        elif isinstance(val, int):
            out += bytes([T_INT]) + k + struct.pack("<I", val & 0xFFFFFFFF)
        else:
            out += bytes([T_STR]) + k + str(val).encode("utf-8") + b"\x00"
    out += bytes([T_END])
    return bytes(out)


def binary_dumps(d):
    return _dump_map(d)


def load_shortcuts(path):
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return {"shortcuts": {}}
    with open(path, "rb") as f:
        data = binary_loads(f.read())
    data.setdefault("shortcuts", {})
    return data


def _backup_file(path, keep=10):
    """Copy `path` to a unique .bak-<stamp>[-n] next to it and keep only the newest `keep`."""
    if not os.path.isfile(path):
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = f"{path}.bak-{stamp}"
    n = 1
    while os.path.exists(bak):
        n += 1
        bak = f"{path}.bak-{stamp}-{n}"
    shutil.copy2(path, bak)
    olds = sorted((f for f in os.listdir(os.path.dirname(path)) if f.startswith(os.path.basename(path) + ".bak-")),
                  key=lambda f: os.path.getmtime(os.path.join(os.path.dirname(path), f)), reverse=True)
    for f in olds[keep:]:
        try:
            os.remove(os.path.join(os.path.dirname(path), f))
        except OSError:
            pass
    return bak


def save_shortcuts(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _backup_file(path)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(binary_dumps(data))
    # Keep the file executable. Steam does not care, but NonSteamLaunchers' background scanner
    # (NSLGameScanner.service) replaces a non-executable shortcuts.vdf with an EMPTY one.
    os.chmod(tmp, 0o755)
    os.replace(tmp, path)


def compute_appid(exe, name):
    """Steam's non-Steam app id: crc32 of quoted exe + name, high bit set (unsigned)."""
    key = f'"{exe}"{name}'
    return (zlib.crc32(key.encode("utf-8")) | 0x80000000) & 0xFFFFFFFF


def _renumber(shortcuts):
    return {str(i): v for i, v in enumerate(shortcuts.values())}


def find_by_name(data, name):
    return [(k, v) for k, v in data["shortcuts"].items() if v.get("AppName") == name]


def _exe_of(v):
    return v.get("Exe", "").strip('"')


def find_by_name_exe(data, name, exe):
    return [(k, v) for k, v in find_by_name(data, name) if _exe_of(v) == exe]


# ----------------------------------------------------------------------------
# Text VDF (config.vdf) - targeted edit of CompatToolMapping only
# ----------------------------------------------------------------------------

def _match_brace(text, open_idx):
    """Given index of '{', return index of its matching '}' (string-aware)."""
    depth = 0
    i = open_idx
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i += 1
            while i < n and text[i] != '"':
                if text[i] == "\\":
                    i += 1
                i += 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("Unbalanced braces in config.vdf")


def _find_block(text, key, start=0):
    """Return (key_start, open_idx, close_idx) of `"key" { ... }` at or after start."""
    m = re.compile(r'"' + re.escape(key) + r'"\s*\{').search(text, start)
    if not m:
        return None
    open_idx = m.end() - 1
    return m.start(), open_idx, _match_brace(text, open_idx)


def _steam_block(text):
    """Locate InstallConfigStore/Software/Valve/Steam block."""
    pos = 0
    for key in ("InstallConfigStore", "Software", "Valve", "Steam"):
        blk = _find_block(text, key, pos)
        if not blk:
            raise ValueError(f'Could not find "{key}" block in config.vdf')
        pos = blk[1] + 1
    return blk


def set_compat_tool(text, appid, tool_name, priority=250):
    appid = str(appid)
    entry = (f'\t\t\t\t\t"{appid}"\n'
             f'\t\t\t\t\t{{\n'
             f'\t\t\t\t\t\t"name"\t\t"{tool_name}"\n'
             f'\t\t\t\t\t\t"config"\t\t""\n'
             f'\t\t\t\t\t\t"priority"\t\t"{priority}"\n'
             f'\t\t\t\t\t}}\n')
    s_start, s_open, s_close = _steam_block(text)
    ctm = _find_block(text, "CompatToolMapping", s_open + 1)
    if ctm and ctm[0] < s_close:
        c_start, c_open, c_close = ctm
        existing = _find_block(text, appid, c_open + 1)
        if existing and existing[0] < c_close:
            e_start, _, e_close = existing
            # Replace the whole existing entry including trailing newline.
            line_start = text.rfind("\n", 0, e_start) + 1
            line_end = text.find("\n", e_close) + 1
            return text[:line_start] + entry + text[line_end:]
        insert_at = text.find("\n", c_open) + 1
        return text[:insert_at] + entry + text[insert_at:]
    # No CompatToolMapping block yet: create one at the top of the Steam block.
    insert_at = text.find("\n", s_open) + 1
    block = ('\t\t\t\t"CompatToolMapping"\n'
             '\t\t\t\t{\n' + entry + '\t\t\t\t}\n')
    return text[:insert_at] + block + text[insert_at:]


def remove_compat_tool(text, appid):
    appid = str(appid)
    s_start, s_open, s_close = _steam_block(text)
    ctm = _find_block(text, "CompatToolMapping", s_open + 1)
    if not ctm or ctm[0] > s_close:
        return text
    c_start, c_open, c_close = ctm
    existing = _find_block(text, appid, c_open + 1)
    if not existing or existing[0] > c_close:
        return text
    e_start, _, e_close = existing
    line_start = text.rfind("\n", 0, e_start) + 1
    line_end = text.find("\n", e_close) + 1
    return text[:line_start] + text[line_end:]


def edit_config(path, fn):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    new = fn(text)
    if new == text:
        return False
    _backup_file(path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new)
    os.replace(tmp, path)
    return True


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------

def cmd_add(a):
    root = steam_root()
    id3 = steamid3(root)
    spath = shortcuts_path(root, id3)
    data = load_shortcuts(spath)
    appid = compute_appid(a.exe, a.name)
    quoted_exe = f'"{a.exe}"'
    quoted_dir = f'"{a.startdir}"'
    entry = {
        "appid": appid,
        "AppName": a.name,
        "Exe": quoted_exe,
        "StartDir": quoted_dir,
        "icon": a.icon or "",
        "ShortcutPath": "",
        "LaunchOptions": a.launch_options or "",
        "IsHidden": 0,
        "AllowDesktopConfig": 1,
        "AllowOverlay": 0 if a.no_overlay else 1,
        "OpenVR": 0,
        "Devkit": 0,
        "DevkitGameID": "",
        "DevkitOverrideAppID": 0,
        "LastPlayTime": 0,
        "FlatpakAppID": "",
        "tags": {str(i): t for i, t in enumerate(a.tag or [])},
    }
    # Only touch entries that are ours: same name AND same executable. Another launcher may
    # legitimately own a shortcut with the same name (e.g. NonSteamLaunchers' "Battle.net").
    existing = find_by_name_exe(data, a.name, a.exe)
    if not existing and a.replace_exe:
        existing = find_by_name_exe(data, a.name, a.replace_exe)
    stale_appids = []
    if existing:
        for k, old in existing:
            # Keep play time / hidden flags, refresh everything else.
            entry["LastPlayTime"] = old.get("LastPlayTime", 0)
            if old.get("appid") and old.get("appid") != appid:
                stale_appids.append(old["appid"])     # exe changed -> appid changed -> old mapping is orphaned
            data["shortcuts"][k] = entry
        action = "updated"
    else:
        data["shortcuts"][str(len(data["shortcuts"]))] = entry
        action = "added"
    data["shortcuts"] = _renumber(data["shortcuts"])
    save_shortcuts(spath, data)

    cpath = config_path(root)
    if os.path.isfile(cpath):
        for old_id in stale_appids:
            edit_config(cpath, lambda t, aid=old_id: remove_compat_tool(t, aid))
        if a.compat_tool:
            if not compat_tool_installed(root, a.compat_tool) and not a.compat_tool.startswith("proton"):
                print(f"WARNING: compat tool '{a.compat_tool}' not found in compatibilitytools.d; "
                      f"Steam will fall back to its default Proton.", file=sys.stderr)
            edit_config(cpath, lambda t: set_compat_tool(t, appid, a.compat_tool))
        else:
            edit_config(cpath, lambda t: remove_compat_tool(t, appid))   # native shortcut: no Proton
    print(json.dumps({"action": action, "appid": appid, "name": a.name, "steamid3": id3}))


def cmd_remove(a):
    root = steam_root()
    id3 = steamid3(root)
    spath = shortcuts_path(root, id3)
    data = load_shortcuts(spath)
    removed = []
    matches = find_by_name(data, a.name)
    if a.exe_under:
        base = os.path.realpath(a.exe_under)
        matches = [(k, v) for k, v in matches
                   if os.path.realpath(_exe_of(v)).startswith(base + os.sep)]
    if a.keep_exe:
        matches = [(k, v) for k, v in matches if _exe_of(v) != a.keep_exe]
    for k, v in matches:
        removed.append(_entry_appid(v))
        del data["shortcuts"][k]
    if removed:
        data["shortcuts"] = _renumber(data["shortcuts"])
        save_shortcuts(spath, data)
        cpath = config_path(root)
        if os.path.isfile(cpath):
            for appid in removed:
                edit_config(cpath, lambda t, aid=appid: remove_compat_tool(t, aid))
    print(json.dumps({"removed": removed, "name": a.name}))


def dedupe(data, only_under=None):
    """Drop later entries that repeat an earlier (AppName, Exe) pair. With `only_under`, only
    entries whose exe lives under that folder are considered (never touch other launchers'
    shortcuts). Returns removed appids."""
    base = os.path.realpath(only_under) + os.sep if only_under else None
    seen, removed, kept = set(), [], {}
    for k, v in data["shortcuts"].items():
        ours = base is None or os.path.realpath(_exe_of(v)).startswith(base)
        key = (v.get("AppName", ""), v.get("Exe", ""))
        if ours and key in seen:
            removed.append(_entry_appid(v))
            continue
        if ours:
            seen.add(key)
        kept[k] = v
    data["shortcuts"] = _renumber(kept)
    return removed


def cmd_dedupe(a):
    root = steam_root()
    id3 = steamid3(root)
    spath = shortcuts_path(root, id3)
    data = load_shortcuts(spath)
    removed = dedupe(data, a.only_under or None)
    if removed:
        save_shortcuts(spath, data)
        cpath = config_path(root)
        if os.path.isfile(cpath):
            for appid in removed:
                if appid:
                    edit_config(cpath, lambda t, aid=appid: remove_compat_tool(t, aid))
    print(json.dumps({"removed_duplicates": removed, "remaining": len(data["shortcuts"])}))


def _mapping_ids(text):
    """App ids that currently have a CompatToolMapping entry."""
    blk = _find_block(text, "CompatToolMapping")
    if not blk:
        return []
    inner = text[blk[1] + 1:blk[2]]
    return re.findall(r'^\s*"(\d+)"\s*$', inner, re.M)


def _entry_appid(v):
    return int(v["appid"]) if v.get("appid") else compute_appid(_exe_of(v), v.get("AppName", ""))


def all_live_appids(root):
    """Non-Steam app ids referenced by ANY account's shortcuts.vdf on this device
    (config.vdf and the grid folder are per device / per account, shortcuts are per account)."""
    live = set()
    userdata = os.path.join(root, "userdata")
    try:
        users = [d for d in os.listdir(userdata) if d.isdigit()]
    except FileNotFoundError:
        return live
    for u in users:
        try:
            for v in load_shortcuts(shortcuts_path(root, u))["shortcuts"].values():
                live.add(_entry_appid(v))
        except Exception:
            continue
    return live


def prune(data, root, id3, missing_under=()):
    """Remove dead non-Steam leftovers. Returns a summary dict.

    - shortcuts whose exe is under one of `missing_under` folders but no longer exists on disk
      (e.g. a deleted launcher prefix); other people's shortcuts are left alone
    - CompatToolMapping entries for non-Steam app ids (high bit set) that have no shortcut
    - grid artwork named after such app ids"""
    removed = []
    keep = {}
    bases = tuple(os.path.realpath(b) + os.sep for b in missing_under)
    for k, v in data["shortcuts"].items():
        exe = _exe_of(v)
        if bases and os.path.realpath(exe).startswith(bases) and not os.path.exists(exe):
            removed.append(v.get("AppName", ""))
            continue
        keep[k] = v
    data["shortcuts"] = _renumber(keep)
    # Live ids = every other account's shortcuts on disk + this account's in-memory list
    # (the caller has not saved `data` yet).
    this_user_on_disk = set()
    try:
        this_user_on_disk = {_entry_appid(v) for v in load_shortcuts(shortcuts_path(root, id3))["shortcuts"].values()}
    except Exception:
        pass
    live = (all_live_appids(root) - this_user_on_disk) | {_entry_appid(v) for v in data["shortcuts"].values()}

    stale_ids = []
    cpath = config_path(root)
    if os.path.isfile(cpath):
        with open(cpath, encoding="utf-8") as f:
            text = f.read()
        for sid in _mapping_ids(text):
            n = int(sid)
            if n >= 0x80000000 and n not in live:
                stale_ids.append(n)
        if stale_ids:
            def _drop(t):
                for n in stale_ids:
                    t = remove_compat_tool(t, n)
                return t
            edit_config(cpath, _drop)

    art = 0
    grid = os.path.join(root, "userdata", id3, "config", "grid")
    if os.path.isdir(grid):
        for fn in os.listdir(grid):
            m = re.match(r"^(\d+)(?:p|_hero|_logo|_bigpicture|-icon)?\.[A-Za-z0-9]+$", fn)
            if m and int(m.group(1)) >= 0x80000000 and int(m.group(1)) not in live:
                try:
                    os.remove(os.path.join(grid, fn))
                    art += 1
                except OSError:
                    pass
    return {"removed_shortcuts": removed, "stale_mappings": stale_ids, "artwork_removed": art}


def cmd_prune(a):
    root = steam_root()
    id3 = steamid3(root)
    spath = shortcuts_path(root, id3)
    data = load_shortcuts(spath)
    before = len(data["shortcuts"])
    summary = prune(data, root, id3, a.missing_under or [])
    if len(data["shortcuts"]) != before:
        save_shortcuts(spath, data)
    print(json.dumps(summary))


def cmd_list(a):
    root = steam_root()
    id3 = steamid3(root)
    data = load_shortcuts(shortcuts_path(root, id3))
    for k, v in data["shortcuts"].items():
        print(f'{v.get("appid", "?"):>11}  {v.get("AppName", "")!r}  exe={v.get("Exe", "")}  '
              f'opts={v.get("LaunchOptions", "")}')


def cmd_appid(a):
    print(compute_appid(a.exe, a.name))


def cmd_info(a):
    root = steam_root()
    id3 = steamid3(root)
    print(json.dumps({"steam_root": root, "steamid3": id3,
                      "shortcuts": shortcuts_path(root, id3), "config": config_path(root)}))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("add")
    s.add_argument("--name", required=True)
    s.add_argument("--exe", required=True)
    s.add_argument("--startdir", required=True)
    s.add_argument("--launch-options", default="")
    s.add_argument("--compat-tool", default="")
    s.add_argument("--icon", default="")
    s.add_argument("--tag", action="append")
    s.add_argument("--replace-exe", default="", help="also update an entry with this name and this old exe")
    s.add_argument("--no-overlay", action="store_true",
                   help="disable the Steam overlay for this entry (needed for Electron/Chromium apps, which crash when it is injected)")
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("remove")
    s.add_argument("--name", required=True)
    s.add_argument("--exe-under", default="", help="only remove entries whose exe lives under this folder")
    s.add_argument("--keep-exe", default="", help="do not remove the entry whose exe is exactly this path")
    s.set_defaults(fn=cmd_remove)

    sub.add_parser("list").set_defaults(fn=cmd_list)
    s = sub.add_parser("dedupe")
    s.add_argument("--only-under", default="", help="only consider entries whose exe lives under this folder")
    s.set_defaults(fn=cmd_dedupe)

    s = sub.add_parser("prune")
    s.add_argument("--missing-under", action="append",
                   help="drop shortcuts whose exe is under this folder and no longer exists (repeatable)")
    s.set_defaults(fn=cmd_prune)

    s = sub.add_parser("appid")
    s.add_argument("--name", required=True)
    s.add_argument("--exe", required=True)
    s.set_defaults(fn=cmd_appid)

    sub.add_parser("info").set_defaults(fn=cmd_info)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    try:
        main()
    except SteamNotFound as e:
        raise SystemExit(str(e))
