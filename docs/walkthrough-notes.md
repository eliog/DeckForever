# Walkthrough notes (source material for the illustrated install guide)

Screens are in `docs/screenshots/`, numbered in the order a new user meets them.

## Desktop Mode controls on the Steam Deck (say this early in the guide)

- **Right trackpad** moves the mouse pointer.
- **R2** (right trigger) = left click. **L2** (left trigger) = right click.
- A long press on the touchscreen also opens the right-click menu.
- **Steam + X** opens the on-screen keyboard (it works best in Game Mode; in Desktop Mode
  taps can fall through to the window underneath).
- **Steam + R1** takes a screenshot in Game Mode.

## Steps and matching screenshots

| # | Screen | File |
|---|---|---|
| 1 | Hold the power button, choose *Switch to Desktop* | `01-power-menu.jpg` |
| 2 | The desktop (after install the DeckForever icon sits top-left) | `02-desktop.png` |
| 3 | Firefox: github.com/eliog/DeckForever/releases | `03-releases-page.png` |
| 4 | The Assets list; tap `DeckForever-installer.zip` | `04-release-assets.png` |
| 5 | Dolphin (taskbar folder icon) > Downloads: the zip | `05-dolphin-downloads-zip.png` |
| 6 | Right-click (L2) the zip > *Extract* > *Extract here* | `06-extract-menu.png` |
| 7 | Double-click `DeckForever.desktop`; Dolphin asks "What do you wish to do with this file?": choose *Launch* | `07-dolphin-launch-prompt.png` |
| 8 | KDE warning "This will start the program: DeckForever": choose *Continue* (both prompts appear only the first time) | `08-kde-trust-prompt.png` |
| 9 | The DeckForever window, empty state; press *Install* | `09-app-window.png` |
| 10 | Install running (GE-Proton download and unpack) | `10-install-progress.png` |
| 10b | Steam asks to install "Steam Linux Runtime 4.0" (first time only): click Install there | (not captured) |
| 11 | Blizzard's Battle.net installer running on its own; do not log in | `11-battlenet-installing.png` |
| 12 | "Also install CurseForge?": Yes | `12-curseforge-question.png` |
| 13 | "Steam has to close for a moment": Yes | `13-close-steam-question.png` |
| 14 | "Switch to Game Mode now?" with the login steps: Yes | `14-game-mode-offer.png` |
| 15 | Game Mode library, Non-Steam tab: Battle.net, CurseForge, DeckForever tiles | `15-game-mode-library.jpg` |
| 16 | Battle.net login (type with Steam + X) | `16-battlenet-login.jpg` |
| 17 | Battle.net: World of Warcraft, Game Version "WoW: Forever", press Install (account panel cropped) | `17-battlenet-forever-install.png` |
| 18 | Battle.net's "Unsupported" handheld notice: press Install anyway | `18-battlenet-unsupported-notice.png` |
| 19 | "WoW: Forever Installation": keep the default folder, Start Install | `19-wow-forever-install-dialog.jpg` |
| 20 | Installing; playable before the download completes | `20-wow-forever-installing.png` |
| 21 | First character screen: it runs | `21-character-screen.jpg` |

Privacy: Battle.net screenshots are cropped to remove the account name and friends list before
they go into the repo. Never commit a shot with a BattleTag, e-mail or friends visible.

Reference shot for the troubleshooting section: `98-battlenet-patch-service-error.png` (what you see
when the Steam runtime is missing; fixed in 0.3.1).

Why the download is a zip: Firefox renames downloaded `.desktop` files to `.desktop.download`
(`99-why-zip-firefox-renames-desktop.png`); a zip is left alone and Dolphin extracts it with
two clicks and no typing.
