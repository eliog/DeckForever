#!/usr/bin/env python3
"""Engine tests that run anywhere: backup/restore, flavor detection, adopt, status. No Proton, no Steam."""
import os, sys, tarfile, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from deckforever import engine as eng


class RecordingUI(eng.BaseUI):
    def __init__(self, answers=None):
        self.answers = answers or {}
        self.logs, self.infos = [], []
    def log(self, m): self.logs.append(m)
    def ask(self, q, default=True):
        for k, v in self.answers.items():
            if k in q:
                return v
        return default
    def info(self, m): self.infos.append(m)


def touch(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.home = os.path.join(t, "home")
        self.steam = os.path.join(self.home, ".local/share/Steam")
        os.makedirs(os.path.join(self.steam, "userdata/1/config"))
        os.makedirs(os.path.join(self.steam, "compatibilitytools.d/GE-Proton10-30"))
        touch(os.path.join(self.steam, "compatibilitytools.d/GE-Proton10-30/proton"))
        os.environ["HOME"] = self.home
        for k in ("WOWF_FLAVOR_DIR", "WOWF_ADOPT_FROM", "WOWF_PROTON"):
            os.environ.pop(k, None)
        self.ui = RecordingUI()
        self.e = eng.Engine(self.ui, root=os.path.join(t, "root"), steam_root=self.steam)
        for d in (self.e.backups, self.e.logs, self.e.downloads, self.e.bnet_cfg_dir):
            os.makedirs(d, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def make_client(self, wow_dir, flavor="_classic_beta_"):
        fl = os.path.join(wow_dir, flavor)
        touch(os.path.join(fl, "WTF/Config.wtf"), "SET x 1")
        touch(os.path.join(fl, "WTF/Account/ACC/SavedVariables/Questie.lua"))
        touch(os.path.join(fl, "Interface/AddOns/SomeAddon/SomeAddon.toc"))
        touch(os.path.join(fl, "Cache/junk.bin"))
        touch(os.path.join(fl, "WowB.exe"))
        touch(os.path.join(wow_dir, "Data/data.bin"))
        return fl

    def test_flavor_detection_prefers_beta_then_exe(self):
        self.assertIsNone(self.e.find_flavor_dir())
        self.make_client(self.e.wow_dir, "_retail_")
        self.assertTrue(self.e.find_flavor_dir().endswith("_retail_"))
        self.make_client(self.e.wow_dir, "_classic_beta_")
        self.assertTrue(self.e.find_flavor_dir().endswith("_classic_beta_"))
        os.environ["WOWF_FLAVOR_DIR"] = "_retail_"
        self.assertTrue(self.e.find_flavor_dir().endswith("_retail_"))

    def test_backup_and_restore(self):
        fl = self.make_client(self.e.wow_dir)
        touch(os.path.join(self.e.bnet_cfg_dir, "Battle.net.config"), "{}")
        out = self.e.backup()
        with tarfile.open(out) as tf:
            names = tf.getnames()
        self.assertIn("WTF/Config.wtf", names)
        self.assertIn("Interface/AddOns/SomeAddon/SomeAddon.toc", names)
        self.assertIn("Battle.net.config", names)
        self.assertFalse(any("Cache" in n for n in names))
        import shutil
        shutil.rmtree(os.path.join(fl, "WTF"))
        os.remove(os.path.join(self.e.bnet_cfg_dir, "Battle.net.config"))
        self.e.restore(out)
        self.assertTrue(os.path.isfile(os.path.join(fl, "WTF/Config.wtf")))
        self.assertTrue(os.path.isfile(os.path.join(self.e.bnet_cfg_dir, "Battle.net.config")))
        self.assertEqual(self.e.list_backups(), [out])

    def test_restore_rejects_unsafe_archive(self):
        self.make_client(self.e.wow_dir)
        bad = os.path.join(self.tmp.name, "bad.tar.gz")
        with tarfile.open(bad, "w:gz") as tf:
            ti = tarfile.TarInfo("../evil.txt"); ti.size = 0
            tf.addfile(ti)
        with self.assertRaises(eng.EngineError):
            self.e.restore(bad)

    def test_adopt_from_nonsteamlaunchers(self):
        nsl = os.path.join(self.steam, "steamapps/compatdata/NonSteamLaunchers/pfx/drive_c/Program Files (x86)/World of Warcraft")
        self.make_client(nsl)
        # same folder reachable through a second prefix must be listed once
        other = os.path.join(self.steam, "steamapps/compatdata/999/pfx")
        os.makedirs(other)
        os.symlink(os.path.dirname(os.path.dirname(os.path.dirname(nsl))), os.path.join(other, "drive_c"))
        found = self.e.find_existing_installs()
        self.assertEqual(found, [os.path.realpath(nsl)])
        self.e.adopt()
        self.assertTrue(os.path.islink(nsl))
        self.assertTrue(os.path.isfile(os.path.join(self.e.wow_dir, "_classic_beta_/WTF/Config.wtf")))
        self.assertEqual(self.e.find_existing_installs(), [])
        self.assertEqual(len(self.e.list_backups()), 1)        # backed up before moving
        with self.assertRaises(eng.EngineError):              # second adopt refuses: folder not empty
            self.e.adopt(nsl)

    def test_adopt_declined_is_cancelled(self):
        nsl = os.path.join(self.steam, "steamapps/compatdata/NonSteamLaunchers/pfx/drive_c/Program Files (x86)/World of Warcraft")
        self.make_client(nsl)
        self.ui.answers["Move it into"] = False
        with self.assertRaises(eng.Cancelled):
            self.e.adopt()
        self.assertFalse(os.path.islink(nsl))

    def test_status_and_proton_sorting(self):
        os.makedirs(os.path.join(self.steam, "compatibilitytools.d/GE-Proton9-27"))
        touch(os.path.join(self.steam, "compatibilitytools.d/GE-Proton9-27/proton"))
        self.assertEqual(self.e.installed_protons(), ["GE-Proton9-27", "GE-Proton10-30"])
        st = self.e.status()
        self.assertEqual(st["proton"], "GE-Proton10-30")
        self.assertFalse(st["battlenet"])
        self.assertIsNone(st["game"])
        self.assertEqual(st["existing_installs"], [])

    def test_required_runtime_resolution(self):
        ge = os.path.join(self.steam, "compatibilitytools.d/GE-Proton10-30")
        touch(os.path.join(ge, "toolmanifest.vdf"), '"manifest"\n{\n  "require_tool_appid" "4183110"\n}\n')
        self.e.proton_name = "GE-Proton10-30"
        self.assertIsNone(self.e.required_runtime())             # runtime app not installed
        cmd, _env = self.e.proton_command("wineboot")
        self.assertEqual(cmd[0], os.path.join(ge, "proton"))       # falls back to a direct run
        touch(os.path.join(self.steam, "steamapps/appmanifest_4183110.acf"),
              '"AppState"\n{\n\t"appid"\t\t"4183110"\n\t"installdir"\t\t"SteamLinuxRuntime_medic"\n}\n')
        run = os.path.join(self.steam, "steamapps/common/SteamLinuxRuntime_medic/run")
        touch(run); os.chmod(run, 0o755)
        self.assertEqual(self.e.required_runtime(), run)
        cmd, env = self.e.proton_command("wineboot")
        self.assertEqual(cmd[:2], [run, "--"])
        self.assertEqual(env["STEAM_COMPAT_DATA_PATH"], self.e.prefix)

    def test_shortcut_specs(self):
        self.e.proton_name = "GE-Proton10-30"
        specs = self.e.shortcut_specs()
        names = [x[0] for x in specs]
        self.assertEqual(names, [eng.SHORTCUT_BNET, eng.APP_NAME])
        self.assertTrue(specs[-1][1].endswith("run.sh")); self.assertEqual(specs[-1][4], "")
        self.assertTrue(specs[0][5]); self.assertFalse(specs[-1][5])      # overlay on for Proton, off for native
        # a foreign "Battle.net" shortcut (another launcher) forces the alternate name
        from deckforever import steam_shortcuts as s
        s.save_shortcuts(s.shortcuts_path(self.steam, "1"), {"shortcuts": {"0": {
            "appid": 1, "AppName": "Battle.net", "Exe": '"/elsewhere/Battle.net.exe"', "StartDir": '"/"'}}})
        self.assertEqual(self.e.main_shortcut_name(), eng.SHORTCUT_BNET_ALT)
        wow = specs[0]
        self.assertEqual(wow[1], self.e.bnet_exe)
        self.assertIn('STEAM_COMPAT_DATA_PATH="%s" %%command%%' % self.e.prefix, wow[3])
        self.assertNotIn("--exec", wow[3])                 # user presses Play inside Battle.net
        self.assertEqual(wow[4], "GE-Proton10-30")

    def test_pick_proton_asset_matches_architecture(self):
        names = ["GE-Proton11-7-aarch64.tar.gz", "GE-Proton11-7-aarch64.sha512sum",
                 "GE-Proton11-7-x86_64.tar.gz", "GE-Proton11-7-x86_64.sha512sum", "release.json"]
        self.assertEqual(eng.Engine.pick_proton_asset(names, "x86_64"),
                         ("GE-Proton11-7-x86_64.tar.gz", "GE-Proton11-7-x86_64.sha512sum"))
        self.assertEqual(eng.Engine.pick_proton_asset(names, "aarch64")[0], "GE-Proton11-7-aarch64.tar.gz")
        old = ["GE-Proton9-20.tar.gz", "GE-Proton9-20.sha512sum"]
        self.assertEqual(eng.Engine.pick_proton_asset(old, "x86_64"), ("GE-Proton9-20.tar.gz", "GE-Proton9-20.sha512sum"))
        with self.assertRaises(eng.EngineError):
            eng.Engine.pick_proton_asset(["GE-Proton11-7-aarch64.tar.gz"], "x86_64")

    def test_game_mode_command_shape(self):
        cmd = eng.Engine.game_mode_command()
        if cmd:                                   # depends on what the host has; just check the shape
            self.assertTrue(any(k in " ".join(cmd) for k in ("steamosctl", "steamos-session-select", "qdbus")))

    def test_restore_cancel_does_not_restore(self):
        fl = self.make_client(self.e.wow_dir)
        self.e.backup()
        import shutil
        shutil.rmtree(os.path.join(fl, "WTF"))
        self.ui.pick_file = lambda *a: None               # user pressed Cancel in the chooser
        with self.assertRaises(eng.Cancelled):
            self.e.restore()
        self.assertFalse(os.path.isdir(os.path.join(fl, "WTF")))
        self.ui.pick_file = lambda *a: NotImplemented     # no chooser (CLI): newest backup
        self.e.restore()
        self.assertTrue(os.path.isfile(os.path.join(fl, "WTF/Config.wtf")))

    def test_rescue_game_folder_before_wipe(self):
        inside = self.e.wow_link                         # real dir inside the prefix (old layout)
        touch(os.path.join(inside, "_classic_beta_/WTF/Config.wtf"), "SET x 1")
        touch(os.path.join(inside, "Data/data.bin"))
        self.e.rescue_game_folder()
        self.assertFalse(os.path.exists(inside))
        self.assertTrue(os.path.isfile(os.path.join(self.e.wow_dir, "_classic_beta_/WTF/Config.wtf")))
        touch(os.path.join(inside, "Data/other.bin"))     # a second copy must not be clobbered
        with self.assertRaises(eng.EngineError):
            self.e.rescue_game_folder()

    def test_missing_steam_is_a_normal_error(self):
        empty_home = os.path.join(self.tmp.name, "emptyhome"); os.makedirs(empty_home)
        os.environ["HOME"] = empty_home                                  # no ~/.steam, ~/.local/share/Steam
        os.environ["STEAM_ROOT"] = os.path.join(self.tmp.name, "nowhere")
        try:
            e = eng.Engine(self.ui, root=os.path.join(self.tmp.name, "r2"), steam_root=None)
            with self.assertRaises(eng.EngineError):
                _ = e.steam_root
        finally:
            os.environ.pop("STEAM_ROOT", None)
            os.environ["HOME"] = self.home

    def test_install_continues_when_adopt_refuses(self):
        nsl = os.path.join(self.steam, "steamapps/compatdata/NonSteamLaunchers/pfx/drive_c/Program Files (x86)/World of Warcraft")
        self.make_client(nsl)
        touch(os.path.join(self.e.wow_dir, "Data/partial.bin"))      # Battle.net already started downloading
        calls = []
        for name in ("preflight", "self_install", "select_proton", "init_prefix", "install_battlenet",
                     "write_shortcuts", "save_state"):
            setattr(self.e, name, lambda *a, _n=name, **k: calls.append(_n))
        self.ui.answers["Switch to Game Mode"] = False
        self.e.install(open_bnet=False)
        self.assertIn("write_shortcuts", calls)                        # did not abort on the adopt error
        self.assertTrue(any("not adopted" in m for m in self.ui.logs))

    def test_proton_selection_prefers_state_then_minimum_version(self):
        for n in ("GE-Proton8-25", "GE-Proton10-30"):
            touch(os.path.join(self.steam, f"compatibilitytools.d/{n}/proton"))
            os.makedirs(os.path.join(self.steam, f"compatibilitytools.d/{n}/files"), exist_ok=True)
        self.e.proton_name = "GE-Proton8-25"; self.e.save_state()      # shortcut currently uses 8-25
        self.e.select_proton()
        self.assertEqual(self.e.proton_name, "GE-Proton8-25")          # keep what the shortcut uses
        os.remove(self.e.state_file)
        self.e.select_proton()
        self.assertEqual(self.e.proton_name, "GE-Proton10-30")         # newest installed, new enough
        import shutil
        shutil.rmtree(os.path.join(self.steam, "compatibilitytools.d/GE-Proton10-30"))
        self.e.install_latest_proton = lambda: setattr(self.e, "proton_name", "GE-Proton11-7-x86_64")
        self.e.select_proton()
        self.assertEqual(self.e.proton_name, "GE-Proton11-7-x86_64")   # 8-25 too old: downloaded

    def test_proton_unpack_is_atomic(self):
        import tarfile, io
        tagdir = os.path.join(self.tmp.name, "mk/GE-Proton11-9-x86_64")
        touch(os.path.join(tagdir, "proton")); touch(os.path.join(tagdir, "files/bin/wine"))
        touch(os.path.join(tagdir, "toolmanifest.vdf"), '"manifest" {}')
        good = os.path.join(self.tmp.name, "good.tar.gz")
        with tarfile.open(good, "w:gz") as tf:
            tf.add(tagdir, arcname="GE-Proton11-9-x86_64")
        bad = os.path.join(self.tmp.name, "bad.tar.gz")           # proton present but no files/
        with tarfile.open(bad, "w:gz") as tf:
            ti = tarfile.TarInfo("GE-Proton11-8-x86_64/proton"); ti.size = 0; tf.addfile(ti, io.BytesIO(b""))
        rel = {"tag_name": "GE-Proton11-9", "assets": [
            {"name": "GE-Proton11-9-x86_64.tar.gz", "browser_download_url": "file://" + good}]}
        self.e.github_json = lambda url: rel
        self.e.download = lambda url, dest, label: __import__("shutil").copy(url[7:], dest)
        self.e.pick_proton_asset = lambda names: eng.Engine.pick_proton_asset(names, "x86_64")
        os.makedirs(self.e.downloads, exist_ok=True)
        self.assertEqual(self.e.install_latest_proton(), "GE-Proton11-9-x86_64")
        self.assertTrue(self.e._proton_ok("GE-Proton11-9-x86_64"))
        rel["tag_name"] = "GE-Proton11-8"; rel["assets"][0]["name"] = "GE-Proton11-8-x86_64.tar.gz"
        rel["assets"][0]["browser_download_url"] = "file://" + bad
        with self.assertRaises(eng.EngineError):
            self.e.install_latest_proton()
        self.assertFalse(os.path.exists(os.path.join(self.steam, "compatibilitytools.d/GE-Proton11-8-x86_64")))
        self.assertFalse(any(d.startswith(".wowf-unpack") for d in os.listdir(os.path.join(self.steam, "compatibilitytools.d"))))

    def test_uninstall_refuses_foreign_root(self):
        foreign = os.path.join(self.tmp.name, "sdcard"); touch(os.path.join(foreign, "precious.txt"))
        e = eng.Engine(self.ui, root=foreign, steam_root=self.steam)
        e.preflight = lambda: None
        e.remove_shortcuts = lambda: None
        self.ui.answers["Remove the Steam shortcut"] = False
        e.uninstall()
        self.assertTrue(os.path.isfile(os.path.join(foreign, "precious.txt")))

    def test_curseforge_configure_and_shortcut(self):
        fl = self.make_client(self.e.wow_dir)
        # no AppImage yet: no CurseForge shortcut
        self.e.proton_name = "GE-Proton10-30"
        self.assertEqual([x[0] for x in self.e.shortcut_specs()], [eng.SHORTCUT_BNET, eng.APP_NAME])
        # fake a valid AppImage download
        img = b"\x7fELF\x02\x01\x01\x00AI\x02" + b"\0" * (60 * 1024 * 1024)
        self.e.download = lambda url, dest, label: open(dest, "wb").write(img)
        self.e.install_curseforge()
        self.assertTrue(self.e.curseforge_installed())
        self.assertEqual([x[0] for x in self.e.shortcut_specs()], [eng.SHORTCUT_BNET, eng.SHORTCUT_CF, eng.APP_NAME])
        self.assertEqual(self.e.shortcut_specs()[1][4], "")          # native, no Proton
        self.assertFalse(self.e.shortcut_specs()[1][5])              # Electron: Steam overlay off
        self.assertEqual(self.e.shortcut_specs()[1][1], self.e.cf_launcher)   # via the env-scrubbing wrapper
        with open(self.e.cf_launcher) as f:
            wrapper = f.read()
        self.assertIn("unset LD_PRELOAD LD_LIBRARY_PATH", wrapper)
        self.assertIn("exec ./CurseForge.AppImage", wrapper)
        self.assertTrue(os.access(self.e.cf_launcher, os.X_OK))
        # configure: record written, storage points at it, idempotent
        self.e.cf_config = os.path.join(self.home, ".config/CurseForge")
        self.assertFalse(self.e.curseforge_configured())
        self.assertTrue(self.e.configure_curseforge())
        self.assertTrue(self.e.curseforge_configured())
        import json
        recs = json.load(open(self.e.cf_instances_file()))
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["gameVersionTypeId"], eng.CF_FOREVER_TYPE_ID)
        self.assertEqual(recs[0]["installPath"], fl.rstrip("/") + "/")
        st = json.load(open(os.path.join(self.e.cf_config, "storage.json")))
        self.assertIn(recs[0]["guid"], st["internal-last-game-instances"])
        self.e.configure_curseforge()
        self.assertEqual(len(json.load(open(self.e.cf_instances_file()))), 1)
        # a bad download is rejected and leaves nothing behind
        self.e.download = lambda url, dest, label: open(dest, "wb").write(b"<html>oops</html>")
        with self.assertRaises(eng.EngineError):
            self.e.install_curseforge(update=True)
        self.assertTrue(self.e.curseforge_installed())               # previous good file kept

    def test_artwork_files_named_after_appids(self):
        from deckforever import art, steam_shortcuts as ss
        self.e.proton_name = "GE-Proton10-30"
        specs = self.e.shortcut_specs()
        made = []
        def fake_render(kind, theme, path):
            open(path, "wb").write(b"\x89PNG" + theme["title"].encode()); made.append(kind)
        orig = art.render_set
        art.render_set = lambda key, grid, appid: orig(key, grid, appid, renderer=fake_render)
        art.available = lambda: True
        try:
            icons = self.e.apply_artwork(specs)
        finally:
            art.render_set = orig
        grid = self.e.grid_dir()
        for name, exe, *_ in specs:
            appid = ss.compute_appid(exe, name)
            for fn in (f"{appid}p.png", f"{appid}.png", f"{appid}_hero.png", f"{appid}_logo.png", f"{appid}_icon.png"):
                self.assertTrue(os.path.isfile(os.path.join(grid, fn)), fn)
            self.assertEqual(icons[name], os.path.join(grid, f"{appid}_icon.png"))
        self.assertEqual(sorted(set(made)), ["hero", "icon", "logo", "p", "wide"])

    def test_require_flavor_message(self):
        with self.assertRaises(eng.EngineError) as cm:
            self.e.require_flavor()
        self.assertIn("not installed yet", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
