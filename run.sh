#!/usr/bin/env bash
# Starts the DeckForever app (window in Desktop Mode, text mode over SSH). Pass a command to use the CLI.
# When Steam launches us it injects its own (old) runtime libraries and preloads; a system GTK/Python app
# must not inherit those, so scrub them first.
unset LD_PRELOAD LD_LIBRARY_PATH STEAM_RUNTIME STEAM_RUNTIME_LIBRARY_PATH SYSTEM_LD_LIBRARY_PATH \
      STEAM_ZENITY SDL_VIDEO_X11_FORCE_EGL ENABLE_VK_LAYER_VALVE_steam_overlay_1 ENABLE_VK_LAYER_VALVE_steam_fossilize_1
cd "$(dirname "$0")" && exec python3 -m deckforever "$@"
