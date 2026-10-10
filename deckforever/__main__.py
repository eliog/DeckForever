import os
import sys


def main():
    argv = sys.argv[1:]
    gui_possible = (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and not (os.environ.get("DECKFOREVER_NO_GUI") or os.environ.get("WOWF_NO_GUI"))
    if not argv and gui_possible:
        try:
            from . import gui
        except (ImportError, ValueError) as e:
            print(f"GTK is not available ({e}); falling back to the command line.", file=sys.stderr)
        else:
            gui.main()
            return 0
    from . import cli
    return cli.main(argv)


if __name__ == "__main__":
    sys.exit(main())
