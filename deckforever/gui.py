"""GTK 3 window for DeckForever. Runs engine tasks on a worker thread."""
import os
import threading
import traceback

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango  # noqa: E402

from . import engine as eng  # noqa: E402

ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.svg")


class GtkUI(eng.BaseUI):
    """Bridges engine callbacks (worker thread) to GTK (main thread)."""

    def __init__(self, win):
        self.win = win
        self.cancel = threading.Event()

    def _call(self, fn, *args):
        """Run fn on the main thread and wait for its result."""
        done = threading.Event()
        box = {}

        def runner():
            try:
                box["r"] = fn(*args)
            except Exception as e:  # pragma: no cover
                box["e"] = e
            done.set()
            return False
        GLib.idle_add(runner)
        done.wait()
        if "e" in box:
            raise box["e"]
        return box.get("r")

    def log(self, msg):
        GLib.idle_add(self.win.append_log, msg)

    def step(self, msg):
        GLib.idle_add(self.win.set_status, msg)

    def progress(self, fraction):
        GLib.idle_add(self.win.set_progress, fraction)

    def ask(self, question, default=True):
        return self._call(self.win.dialog_question, question, default)

    def choose(self, title, options):
        return self._call(self.win.dialog_choose, title, options)

    def pick_folder(self, title):
        return self._call(self.win.dialog_folder, title)

    def pick_file(self, title, folder, pattern):
        return self._call(self.win.dialog_file, title, folder, pattern)

    def info(self, msg):
        self._call(self.win.dialog_message, msg, Gtk.MessageType.INFO)

    def error(self, msg):
        self._call(self.win.dialog_message, msg, Gtk.MessageType.ERROR)

    def is_cancelled(self):
        return self.cancel.is_set()


class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title=eng.APP_NAME)
        self.set_default_size(760, 600)
        self.set_border_width(12)
        if os.path.isfile(ICON):
            try:
                self.set_icon_from_file(ICON)
            except Exception:
                pass
        self.ui = GtkUI(self)
        self.engine = eng.Engine(self.ui)
        self.worker = None
        self.connect("delete-event", self._on_close)
        self._build()
        self.refresh_status()
        self.set_busy(False)

    # ------------------------------------------------------------------ layout
    def _build(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(outer)

        title = Gtk.Label()
        title.set_markup(f"<span size='x-large' weight='bold'>{eng.APP_NAME}</span>\n"
                         "<span size='small'>World of Warcraft: Forever on Steam Deck. Install, repair, back up, uninstall.</span>")
        title.set_xalign(0)
        outer.pack_start(title, False, False, 0)

        # status grid
        grid = Gtk.Grid(column_spacing=16, row_spacing=4)
        self.status_labels = {}
        for i, (key, text) in enumerate([("proton", "Proton"), ("battlenet", "Battle.net"), ("game", "Game files"),
                                          ("curseforge", "CurseForge"), ("backup", "Last backup"),
                                          ("shortcuts", "Steam shortcut")]):
            k = Gtk.Label(label=text + ":")
            k.set_xalign(1)
            k.get_style_context().add_class("dim-label")
            v = Gtk.Label(label="...")
            v.set_xalign(0)
            v.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            v.set_hexpand(True)
            grid.attach(k, 0, i, 1, 1)
            grid.attach(v, 1, i, 1, 1)
            self.status_labels[key] = v
        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.IN)
        pad = Gtk.Box()
        pad.set_border_width(8)
        pad.pack_start(grid, True, True, 0)
        frame.add(pad)
        outer.pack_start(frame, False, False, 0)

        # primary button
        self.btn_install = Gtk.Button(label="Install")
        self.btn_install.get_style_context().add_class("suggested-action")
        self.btn_install.set_size_request(-1, 48)
        self.btn_install.connect("clicked", lambda _b: self.run_task("Install", self.engine.install))
        outer.pack_start(self.btn_install, False, False, 0)
        self.game_mode = eng.Engine.in_game_mode()
        if self.game_mode:
            note = Gtk.Label(label="Game Mode: install, repair, Proton updates and uninstall need Desktop Mode "
                                   "(they restart Steam). Backups and restores work here.")
            note.set_xalign(0)
            note.set_line_wrap(True)
            note.get_style_context().add_class("dim-label")
            outer.pack_start(note, False, False, 0)

        # secondary buttons
        row = Gtk.Box(spacing=6)
        self.secondary = []
        self.desktop_only = []
        for label, fn, needs_desktop in [
                ("Back up settings", lambda: self._with_preflight(self.engine.backup), False),
                ("Restore", lambda: self._with_preflight(self.engine.restore), False),
                ("Open Battle.net", lambda: self._with_preflight(self.open_bnet), False),
                ("Install CurseForge", self.engine.curseforge, True),
                ("Fresh reinstall", self.engine.reinstall, True),
                ("Update Proton", self.engine.update_proton, True),
                ("Uninstall", self.engine.uninstall, True)]:
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, l=label, f=fn: self.run_task(l, f))
            row.pack_start(b, True, True, 0)
            self.secondary.append(b)
            if needs_desktop:
                self.desktop_only.append(b)
        outer.pack_start(row, False, False, 0)

        # progress + status + cancel
        prow = Gtk.Box(spacing=8)
        self.progress = Gtk.ProgressBar()
        self.progress.set_hexpand(True)
        self.progress.set_valign(Gtk.Align.CENTER)
        prow.pack_start(self.progress, True, True, 0)
        self.btn_cancel = Gtk.Button(label="Cancel")
        self.btn_cancel.set_sensitive(False)
        self.btn_cancel.connect("clicked", lambda _b: self.ui.cancel.set())
        prow.pack_start(self.btn_cancel, False, False, 0)
        outer.pack_start(prow, False, False, 0)
        self.status = Gtk.Label(label="Ready.")
        self.status.set_xalign(0)
        self.status.set_line_wrap(True)
        outer.pack_start(self.status, False, False, 0)

        # log
        exp = Gtk.Expander(label="Details")
        sw = Gtk.ScrolledWindow()
        sw.set_min_content_height(180)
        self.logview = Gtk.TextView()
        self.logview.set_editable(False)
        self.logview.set_monospace(True)
        self.logview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        sw.add(self.logview)
        exp.add(sw)
        exp.set_expanded(True)
        outer.pack_start(exp, True, True, 0)

        foot = Gtk.Label(label=f"Install folder: {self.engine.root}    v{eng.VERSION}")
        foot.set_xalign(0)
        foot.get_style_context().add_class("dim-label")
        outer.pack_start(foot, False, False, 0)
        self.pulse_id = None

    def _on_close(self, *_a):
        if self.worker and self.worker.is_alive():
            self.dialog_message("A task is still running (Steam may be closed or files may be moving).\n"
                                "Wait for it to finish, or press Cancel first.", Gtk.MessageType.WARNING)
            return True        # keep the window open
        return False

    # ------------------------------------------------------------------ helpers
    def _with_preflight(self, fn, **kw):
        self.engine.preflight()
        return fn(**kw)

    def open_bnet(self):
        if not self.engine.bnet_installed():
            raise eng.EngineError("Battle.net is not installed yet. Press Install first.")
        self.engine.select_proton()
        self.engine.ensure_runtime()
        self.engine.launch_battlenet()
        self.ui.info("Battle.net will open shortly (it can take up to a minute). Log in, then install or "
                     "update World of Warcraft: Forever from there.")

    def append_log(self, msg):
        buf = self.logview.get_buffer()
        buf.insert(buf.get_end_iter(), msg + "\n")
        self.logview.scroll_to_mark(buf.get_insert(), 0, False, 0, 0)
        return False

    def set_status(self, msg):
        self.status.set_text(msg)
        return False

    def set_progress(self, fraction):
        if fraction is None:
            self.progress.set_fraction(0)
        else:
            self.progress.set_fraction(max(0.0, min(1.0, fraction)))
        return False

    def _pulse(self):
        if self.worker and self.worker.is_alive():
            if self.progress.get_fraction() == 0:
                self.progress.pulse()
            return True
        self.progress.set_fraction(0)
        return False

    def refresh_status(self):
        try:
            st = self.engine.status()
        except BaseException as e:
            self.status_labels["proton"].set_text(f"(could not read Steam: {e})")
            return
        L = self.status_labels
        L["proton"].set_text(st["proton"] or "not installed (will be downloaded)")
        L["battlenet"].set_text("installed" if st["battlenet"] else "not installed")
        if st["game"]:
            L["game"].set_text(st["game"])
        elif st["existing_installs"]:
            L["game"].set_text("found elsewhere, will be adopted: " + st["existing_installs"][0])
        else:
            L["game"].set_text("not installed")
        L["curseforge"].set_text("not installed" if not st["curseforge"] else
                                 ("installed, pointed at the game" if st["curseforge_configured"] else
                                  "installed (press Repair after WoW is installed)"))
        L["backup"].set_text(st["last_backup"] or "none")
        L["shortcuts"].set_text("present" if st["shortcuts"] else "missing")
        self.btn_install.set_label("Install" if not st["battlenet"] else "Repair / update")

    def set_busy(self, busy):
        for b in [self.btn_install] + self.secondary:
            b.set_sensitive(not busy)
        if self.game_mode and not busy:
            for b in [self.btn_install] + self.desktop_only:
                b.set_sensitive(False)
                b.set_tooltip_text("Switch to Desktop Mode for this")
        self.btn_cancel.set_sensitive(busy)
        if busy and not self.pulse_id:
            self.pulse_id = GLib.timeout_add(120, self._pulse)
        if not busy:
            self.pulse_id = None

    def run_task(self, label, fn):
        if self.worker and self.worker.is_alive():
            return
        self.ui.cancel.clear()
        self.set_busy(True)
        self.set_status(f"{label}...")

        def work():
            try:
                fn()
                GLib.idle_add(self.set_status, f"{label}: done.")
            except eng.Cancelled:
                GLib.idle_add(self.set_status, f"{label}: cancelled.")
            except eng.EngineError as e:
                self.ui.error(str(e))
                GLib.idle_add(self.set_status, f"{label}: failed.")
            except BaseException as e:                       # includes SystemExit from helpers
                self.engine.log(traceback.format_exc())      # goes to the log file too
                self.ui.error(f"{label} failed: {e}\n\nSee Details and the logs folder.")
                GLib.idle_add(self.set_status, f"{label}: failed.")
            finally:
                GLib.idle_add(self._task_done)
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _task_done(self):
        self.set_busy(False)
        self.set_progress(None)
        self.refresh_status()
        return False

    # ------------------------------------------------------------------ dialogs (main thread)
    def dialog_message(self, msg, mtype):
        d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=mtype,
                              buttons=Gtk.ButtonsType.OK, text=msg)
        d.run()
        d.destroy()

    def dialog_question(self, q, default):
        d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                              buttons=Gtk.ButtonsType.YES_NO, text=q)
        d.set_default_response(Gtk.ResponseType.YES if default else Gtk.ResponseType.NO)
        r = d.run()
        d.destroy()
        return r == Gtk.ResponseType.YES

    def dialog_choose(self, title, options):
        d = Gtk.Dialog(title=title, transient_for=self, modal=True)
        d.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
        box = d.get_content_area()
        box.set_spacing(6)
        box.set_border_width(10)
        first = None
        radios = []
        for value, label in options:
            rb = Gtk.RadioButton.new_with_label_from_widget(first, label)
            first = first or rb
            radios.append((rb, value))
            box.pack_start(rb, False, False, 0)
        d.show_all()
        r = d.run()
        chosen = next((v for rb, v in radios if rb.get_active()), None)
        d.destroy()
        return chosen if r == Gtk.ResponseType.OK else None

    def dialog_folder(self, title):
        d = Gtk.FileChooserDialog(title=title, transient_for=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        d.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Select", Gtk.ResponseType.OK)
        r = d.run()
        p = d.get_filename() if r == Gtk.ResponseType.OK else None
        d.destroy()
        return p

    def dialog_file(self, title, folder, pattern):
        d = Gtk.FileChooserDialog(title=title, transient_for=self, action=Gtk.FileChooserAction.OPEN)
        d.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Open", Gtk.ResponseType.OK)
        if folder and os.path.isdir(folder):
            d.set_current_folder(folder)
        f = Gtk.FileFilter()
        f.set_name(pattern)
        f.add_pattern(pattern)
        d.add_filter(f)
        r = d.run()
        p = d.get_filename() if r == Gtk.ResponseType.OK else None
        d.destroy()
        return p


def main():
    win = MainWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
