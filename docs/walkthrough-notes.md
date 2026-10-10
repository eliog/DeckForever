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
| 9 | The DeckForever window, empty state | (pending) |
| 10 | Install running; the "close Steam?" question; the Game Mode handoff | (pending) |
| 11 | Game Mode library with the Battle.net, CurseForge and DeckForever tiles | (pending, Steam+R1) |
| 12 | Battle.net login; WoW Forever install; first character screen | (pending, Steam+R1) |

Why the download is a zip: Firefox renames downloaded `.desktop` files to `.desktop.download`
(`99-why-zip-firefox-renames-desktop.png`); a zip is left alone and Dolphin extracts it with
two clicks and no typing.
