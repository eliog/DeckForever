# ADDON.md: DeckForever addon (Steam Deck settings for World of Warcraft: Forever)

Specification and collected facts for a **separate project**: an in-game addon that applies and
manages Steam Deck tuned settings. Written 2026-10-10 from research on the Forever beta
(client 1.60.1, interface 16001). Re-verify the client facts against the launch client
(Nov 4, 2026). Companion data: `reference/deck-settings-notes.md` and
`reference/config-forever-16001-first-run.wtf` in this repo.

Names: repository **DeckForeverAddon**; CurseForge/Wago listing **DeckForever**; addon folder and
TOC name `DeckForever` (distinct from the installer repo, which is `DeckForever` too, so the addon
repo carries the `Addon` suffix). Slash command `/deckforever`.

## 1. Purpose and scope

- One-click, in-game presets for the Steam Deck: **Performance** (60 fps target),
  **Battery** (40 fps target), **Quality** (60 fps, nicer visuals), and **Restore previous**.
- Everything is applied live through console variables (CVars). No file editing, no restart,
  no desktop trip.
- Defensive by design: never assumes a CVar exists; validates against the running client and
  reports what it skipped.
- Distributed through CurseForge (and GitHub releases) like any other addon; the Deck already
  has CurseForge installed by the DeckForever installer.

Non-goals: installing Battle.net or the game (DeckForever (the installer) does that), addon management
(CurseForge does that), controller key binding (the native Gamepad UI / ConsolePort do that),
anything that needs a client restart (renderer API, window mode: both are already right on
the Deck by default).

## 2. Facts about the Forever client (as of the beta)

| Item | Value | Confidence |
|---|---|---|
| Client folder | `World of Warcraft/_classic_beta_/` (beta); launch folder may differ | confirmed (beta) |
| Executable | `WowB.exe` | confirmed (beta) |
| TOC `## Interface:` | `16001` | confirmed (Questie, ConsolePort, Bagnon TOCs) |
| Multi-TOC suffix | addons list all flavors in one TOC (`## Interface: 120100, 16001, ...`); a `_Forever` suffix is not required | confirmed |
| Engine generation | modern engine (same CVar family as retail 11.x/12.x and Classic Era 1.15) | confirmed by Config.wtf |
| First-run auto-detect on the Deck | `graphicsQuality 4`, `GxApi D3D12`, `vsync 1`, `GxMaximize 1`, no fps cap, no render scale, no gamepad | confirmed (real Deck) |
| SavedVariables | load correctly (the Sept 18 beta bug was fixed in 1.60.1.70009) | confirmed |
| Built-in gamepad | "Gamepad UI (Alpha)" checkbox in Options; bindings static since Oct 1; toggling resets Edit Mode layout | reported |
| Frame generation | exists in Forever; community advises off (unconfirmed cheat-flag reports) | reported |
| Memory leak | ~29 MB/min RAM, 12-15 MB/min VRAM over a session (beta) | measured by one guide |

## 3. CVar inventory

Names below come from the client's own first-run Config.wtf on the Deck (marked **seen**) or
from the modern client's defaults list on warcraft.wiki.gg (marked **wiki**). Every graphics
CVar has a raid/battleground twin (`RAID…` or `raidGraphics…`); set both.

### Performance levers (highest impact first)

| UI name | CVar(s) | Seen in | Notes |
|---|---|---|---|
| Secondary Lighting | `giQuality`, `RAIDgiQuality` (UI index likely `graphicsLightMode`, `raidGraphicsLightMode`) | seen | Biggest lever in Forever: High -> Fair cut GPU load from ~100% to 60-75%. Beta workaround after Oct 1: `/console giquality 1`. Mapping UI value -> giQuality value must be verified by diff. |
| Target Framerate | `useTargetFPS` (0/1), `targetFPS` | wiki | Dynamic quality scaler, not a cap. Turn OFF; players report FPS doubling. |
| Max Foreground FPS | `useMaxFPS` (0/1), `maxFPS` | wiki | The real cap: 60 or 40. |
| Max Background FPS | `useMaxFPSBk`, `maxFPSBk`; loading: `maxFPSLoading` | wiki | 30 / 30 (20 for battery). |
| SSAO | `graphicsSSAO`, `raidGraphicsSSAO`, `SSAO`, `SSAOType` | seen | Off. |
| Shadow Quality | `graphicsShadowQuality`, `raidGraphicsShadowQuality`, `shadowMode`, `shadowRt` | seen | Low. Ray-traced shadows (`shadowRt`) removed from the beta Oct 1; keep 0. |
| Render Scale | `RenderScale` (0.5-2.0), `ResampleQuality` (3 = FSR 1.0 per guides; wiki default 3), `ResampleAlwaysSharpen` | wiki | 1.0 on the Deck unless needed; then 0.85 / 0.75. |
| Compute Effects | `graphicsComputeEffects`, `raidGraphicsComputeEffects` | seen | Low. |
| Particle Density | `graphicsParticleDensity`, `raidGraphicsParticleDensity`, `particleDensity`, `RAIDparticleDensity`, `particleMTDensity` | seen | Low/Fair. |
| Depth Effects | `graphicsDepthEffects`, `raidGraphicsDepthEffects` | seen | Off. |
| View Distance | `graphicsViewDistance`, `raidGraphicsViewDistance`, `farclip`, `horizonStart`, `horizonClip` | seen | 4-5. |
| Environment Detail | `graphicsEnvironmentDetail`, `raidGraphicsEnvironmentDetail`, `lodObjectCullSize`, `wmoLodDist` | seen | 3. |
| Ground Clutter | `graphicsGroundClutter`, `raidGraphicsGroundClutter`, `groundEffectDensity`, `groundEffectDist` | seen | 2-3. |
| Liquid Detail | `graphicsLiquidDetail`, `raidGraphicsLiquidDetail`, `waterDetail`, `pbrLiquidDetail`, `rippleDetail` | seen | Low. |
| Projected Textures | `graphicsProjectedTextures`, `raidGraphicsProjectedTextures`, `projectedTextures` | seen | KEEP ON (ground mechanics). Battery profile may offer off. |
| Texture Resolution | `graphicsTextureResolution`, `raidGraphicsTextureResolution` | seen | Keep High (shared 16 GB). |
| Spell Density | `graphicsSpellDensity`, `raidGraphicsSpellDensity`, `spellClutter` | seen | Essential. |
| Anti-aliasing | `ffxAntiAliasingMode` (0 off, 1 FXAA low, ...), `MSAAQuality` | wiki | FXAA Low or off; MSAA 0. |
| Extras | `sunShafts`, `refraction`, `reflectionMode`, `volumeFogLevel`, `weatherDensity`, `ffxGlow`, `graphicsBloomUserMult`, `graphicsOutlineMode` | seen | Off / low for battery. |
| Physics | `physicsLevel` | wiki | 1 (Player Only). |
| VSync | `vsync` | seen | 1 on the Deck (tearing otherwise); pair with a cap. |
| Renderer | `GxApi` (D3D12 default, D3D11 fallback), `GxMaximize`, `gxWindow` | seen | Restart-only. Not touched by the addon; report only. |

### UI / camera / nameplates

| Purpose | CVar(s) | Notes |
|---|---|---|
| UI scale | `useUiScale` (1), `uiScale` (0.64-1.0; 1.0 is base size, NOT "largest") | 0.7-0.8 suggested for the 7-inch screen; verify readability with the Gamepad UI |
| Font scale | `userFontScale`, `WorldTextScale_v2` | optional |
| Camera zoom-out | `cameraDistanceMaxZoomFactor` (default 1.9, max 2.6) | 2.6 |
| Nameplate range | `nameplateMaxDistance` (default 60) | taste |

### Gamepad (modern client, wiki defaults)

`GamePadEnable` (0 default), `GamePadCursorAutoEnable`, `GamePadCursorCentering`,
`GamePadCursorCenteredEmulation`, `GamePadCursorForTargeting`, `GamePadCursorLeftClick`
(`PADRTRIGGER`), `GamePadCursorRightClick` (`PADRSHOULDER`), `GamePadCursorOnLogin`,
`GamePadCursorSpeedStart/Max/Accel`, `GamePadCursorPushCamera`, `GamePadEmulateShift`
(`PADLTRIGGER`), `GamePadEmulateCtrl` (`PADLSHOULDER`), `GamePadEmulateAlt`,
`GamePadEmulateTapWindowMs`, `GamePadCameraYawSpeed`, `GamePadCameraPitchSpeed`,
`GamePadCameraLookMaxYaw/Pitch`, `GamePadAnalogMovement`, `GamePadRunThreshold`,
`GamePadTurnWithCamera`, `GamePadFaceMovementMaxAngle(Combat)`, `GamePadTankTurnSpeed`,
`GamePadStickAxisButtons`, `GamePadVibrationStrength`, `GamePadTouchCursorEnable`,
`GamePadSingleActiveID`, `GamePadFactionColor`, `GamePadOverlapMouseMs`.

**Open question:** which CVar the Forever "Enable Gamepad UI (Alpha)" checkbox writes
(possibly `GamePadEnable`, possibly new). Verify by diffing `WTF/Config.wtf` after toggling.
Also `WTF/GamePadConfig_Default.json` exists in the beta client; inspect it.

## 4. Presets (starting values; tune on the Deck)

| CVar | Performance (60) | Battery (40) | Quality (60) |
|---|---|---|---|
| `giQuality` / `RAIDgiQuality` | 1 / 1 | 0 / 0 | 1 / 1 |
| `useTargetFPS` | 0 | 0 | 0 |
| `useMaxFPS` / `maxFPS` | 1 / 60 | 1 / 40 | 1 / 60 |
| `useMaxFPSBk` / `maxFPSBk` / `maxFPSLoading` | 1 / 30 / 30 | 1 / 20 / 30 | 1 / 30 / 30 |
| `vsync` | 1 | 1 | 1 |
| `RenderScale` / `ResampleQuality` | 1.0 / 3 | 0.85 / 3 | 1.0 / 3 |
| `graphicsShadowQuality` (+raid), `shadowMode` | 1, 1 | 0, 0 | 2, 2 |
| `graphicsSSAO` (+raid), `SSAO` | 0 | 0 | 1 |
| `graphicsDepthEffects` (+raid) | 0 | 0 | 1 |
| `graphicsComputeEffects` (+raid) | 1 | 0 | 2 |
| `graphicsParticleDensity` (+raid), `particleDensity` | 2, 40 | 1, 20 | 3, 60 |
| `graphicsLiquidDetail` (+raid), `waterDetail` | 1 | 0 | 2 |
| `graphicsViewDistance` / raid | 5 / 4 | 4 / 3 | 6 / 5 |
| `graphicsEnvironmentDetail` / raid | 3 / 3 | 2 / 2 | 4 / 3 |
| `graphicsGroundClutter` / raid | 3 / 2 | 2 / 1 | 4 / 3 |
| `graphicsProjectedTextures` (+raid), `projectedTextures` | 1 | 1 | 1 |
| `graphicsTextureResolution` (+raid) | 2 | 2 | 2 |
| `graphicsSpellDensity` (+raid) | 1 | 1 | 1 |
| `ffxAntiAliasingMode` / `MSAAQuality` | 1 / 0 | 0 / 0 | 1 / 0 |
| `sunShafts`, `refraction`, `reflectionMode`, `rippleDetail`, `volumeFogLevel` | 0,0,0,0,1 | 0,0,0,0,0 | 1,1,1,1,2 |
| `physicsLevel` | 1 | 1 | 1 |
| `useUiScale` / `uiScale` | 1 / 0.75 | 1 / 0.75 | 1 / 0.75 |
| `cameraDistanceMaxZoomFactor` | 2.6 | 2.6 | 2.6 |
| `GamePadEnable` | 1 if Gamepad UI chosen | same | same |

Deck-side pairing (Quick Access menu, not addon-controlled): 40 Hz refresh + 40 fps profile
for battery; TDP 10-12 W; leave GPU clock auto; do not use gamescope FSR (blurs the UI).

## 5. Features

1. **Presets panel**: Performance / Battery / Quality / Restore previous. Shows current
   frame rate (`GetFramerate()`) and the active preset. Usable with the gamepad cursor
   (large buttons, no hover-only affordances).
2. **First-login offer**: once per account, if the client looks like a Deck (see 6), offer
   "Apply the Steam Deck preset?" with a preview of what changes. Never silent.
3. **Snapshot / restore**: before applying a preset, store every CVar's current value in
   SavedVariables; "Restore previous" puts them back exactly.
4. **Validation report** (`/deckforever check`): for every CVar in the presets, say whether
   the client knows it (`C_CVar.GetCVarInfo` / `GetCVarDefault`), its current value, and
   whether the value is within range. Unknown CVars are skipped on apply and listed. This is
   the tool for re-validating after each client build.
5. **Raid twin sync**: when the user changes a normal setting through our panel, mirror it to
   the raid twin unless they opted out.
6. **Session reminder** (optional): after N minutes, suggest a relog to recover from the
   beta memory leak, if `GetFramerate()` has sagged more than X% since login. Off by default
   once Blizzard fixes the leak.
7. **Slash commands**: `/deckforever` (panel), `/deckforever apply performance|battery|quality`,
   `/deckforever restore`, `/deckforever check`, `/deckforever fps`.
8. **No combat changes**: queue applies until out of combat (some CVars are refused in combat).

## 6. Steam Deck detection (heuristic; Wine reports Windows)

- `GetPhysicalScreenSize()` returns 1280x800 (or 1280x800 window via `GetScreenWidth/Height`).
- Gamepad active: `C_GamePad.IsEnabled()` / `GamePadEnable == 1`, or any `PAD*` key seen.
- Optional: user confirms on first prompt. Store the decision; never re-prompt.

## 7. Technical notes

- APIs: `C_CVar.SetCVar(name, value)`, `C_CVar.GetCVar`, `C_CVar.GetCVarDefault`,
  `C_CVar.GetCVarInfo` (existence, default, range flags), `C_CVar.RegisterCVar` (do not use),
  `GetFramerate()`, `GetPhysicalScreenSize()`, `C_GamePad.*`, `InCombatLockdown()`,
  events `PLAYER_LOGIN`, `PLAYER_ENTERING_WORLD`, `PLAYER_REGEN_ENABLED`, `CVAR_UPDATE`.
- Graphics CVars are not protected; they apply immediately. A few trigger a reload of
  resources (texture resolution). Renderer (`GxApi`) and window mode need a restart: report
  only.
- SavedVariables: one account-wide table (`DeckForeverDB`): `{ version, snapshot = {cvar=value},
  activePreset, promptedOnce, options }`.
- TOC: `## Interface: 16001` (add the other flavors only if the addon is meant to run there),
  `## SavedVariables: DeckForeverDB`, `## X-Curse-Project-ID`, `## X-Wago-ID`.
- Packaging: BigWigs packager (GitHub Action) producing one zip plus `release.json` with a
  `forever` flavor entry (this is what Questie/ConsolePort ship and what tooling checks).
- Keep the UI library-free (plain frames) to avoid Ace3 version drift on a new client, or
  embed libs explicitly.

## 8. Testing plan

1. On the Deck, set each preset value through the game's own Options panel, log out, and
   diff `WTF/Config.wtf` to confirm every CVar name and the UI->value mapping (especially
   Secondary Lighting and the Gamepad UI checkbox).
2. `/deckforever check` on each new client build; fix renamed/removed CVars.
3. Measure: 10 minutes in a capital city and 10 minutes questing per preset, note average
   fps and battery drain from the Deck's performance overlay.
4. Verify `Restore previous` is byte-exact against the snapshot.

## 8b. Preloading by DeckForever (the installer) (so CurseForge auto-detects it)

CurseForge fingerprints every folder in `Interface/AddOns` on start-up and matches them
against its published files, so an addon copied in ahead of time shows up as installed and
managed. Requirements:
- The addon must be published on CurseForge, and the folder we drop in must be byte-identical
  to that published release (same packager output uploaded to GitHub and CurseForge).
- DeckForever (the installer) gets a small Repair step: when the client folder exists and the addon is
  missing, download the GitHub release zip, verify, unpack into `Interface/AddOns`.
- Preferred: **seed the folder before the game is installed.** Battle.net installs into
  existing, non-empty folders and never touches `Interface/AddOns` or `WTF`, so the installer
  can create `<client>/Interface/AddOns/<addon>` (and a starter `WTF/Config.wtf`) right after
  Battle.net is set up. The first session then already has the addon and the Deck preset, and
  CurseForge detects the addon on its first scan. Risk: the client folder name (`_classic_beta_`
  in the beta) may change at launch; keep the name configurable and have Repair move seeded
  files into the real client folder if they ended up next to it. Confirm once on a Deck that
  has not installed the game yet before relying on it.
- Fallback: drop the addon on the next Repair once the client folder exists.

## 9. Open questions

- CVar written by "Enable Gamepad UI (Alpha)"; whether Forever adds new Gamepad* CVars.
- Exact `graphicsLightMode` -> `giQuality` mapping and value range for Secondary Lighting.
- Launch client folder name and whether beta settings migrate.
- Whether Blizzard clamps any of these CVars at launch (the beta clamped some between builds).
- `ResampleQuality` value meanings in Forever (guides: 3 = FSR 1.0; verify).

## 10. Sources

See the Sources list at the end of `reference/deck-settings-notes.md`, plus:
- https://warcraft.wiki.gg/wiki/Config.wtf_defaults (CVar names/defaults)
- https://us.forums.blizzard.com/en/wow/t/wow-forever-beta-major-gpu-optimisation-performance-regression-versus-retail/2354726
- https://tier1settings.com/best-wow-forever-settings-for-fps/
- https://mythic-store.com/blog/wow-forever-best-settings-graphics-interface-and-what-actually-matters
- https://gamingonsteam.com/2026/09/18/world-of-warcraft-forever-on-steam-deck-easy-install-guide-with-full-controller-support/
