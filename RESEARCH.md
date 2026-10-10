# Research: Installing WoW Forever (Battle.net) on Steam Deck

Compiled 2026-10-10. Goal: understand what an easy-to-use installer must do.

## 1. WoW Forever context

- Announced at BlizzCon on 2026-09-12. Beta runs 2026-09-17 to 2026-10-21. Launch is 2026-11-04.
- Included in a standard WoW subscription. Distributed only via Battle.net (Windows/Mac). Not on Steam.
- Blizzard has said there are no plans for official Steam Deck support ("subscription nature makes it a better fit for Battle.net"). Linux/Wine/Proton is an unsupported configuration.
- Native gamepad support ships in the client as "Gamepad (Alpha)", enabled in Settings > controls. Keyboard and mouse are still listed as required.
- Battle.net product codes (from Lutris installer scripts):
  - Retail: `--exec="launch WoW"`
  - Classic: `--exec="launch WoWC"`
  - Forever: `--exec="launch WoWF"`
  - Forever beta install trigger: `--game=wow_classic_beta --install` (launch Battle.net once with this, then clear it)

## 2. How people do it today

### A. Manual (every guide's baseline)
1. Switch to Desktop Mode.
2. Download `Battle.net-Setup.exe` from Blizzard.
3. Steam > Add a Non-Steam Game > pick the .exe.
4. Properties > Compatibility > force GE-Proton (or Proton Experimental).
5. Run it from Steam. Installer puts Battle.net inside the Proton prefix.
6. Re-point the shortcut (or add a new one) to `~/.local/share/Steam/steamapps/compatdata/<appid>/pfx/drive_c/Program Files (x86)/Battle.net/Battle.net.exe`, same Proton.
7. Log in, install WoW Forever from the dropdown, play.
8. Install ConsolePort addon or enable the native gamepad UI.

### B. NonSteamLaunchers (bash script + optional Decky plugin)
Repo: github.com/moraroy/NonSteamLaunchers-On-Steam-Deck. The most relevant prior art. What it does for Battle.net:
- Downloads installer from the official URL:
  `https://www.battle.net/download/getInstallerForGame?os=win&gameProgram=BATTLENET_APP&version=Live`
- Downloads latest GE-Proton / UMU-Proton into `~/.steam/root/compatibilitytools.d/`.
- Runs the installer under Proton through the Steam runtime:
  `"$STEAM_RUNTIME" -- "$proton_dir/proton" run "Battle.net-Setup.exe" --lang=enUS --installpath="C:\Program Files (x86)\Battle.net"`
  with `STEAM_COMPAT_DATA_PATH=.../compatdata/Battle.netLauncher` (its own named prefix folder).
- Polls `pgrep -f Battle.net.exe` until the launcher appears post-install, then kills it (`terminate_processes`).
- Shortcut launch options: `STEAM_COMPAT_DATA_PATH=".../compatdata/Battle.netLauncher/" %command%`
- Adds Steam shortcuts by connecting to Steam's CEF debugger (port 8080, `SharedJSContext`) and calling `SteamClient.Apps.AddShortcut`, `SetShortcutExe`, `SpecifyCompatTool`, `SetCustomArtworkForApp`. Falls back to `proton_experimental` if the requested tool is missing. Requires Steam started with `-dev -cef-enable-debugging -cef-single-process`.
- Computes shortcut appid as `crc32('"' + exe + '"' + appname) | 0x80000000`.
- Uses Python `vdf` library to read `~/.steam/root/userdata/<steamid3>/config/shortcuts.vdf`.

### C. UnifiDeck (Decky Loader plugin, Game Mode only)
Repo: github.com/mubaraknumann/unifideck. Battle.net added in v0.7.4. Used by the Sept 2026 "WoW Forever on Steam Deck" guide. Requires Decky Loader + developer mode sideload. Bundles umu-launcher. Nice UX but a heavier dependency chain.

### D. Lutris / Bottles / Heroic / Faugus (Desktop Mode launchers)
Lutris `battlenet-standard` is the canonical known-good recipe (see section 3). Faugus and Heroic get the most positive 2026 forum reports; Lutris and Bottles get "fiddly first install" reports. All add a layer the end user must understand, so less ideal for a one-click installer.

## 3. Known-good prefix recipe (from Lutris `battlenet-standard`)

- 64-bit prefix.
- Registry: `HKEY_CURRENT_USER\Software\Wine\DXVA2` `backend` = `va`.
- DLL override: `locationapi` = disabled.
- Pre-seed `drive_c/users/<user>/AppData/Roaming/Battle.net/Battle.net.config` before first run:
  ```json
  {
    "Client": {
      "GameLaunchWindowBehavior": "2",
      "GameSearch": { "BackgroundSearch": "true" },
      "HardwareAcceleration": "false",
      "Install": { "DownloadLimitNextPatchInBps": "0" },
      "Sound": { "Enabled": "false" },
      "Streaming": { "StreamingEnabled": "false" }
    }
  }
  ```
  HardwareAcceleration=false fixes the blank/spinning login window. Streaming=false fixes black screen on game start.
- Run `Battle.net-Setup.exe`, do NOT log in on first run, close window, `winekill`.
- Env: `WINE_SIMULATE_WRITECOPY=1` (fixes the Dec 2023 CEF breakage on older Proton; GE-Proton 10-18+ enables writecopy for Battle.net automatically, restored in 10-21).
- Exclude from process tracking: `Agent.exe`, `Battle.net Helper.exe`.
- Must be on ext4/btrfs, never NTFS.

## 4. Proton choice

- GE-Proton latest is the community default. GE-Proton 10-21 (Oct 2025) and later carry the Battle.net writecopy fix. rootandraid.com runs Forever on GE-Proton 11-6.
- proton-ge-custom issue #796: Forever beta `wowb.exe` slowed then core-dumped on GE-Proton 11-7. Resolved after the reporter removed stacked HDR/Wayland/D7VK env vars and a new beta build shipped. Lesson: keep launch options minimal.
- Proton Experimental (bleeding-edge branch) also works and is Valve-maintained.
- `CompatToolMapping` in `config.vdf` must use the installed directory name (e.g. `GE-Proton10-34`), not a bare `GE-Proton`, or Steam silently falls back to bundled Proton.

## 5. Steam integration mechanics an installer must handle

| Thing | Where |
|---|---|
| Non-Steam shortcuts | `~/.steam/root/userdata/<steamid3>/config/shortcuts.vdf` (binary VDF) |
| Per-app compat tool | `~/.steam/root/config/config.vdf` > `InstallConfigStore/Software/Valve/Steam/CompatToolMapping/<appid>` |
| Custom Proton | `~/.steam/root/compatibilitytools.d/<GE-ProtonX-Y>/` |
| Prefix | `~/.local/share/Steam/steamapps/compatdata/<appid>/pfx/` |
| Grid art | `~/.steam/root/userdata/<steamid3>/config/grid/<appid>{,p,_hero,_logo}.png` |
| Controller layout | `~/.steam/root/steamapps/common/Steam Controller Configs/<steamid3>/config/<appname>/controller_neptune.vdf` (or ship via Steam Input template) |

Two ways to write shortcuts:
1. Steam closed: edit `shortcuts.vdf` + `config.vdf` directly with Python `vdf`, then restart Steam. Simple, deterministic.
2. Steam running: CEF debugger JS calls (NSL approach) or a Decky plugin (UnifiDeck approach). Works in Game Mode but more fragile.

Shortcut should be `Battle.net.exe` with launch options `--exec="launch WoWF"` so Steam opens straight into the game. Launching `Wow.exe` directly works but prompts for the password every time; going through Battle.net keeps "remember me".

## 6. Controller and UI

- Forever: Settings > controls > Gamepad (Alpha). Known issues: switching gamepad UI resets Edit Mode layout; gamepad bindings are static since the Oct 1 patch.
- ConsolePort addon is the mature alternative and offers a Steam Deck preset on first launch. Some users run `/console GamePadEnable 1` once with addons off, then enable ConsolePort.
- Steam Input: keep a trackpad-as-mouse mapping available for launcher/login screens. Ship a controller template.
- Login needs typing: suggest dock + keyboard, or Steam's on-screen keyboard (Steam + X).

## 7. Performance

- Low graphics preset, ~40-50 fps reported in beta, ~30 fps in crowded zones. Client uses FSR 1.
- Avoid frame-generation injectors; reports that they can be flagged as cheating.
- Optional: raise UMA frame buffer to 4 GB in BIOS (single-source tip).
- Set Battle.net to close/minimise when a game launches to save RAM.

## 8. Known failure modes to handle in the installer

- Blizzard launcher updates periodically break under Wine (CEF). Fix path: latest GE-Proton; `WINE_SIMULATE_WRITECOPY=1`; last resort delete prefix and reinstall.
- Blank login window: HardwareAcceleration=false (pre-seeded) or `--in-process-gpu`.
- "Blizzard Agent went to sleep" / stuck update: kill Agent.exe, Battle.net.exe, wineserver; delete `drive_c/ProgramData/Battle.net`; reopen and "Scan for Games".
- Auto-login only works once per boot on some setups.
- Shortcut keeps opening the installer: target must be re-pointed to Battle.net.exe.
- Installer window missing: usually missing 32-bit Vulkan/Mesa libs (not an issue on stock SteamOS).
- SteamOS specifics: root filesystem is read-only (no pacman), `deck` user may have no sudo password, Desktop Mode is Wayland in SteamOS 3.8, Flatpak and user-space installs only.

## 9. Legal / distribution

- Do not redistribute `Battle.net-Setup.exe` or game files. Download from the official Blizzard URL at run time.
- User needs their own Battle.net account and active WoW subscription or game time.

## 10. Recommended approach for our installer

**Phase 1: Desktop Mode one-click script**
- Single `install-wow-forever.sh` plus a `.desktop` launcher the user double-clicks after downloading (NSL pattern). No root, no Decky.
- Steps: detect Steam paths and steamid3 > download latest GE-Proton to `compatibilitytools.d` > create a dedicated prefix (`compatdata/WoWForever`) > pre-seed `Battle.net.config` + registry > download and run `Battle.net-Setup.exe --lang=enUS --installpath=...` under Proton > wait for Battle.net.exe, kill it > ask Steam to quit (`steam -shutdown`) > write `shortcuts.vdf` entry for Battle.net.exe with `--exec="launch WoWF"` and `CompatToolMapping` > drop grid art and controller template > relaunch Steam > tell the user to log in and install WoW Forever.
- Progress UI via `zenity` (present on SteamOS) so it feels like an app rather than a terminal.
- Idempotent: re-running repairs rather than duplicates. Include "Repair" (reinstall Battle.net, keep game data) and "Uninstall" actions.

**Phase 2 (optional): Decky plugin** for Game Mode install, modelled on UnifiDeck/NSL-Decky.

## Sources

- https://gamingonsteam.com/2026/09/18/world-of-warcraft-forever-on-steam-deck-easy-install-guide-with-full-controller-support/
- https://steammachinelife.com/wow-forever-on-steam-machine/
- https://rootandraid.com/guides/wow-forever-on-linux/
- https://barrens.chat/viewtopic.php?f=56&t=13371
- https://wofwforever.com/en/guides/wow-forever-gamepad-controller/
- https://expcarry.com/wow-forever-controller-support
- https://steamdeckhq.com/tips-and-guides/how-to-play-world-of-warcraft-on-steam-deck/
- https://github.com/moraroy/NonSteamLaunchers-On-Steam-Deck
- https://github.com/mubaraknumann/unifideck
- https://github.com/GloriousEggroll/proton-ge-custom/issues/796
- https://lutris.net/api/installers/battlenet-standard?format=json
- https://lutris.net/games/install/40020/view (world-of-warcraft-forever-battlenet)
- https://lutris.net/games/install/37008/view (world-of-warcraft-battlenet)
- https://github.com/lutris/docs/blob/master/Battle.Net.md
- https://www.gamingonlinux.com/2023/12/battlenet-broke-in-wine-proton-heres-how-to-fix-for-steam-deck-linux/
- https://www.gamingonlinux.com/2025/10/ge-proton-10-21-brings-fixes-for-blue-protocol-black-desert-battle-net-ubisoft-connect
- https://developer.valvesoftware.com/wiki/Add_Non-Steam_Game
- https://silentinstallhq.com/battle-net-silent-install-how-to-guide/
- https://overkill.wtf/how-to-battlenet-steam-deck-lutris-bottles-native
- https://0xdd.org.ru/post/89684 (2026 Battle.net on SteamOS thread)
- https://www.warcrafttavern.com/forever/news/warcraft-forever-classic-announced-at-blizzcon-2026/

## 11. Addons, settings and backups (added 2026-10-10)

- **Client folder:** during the beta the Forever client lives in `World of Warcraft/_classic_beta_/`. The launch folder name is not confirmed, so the installer auto-detects any `_xxx_` folder (preferring names with "forever", then `_classic_beta_`, then `_classic_era_`) and `WOWF_FLAVOR_DIR` overrides it.
- **Interface number:** 16001 (game version 1.60.1). Classic Era addons (11509) do not load unmodified.
- **Where settings live:** `<client>/WTF/` holds Config.wtf (graphics, CVars), `Account/<ACCOUNT>/SavedVariables/` (account-wide addon data) and `Account/<ACCOUNT>/<Realm>/<Char>/` (per-character layouts, keybinds, macros). Addons live in `<client>/Interface/AddOns/`. Battle.net's own settings are in `drive_c/users/steamuser/AppData/Roaming/Battle.net/Battle.net.config`.
- **Beta bug:** since Sept 18 the beta client (1.60.1.69913) writes `WTF/Account/<acct>/SavedVariables/*.lua` but never reads them back, so addon settings reset every login. Top-level `WTF/SavedVariables/` still loads. A Windows-only helper addon (ForeverSVBridge) worked around it. Reported fixed in a later beta build (per the user, 2026-10-10).
- **Addon sources:** Questie (github.com/Questie/Questie) and ConsolePort (github.com/seblindfors/ConsolePort) publish one multi-flavor zip per release plus a `release.json` (BigWigs packager format) listing `{"flavor": "forever", "interface": 16001}`. The installer uses that file to verify Forever support before extracting. Leatrix Plus/Maps, Bagnon, Auctionator, Baganator and RestedXP ship Forever builds on CurseForge only (file names end in `-forever`), which needs an API key for automated download, so those are supported via direct `url:` entries.
- **Controller:** ConsolePort 3.3.x has explicit Forever fixes (menu items for Forever clients in 3.3.10). Blizzard's built-in Gamepad (Alpha) mode is the no-addon alternative.

Additional sources:
- https://metammo.com/wow-forever/addons
- https://wowforeverguides.com/addons
- https://allthings.how/world-of-warcraft-forever-how-to-install-addons-without-the-curseforge-app/
- https://us.forums.blizzard.com/en/wow/t/2353992 (UI/Addon settings wiped on client restart)
- https://www.curseforge.com/wow/addons/foreversvbridge
- https://github.com/Questie/Questie/releases
- https://github.com/seblindfors/ConsolePort/releases
