// LinPaste Capture — GNOME Shell extension (GNOME 46+ / ESM).
//
// Why this exists: GNOME's Mutter compositor exposes no data-control Wayland
// protocol, so background tools like `wl-paste --watch` cannot observe clipboard
// changes. The shell itself is the only component with unrestricted clipboard
// access, so we listen for Mutter's `owner-changed` selection signal (one event
// per copy) and read St.Clipboard on each change, handing every new copy to the
// LinPaste Python backend by spawning `linpaste store` (text on stdin) — the
// exact same contract the rest of LinPaste already speaks.
//
// The shell is also the only component that can synthesize input on Wayland, so
// we expose a `Paste` D-Bus method: after the popup copies an entry and closes,
// the Python UI calls it and we fire a virtual Ctrl+V into the now-focused
// window — the "paste on select" behaviour of Win+V.

import St from 'gi://St';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Clutter from 'gi://Clutter';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

// Capture is primarily event-driven (see the `owner-changed` handler in
// enable()), but we keep a slow timer as a backstop in case a clipboard change
// ever slips past the signal. This is no longer the main mechanism, so it can
// be lazy — the signal catches copies the instant they happen.
const POLL_INTERVAL_MS = 1500;

// Image formats we try to capture, in order of preference. PNG first because
// it's lossless and what most apps and screenshot tools put on the clipboard.
const IMAGE_MIMES = ['image/png', 'image/jpeg', 'image/bmp', 'image/gif', 'image/webp'];

// Exported on gnome-shell's own bus connection, so callers address it via the
// well-known name `org.gnome.Shell` at this path.
const DBUS_PATH = '/io/github/anantapodder/LinPaste';
const DBUS_IFACE = `
<node>
  <interface name="io.github.anantapodder.LinPaste">
    <method name="Paste"/>
  </interface>
</node>`;

// The popup must close and focus must return to the previous window before the
// synthesized keystroke lands, otherwise we'd paste into nothing. A short grace
// period covers the compositor's refocus.
const PASTE_DELAY_MS = 80;

export default class LinPasteCaptureExtension extends Extension {
    enable() {
        this._clipboard = St.Clipboard.get_default();
        this._last = null;
        this._lastImage = null;
        this._linpaste = this._resolveLinpaste();
        this._virtualKeyboard = null;
        this._pasteTimeoutId = 0;

        // Primary capture path: react the moment the clipboard owner changes.
        // GNOME exposes no data-control protocol to read the clipboard in the
        // background, but Mutter *does* tell the shell whenever the selection
        // owner changes — one signal per copy. Driving capture off this event
        // (instead of only sampling on a timer) is what lets us catch several
        // copies made in quick succession; a 1s poll would only ever see the
        // last item still on the clipboard when the tick fired.
        this._selection = global.display.get_selection();
        this._ownerChangedId = this._selection.connect(
            'owner-changed',
            (_selection, selectionType) => {
                if (selectionType === Meta.SelectionType.SELECTION_CLIPBOARD)
                    this._poll();
            }
        );

        // Backstop timer in case a change ever slips past the signal.
        this._timeoutId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT,
            POLL_INTERVAL_MS,
            () => {
                this._poll();
                return GLib.SOURCE_CONTINUE;
            }
        );

        // Capture whatever is already on the clipboard at load time — no
        // owner-changed fires for content that predates us.
        this._poll();

        this._dbus = Gio.DBusExportedObject.wrapJSObject(DBUS_IFACE, this);
        this._dbus.export(Gio.DBus.session, DBUS_PATH);
    }

    disable() {
        if (this._ownerChangedId) {
            this._selection.disconnect(this._ownerChangedId);
            this._ownerChangedId = 0;
        }
        this._selection = null;
        if (this._timeoutId) {
            GLib.source_remove(this._timeoutId);
            this._timeoutId = null;
        }
        if (this._pasteTimeoutId) {
            GLib.source_remove(this._pasteTimeoutId);
            this._pasteTimeoutId = 0;
        }
        if (this._dbus) {
            this._dbus.unexport();
            this._dbus = null;
        }
        this._virtualKeyboard = null;
        this._clipboard = null;
        this._last = null;
        this._lastImage = null;
    }

    // D-Bus: synthesize Ctrl+V into whatever window holds focus once the popup
    // has gone away. Fire-and-forget — we schedule the keystroke and return so
    // the caller's call_sync doesn't block on the delay.
    Paste() {
        if (this._pasteTimeoutId)
            GLib.source_remove(this._pasteTimeoutId);
        this._pasteTimeoutId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT,
            PASTE_DELAY_MS,
            () => {
                this._pasteTimeoutId = 0;
                this._sendPaste();
                return GLib.SOURCE_REMOVE;
            }
        );
    }

    _sendPaste() {
        try {
            if (!this._virtualKeyboard) {
                const seat = Clutter.get_default_backend().get_default_seat();
                this._virtualKeyboard = seat.create_virtual_device(
                    Clutter.InputDeviceType.KEYBOARD_DEVICE);
            }
            const t = global.get_current_time();
            const kbd = this._virtualKeyboard;
            kbd.notify_keyval(t, Clutter.KEY_Control_L, Clutter.KeyState.PRESSED);
            kbd.notify_keyval(t, Clutter.KEY_v, Clutter.KeyState.PRESSED);
            kbd.notify_keyval(t, Clutter.KEY_v, Clutter.KeyState.RELEASED);
            kbd.notify_keyval(t, Clutter.KEY_Control_L, Clutter.KeyState.RELEASED);
        } catch (e) {
            console.error(`LinPaste: paste failed: ${e}`);
        }
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
            if (text) {
                if (text === this._last)
                    return;
                this._last = text;
                this._store(text);
                return;
            }
            // No text on the clipboard — it may be holding an image instead.
            this._pollImage();
        });
    }

    _pollImage() {
        const available = this._clipboard.get_mimetypes(St.ClipboardType.CLIPBOARD) || [];
        const mime = IMAGE_MIMES.find(m => available.includes(m));
        if (!mime)
            return;
        this._clipboard.get_content(St.ClipboardType.CLIPBOARD, mime, (_cb, bytes) => {
            if (!bytes)
                return;
            const data = bytes.get_data();
            if (!data || data.length === 0)
                return;
            // Cheap signature to avoid re-spawning every poll for the same image.
            // The Python side dedups authoritatively by content hash.
            const sig = `${mime}:${data.length}:${data[0]}:${data[data.length - 1]}`;
            if (sig === this._lastImage)
                return;
            this._lastImage = sig;
            this._storeImage(bytes, mime);
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

    _storeImage(bytes, mime) {
        try {
            const proc = Gio.Subprocess.new(
                [this._linpaste, 'store', '--image', '--mime', mime],
                Gio.SubprocessFlags.STDIN_PIPE |
                Gio.SubprocessFlags.STDOUT_SILENCE |
                Gio.SubprocessFlags.STDERR_SILENCE
            );
            // Binary stdin, so communicate_async with raw GLib.Bytes (not utf8).
            proc.communicate_async(bytes, null, (p, res) => {
                try {
                    p.communicate_finish(res);
                } catch (e) {
                    console.error(`LinPaste: image store failed: ${e}`);
                }
            });
        } catch (e) {
            console.error(`LinPaste: could not spawn ${this._linpaste}: ${e}`);
        }
    }
}
