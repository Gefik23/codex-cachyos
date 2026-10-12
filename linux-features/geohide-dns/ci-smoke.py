"""CI-only real desktop startup check under Xvfb, with Chromium sandboxing."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def desktop_processes(executable):
    browsers, renderers = [], []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            # Sandboxed renderers can be non-dumpable: /proc/PID/exe is then
            # unreadable by the parent even with the same UID. cmdline remains
            # readable; match only the exact executable used by this CI app.
            arguments = (entry / "cmdline").read_bytes().split(b"\0")
            if not arguments or os.fsdecode(arguments[0]) != str(executable):
                continue
            if b"--no-sandbox" in arguments:
                raise RuntimeError("Desktop disabled Chromium sandboxing")
            if b"--type=renderer" in arguments:
                renderers.append(int(entry.name))
            elif not any(argument.startswith(b"--type=") for argument in arguments):
                browsers.append(int(entry.name))
        except OSError:
            continue
    return browsers, renderers


def main():
    launcher = Path(sys.argv[1]).resolve()
    app = launcher.parent.parent.parent.parent
    profile = Path(os.environ["RUNNER_TEMP"]) / "geohide-smoke-profile"
    profile.mkdir(mode=0o700, exist_ok=True)
    env = dict(os.environ, CODEX_HOME=str(profile / "codex"),
               XDG_CONFIG_HOME=str(profile / "config"),
               XDG_STATE_HOME=str(profile / "state"),
               CODEX_LINUX_DISABLE_USAGE_REPORTING="1", CODEX_OZONE_PLATFORM="x11")
    log = profile / "desktop.log"
    executable = (app / "ChatGPT").resolve()
    with log.open("wb") as output:
        process = subprocess.Popen([str(launcher), "--region", "eu",
                                    "--user-data-dir=" + str(profile / "electron")],
                                   env=env, stdout=output, stderr=output, start_new_session=True)
        try:
            deadline = time.monotonic() + 45
            ready_since = None
            observation = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Desktop exited early: {process.returncode}")
                browsers, renderers = desktop_processes(executable)
                visible = []
                for pid in browsers:
                    windows = subprocess.run(["xdotool", "search", "--onlyvisible", "--pid", str(pid)],
                                             capture_output=True, timeout=3)
                    if windows.returncode == 0:
                        visible.extend(windows.stdout.decode().split())
                observation = {"browserPids": browsers, "rendererPids": renderers, "visibleWindows": visible}
                ready = bool(visible and renderers)
                if ready:
                    if ready_since is None:
                        ready_since = time.monotonic()
                    elif time.monotonic() - ready_since >= 5:
                        print("GeoHide desktop: visible window and live Electron renderer for 5 seconds")
                        break
                else:
                    ready_since = None
                time.sleep(1)
            else:
                raise RuntimeError(f"No stable visible desktop window and renderer within 45 seconds: {observation}")
            if b"FATAL:" in log.read_bytes() or b"Failed to open /dev/null" in log.read_bytes():
                raise RuntimeError("Desktop log contains a fatal runtime error")
        except Exception:
            print(log.read_text(errors="replace")[-3500:], file=sys.stderr)
            raise
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


if __name__ == "__main__":
    main()
