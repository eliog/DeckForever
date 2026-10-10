"""DeckForever command-line front end (used over SSH or when no display is available)."""
import os
import sys

from . import engine as eng


class CliUI(eng.BaseUI):
    def __init__(self):
        self.assume_yes = bool(eng.env("ASSUME_YES"))

    def step(self, msg):
        print("==> " + msg, flush=True)

    def ask(self, question, default=True):
        if self.assume_yes or not sys.stdin.isatty():
            print(f"{question}\n-> auto: {'yes' if default else 'no'}")
            return default
        ans = input(f"{question} [{'Y/n' if default else 'y/N'}] ").strip().lower()
        return default if not ans else ans.startswith("y")

    def choose(self, title, options):
        print(title)
        for i, (_v, label) in enumerate(options, 1):
            print(f"  {i}) {label}")
        if self.assume_yes or not sys.stdin.isatty():
            return options[0][0]
        ans = input("> ").strip()
        try:
            return options[int(ans) - 1][0]
        except (ValueError, IndexError):
            return None

    def pick_file(self, title, folder, pattern):
        return None  # engine falls back to the newest backup

    def info(self, msg):
        print("\n" + msg + "\n")

    def error(self, msg):
        print("\nERROR: " + msg + "\n", file=sys.stderr)


USAGE = """usage: python3 -m deckforever [command] [options]

  (no command)   open the window, or the text menu when there is no display
  install        install/repair GE-Proton, Battle.net and the Steam shortcut
  adopt [dir]    move an existing WoW install (NonSteamLaunchers etc.) into our folder
  curseforge     install/update CurseForge, add its Steam shortcut, point it at the game
  backup         back up WTF + Interface + Battle.net.config (settings, keybinds, addons)
  restore [file] restore a backup (latest if no file given)
  reinstall      fresh reinstall: backup -> wipe prefix -> install -> restore
  update-proton  download the newest GE-Proton and switch shortcuts to it
  status         show what is installed
  uninstall      remove Steam shortcuts and optionally the whole folder

options: --force-battlenet  --no-bnet (do not open Battle.net after install)
env:     DECKFOREVER_ROOT DECKFOREVER_PROTON DECKFOREVER_FLAVOR_DIR DECKFOREVER_ADOPT_FROM DECKFOREVER_ASSUME_YES
         (the older WOWF_* spellings still work)
"""


def main(argv):
    ui = CliUI()
    e = eng.Engine(ui)
    cmd = argv[0] if argv else "status"
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    try:
        if cmd in ("-h", "--help", "help"):
            print(USAGE)
        elif cmd == "install":
            e.install(force_bnet="--force-battlenet" in flags, open_bnet="--no-bnet" not in flags)
        elif cmd == "adopt":
            e.preflight(); e.adopt(args[0] if args else None)
        elif cmd == "curseforge":
            e.curseforge(update="--update" in flags)
        elif cmd == "backup":
            e.preflight(); print(e.backup())
        elif cmd == "restore":
            e.preflight(); e.restore(args[0] if args else None)
        elif cmd == "reinstall":
            e.reinstall()
        elif cmd == "update-proton":
            e.update_proton()
        elif cmd == "uninstall":
            e.uninstall()
        elif cmd == "status":
            st = e.status()
            print(f"{eng.APP_NAME} v{st['version']}")
            print(f"  Install folder : {st['root']}")
            print(f"  GE-Proton      : {st['proton'] or 'none'}")
            print(f"  Prefix         : {'present' if st['prefix'] else 'missing'}")
            print(f"  Battle.net     : {'installed' if st['battlenet'] else 'missing'}")
            print(f"  WoW client     : {st['game'] or 'not installed'}")
            if st["existing_installs"]:
                print(f"  Adoptable      : {', '.join(st['existing_installs'])}")
            print(f"  Backups        : {st['backups']} ({st['last_backup'] or '-'})")
            print(f"  CurseForge     : {'installed' + (' + configured' if st['curseforge_configured'] else '') if st['curseforge'] else 'not installed'}")
            print(f"  Steam shortcut : {'present' if st['shortcuts'] else 'missing'}")
        else:
            print(USAGE)
            return 2
    except eng.Cancelled:
        print("Cancelled.")
        return 130
    except eng.EngineError as err:
        ui.error(str(err))
        return 1
    return 0
