"""CI-only real desktop startup check under Xvfb, with Chromium sandboxing."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def desktop_processes(root_pid):
    processes = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            status = (entry / "status").read_text()
            parent = int(next(line.split()[1] for line in status.splitlines() if line.startswith("PPid:")))
            arguments = (entry / "cmdline").read_bytes().split(b"\0")
            processes[int(entry.name)] = (parent, arguments, (entry / "comm").read_text().strip())
        except (OSError, ValueError, StopIteration):
            continue
    # Electron can rewrite argv[0] to the app title. Identify this launch by
    # ancestry, independent of process title or ptrace-protected exe links.
    descendants = {root_pid}
    while True:
        expanded = descendants | {pid for pid, (parent, _, _) in processes.items() if parent in descendants}
        if expanded == descendants:
            break
        descendants = expanded
    browsers, renderers, labels = [], [], []
    for pid in sorted(descendants):
        if pid not in processes:
            continue
        _, arguments, label = processes[pid]
        labels.append({"pid": pid, "name": label})
        if b"--no-sandbox" in arguments:
            raise RuntimeError("Desktop disabled Chromium sandboxing")
        if b"--type=renderer" in b"\0".join(arguments):
            renderers.append(pid)
        else:
            browsers.append(pid)
    return browsers, renderers, labels


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
                browsers, renderers, labels = desktop_processes(process.pid)
                visible = []
                for pid in browsers:
                    windows = subprocess.run(["xdotool", "search", "--onlyvisible", "--pid", str(pid)],
                                             capture_output=True, timeout=3)
                    if windows.returncode == 0:
                        visible.extend(windows.stdout.decode().split())
                observation = {"browserPids": browsers, "rendererPids": renderers, "visibleWindows": visible, "processNames": labels}
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
