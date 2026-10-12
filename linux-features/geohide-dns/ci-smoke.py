"""CI-only real desktop startup check under Xvfb, with Chromium sandboxing."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def has_renderer(executable):
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            if (entry / "exe").resolve() != executable:
                continue
            if b"--type=renderer" in (entry / "cmdline").read_bytes().split(b"\0"):
                return True
        except OSError:
            continue
    return False


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
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Desktop exited early: {process.returncode}")
                windows = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", "codex-desktop"],
                                         capture_output=True, timeout=3)
                ready = windows.returncode == 0 and windows.stdout.strip() and has_renderer(executable)
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
                raise RuntimeError("No stable visible desktop window and renderer within 45 seconds")
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
