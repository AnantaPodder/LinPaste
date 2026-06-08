// LinPaste Capture — GNOME Shell extension (GNOME 46+ / ESM).
//
// Why this exists: GNOME's Mutter compositor exposes no data-control Wayland
// protocol, so background tools like `wl-paste --watch` cannot observe clipboard
// changes. The shell itself is the only component with unrestricted clipboard
// access, so we poll St.Clipboard here and hand each new copy to the LinPaste
// Python backend by spawning `linpaste store` (text on stdin) — the exact same
// contract the rest of LinPaste already speaks.

import St from 'gi://St';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const POLL_INTERVAL_MS = 1000;

export default class LinPasteCaptureExtension extends Extension {
    enable() {
        this._clipboard = St.Clipboard.get_default();
        this._last = null;
        this._linpaste = this._resolveLinpaste();

        this._timeoutId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT,
            POLL_INTERVAL_MS,
            () => {
                this._poll();
                return GLib.SOURCE_CONTINUE;
            }
        );
    }

    disable() {
        if (this._timeoutId) {
            GLib.source_remove(this._timeoutId);
            this._timeoutId = null;
        }
        this._clipboard = null;
        this._last = null;
    }

    // The shell's session PATH may not include ~/.local/bin, so resolve the
    // command to an absolute path when we can.
    _resolveLinpaste() {
        const found = GLib.find_program_in_path('linpaste');
        if (found)
            return found;
        const local = GLib.build_filenamev(
            [GLib.get_home_dir(), '.local', 'bin', 'linpaste']);
        if (GLib.file_test(local, GLib.FileTest.IS_EXECUTABLE))
            return local;
        return 'linpaste';
    }

    _poll() {
        this._clipboard.get_text(St.ClipboardType.CLIPBOARD, (_cb, text) => {
            if (!text)
                return;
            if (text === this._last)
                return;
            this._last = text;
            this._store(text);
        });
    }

    _store(text) {
        try {
            const proc = Gio.Subprocess.new(
                [this._linpaste, 'store'],
                Gio.SubprocessFlags.STDIN_PIPE |
                Gio.SubprocessFlags.STDOUT_SILENCE |
                Gio.SubprocessFlags.STDERR_SILENCE
            );
            // Fire-and-forget; reap the child so it doesn't linger as a zombie.
            proc.communicate_utf8_async(text, null, (p, res) => {
                try {
                    p.communicate_utf8_finish(res);
                } catch (e) {
                    console.error(`LinPaste: store failed: ${e}`);
                }
            });
        } catch (e) {
            console.error(`LinPaste: could not spawn ${this._linpaste}: ${e}`);
        }
    }
}
