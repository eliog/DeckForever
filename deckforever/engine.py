"""
DeckForever install engine: Battle.net for World of Warcraft: Forever on Steam Deck. UI-agnostic: every front end (GTK window,
command line) passes a UI object with log/step/ask/choose/... methods.

Everything lives under one root folder (default ~/Games/DeckForever):
  prefix/                 Proton prefix; Battle.net is installed in here
  games/World of Warcraft game files, symlinked into the prefix so a prefix wipe never
                          touches them
  backups/ downloads/ logs/ app/ state.json
"""
import glob
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
import urllib.request

from . import art
from . import steam_shortcuts as ss

VERSION = "0.3.1"
BNET_URL = ("https://www.battle.net/download/getInstallerForGame"
            "?os=win&gameProgram=BATTLENET_APP&version=Live")
GE_API = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest"
APP_NAME = "DeckForever"                           # name of this app (window, desktop icon, Steam entry)
OLD_APP_NAMES = ("steamdeck-forever", "WoW Forever Tools", "WoW Forever")
SHORTCUT_BNET = "Battle.net"                       # preferred name of the main shortcut
SHORTCUT_BNET_ALT = "Battle.net (WoW Forever)"     # used when another launcher already owns "Battle.net"
SHORTCUT_CF = "CurseForge"
SHORTCUT_CF_ALT = "CurseForge (WoW Forever)"
CF_URL = "https://curseforge.overwolf.com/downloads/curseforge-latest-linux.AppImage"
CF_FOREVER_TYPE_ID = 88568                         # CurseForge's "Forever" WoW flavor id (seen in its instance file)
OLD_SHORTCUTS = ("World of Warcraft: Forever", "Battle.net (WoW Forever)", "Battle.net",
                 "WoW Forever Tools", "steamdeck-forever", "CurseForge", "CurseForge (WoW Forever)")   # ours only
APP_FILES = ("__init__.py", "__main__.py", "engine.py", "gui.py", "cli.py", "steam_shortcuts.py", "art.py", "icon.svg")


class Cancelled(Exception):
    pass


class EngineError(Exception):
    pass


class BaseUI:
    """Interface the engine talks to. Front ends override what they can show."""
    def log(self, msg): print(msg, flush=True)
    def step(self, msg): self.log("* " + msg)
    def progress(self, fraction): pass                       # 0..1 or None (pulse)
    def ask(self, question, default=True): return default    # yes/no
    def choose(self, title, options): return options[0][0] if options else None  # [(value,label)]
    def pick_folder(self, title): return None
    def pick_file(self, title, folder, pattern): return NotImplemented   # None means "cancelled"
    def info(self, msg): self.log(msg)
    def error(self, msg): self.log("ERROR: " + msg)
    def is_cancelled(self): return False


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.0f} PB"


def dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def env(name, default=None):
    """DECKFOREVER_<name>, falling back to the older WOWF_<name> spelling."""
    return os.environ.get(f"DECKFOREVER_{name}", os.environ.get(f"WOWF_{name}", default))


DEFAULT_ROOT = "~/Games/DeckForever"


class Engine:
    def __init__(self, ui, root=None, steam_root=None):
        self.ui = ui
        self.root = os.path.abspath(root or env("ROOT") or os.path.expanduser(DEFAULT_ROOT))
        self.prefix = os.path.join(self.root, "prefix")
        self.pfx = os.path.join(self.prefix, "pfx")
        self.games_dir = os.path.join(self.root, "games")
        self.wow_dir = os.path.join(self.games_dir, "World of Warcraft")
        self.wow_link = os.path.join(self.pfx, "drive_c", "Program Files (x86)", "World of Warcraft")
        self.bnet_dir = os.path.join(self.pfx, "drive_c", "Program Files (x86)", "Battle.net")
        self.bnet_exe = os.path.join(self.bnet_dir, "Battle.net.exe")
        self.bnet_cfg_dir = os.path.join(self.pfx, "drive_c", "users", "steamuser", "AppData", "Roaming", "Battle.net")
        self.backups = os.path.join(self.root, "backups")
        self.downloads = os.path.join(self.root, "downloads")
        self.logs = os.path.join(self.root, "logs")
        self.app_home = os.path.join(self.root, "app")
        self.tools_dir = os.path.join(self.root, "tools")
        self.cf_appimage = os.path.join(self.tools_dir, "CurseForge.AppImage")
        self.cf_launcher = os.path.join(self.tools_dir, "launch-curseforge.sh")
        self.cf_config = os.path.join(os.path.expanduser("~"), ".config", "CurseForge")
        self.state_file = os.path.join(self.root, "state.json")
        self._steam_root = steam_root          # else resolved (and validated) by steam_shortcuts.steam_root()
        self.proton_name = ""
        self.steam_was_running = False
        self.logfile = None

    # ------------------------------------------------------------------ basics
    @property
    def steam_root(self):
        if not self._steam_root:
            try:
                self._steam_root = ss.steam_root()
            except ss.SteamNotFound as e:
                raise EngineError(str(e))
        return self._steam_root

    @staticmethod
    def _ss(args):
        """Run a steam_shortcuts command, mapping its errors to EngineError."""
        try:
            ss.main(args)
        except ss.SteamNotFound as e:
            raise EngineError(str(e))

    @property
    def compat_dir(self):
        return os.path.join(self.steam_root, "compatibilitytools.d")

    @property
    def proton_dir(self):
        return os.path.join(self.compat_dir, self.proton_name)

    def log(self, msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        self.ui.log(msg)
        if self.logfile:
            try:
                with open(self.logfile, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass

    def step(self, msg):
        self.ui.step(msg)
        self.log(msg)

    def check_cancel(self):
        if self.ui.is_cancelled():
            raise Cancelled()

    def preflight(self):
        if os.uname().sysname != "Linux":
            raise EngineError("This installer must run on the Steam Deck (SteamOS).")
        for tool in ("curl", "tar"):
            if not shutil.which(tool):
                raise EngineError(f"Missing required tool: {tool}")
        _ = self.steam_root
        for d in (self.root, self.backups, self.downloads, self.logs, self.compat_dir):
            os.makedirs(d, exist_ok=True)
        if not self.logfile:
            self.logfile = os.path.join(self.logs, f"installer-{time.strftime('%Y%m%d-%H%M%S')}.log")
        try:
            fs = subprocess.run(["df", "-T", self.root], capture_output=True, text=True).stdout.split("\n")[1].split()[1]
            if fs.lower().startswith(("ntfs", "exfat", "vfat", "fuseblk")):
                raise EngineError(f"{self.root} is on an NTFS/exFAT drive. Battle.net needs ext4 or btrfs. Choose another folder.")
        except (IndexError, FileNotFoundError):
            pass
        self.log(f"{APP_NAME} v{VERSION}  root={self.root}")

    def load_state(self):
        try:
            with open(self.state_file, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save_state(self, **extra):
        st = self.load_state()
        st.update({"version": VERSION, "proton": self.proton_name,
                   "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, **extra)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2)

    def self_install(self):
        """Keep a stable copy of the app inside the root folder and create launcher entries."""
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        src_root = os.path.dirname(pkg_dir)
        dst_pkg = os.path.join(self.app_home, "deckforever")
        if os.path.realpath(src_root) != os.path.realpath(self.app_home):
            os.makedirs(dst_pkg, exist_ok=True)
            for f in APP_FILES:
                if os.path.isfile(os.path.join(pkg_dir, f)):
                    shutil.copy2(os.path.join(pkg_dir, f), os.path.join(dst_pkg, f))
            for f in ("run.sh", "README.md"):
                if os.path.isfile(os.path.join(src_root, f)):
                    shutil.copy2(os.path.join(src_root, f), os.path.join(self.app_home, f))
        run_sh = os.path.join(self.app_home, "run.sh")
        if not os.path.isfile(run_sh):
            with open(run_sh, "w") as f:
                f.write('#!/usr/bin/env bash\ncd "$(dirname "$0")" && exec python3 -m deckforever "$@"\n')
        os.chmod(run_sh, 0o755)
        icon = os.path.join(dst_pkg, "icon.svg")
        desktop = (f"[Desktop Entry]\nType=Application\nName={APP_NAME}\n"
                   "Comment=World of Warcraft: Forever on Steam Deck: install, repair, back up, uninstall\n"
                   f'Exec="{run_sh}"\nIcon={icon if os.path.isfile(icon) else "applications-games"}\n'
                   "Terminal=false\nCategories=Game;\n")
        apps = os.path.expanduser("~/.local/share/applications")
        os.makedirs(apps, exist_ok=True)
        with open(os.path.join(apps, "deckforever.desktop"), "w") as f:
            f.write(desktop)
        desk = os.path.expanduser("~/Desktop")
        if os.path.isdir(desk):
            p = os.path.join(desk, f"{APP_NAME}.desktop")
            with open(p, "w") as f:
                f.write(desktop)
            os.chmod(p, 0o755)
        for stale in self._old_desktop_entries():
            try:
                os.remove(stale)
            except OSError:
                pass

    @staticmethod
    def _old_desktop_entries():
        home = os.path.expanduser("~")
        out = [os.path.join(home, ".local/share/applications/wow-forever.desktop")]
        out += [os.path.join(home, "Desktop", f"{n}.desktop") for n in OLD_APP_NAMES]
        return out

    # ------------------------------------------------------------------ downloads
    def download(self, url, dest, label):
        tmp = dest + ".part"
        req = urllib.request.Request(url, headers={"User-Agent": f"DeckForever/{VERSION}"})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            last = 0
            while True:
                self.check_cancel()
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total and time.time() - last > 0.5:
                    last = time.time()
                    self.ui.progress(done / total)
                    self.ui.step(f"{label} ({human_size(done)} of {human_size(total)})")
        os.replace(tmp, dest)
        self.ui.progress(None)

    def github_json(self, url):
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": f"DeckForever/{VERSION}"})
        tok = os.environ.get("GITHUB_TOKEN")
        if tok:
            req.add_header("Authorization", f"Bearer {tok}")
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)

    # ------------------------------------------------------------------ GE-Proton
    def installed_protons(self):
        try:
            names = [d for d in os.listdir(self.compat_dir)
                     if d.startswith("GE-Proton") and os.path.isfile(os.path.join(self.compat_dir, d, "proton"))]
        except FileNotFoundError:
            return []
        return sorted(names, key=lambda n: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", n)])

    @staticmethod
    def pick_proton_asset(names, arch=None):
        """Choose the GE-Proton tarball for this machine. Releases ship one per architecture
        (GE-ProtonX-Y-x86_64.tar.gz, GE-ProtonX-Y-aarch64.tar.gz); older ones ship a single
        GE-ProtonX-Y.tar.gz. Returns (tarball_name, checksum_name_or_None)."""
        arch = arch or os.uname().machine
        aliases = {"x86_64": ("x86_64", "amd64"), "aarch64": ("aarch64", "arm64")}.get(arch, (arch,))
        others = {"x86_64", "amd64", "aarch64", "arm64"} - set(aliases)
        tars = [n for n in names if n.endswith(".tar.gz") or n.endswith(".tar.xz")]
        mine = [n for n in tars if any(a in n for a in aliases)]
        plain = [n for n in tars if not any(o in n for o in others) and n not in mine]
        if not (mine or plain):
            raise EngineError(f"No GE-Proton download for {arch} in this release ({', '.join(tars) or 'no tarballs'}).")
        tar_name = (mine or plain)[0]
        base = tar_name.rsplit(".tar", 1)[0]
        sums = [n for n in names if n.endswith(".sha512sum") and n.startswith(base)]
        return tar_name, (sums[0] if sums else None)

    def install_latest_proton(self):
        self.step("Checking the newest GE-Proton release...")
        rel = self.github_json(GE_API)
        assets = {a["name"]: a["browser_download_url"] for a in rel["assets"]}
        tag = rel["tag_name"]
        tar_name, sum_name = self.pick_proton_asset(list(assets))
        expected = tar_name.rsplit(".tar", 1)[0]          # folder inside the tarball normally matches
        if os.path.isfile(os.path.join(self.compat_dir, expected, "proton")):
            self.log(f"{expected} already installed")
            self.proton_name = expected
            return expected
        tarball = os.path.join(self.downloads, tar_name)
        self.download(assets[tar_name], tarball, f"Downloading {tag}")
        if sum_name:
            self.download(assets[sum_name], tarball + ".sha512sum", "Downloading checksum")
            r = subprocess.run(["sha512sum", "-c", "--quiet", os.path.basename(tarball) + ".sha512sum"],
                               cwd=self.downloads, capture_output=True, text=True)
            if r.returncode != 0:
                os.remove(tarball)
                raise EngineError(f"Checksum mismatch for {tag}. Please try again.")
        self.step(f"Unpacking {tag} into Steam's compatibility tools...")
        staging = os.path.join(self.compat_dir, f".wowf-unpack-{tag}")
        shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging)
        try:
            with tarfile.open(tarball) as tf:
                tops = {m.name.split("/", 1)[0] for m in tf.getmembers() if m.name and not m.name.startswith(".")}
                _safe_extract(tf, staging)
            folder = next((t for t in tops if os.path.isfile(os.path.join(staging, t, "proton"))
                           and os.path.isdir(os.path.join(staging, t, "files"))), None)
            if not folder:
                raise EngineError(f"{tag} unpacked but no complete Proton folder was found "
                                  f"(archive top level: {', '.join(sorted(tops)) or 'empty'}).")
            final = os.path.join(self.compat_dir, folder)
            shutil.rmtree(final, ignore_errors=True)
            os.rename(os.path.join(staging, folder), final)    # atomic: a half-extracted tool never appears
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        os.remove(tarball)
        if sum_name:
            os.remove(tarball + ".sha512sum")
        self.proton_name = folder
        return folder

    MIN_PROTON = (10, 21)     # first GE-Proton with the Battle.net launcher fixes (Oct 2025)

    @staticmethod
    def proton_version(name):
        m = re.match(r"GE-Proton(\d+)-(\d+)", name)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)

    def _proton_ok(self, name):
        return os.path.isfile(os.path.join(self.compat_dir, name, "proton")) and \
            os.path.isdir(os.path.join(self.compat_dir, name, "files"))

    def select_proton(self):
        forced = env("PROTON")
        if forced:
            if not self._proton_ok(forced):
                raise EngineError(f"DECKFOREVER_PROTON={forced} is not installed in {self.compat_dir}")
            self.proton_name = forced
            self.log(f"Using {self.proton_name} (pinned)")
            return
        # Prefer the build the shortcut already uses, so opening Battle.net from the app never
        # silently upgrades the prefix; otherwise the newest installed; download if too old/none.
        wanted = self.load_state().get("proton")
        if wanted and self._proton_ok(wanted):
            self.proton_name = wanted
        else:
            installed = [n for n in self.installed_protons() if self._proton_ok(n)]
            if installed and self.proton_version(installed[-1]) >= self.MIN_PROTON:
                self.proton_name = installed[-1]
            else:
                if installed:
                    self.log(f"{installed[-1]} is older than GE-Proton{self.MIN_PROTON[0]}-{self.MIN_PROTON[1]}; "
                             "downloading a current build")
                self.install_latest_proton()
        self.log(f"Using {self.proton_name}")

    def required_runtime(self, proton_dir=None):
        """Return the Steam Linux Runtime 'run' entry point the Proton build asks for, or None.

        Each Proton ships a toolmanifest.vdf with require_tool_appid (1628350 = Sniper, newer
        builds ask for newer runtimes). Steam records where that app is installed in
        steamapps/appmanifest_<appid>.acf. Running Proton under the wrong runtime fails,
        e.g. GE-Proton 11 needs a runtime with Python >= 3.11."""
        proton_dir = proton_dir or self.proton_dir
        try:
            with open(os.path.join(proton_dir, "toolmanifest.vdf"), encoding="utf-8", errors="replace") as f:
                m = re.search(r'"require_tool_appid"\s*"(\d+)"', f.read())
        except OSError:
            m = None
        if not m:
            return None
        appid = m.group(1)
        for lib in self.steam_library_dirs():
            acf = os.path.join(lib, "steamapps", f"appmanifest_{appid}.acf")
            try:
                with open(acf, encoding="utf-8", errors="replace") as f:
                    d = re.search(r'"installdir"\s*"([^"]+)"', f.read())
            except OSError:
                continue
            if d:
                run = os.path.join(lib, "steamapps", "common", d.group(1), "run")
                if os.access(run, os.X_OK):
                    return run
        return None

    def steam_library_dirs(self):
        libs = [self.steam_root]
        try:
            with open(os.path.join(self.steam_root, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace") as f:
                for p in re.findall(r'"path"\s*"([^"]+)"', f.read()):
                    p = p.replace("\\\\", "/")
                    if os.path.isdir(p) and os.path.realpath(p) not in [os.path.realpath(x) for x in libs]:
                        libs.append(p)
        except OSError:
            pass
        return libs

    RUNTIME_NAMES = {"1628350": "Steam Linux Runtime 3.0 (sniper)", "4183110": "Steam Linux Runtime 4.0",
                     "1391110": "Steam Linux Runtime 2.0 (soldier)"}

    def required_runtime_appid(self, proton_dir=None):
        try:
            with open(os.path.join(proton_dir or self.proton_dir, "toolmanifest.vdf"), encoding="utf-8", errors="replace") as f:
                m = re.search(r'"require_tool_appid"\s*"(\d+)"', f.read())
        except OSError:
            return None
        return m.group(1) if m else None

    def ensure_runtime(self, timeout_s=900):
        """Make sure the Steam Linux Runtime this Proton needs is installed. Running Proton outside
        its runtime container breaks HTTPS inside Wine (Battle.net's installer cannot reach the patch
        service), so this is not optional. Steam downloads the runtime itself from a steam:// link;
        the user confirms once in Steam's dialog."""
        if self.required_runtime():
            return True
        appid = self.required_runtime_appid()
        if not appid:
            return True            # old Proton with no runtime requirement
        name = self.RUNTIME_NAMES.get(appid, f"Steam tool {appid}")
        if not self.steam_running():
            raise EngineError(f"{self.proton_name} needs '{name}', which Steam has not downloaded yet. "
                              "Start Steam, then press Install again.")
        # Explain first and wait for OK; only then hand over to Steam, so its window does not
        # appear on top of this message before the user has read it.
        self.ui.info(f"One more download is needed: '{name}' (about 500 MB). Proton cannot run "
                     "without it.\n\nWhen you press OK, Steam opens a window asking to install it. "
                     "Click Install (or Next) there and wait for the download to finish. DeckForever "
                     "continues on its own when it is done.")
        self.step(f"Waiting for Steam to download {name} (about 500 MB)...")
        # Hand the URL to the running Steam client directly; xdg-open can also wake Discover.
        opener = ["steam"] if shutil.which("steam") else ["xdg-open"]
        subprocess.Popen(opener + [f"steam://install/{appid}"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            self.check_cancel()
            if self.required_runtime():
                self.log(f"{name} is installed")
                time.sleep(2)
                return True
            time.sleep(3)
        raise EngineError(f"'{name}' did not finish installing. Let Steam complete the download "
                          "(Library > Tools, or the Downloads page), then press Install again.")

    def proton_command(self, *args):
        cmd = [os.path.join(self.proton_dir, "proton"), "run", *args]
        runtime = self.required_runtime()
        if runtime:
            cmd = [runtime, "--", *cmd]
        elif not getattr(self, "_warned_runtime", False):
            self._warned_runtime = True
            self.log(f"Warning: the Steam runtime required by {self.proton_name} is not installed; "
                     "running Proton directly on the system (HTTPS inside Wine may fail).")
        env = os.environ.copy()
        env.update({"STEAM_COMPAT_DATA_PATH": self.prefix,
                    "STEAM_COMPAT_CLIENT_INSTALL_PATH": self.steam_root,
                    "WINEDEBUG": os.environ.get("WINEDEBUG", "-all")})
        return cmd, env

    def proton_run(self, *args, wait=True, logname="proton.log"):
        cmd, env = self.proton_command(*args)
        with open(os.path.join(self.logs, logname), "ab") as out:
            p = subprocess.Popen(cmd, env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        if wait:
            p.wait()
        return p

    # ------------------------------------------------------------------ prefix + Battle.net
    def init_prefix(self):
        os.makedirs(self.prefix, exist_ok=True)
        os.makedirs(self.wow_dir, exist_ok=True)
        if not os.path.isdir(os.path.join(self.pfx, "drive_c")):
            self.step("Creating the Wine prefix (first run takes a minute)...")
            self.proton_run("wineboot", "-u")
            if not os.path.isdir(os.path.join(self.pfx, "drive_c")):
                raise EngineError(f"Proton did not create the prefix at {self.pfx}.\n\n"
                                  f"Last lines of logs/proton.log:\n{self._tail('proton.log')}")
        os.makedirs(os.path.dirname(self.wow_link), exist_ok=True)
        self.rescue_game_folder()
        if not os.path.islink(self.wow_link):
            os.symlink(self.wow_dir, self.wow_link)
        # Battle.net client settings. Hardware acceleration stays ON: with GE-Proton 10/11 on the
        # Deck the launcher's web view renders fine with it, and turning it off (the old Lutris
        # recipe) produced a white login page. Launcher closes when a game starts (saves RAM).
        os.makedirs(self.bnet_cfg_dir, exist_ok=True)
        cfg = os.path.join(self.bnet_cfg_dir, "Battle.net.config")
        if not os.path.isfile(cfg):
            with open(cfg, "w") as f:
                json.dump({"Client": {
                    "GameLaunchWindowBehavior": "2",
                    "GameSearch": {"BackgroundSearch": "true"},
                    "HardwareAcceleration": "true",
                    "Install": {"DownloadLimitNextPatchInBps": "0"},
                    "Sound": {"Enabled": "false"},
                    "Streaming": {"StreamingEnabled": "false"}}}, f, indent=2)
        self.proton_run("reg", "add", r"HKCU\Software\Wine\DXVA2", "/v", "backend", "/t", "REG_SZ", "/d", "va", "/f")
        self.proton_run("reg", "add", r"HKCU\Software\Wine\DllOverrides", "/v", "locationapi", "/t", "REG_SZ", "/d", "", "/f")

    def _tail(self, logname, n=8):
        try:
            with open(os.path.join(self.logs, logname), encoding="utf-8", errors="replace") as f:
                return "".join(f.readlines()[-n:])
        except OSError:
            return "(no log)"

    def _our_pids(self, pattern):
        """PIDs matching `pattern` whose environment says they run in OUR prefix (never another
        launcher's Battle.net)."""
        r = subprocess.run(["pgrep", "-f", "--", pattern], capture_output=True, text=True)
        out = []
        for pid in r.stdout.split():
            try:
                with open(f"/proc/{pid}/environ", "rb") as f:
                    env = f.read()
            except OSError:
                continue
            if f"STEAM_COMPAT_DATA_PATH={self.prefix}".encode() in env or \
               f"WINEPREFIX={self.pfx}".encode() in env:
                out.append(int(pid))
        return out

    def _pgrep(self, pattern):
        return bool(self._our_pids(pattern))

    def kill_bnet(self):
        for pat in (r"Battle\.net\.exe", r"Agent\.exe", r"Battle\.net Helper"):
            for pid in self._our_pids(pat):
                subprocess.run(["kill", str(pid)], capture_output=True)

    def bnet_installed(self):
        return os.path.isfile(self.bnet_exe)

    def install_battlenet(self, force=False):
        if self.bnet_installed() and not force:
            self.log("Battle.net already installed")
            return
        setup = os.path.join(self.downloads, "Battle.net-Setup.exe")
        self.download(BNET_URL, setup, "Downloading the Battle.net installer from Blizzard")
        self.step("Installing Battle.net (a Blizzard window may appear, do not log in yet)...")
        self.kill_bnet()
        p = self.proton_run(setup, "--lang=enUS", r"--installpath=C:\Program Files (x86)\Battle.net",
                            wait=False, logname="battlenet-setup.log")
        waited = 0
        try:
            while waited < 900:
                self.check_cancel()
                if self.bnet_installed() and self._pgrep(r"Battle\.net\.exe"):
                    break
                if p.poll() is not None and (self.bnet_installed() or waited > 20):
                    break
                time.sleep(2)
                waited += 2
        except Cancelled:
            self.kill_bnet()
            p.kill()
            raise
        time.sleep(8)
        self.kill_bnet()
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()
        if not self.bnet_installed():
            raise EngineError("Battle.net did not install. See logs/battlenet-setup.log and try again.")
        self.log("Battle.net installed")

    def launch_battlenet(self, *extra):
        """Open Battle.net from our prefix (outside Steam), e.g. so the user can log in and install the game."""
        self.kill_bnet()
        return self.proton_run(self.bnet_exe, *extra, wait=False, logname="battlenet.log")

    # ------------------------------------------------------------------ Steam shortcuts
    @staticmethod
    def steam_pids():
        """PIDs of the real Steam client processes (the ubuntu12_32/steam binary and its steam.sh wrapper).

        `pgrep -x steam` is not enough: during shutdown the client keeps running for many seconds
        after the process named 'steam' is gone, and on its final exit it rewrites shortcuts.vdf
        from memory, wiping anything written in between."""
        pids = set()
        for pat in (r"/ubuntu12_32/steam( |$)", r"/steam\.sh( |$)"):
            r = subprocess.run(["pgrep", "-f", "--", pat], capture_output=True, text=True)
            pids.update(int(x) for x in r.stdout.split() if x.isdigit())
        try:
            with open(os.path.expanduser("~/.steam/steam.pid")) as f:
                pid = int(f.read().strip())
            # The pid file is left behind after exit and the number can be reused by an unrelated
            # process, so only trust it when that process really is Steam.
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode(errors="replace")
            if re.search(r"/ubuntu12_32/steam( |$)|/steam\.sh( |$)", cmd):
                pids.add(pid)
        except (OSError, ValueError):
            pass
        return pids

    @classmethod
    def steam_running(cls):
        return bool(cls.steam_pids())

    def steam_stop(self):
        self.steam_was_running = False
        if not self.steam_running():
            self.log("Steam is not running")
            return
        if self.in_game_mode():
            raise EngineError("The Deck is in Game Mode, where Steam restarts itself the moment it closes. "
                              "Switch to Desktop Mode before installing, repairing or uninstalling.")
        if not self.ui.ask("Steam has to close for a moment so the shortcuts can be written.\nClose Steam now?", True):
            raise Cancelled()
        self.steam_was_running = True
        self.step("Closing Steam (this can take up to a minute)...")
        subprocess.run(["steam", "-shutdown"], capture_output=True)
        deadline = time.time() + 120
        while time.time() < deadline:
            if not self.steam_running():
                time.sleep(3)                      # settle: make sure nothing is still exiting
                if not self.steam_running():
                    break
            time.sleep(1)
        if self.steam_running():
            self.log("Steam did not exit in time, forcing it to close")
            for pid in self.steam_pids():
                subprocess.run(["kill", str(pid)], capture_output=True)
            time.sleep(5)
        if self.steam_running():
            raise EngineError("Steam would not close. Close it manually and try again.")
        self.log("Steam is closed")

    @staticmethod
    def game_mode_command():
        """What SteamOS's own 'Return to Gaming Mode' icon runs (SteamOS 3.8), with fallbacks."""
        if shutil.which("steamosctl"):
            return ["bash", "-c", 'if [[ "$(steamosctl get-default-login-mode)" == desktop ]]; then '
                                'steamosctl switch-to-game-mode; else qdbus org.kde.Shutdown /Shutdown '
                                'org.kde.Shutdown.logout; fi']
        if shutil.which("steamos-session-select"):
            return ["steamos-session-select", "gamescope"]
        if shutil.which("qdbus"):
            return ["qdbus", "org.kde.Shutdown", "/Shutdown", "org.kde.Shutdown.logout"]
        return None

    def switch_to_game_mode(self):
        cmd = self.game_mode_command()
        if not cmd:
            raise EngineError("Could not find the SteamOS command to switch to Game Mode. "
                              "Use the 'Return to Gaming Mode' icon on the desktop.")
        self.log("Switching to Game Mode: " + " ".join(cmd))
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    @staticmethod
    def in_game_mode():
        """True when the Deck is in Game Mode (gamescope session), however this process was started."""
        if os.environ.get("GAMESCOPE_WAYLAND_DISPLAY") or os.environ.get("XDG_CURRENT_DESKTOP", "").lower() == "gamescope":
            return True
        if subprocess.run(["pgrep", "-x", "gamescope-session"], capture_output=True).returncode == 0:
            return True
        return subprocess.run(["pgrep", "-x", "gamescope"], capture_output=True).returncode == 0 and \
            subprocess.run(["pgrep", "-x", "plasmashell"], capture_output=True).returncode != 0

    @staticmethod
    def session_env():
        """Environment of the user's graphical session (needed to start Steam, e.g. from SSH).

        Steam started without a usable display exits early and writes an EMPTY shortcuts.vdf,
        so we must never launch it blind."""
        keys = ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS",
                "XDG_SESSION_TYPE")
        env = {k: os.environ[k] for k in keys if k in os.environ}
        if "XAUTHORITY" not in env or "DISPLAY" not in env:
            for proc in ("plasmashell", "gamescope-session", "steam"):
                r = subprocess.run(["pgrep", "-x", proc], capture_output=True, text=True)
                for pid in r.stdout.split():
                    try:
                        with open(f"/proc/{pid}/environ", "rb") as f:
                            items = f.read().split(b"\0")
                    except OSError:
                        continue
                    found = {}
                    for it in items:
                        k, _, v = it.decode(errors="replace").partition("=")
                        if k in keys:
                            found[k] = v
                    if "DISPLAY" in found or "WAYLAND_DISPLAY" in found:
                        found.update(env)          # explicit values win
                        return found
        return env

    def steam_start(self):
        if not self.steam_was_running:
            return
        env = self.session_env()
        if not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
            self.ui.info("Steam was closed and could not be restarted automatically (no desktop session found). "
                         "Start Steam yourself from the desktop.")
            return
        self.step("Restarting Steam...")
        full = os.environ.copy()
        full.update(env)
        subprocess.Popen(["steam"], env=full, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, start_new_session=True)
        self.steam_was_running = False
        for _ in range(30):
            time.sleep(1)
            if self.steam_running():
                return
        self.log("Steam did not come back within 30 s; start it from the desktop if it is not open.")

    def _all_shortcuts(self):
        try:
            root = self.steam_root
            return list(ss.load_shortcuts(ss.shortcuts_path(root, ss.steamid3(root)))["shortcuts"].values())
        except Exception:
            return []

    def _is_ours(self, entry):
        return entry.get("Exe", "").strip('"').startswith(self.root + os.sep)

    def _unique_name(self, preferred, alternate):
        """`preferred`, unless some other launcher already has a shortcut by that name."""
        for v in self._all_shortcuts():
            if v.get("AppName") == preferred and not self._is_ours(v):
                return alternate
        return preferred

    def main_shortcut_name(self):
        return self._unique_name(SHORTCUT_BNET, SHORTCUT_BNET_ALT)

    def cf_shortcut_name(self):
        return self._unique_name(SHORTCUT_CF, SHORTCUT_CF_ALT)

    def shortcut_specs(self):
        """The Steam shortcuts this app maintains: (name, exe, startdir, launch options, compat tool)."""
        specs = [
            # Battle.net under Proton in our prefix. You press Play inside Battle.net.
            (self.main_shortcut_name(), self.bnet_exe, self.bnet_dir,
             f'STEAM_COMPAT_DATA_PATH="{self.prefix}" %command%', self.proton_name, True, "bnet"),
        ]
        if self.curseforge_installed():
            # CurseForge is a native Electron app (AppImage): no Proton, no Steam overlay, and started
            # through a wrapper that drops Steam's injected runtime libraries (they crash Chromium).
            if not os.path.isfile(self.cf_launcher):
                self.write_cf_launcher()
            specs.append((self.cf_shortcut_name(), self.cf_launcher, self.tools_dir, "", "", False, "cf"))
        # This app itself, so backups/restores/Open Battle.net are reachable from Game Mode
        # (the Steam-restarting actions are disabled there by the window). GTK: overlay off too.
        specs.append((APP_NAME, self.launcher_sh, self.app_home, "", "", False, "app"))
        return specs

    def grid_dir(self):
        root = self.steam_root
        return os.path.join(root, "userdata", ss.steamid3(root), "config", "grid")

    def apply_artwork(self, specs):
        """Draw library art for each of our entries. Returns {spec name: icon path}. Never fatal."""
        icons = {}
        if not art.available():
            self.log("cairo not available: skipping library artwork")
            return icons
        try:
            grid = self.grid_dir()
        except (EngineError, ss.SteamNotFound):
            return icons
        for name, exe, _sd, _o, _t, _ov, key in specs:
            appid = ss.compute_appid(exe, name)
            try:
                files = art.render_set(key, grid, appid)
                icons[name] = files["icon"]
            except Exception as e:
                self.log(f"artwork for {name} skipped: {e}")
        return icons

    @property
    def launcher_sh(self):
        return os.path.join(self.app_home, "run.sh")

    def write_shortcuts(self, restart_steam=True):
        """Close Steam, write our entries, and (normally) start Steam again. The install flow passes
        restart_steam=False when it is about to switch to Game Mode anyway, so Desktop Steam does not
        pop up over the app; it calls steam_start() itself if the user declines the switch."""
        self.steam_stop()
        ok = False
        try:
            self.step("Adding Steam shortcuts...")
            specs = self.shortcut_specs()
            current = {spec[0] for spec in specs}
            for name in OLD_SHORTCUTS:                      # renamed in earlier versions; ours only
                if name not in current:
                    self._ss(["remove", "--name", name, "--exe-under", self.root])
            icons = self.apply_artwork(specs)
            for name, exe, startdir, opts, tool, overlay, _key in specs:
                # Same name, our folder, different target (e.g. the target moved to a wrapper script):
                # drop the stale entry so the library never shows two of ours.
                self._ss(["remove", "--name", name, "--exe-under", self.root, "--keep-exe", exe])
                self._ss(["add", "--name", name, "--exe", exe, "--startdir", startdir,
                          "--launch-options", opts, "--compat-tool", tool, "--tag", "WoW Forever",
                          "--icon", icons.get(name, "")]
                         + ([] if overlay else ["--no-overlay"]))
            self._ss(["dedupe", "--only-under", self.root])          # Steam can re-add cached copies after a bad start; keep one of each
            # Dead leftovers from deleted launcher prefixes (ours or e.g. NonSteamLaunchers'), stale
            # Proton mappings and orphaned artwork. Only touches entries that cannot launch anyway.
            self._ss(["prune", "--missing-under", os.path.join(self.steam_root, "steamapps", "compatdata"),
                      "--missing-under", self.root])
            if not self.shortcuts_present():
                raise EngineError("The shortcut was written but could not be read back. See the log.")
            self.log("Shortcuts written")
            ok = True
        finally:
            if restart_steam or not ok:
                self.steam_start()

    def remove_shortcuts(self):
        self.steam_stop()
        try:
            for name in (SHORTCUT_BNET, SHORTCUT_BNET_ALT, *OLD_SHORTCUTS):
                self._ss(["remove", "--name", name, "--exe-under", self.root])
        finally:
            self.steam_start()

    def shortcuts_present(self):
        return any(self._is_ours(v) and v.get("Exe", "").strip('"') == self.bnet_exe
                   for v in self._all_shortcuts())

    # ------------------------------------------------------------------ game folder, backups
    def find_flavor_dir(self, wow_dir=None):
        wow_dir = wow_dir or self.wow_dir
        forced = env("FLAVOR_DIR")
        if forced:
            p = os.path.join(wow_dir, forced)
            return p if os.path.isdir(p) else None
        if not os.path.isdir(wow_dir):
            return None
        for pat in ("_*forever*_", "_classic_beta_", "_classic_era_"):
            hits = sorted(glob.glob(os.path.join(wow_dir, pat)))
            if hits:
                return hits[0]
        cands = [d for d in glob.glob(os.path.join(wow_dir, "_*_")) if glob.glob(os.path.join(d, "Wow*.exe"))]
        cands.sort(key=os.path.getmtime, reverse=True)
        return cands[0] if cands else None

    def require_flavor(self):
        fl = self.find_flavor_dir()
        if not fl:
            raise EngineError("World of Warcraft is not installed yet.\n\n"
                              f"Open '{self.main_shortcut_name()}' in Steam, log in, pick World of Warcraft, "
                              "choose the Forever version in the dropdown and install it. Then come back here.")
        return fl

    def backup(self, client_dir=None):
        fl = client_dir or self.require_flavor()
        out = os.path.join(self.backups, f"wowf-backup-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz")
        items = [(os.path.join(fl, n), n) for n in ("WTF", "Interface", "Fonts") if os.path.isdir(os.path.join(fl, n))]
        cfg = os.path.join(self.bnet_cfg_dir, "Battle.net.config")
        if os.path.isfile(cfg):
            items.append((cfg, "Battle.net.config"))
        if not items:
            raise EngineError(f"Nothing to back up yet (no WTF or Interface folder in {fl}).")
        self.step(f"Backing up settings and addons to {os.path.basename(out)} ...")

        def _filter(ti):
            parts = ti.name.split("/")
            return None if "Cache" in parts else ti
        with tarfile.open(out, "w:gz") as tf:
            for path, arc in items:
                tf.add(path, arcname=arc, filter=_filter)
        self.log(f"Backup written: {out} ({human_size(os.path.getsize(out))})")
        return out

    def list_backups(self):
        files = glob.glob(os.path.join(self.backups, "wowf-backup-*.tar.gz"))
        return sorted(files, key=os.path.getmtime, reverse=True)

    def restore(self, file=None):
        if not file:
            backups = self.list_backups()
            if not backups:
                raise EngineError("There are no backups yet.")
            chosen = self.ui.pick_file("Choose a backup to restore", self.backups, "*.tar.gz")
            if chosen is None:
                raise Cancelled()                      # the user closed the chooser
            file = backups[0] if chosen is NotImplemented else chosen   # no chooser available: newest
        if not os.path.isfile(file):
            raise EngineError(f"Backup not found: {file}")
        fl = self.require_flavor()
        self.step(f"Restoring {os.path.basename(file)} ...")
        with tarfile.open(file) as tf:
            members = tf.getmembers()
            for m in members:
                if m.name.startswith("/") or ".." in m.name.split("/"):
                    raise EngineError(f"Unsafe path in backup: {m.name}")
            game_members = [m for m in members if m.name.split("/")[0] != "Battle.net.config"]
            cfg_members = [m for m in members if m.name == "Battle.net.config"]
            _safe_extract(tf, fl, game_members)
            if cfg_members:
                os.makedirs(self.bnet_cfg_dir, exist_ok=True)
                _safe_extract(tf, self.bnet_cfg_dir, cfg_members)
        self.log("Restore complete")

    # ------------------------------------------------------------------ CurseForge (addon manager)
    def curseforge_installed(self):
        return os.path.isfile(self.cf_appimage) and os.access(self.cf_appimage, os.X_OK)

    def curseforge_running(self):
        r = subprocess.run(["pgrep", "-f", "--", re.escape(self.cf_appimage)], capture_output=True)
        return r.returncode == 0

    def install_curseforge(self, update=False):
        """Download the official CurseForge Linux build (an AppImage) into tools/."""
        if self.curseforge_installed() and not update:
            self.log("CurseForge already installed")
            return self.cf_appimage
        if self.curseforge_running():
            raise EngineError("CurseForge is running. Close it first.")
        os.makedirs(self.tools_dir, exist_ok=True)
        tmp = self.cf_appimage + ".download"
        self.download(CF_URL, tmp, "Downloading CurseForge")
        with open(tmp, "rb") as f:
            head = f.read(16)
        if os.path.getsize(tmp) < 50 * 1024 * 1024 or head[8:11] != b"AI\x02":
            os.remove(tmp)
            raise EngineError("The CurseForge download does not look like a valid AppImage. Try again later.")
        os.chmod(tmp, 0o755)
        os.replace(tmp, self.cf_appimage)
        self.write_cf_launcher()
        self.save_state(curseforge=True)
        self.log(f"CurseForge installed at {self.cf_appimage}")
        return self.cf_appimage

    def write_cf_launcher(self):
        """Wrapper Steam launches instead of the AppImage directly. Steam injects its legacy runtime
        libraries and overlay preload into every launched process; Electron's helper processes crash
        on them (SIGTRAP/SIGSEGV in the zygote), so the wrapper starts CurseForge with a clean env."""
        os.makedirs(self.tools_dir, exist_ok=True)
        with open(self.cf_launcher, "w") as f:
            f.write('#!/usr/bin/env bash\n'
                    '# Launch CurseForge with the environment Steam adds stripped away (see DeckForever).\n'
                    'unset LD_PRELOAD LD_LIBRARY_PATH STEAM_RUNTIME STEAM_RUNTIME_LIBRARY_PATH SYSTEM_LD_LIBRARY_PATH \\\n'
                    '      STEAM_ZENITY GTK_IM_MODULE QT_IM_MODULE SDL_VIDEO_X11_FORCE_EGL \\\n'
                    '      ENABLE_VK_LAYER_VALVE_steam_overlay_1 ENABLE_VK_LAYER_VALVE_steam_fossilize_1\n'
                    'cd "$(dirname "$0")"\n'
                    'exec ./CurseForge.AppImage "$@"\n')
        os.chmod(self.cf_launcher, 0o755)
        return self.cf_launcher

    def cf_instances_file(self):
        return os.path.join(self.cf_config, "agent", "GameInstances", "AddonGameInstance.json")

    def curseforge_configured(self):
        fl = self.find_flavor_dir()
        if not fl:
            return False
        try:
            with open(self.cf_instances_file(), encoding="utf-8") as f:
                recs = json.load(f)
        except (OSError, ValueError):
            return False
        want = os.path.realpath(fl)
        return any(os.path.realpath(r.get("installPath", "").rstrip("/")) == want for r in recs)

    def configure_curseforge(self):
        """Point CurseForge at the installed Forever client so the user does not have to browse for it.
        CurseForge keeps its game list in a JSON file; its SQLite database only holds download history."""
        fl = self.find_flavor_dir()
        if not fl:
            self.log("CurseForge: WoW is not installed yet, nothing to configure")
            return False
        if self.curseforge_running():
            self.log("CurseForge is running; its game list will be configured next time it is closed")
            return False
        path = self.cf_instances_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, encoding="utf-8") as f:
                recs = json.load(f)
            if not isinstance(recs, list):
                recs = []
        except (OSError, ValueError):
            recs = []
        want = os.path.realpath(fl)
        guid = None
        for r in recs:
            if os.path.realpath(r.get("installPath", "").rstrip("/")) == want:
                r["isValid"] = True
                r["isEnabled"] = True
                guid = r["guid"]
        if guid is None:
            import uuid
            guid = str(uuid.uuid4())
            now = time.strftime("%Y-%m-%dT%H:%M:%S.0000000Z", time.gmtime())
            recs.append({
                "guid": guid, "gameTypeID": 1, "installPath": fl.rstrip("/") + "/", "name": "Forever",
                "cachedScans": [], "isValid": True, "lastPreviousMatchUpdate": "0001-01-01T00:00:00",
                "lastRefreshAttempt": "0001-01-01T00:00:00", "isEnabled": True,
                "gameVersion": None, "gameVersionFlavor": None, "gameVersionTypeId": CF_FOREVER_TYPE_ID,
                "preferenceAlternateFile": False, "preferenceAutoInstallUpdates": False,
                "preferenceDeleteOrphanedDependencies": False, "preferenceDeleteSavedVariables": False,
                "preferenceReleaseType": 1, "preferenceModdingFolderPath": None,
                "syncProfile": {"PreferenceEnabled": False, "PreferenceAutoSync": True, "PreferenceAutoDelete": False,
                                "PreferenceBackupSavedVariables": False, "GameInstanceGuid": guid,
                                "SyncProfileID": 0, "SavedVariablesProfile": None,
                                "LastSyncDate": "0001-01-01T00:00:00"},
                "installDate": now, "installedAddons": [], "installedGamePrerequisites": [],
                "wasNameManuallyChanged": False, "wasGameVersionTypeIdManuallyChanged": False,
            })
        if os.path.isfile(path):
            shutil.copy2(path, path + ".bak")
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(recs, f, indent=2)
        os.replace(path + ".tmp", path)
        # Open on the Forever instance next time.
        storage = os.path.join(self.cf_config, "storage.json")
        try:
            with open(storage, encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            st = {}
        st["internal-last-game-instances"] = json.dumps({"lastGameInstances": {"1": guid}, "startupGameId": 1})
        st.setdefault("is-first-launch-done", "true")
        with open(storage + ".tmp", "w", encoding="utf-8") as f:
            json.dump(st, f, indent=1)
        os.replace(storage + ".tmp", storage)
        self.log(f"CurseForge now knows the Forever client at {fl}")
        return True

    # ------------------------------------------------------------------ adopt an existing install
    def find_existing_installs(self):
        home = os.path.expanduser("~")
        pf = os.path.join("drive_c", "Program Files (x86)", "World of Warcraft")
        patterns = [
            os.path.join(self.steam_root, "steamapps", "compatdata", "*", "pfx", pf),
            os.path.join(home, ".local", "share", "Steam", "steamapps", "compatdata", "*", "pfx", pf),
            os.path.join("/run/media", "*", "*", "steamapps", "compatdata", "*", "pfx", pf),
            os.path.join(home, "Games", "*", pf),
            os.path.join(home, "Games", "Heroic", "Prefixes", "*", "*", "pfx", pf),
            os.path.join(home, ".var", "app", "com.usebottles.bottles", "data", "bottles", "bottles", "*", pf),
        ]
        forced = env("ADOPT_FROM")
        if forced and os.path.isdir(forced):
            return [forced]
        seen, out = set(), []
        mine = os.path.realpath(self.wow_dir)
        for pat in patterns:
            for d in glob.glob(pat):
                r = os.path.realpath(d)
                if r == mine or r in seen or not os.path.isdir(r):
                    continue
                if not (glob.glob(os.path.join(r, "_*_")) or os.path.isdir(os.path.join(r, "Data"))):
                    continue
                seen.add(r)
                out.append(r)
        return out

    def adopt(self, src=None):
        if not src:
            found = self.find_existing_installs()
            if not found:
                src = self.ui.pick_folder('Pick your existing "World of Warcraft" folder')
                if not src:
                    raise EngineError("No existing World of Warcraft folder found.")
            elif len(found) == 1:
                src = found[0]
            else:
                src = self.ui.choose("Which install should be adopted?", [(f, f) for f in found])
                if not src:
                    raise Cancelled()
        src = os.path.realpath(src)
        if not os.path.isdir(src):
            raise EngineError(f"Not a folder: {src}")
        if os.path.isdir(self.wow_dir) and os.listdir(self.wow_dir):
            raise EngineError(f"{self.wow_dir} already has files in it. Move them away first, then adopt again.")
        self.step("Measuring the existing install...")
        size = human_size(dir_size(src))
        if not self.ui.ask(f"Found an existing WoW install ({size}):\n{src}\n\nMove it into\n{self.wow_dir}\n"
                           "so it does not have to be downloaded again?\n\nA link is left behind so your old "
                           "launcher keeps working.", True):
            raise Cancelled()
        old_flavor = self.find_flavor_dir(src)
        if old_flavor:
            try:
                self.backup(old_flavor)
            except EngineError as e:
                self.log(f"Backup skipped: {e}")
        os.makedirs(self.games_dir, exist_ok=True)
        same_fs = os.stat(src).st_dev == os.stat(self.games_dir).st_dev
        if not same_fs:
            need = dir_size(src)
            free = shutil.disk_usage(self.games_dir).free
            if free < need * 1.05:
                raise EngineError(f"Not enough free space to copy the game files ({human_size(need)} needed, "
                                  f"{human_size(free)} free in {self.games_dir}).")
            if not self.ui.ask(f"The game files are on a different drive, so this is a {size} copy rather than an "
                               "instant move. It can take a long time. Continue?", True):
                raise Cancelled()
        self.step(f"Moving game files ({size})...")
        if os.path.isdir(self.wow_dir):
            os.rmdir(self.wow_dir)
        self.kill_bnet()
        try:
            shutil.move(src, self.wow_dir)
        except BaseException:
            if not same_fs and os.path.isdir(self.wow_dir) and os.path.isdir(src):
                shutil.rmtree(self.wow_dir, ignore_errors=True)   # partial copy; the source is intact
            raise
        os.symlink(self.wow_dir, src)
        self.log(f"Adopted {src} -> {self.wow_dir}")
        self.save_state(adopted_from=src)

    # ------------------------------------------------------------------ top-level flows
    def install(self, force_bnet=False, open_bnet=True):
        self.preflight()
        self.self_install()
        if not self.find_flavor_dir() and self.find_existing_installs():
            try:
                self.adopt()
            except Cancelled:
                self.log("Existing install not adopted; continuing with a fresh install.")
            except EngineError as e:
                self.log(f"Existing install not adopted ({e}); continuing with a fresh install.")
        self.select_proton()
        self.ensure_runtime()
        self.init_prefix()
        self.install_battlenet(force_bnet)
        if not self.curseforge_installed() and not env("NO_CURSEFORGE") and \
                self.ui.ask("Also install CurseForge (the addon manager) so it is available in Game Mode?", True):
            try:
                self.install_curseforge()
                self.step("CurseForge downloaded")
            except EngineError as e:
                self.log(f"CurseForge skipped: {e}")
                self.ui.error(f"CurseForge could not be installed ({e}). You can retry later with 'Install CurseForge'.")
        game_installed = bool(self.find_flavor_dir())
        can_switch = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and not self.in_game_mode()
        # When we are about to offer a switch to Game Mode, do not bring Desktop Steam back first:
        # it would open on top of this window and hide the offer.
        self.write_shortcuts(restart_steam=not (can_switch and not game_installed))
        self.save_state()
        if self.curseforge_installed():
            self.configure_curseforge()
        name = self.main_shortcut_name()
        if game_installed:
            extra = f" '{self.cf_shortcut_name()}' is there too, already pointed at your Forever client." \
                if self.curseforge_installed() else ""
            self.ui.info(f"Done. '{name}' is in your Steam library (Non-Steam tab). Press Play there.{extra}")
            return
        if can_switch and self.ui.ask(
                f"Battle.net is ready. The login works best from Game Mode.\n\n"
                f"Switch to Game Mode now? Once there:\n"
                f"1. Launch '{name}' from the Non-Steam tab.\n"
                "2. Press Steam + X for the keyboard, log in, tick 'Keep me logged in'.\n"
                "3. Pick World of Warcraft, choose the Forever version and press Install."
                + (f"\n4. Afterwards, open '{APP_NAME}' once more and press Repair so CurseForge is pointed at the game."
                   if self.curseforge_installed() else ""), True):
            try:
                self.switch_to_game_mode()
                return
            except EngineError as e:
                self.log(str(e))
                self.ui.error(str(e))          # fall through to the written instructions
        self.steam_start()                     # declined (or no switch possible): bring Desktop Steam back
        self.ui.info(f"Battle.net is ready.\n\n"
                     f"1. Switch to Game Mode and launch '{name}' from the Non-Steam tab.\n"
                     "2. Log in with Steam + X for the keyboard (tick 'Keep me logged in').\n"
                     "3. Pick World of Warcraft, choose the Forever version and press Install.\n\n"
                     "Logging in from Game Mode avoids a Desktop Mode quirk where on-screen keyboard taps "
                     "also land in the Battle.net window.")
        if open_bnet and self.ui.ask("Open Battle.net here in Desktop Mode anyway? (Use a USB/Bluetooth keyboard, "
                                     "or move the window to the top of the screen before typing.)", False):
            self.launch_battlenet()
            self.ui.info("Battle.net will open shortly (it can take up to a minute the first time).")

    def rescue_game_folder(self):
        """If game files live inside the prefix (old layout, or a user who installed before the link
        existed), move them out to games/ so a prefix wipe cannot destroy them."""
        if os.path.isdir(self.wow_link) and not os.path.islink(self.wow_link):
            self.step("Moving game files out of the prefix...")
            os.makedirs(self.wow_dir, exist_ok=True)
            for item in os.listdir(self.wow_link):
                dst = os.path.join(self.wow_dir, item)
                if os.path.exists(dst):
                    raise EngineError(f"Both the prefix and {self.wow_dir} contain '{item}'. "
                                      "Merge or remove one of them by hand before reinstalling.")
                shutil.move(os.path.join(self.wow_link, item), dst)
            os.rmdir(self.wow_link)
            self.log(f"Game files moved to {self.wow_dir}")

    def reinstall(self):
        self.preflight()
        self.rescue_game_folder()
        if self.find_flavor_dir() and self.ui.ask("Back up your settings and addons before reinstalling? (recommended)", True):
            self.backup()
        wipe_games = self.ui.ask("Also delete the downloaded game files (~40 GB, must be re-downloaded)?\n\n"
                                 "Choose No to keep them.", False)
        self.step("Removing the old prefix...")
        self.kill_bnet()
        time.sleep(1)
        shutil.rmtree(self.prefix, ignore_errors=True)
        if wipe_games:
            shutil.rmtree(self.games_dir, ignore_errors=True)
        self.install(force_bnet=True)
        backups = self.list_backups()
        if backups and self.find_flavor_dir() and self.ui.ask(f"Restore your latest backup now?\n{os.path.basename(backups[0])}", True):
            self.restore(backups[0])

    def curseforge(self, update=False):
        """Install (or update) CurseForge, add its Steam shortcut, and point it at the game."""
        self.preflight()
        self.install_curseforge(update=update)
        self.select_proton()
        self.write_shortcuts()
        configured = self.configure_curseforge()
        self.save_state()
        name = self.cf_shortcut_name()
        if configured:
            self.ui.info(f"'{name}' is in your Steam library and already knows your Forever client.")
        else:
            self.ui.info(f"'{name}' is in your Steam library. Once World of Warcraft: Forever is installed, "
                         "press Repair here and it will be pointed at the game automatically.")

    def update_proton(self):
        self.preflight()
        self.install_latest_proton()
        self.ensure_runtime()
        if self.bnet_installed():
            self.write_shortcuts()
        self.save_state()
        self.ui.info(f"Shortcuts now use {self.proton_name}.")

    def uninstall(self):
        self.preflight()
        if self.ui.ask("Remove the Steam shortcuts for WoW Forever?", True):
            self.remove_shortcuts()
        if not os.path.isfile(self.state_file):
            self.ui.info(f"{self.root} was not set up by this app (no state.json), so its files are left alone.")
            return
        if os.path.isdir(self.root) and self.ui.ask(f"Also delete the Battle.net prefix, game files, backups and logs in\n{self.root}?", False):
            if self.find_flavor_dir() and self.ui.ask("Save a final backup of settings/addons to your home folder first?", True):
                b = self.backup()
                shutil.copy2(b, os.path.expanduser("~"))
                self.ui.info(f"Backup copied to ~/{os.path.basename(b)}")
            self.kill_bnet()
            adopted = self.load_state().get("adopted_from")
            if adopted and os.path.islink(adopted) and os.path.realpath(adopted) == os.path.realpath(self.wow_dir) \
                    and os.path.isdir(self.wow_dir) and self.ui.ask(
                        f"The game files were adopted from\n{adopted}\nMove them back there instead of deleting them?", True):
                os.remove(adopted)
                shutil.move(self.wow_dir, adopted)
                self.log(f"Game files moved back to {adopted}")
            for sub in ("prefix", "games", "backups", "downloads", "logs", "app", "tools"):
                shutil.rmtree(os.path.join(self.root, sub), ignore_errors=True)
            for f in ("state.json",):
                try:
                    os.remove(os.path.join(self.root, f))
                except OSError:
                    pass
            try:
                os.rmdir(self.root)            # only if nothing else lives there
            except OSError:
                pass
            for p in [os.path.expanduser("~/.local/share/applications/deckforever.desktop"),
                      os.path.expanduser(f"~/Desktop/{APP_NAME}.desktop")] + self._old_desktop_entries():
                try:
                    os.remove(p)
                except OSError:
                    pass
            self.ui.info("Removed. GE-Proton and CurseForge's own settings (~/.config/CurseForge) were left in place.")

    def status(self):
        fl = self.find_flavor_dir()
        protons = self.installed_protons()
        st = self.load_state()
        backups = self.list_backups()
        return {
            "version": VERSION,
            "root": self.root,
            "proton": st.get("proton") or (protons[-1] if protons else None),
            "prefix": os.path.isdir(os.path.join(self.pfx, "drive_c")),
            "battlenet": self.bnet_installed(),
            "game": fl,
            "backups": len(backups),
            "last_backup": os.path.basename(backups[0]) if backups else None,
            "shortcuts": self.shortcuts_present(),
            "curseforge": self.curseforge_installed(),
            "curseforge_configured": self.curseforge_configured(),
            "existing_installs": [] if fl else self.find_existing_installs(),
        }


def _safe_extract(tf, dest, members=None):
    dest_real = os.path.realpath(dest)
    for m in (members or tf.getmembers()):
        target = os.path.realpath(os.path.join(dest, m.name))
        if not (target == dest_real or target.startswith(dest_real + os.sep)):
            raise EngineError(f"Unsafe path in archive: {m.name}")
    try:
        tf.extractall(dest, members=members, filter="tar")
    except TypeError:  # Python < 3.12
        tf.extractall(dest, members=members)
