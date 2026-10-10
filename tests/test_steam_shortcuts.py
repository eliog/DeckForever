#!/usr/bin/env python3
"""Unit tests for lib/steam_shortcuts.py against a synthetic Steam folder."""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from deckforever import steam_shortcuts as s

CONFIG = '''"InstallConfigStore"
{
\t"Software"
\t{
\t\t"Valve"
\t\t{
\t\t\t"Steam"
\t\t\t{
\t\t\t\t"AutoUpdateWindowEnabled"\t\t"0"
\t\t\t\t"CompatToolMapping"
\t\t\t\t{
\t\t\t\t\t"0"
\t\t\t\t\t{
\t\t\t\t\t\t"name"\t\t"proton_experimental"
\t\t\t\t\t\t"config"\t\t""
\t\t\t\t\t\t"priority"\t\t"75"
\t\t\t\t\t}
\t\t\t\t}
\t\t\t\t"Accounts" { "alice" { "SteamID" "76561197960333618" } }
\t\t\t}
\t\t}
\t}
\t"Music" { "x" "y" }
}
'''
LOGIN = '''"users"
{
\t"76561197960277928" { "AccountName" "bob" "MostRecent" "0" }
\t"76561197960333618" { "AccountName" "alice" "MostRecent" "1" }
}
'''


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.root = self.tmp.name
        for d in ("userdata/12345/config", "userdata/67890/config", "config", "compatibilitytools.d/GE-Proton10-30"):
            os.makedirs(os.path.join(r, d))
        open(os.path.join(r, "compatibilitytools.d/GE-Proton10-30/proton"), "w").close()
        self._write("config/config.vdf", CONFIG)
        self._write("config/loginusers.vdf", LOGIN)
        os.environ["STEAM_ROOT"] = r
        os.environ.pop("STEAM_USER_ID3", None)

    def _write(self, rel, text):
        with open(os.path.join(self.root, rel), "w") as f:
            f.write(text)

    def _read(self, rel):
        with open(os.path.join(self.root, rel)) as f:
            return f.read()

    def tearDown(self):
        self.tmp.cleanup()

    def test_binary_roundtrip(self):
        d = {"shortcuts": {"0": {"appid": 2882282138, "AppName": "X", "Exe": '"/bin/true"', "IsHidden": 0,
                                 "tags": {"0": "favorite"}}}}
        self.assertEqual(s.binary_loads(s.binary_dumps(d)), d)

    def test_appid_is_high_bit_unsigned(self):
        a = s.compute_appid("/x/Battle.net.exe", "World of Warcraft: Forever")
        self.assertTrue(a & 0x80000000 and a <= 0xFFFFFFFF)

    def test_picks_most_recent_user(self):
        self.assertEqual(s.steamid3(s.steam_root()), "67890")

    def test_add_update_remove(self):
        s.main(["add", "--name", "WoWF", "--exe", "/x/Battle.net.exe", "--startdir", "/x",
                "--launch-options", 'A="b" %command% --exec="launch WoWF"', "--compat-tool", "GE-Proton10-30"])
        s.main(["add", "--name", "WoWF", "--exe", "/x/Battle.net.exe", "--startdir", "/x",
                "--launch-options", "changed", "--compat-tool", "GE-Proton10-30"])
        data = s.load_shortcuts(s.shortcuts_path(self.root, "67890"))
        self.assertEqual(len(data["shortcuts"]), 1)
        self.assertEqual(data["shortcuts"]["0"]["LaunchOptions"], "changed")
        appid = data["shortcuts"]["0"]["appid"]
        cfg = self._read("config/config.vdf")
        self.assertIn(f'"{appid}"', cfg)
        self.assertEqual(cfg.count('"GE-Proton10-30"'), 1)
        self.assertIn('"proton_experimental"', cfg)          # existing entry preserved
        self.assertIn('"Music" { "x" "y" }', cfg)             # unrelated text untouched
        s.main(["remove", "--name", "WoWF"])
        data = s.load_shortcuts(s.shortcuts_path(self.root, "67890"))
        self.assertEqual(data["shortcuts"], {})
        cfg = self._read("config/config.vdf")
        self.assertNotIn(f'"{appid}"', cfg)

    def test_exe_change_drops_stale_mapping_and_native_has_none(self):
        s.main(["add", "--name", "WoWF", "--exe", "/x/Battle.net.exe", "--startdir", "/x",
                "--compat-tool", "GE-Proton10-30"])
        old_id = s.load_shortcuts(s.shortcuts_path(self.root, "67890"))["shortcuts"]["0"]["appid"]
        self.assertIn(f'"{old_id}"', self._read("config/config.vdf"))
        s.main(["add", "--name", "WoWF", "--exe", "/app/run.sh", "--startdir", "/app",
                "--launch-options", "launch", "--compat-tool", "", "--replace-exe", "/x/Battle.net.exe"])
        data = s.load_shortcuts(s.shortcuts_path(self.root, "67890"))["shortcuts"]
        self.assertEqual(len(data), 1)
        new_id = data["0"]["appid"]
        self.assertNotEqual(new_id, old_id)
        cfg = self._read("config/config.vdf")
        self.assertNotIn(f'"{old_id}"', cfg)      # orphaned mapping removed
        self.assertNotIn(f'"{new_id}"', cfg)      # native shortcut gets no Proton mapping
        self.assertIn('"proton_experimental"', cfg)

    def test_written_file_is_executable(self):
        s.main(["add", "--name", "X", "--exe", "/x", "--startdir", "/"])
        mode = os.stat(s.shortcuts_path(self.root, "67890")).st_mode & 0o777
        self.assertEqual(mode, 0o755)

    def test_same_name_other_exe_is_left_alone(self):
        s.main(["add", "--name", "Battle.net", "--exe", "/theirs/Battle.net.exe", "--startdir", "/theirs"])
        s.main(["add", "--name", "Battle.net", "--exe", "/ours/Battle.net.exe", "--startdir", "/ours"])
        data = s.load_shortcuts(s.shortcuts_path(self.root, "67890"))["shortcuts"]
        self.assertEqual(sorted(v["Exe"] for v in data.values()),
                         ['"/ours/Battle.net.exe"', '"/theirs/Battle.net.exe"'])
        s.main(["remove", "--name", "Battle.net", "--exe-under", "/ours"])
        data = s.load_shortcuts(s.shortcuts_path(self.root, "67890"))["shortcuts"]
        self.assertEqual([v["Exe"] for v in data.values()], ['"/theirs/Battle.net.exe"'])

    def test_prune_removes_dead_entries_mappings_and_art(self):
        import tempfile
        gone = os.path.join(self.root, "steamapps/compatdata/999/pfx/drive_c/x.exe")   # never created
        alive = os.path.join(self.root, "compatibilitytools.d/GE-Proton10-30/proton")  # exists
        s.main(["add", "--name", "Dead", "--exe", gone, "--startdir", "/", "--compat-tool", "GE-Proton10-30"])
        s.main(["add", "--name", "Alive", "--exe", alive, "--startdir", "/", "--compat-tool", "GE-Proton10-30"])
        s.main(["add", "--name", "Elsewhere", "--exe", "/nonexistent/other.exe", "--startdir", "/"])
        dead_id = s.compute_appid(gone, "Dead")
        grid = os.path.join(self.root, "userdata/67890/config/grid"); os.makedirs(grid)
        for fn in (f"{dead_id}p.png", f"{dead_id}_hero.png", "4000000000_logo.png", "440.png", "440p.png"):
            open(os.path.join(grid, fn), "w").close()
        cfg = self._read("config/config.vdf").replace('"CompatToolMapping"\n\t\t\t\t{\n',
              '"CompatToolMapping"\n\t\t\t\t{\n\t\t\t\t\t"3000000000"\n\t\t\t\t\t{\n\t\t\t\t\t\t"name"\t\t"GE-Proton9-1"\n\t\t\t\t\t\t"config"\t\t""\n\t\t\t\t\t\t"priority"\t\t"250"\n\t\t\t\t\t}\n')
        self._write("config/config.vdf", cfg)
        s.main(["prune", "--missing-under", os.path.join(self.root, "steamapps/compatdata")])
        data = s.load_shortcuts(s.shortcuts_path(self.root, "67890"))["shortcuts"]
        self.assertEqual(sorted(v["AppName"] for v in data.values()), ["Alive", "Elsewhere"])  # Elsewhere not under the folder: kept
        cfg = self._read("config/config.vdf")
        self.assertNotIn(f'"{dead_id}"', cfg)
        self.assertNotIn('"3000000000"', cfg)                 # stale mapping with no shortcut
        self.assertIn('"proton_experimental"', cfg)           # Steam-app mapping "0" untouched
        left = sorted(os.listdir(grid))
        self.assertEqual(left, ["440.png", "440p.png"])       # real Steam game art kept

    def test_prune_respects_other_accounts_and_missing_appid(self):
        # second account on the same Deck owns a non-Steam game with a Proton mapping
        other = os.path.join(self.root, "userdata/12345/config/shortcuts.vdf")
        s.save_shortcuts(other, {"shortcuts": {"0": {"AppName": "Theirs", "Exe": '"/bin/sh"', "StartDir": '"/"'}}})
        their_id = s.compute_appid("/bin/sh", "Theirs")           # entry has no appid field: computed
        cfg = self._read("config/config.vdf").replace('"CompatToolMapping"\n\t\t\t\t{\n',
              '"CompatToolMapping"\n\t\t\t\t{\n\t\t\t\t\t"%d"\n\t\t\t\t\t{\n\t\t\t\t\t\t"name"\t\t"GE-Proton10-30"\n\t\t\t\t\t\t"config"\t\t""\n\t\t\t\t\t\t"priority"\t\t"250"\n\t\t\t\t\t}\n' % their_id)
        self._write("config/config.vdf", cfg)
        grid = os.path.join(self.root, "userdata/67890/config/grid"); os.makedirs(grid)
        open(os.path.join(grid, f"{their_id}p.png"), "w").close()
        s.main(["add", "--name", "Mine", "--exe", "/bin/true", "--startdir", "/"])
        s.main(["prune"])
        self.assertIn(f'"{their_id}"', self._read("config/config.vdf"))   # other account's mapping kept
        self.assertTrue(os.path.exists(os.path.join(grid, f"{their_id}p.png")))

    def test_dedupe_scoped_to_our_folder(self):
        d = {"shortcuts": {
            "0": {"appid": 1, "AppName": "Firefox", "Exe": '"/usr/bin/firefox"', "LaunchOptions": "-P a"},
            "1": {"appid": 2, "AppName": "Firefox", "Exe": '"/usr/bin/firefox"', "LaunchOptions": "-P b"},
            "2": {"appid": 3, "AppName": "Battle.net", "Exe": '"/home/x/Games/WoWForever/p/b.exe"'},
            "3": {"appid": 4, "AppName": "Battle.net", "Exe": '"/home/x/Games/WoWForever/p/b.exe"'},
        }}
        removed = s.dedupe(d, only_under="/home/x/Games/WoWForever")
        self.assertEqual(removed, [4])
        self.assertEqual([v["appid"] for v in d["shortcuts"].values()], [1, 2, 3])   # both Firefox kept

    def test_backup_names_are_unique_and_capped(self):
        p = s.shortcuts_path(self.root, "67890")
        for i in range(13):
            s.main(["add", "--name", f"N{i}", "--exe", "/bin/true", "--startdir", "/"])
        baks = [f for f in os.listdir(os.path.dirname(p)) if f.startswith("shortcuts.vdf.bak-")]
        self.assertEqual(len(baks), 10)

    def test_no_overlay_flag(self):
        s.main(["add", "--name", "CF", "--exe", "/x/cf.AppImage", "--startdir", "/x", "--no-overlay"])
        s.main(["add", "--name", "BN", "--exe", "/x/b.exe", "--startdir", "/x"])
        d = s.load_shortcuts(s.shortcuts_path(self.root, "67890"))["shortcuts"]
        self.assertEqual({v["AppName"]: v["AllowOverlay"] for v in d.values()}, {"CF": 0, "BN": 1})

    def test_remove_keep_exe_drops_only_stale_target(self):
        s.main(["add", "--name", "CF", "--exe", "/r/tools/CurseForge.AppImage", "--startdir", "/r/tools"])
        s.main(["add", "--name", "CF", "--exe", "/r/tools/launch-curseforge.sh", "--startdir", "/r/tools"])
        s.main(["add", "--name", "CF", "--exe", "/elsewhere/cf", "--startdir", "/"])      # someone else's
        s.main(["remove", "--name", "CF", "--exe-under", "/r", "--keep-exe", "/r/tools/launch-curseforge.sh"])
        d = s.load_shortcuts(s.shortcuts_path(self.root, "67890"))["shortcuts"]
        self.assertEqual(sorted(v["Exe"] for v in d.values()),
                         ['"/elsewhere/cf"', '"/r/tools/launch-curseforge.sh"'])

    def test_dedupe_keeps_first_copy(self):
        d = {"shortcuts": {
            "0": {"appid": 1, "AppName": "A", "Exe": '"/a"'},
            "1": {"appid": 2, "AppName": "B", "Exe": '"/b"'},
            "2": {"appid": 3, "AppName": "A", "Exe": '"/a"'},      # duplicate of 0
            "3": {"appid": 4, "AppName": "A", "Exe": '"/other"'},  # same name, different exe: keep
        }}
        removed = s.dedupe(d)
        self.assertEqual(removed, [3])
        self.assertEqual([v["appid"] for v in d["shortcuts"].values()], [1, 2, 4])
        self.assertEqual(list(d["shortcuts"].keys()), ["0", "1", "2"])

    def test_creates_mapping_block_when_missing(self):
        t = '"InstallConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"x"\t\t"y"\n\t\t\t}\n\t\t}\n\t}\n}\n'
        out = s.set_compat_tool(t, 123, "GE-Proton10-30")
        self.assertIn('"CompatToolMapping"', out)
        self.assertIn('"123"', out)
        self.assertEqual(out, s.set_compat_tool(out, 123, "GE-Proton10-30"))  # idempotent


if __name__ == "__main__":
    unittest.main()
