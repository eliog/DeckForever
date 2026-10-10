# WoW Forever on Steam Deck: settings notes (for the future settings/addon app)

Source: `config-forever-16001-first-run.wtf`, written by the Forever beta client
(`_classic_beta_/WowB.exe`, interface 16001, modern engine) after one session on the Deck,
2026-10-10. The client auto-detected the Deck once (`hwDetect "0"`, `graphicsQuality "4"`).

## How to apply a preset

`<client>/WTF/Config.wtf` is plain text: one `SET name "value"` per line. The client reads it at
startup and rewrites it at exit, so write it while the game is closed. Unknown names are kept but
ignored. Values present in the file are kept instead of being auto-detected, so a preset dropped
in before the first launch is used by the first launch. Per-account settings (keybinds, UI layout,
addon data) live under `WTF/Account/<ACCOUNT>/` and only exist after the first login.

Every graphics setting exists twice: the normal one and a `RAID…`/`raidGraphics…` twin used in
raids and battlegrounds. A preset should set both.

## Confirmed in the Forever client (present in the file)

| Setting (normal / raid twin) | First-run value | Deck preset idea |
|---|---|---|
| `graphicsQuality` / `RAIDgraphicsQuality` | 4 | 3 (performance) or 4 (quality); setting individual CVars below overrides the preset |
| `graphicsShadowQuality` / `raidGraphicsShadowQuality`, `shadowMode` | 2 | 1 |
| `graphicsSSAO` / `raidGraphicsSSAO`, `SSAO` | 2 | 0 |
| `graphicsDepthEffects` / `raidGraphicsDepthEffects` | 2 | 1 |
| `graphicsLiquidDetail` / `raidGraphicsLiquidDetail`, `waterDetail` | 2 | 1 |
| `graphicsParticleDensity` / `raidGraphicsParticleDensity`, `particleDensity` | 3 / 50 | 2 / 30 (battery) |
| `graphicsGroundClutter` / `raidGraphicsGroundClutter`, `groundEffectDensity`, `groundEffectDist` | 4 / 32 / 160 | 2 |
| `graphicsViewDistance` / `raidGraphicsViewDistance`, `farclip`, `horizonStart` | 4 / 6000 / 1400 | 4 (keep) |
| `graphicsEnvironmentDetail` / `raidGraphicsEnvironmentDetail` | 4 | 3 |
| `graphicsTextureResolution` / `raidGraphicsTextureResolution` | 2 | 2 (keep; UMA memory is plentiful) |
| `graphicsProjectedTextures` / `raidGraphicsProjectedTextures`, `projectedTextures` | 1 | 1 (keep; needed to see ground spell effects) |
| `graphicsOutlineMode` / `raidGraphicsOutlineMode`, `OutlineEngineMode` | 1 | 1 |
| `graphicsSpellDensity` / `raidGraphicsSpellDensity`, `spellClutter` | 1 / 2 | 1 |
| `graphicsComputeEffects` / `raidGraphicsComputeEffects` | 2 | 1 |
| `graphicsLightMode` / `raidGraphicsLightMode` | 1 | 1 |
| `sunShafts` / `RAIDsunShafts`, `refraction`, `reflectionMode`, `rippleDetail`, `volumeFogLevel`, `weatherDensity` | 1 / 1 / 2 / 1 / 2 / 1 | 0 / 0 / 0 / 0 / 1 / 1 (battery) |
| `vsync` | 1 | 1 (keep) |
| `GxApi` | D3D12 | D3D12 (vkd3d-proton; fall back to D3D11 only if crashes) |
| `GxMaximize` | 1 | 1 (fills the 1280x800 screen) |

## Not present after the first run (names from the same engine generation, verify in-game)

Unverified for Forever; check with `/console cvar_name` or a CVar browser addon before relying on them.

| Setting | Purpose | Deck idea |
|---|---|---|
| `maxFPS`, `maxFPSBk`, `maxFPSLoading` | frame caps (foreground / background / loading) | 60 / 30 / 30, or 45 for battery |
| `renderScale` | render resolution scale | 100 (the client's upscaler is FSR 1; prefer native) |
| `ResampleQuality` / `ResampleAlwaysSharpen` | upscale filter | leave default |
| `MSAAQuality`, `ffxAntiAliasingMode` | anti-aliasing | FXAA low or off |
| `GamePadEnable`, `GamePadEmulateShift`, `GamePadCursorCentering` | native gamepad | 1 if using the built-in Gamepad UI or ConsolePort |
| `useUiScale`, `uiScale` | UI size | 1 / 1.0 (largest) for the 7-inch screen |
| `gxWindowedResolution`, `gxFullscreenResolution`, `gxWindow` | window mode | not needed with `GxMaximize 1` |
| `Sound_OutputDriverIndex`, `Sound_MasterVolume` | audio | leave |
| `cameraDistanceMaxZoomFactor` | zoom-out range | 2.6 |

## Other observations

- `portal "test"` and `agentUID "wow_classic_beta"`: beta realm; expect `portal "US"` and a different agent uid after launch (Nov 4, 2026). The client folder name may change too; detect it, do not hard-code.
- `WTF/GamePadConfig_Default.json` exists: the client writes a gamepad config file, worth inspecting for the native Gamepad (Alpha) mode.
- Account folder: `WTF/Account/<numeric id>#<n>/` (a Battle.net account id, not the e-mail).
- `Blizzard_GamepadSmartNavigation.lua` and `Blizzard_SettingsDefinitions_Shared.lua` are the client's own saved variables; they were read back fine (the September saved-variables bug is gone).

## Research pass 2026-10-10: best settings for WoW Forever on the Deck

Sources are beta-era (client 1.60.1, Sept 20 to Oct 10 2026). Nothing official from Blizzard
or Valve exists for the Deck; the numbers below come from player measurements and guides and
should be re-checked after the Nov 4 launch client.

### What actually moves the needle (in order)

1. **Secondary Lighting = Fair.** The Forever beta's new lighting is far more expensive than
   retail's. One measured report: GPU load fell from ~100% to 60-75% going High -> Fair, and
   25-35% overall with Projected Textures and "Optional GPU Features" also off. Engine side:
   `giQuality` and `RAIDgiQuality` (a player workaround after the Oct 1 patch is
   `/console giquality 1`). Set both; a Blizzard dev noted the raid/non-raid values were
   swapped in one build.
2. **Target Framerate = Off** (`useTargetFPS 0`). This is Blizzard's dynamic-quality system,
   not a cap; several Forever players report large FPS gains with it off ("over doubled").
   Cap frames with Max Foreground FPS instead (`useMaxFPS 1`, `maxFPS 60` or `40`), and keep
   Max Background FPS at 30 (`maxFPSBk`).
3. **SSAO off, Shadows Low** (`SSAO 0`, `graphicsSSAO 0`, `shadowMode 0/1`,
   `graphicsShadowQuality 1`). In the beta, shadows above Low intermittently disabled the new
   light/fog effects anyway, so Low costs nothing visually.
4. **Render Scale** (`RenderScale`): keep 1.0 on the Deck's 1280x800 if the above gets you to
   40 fps; drop to 0.85 then 0.75 if not. Upscale filter `ResampleQuality 3` (FSR 1.0) when
   below 1.0; the Deck guide notes FSR 1 is dated, and another says point/bilinear looked
   cleaner at low settings. Do not use gamescope's FSR for WoW (blurs the UI).
5. **Compute Effects Low, Particle Density Low, Depth Effects off** (`graphicsComputeEffects 1`,
   `graphicsParticleDensity 1`/`particleDensity 30`, `graphicsDepthEffects 0`).
6. **View Distance 4-5, Environment Detail 3, Ground Clutter 2-3** (`graphicsViewDistance`,
   `graphicsEnvironmentDetail`, `graphicsGroundClutter`). Lower view distance in cities/raids.
7. **Keep**: Projected Textures ON (ground spell effects; turning it off helps GPU but hides
   mechanics; make it a battery-profile choice), Texture Resolution High (`graphicsTextureResolution 2`,
   UMA memory is plentiful), Spell Density Essential (`graphicsSpellDensity 1`).
8. **Anti-aliasing**: FXAA Low or off (`ffxAntiAliasingMode 1` or `0`, `MSAAQuality 0`).
9. **Renderer**: DX12 (`GxApi D3D12`) is the default and works on vkd3d-proton; DX11 only as a
   fallback for crashes. VSync on (`vsync 1`) on the Deck to avoid tearing; with a 40 Hz
   display refresh in Game Mode a 40 fps cap is the usual battery sweet spot.
10. **Frame generation**: off. The Deck guide measured ~30 fps all-low without it and 40-50
    with it, but advises against it over (unconfirmed) cheat-flag reports.
11. **Memory leak**: the beta client leaks (~29 MB/min RAM, 12-15 MB/min VRAM measured);
    FPS sags over a long session. Relog to character select or restart the client. Deleting
    `<client>/Cache` has fixed severe FPS drops for some players.
12. **UI**: `useUiScale 1` + `uiScale` around 0.7-0.8 on the 7-inch screen (one Deck player
    suggested 70% to stop cut-off elements; "1.0 = largest" is NOT how it works, 1.0 is the
    base size). Camera: `cameraDistanceMaxZoomFactor 2.6`, Camera Following Style = Never.
    Nameplates: enemies on, distance to taste (`nameplateMaxDistance`).

### Gamepad (native "Gamepad UI (Alpha)")
- Engine CVars exist from the modern client: `GamePadEnable 1`, `GamePadCursorCentering`,
  `GamePadCursorAutoEnable`, `GamePadCursorLeftClick PADRTRIGGER`, `GamePadCursorRightClick
  PADRSHOULDER`, `GamePadEmulateShift PADLTRIGGER`, `GamePadEmulateCtrl PADLSHOULDER`,
  `GamePadCameraYawSpeed/PitchSpeed`, `GamePadRunThreshold`, `GamePadTurnWithCamera`,
  `GamePadVibrationStrength`. The Forever checkbox "Enable Gamepad UI (Alpha)" may write a
  new CVar: verify by ticking it on the Deck and diffing `WTF/Config.wtf`.
- Known beta issues: face buttons cannot be rebound, Gamepad UI bindings are static since
  Oct 1, switching Gamepad UI resets the Edit Mode layout, some menus still need the trackpad.
- Steam Input: default gamepad template, right trackpad as mouse, back grips to F13-F16 for
  extra binds; Steam + X for text.

### Two presets to ship (values to verify by diffing Config.wtf after setting them in the UI)

| Setting (CVar) | Performance (60 fps target) | Battery (40 fps) |
|---|---|---|
| `giQuality` / `RAIDgiQuality` | 1 | 0 |
| `useTargetFPS` | 0 | 0 |
| `useMaxFPS` / `maxFPS` | 1 / 60 | 1 / 40 |
| `useMaxFPSBk` / `maxFPSBk` | 1 / 30 | 1 / 20 |
| `maxFPSLoading` | 30 | 30 |
| `vsync` | 1 | 1 |
| `RenderScale` / `ResampleQuality` | 1.0 / 3 | 0.85 / 3 |
| `graphicsShadowQuality` / `raidGraphicsShadowQuality`, `shadowMode` | 1 / 1 / 1 | 0 / 0 / 0 |
| `graphicsSSAO` / `raidGraphicsSSAO`, `SSAO` | 0 | 0 |
| `graphicsDepthEffects` / `raidGraphicsDepthEffects` | 0 | 0 |
| `graphicsComputeEffects` / `raidGraphicsComputeEffects` | 1 | 0 |
| `graphicsParticleDensity` / `raidGraphicsParticleDensity`, `particleDensity` | 2 / 2 / 40 | 1 / 1 / 20 |
| `graphicsLiquidDetail` / `raidGraphicsLiquidDetail`, `waterDetail` | 1 | 0 |
| `graphicsViewDistance` / `raidGraphicsViewDistance` | 5 / 4 | 4 / 3 |
| `graphicsEnvironmentDetail` / `raidGraphicsEnvironmentDetail` | 3 / 3 | 2 / 2 |
| `graphicsGroundClutter` / `raidGraphicsGroundClutter` | 3 / 2 | 2 / 1 |
| `graphicsProjectedTextures` / `raidGraphicsProjectedTextures`, `projectedTextures` | 1 | 1 (0 only if desperate) |
| `graphicsTextureResolution` / `raidGraphicsTextureResolution` | 2 | 2 |
| `graphicsSpellDensity` / `raidGraphicsSpellDensity` | 1 | 1 |
| `ffxAntiAliasingMode`, `MSAAQuality` | 1 / 0 | 0 / 0 |
| `sunShafts`, `refraction`, `reflectionMode`, `rippleDetail`, `volumeFogLevel` | 0 / 0 / 0 / 0 / 1 | 0 / 0 / 0 / 0 / 0 |
| `GxApi`, `GxMaximize` | D3D12 / 1 | D3D12 / 1 |
| `useUiScale` / `uiScale` | 1 / 0.75 | 1 / 0.75 |
| `GamePadEnable` | 1 (if using the Gamepad UI) | 1 |
| `cameraDistanceMaxZoomFactor` | 2.6 | 2.6 |

Deck side (Quick Access menu): 40 Hz refresh with the 40 fps profile; TDP limit 10-12 W is
the common starting point for battery; leave GPU clock on auto.

### Sources
- https://us.forums.blizzard.com/en/wow/t/wow-forever-beta-major-gpu-optimisation-performance-regression-versus-retail/2354726 (Secondary Lighting / Projected Textures measurements)
- https://tier1settings.com/best-wow-forever-settings-for-fps/ (Target Framerate off, cache folder, memory-leak figures)
- https://mythic-store.com/blog/wow-forever-best-settings-graphics-interface-and-what-actually-matters (low-end preset, interface settings)
- https://wowvendor.com/media/wow-forever/forever-graphics-settings/ (render scale 75-90%, shadows low, secondary lighting fair, SSAO off)
- https://gamingonsteam.com/2026/09/18/world-of-warcraft-forever-on-steam-deck-easy-install-guide-with-full-controller-support/ (Deck: all low ~30 fps, frame gen 40-50 but not advised)
- https://warcraft.wiki.gg/wiki/Config.wtf_defaults (CVar names and defaults: maxFPS/useMaxFPS, targetFPS/useTargetFPS, RenderScale, ResampleQuality, MSAAQuality, ffxAntiAliasingMode, uiScale/useUiScale, vsync, GamePad*, shadowMode, SSAO, projectedTextures, cameraDistanceMaxZoomFactor, nameplateMaxDistance)
- https://us.support.blizzard.com/en/article/32248 and https://eu.forums.blizzard.com/en/wow/t/target-fps-doesnt-work/202746 (maxfps/maxfpsbk console commands; Target FPS is dynamic scaling, not a cap)
