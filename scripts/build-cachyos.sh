#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
usage() {
    cat <<'HELP'
Usage: bash scripts/build-cachyos.sh [--check] [--geohide]

Build a manual-update codex-desktop pacman package for CachyOS/Arch Linux.
--check verifies the host and build tools without downloading or installing.
The default builds dist/codex-desktop-latest.pkg.tar.zst; it does not install it.
--geohide includes the separate codex-desktop-geohide DNS launcher.
HELP
}

check_only=0
geohide=0
for option in "$@"; do
    case "$option" in
        --help|-h) usage; exit 0 ;;
        --check) check_only=1 ;;
        --geohide) geohide=1 ;;
        *) usage >&2; exit 2 ;;
    esac
done
fail() { printf '[cachyos][ERROR] %s\n' "$*" >&2; exit 1; }

# Use the actual host: a distro override must not turn a Debian machine into Arch.
unset OS_RELEASE_ID OS_RELEASE_ID_LIKE OS_RELEASE_FILE
source "$repo_dir/scripts/lib/linux-target-detect.sh"
OS_RELEASE_ID="$(os_release_field ID || true)"
OS_RELEASE_ID_LIKE="$(os_release_field ID_LIKE || true)"
os_release_matches cachyos arch archlinux || fail 'Run this entrypoint on CachyOS or Arch Linux.'
[ "$(id -u)" -ne 0 ] || fail 'Build as your regular user, without sudo; makepkg rejects root.'
case "$(uname -m)" in
    x86_64|aarch64|arm64) ;;
    *) fail 'The upstream payload supports only x86_64 and aarch64.' ;;
esac

missing=()
for tool in bash curl dpkg-deb gpg gpgv node npm python3 sha256sum tar make makepkg pacman zstd flock; do
    command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if [ "${#missing[@]}" -gt 0 ]; then
    printf '[cachyos] Missing tools: %s\n' "${missing[*]}" >&2
    fail 'Install build dependencies as documented in docs/CACHYOS.md.'
fi
node -e 'const [major, minor] = process.versions.node.split(".").map(Number); if (major < 22 || (major === 22 && minor < 12)) process.exit(1)' || fail 'Node.js 22.12 or newer is required for ASAR tooling.'
printf '[cachyos] Host and build tools passed.\n'
[ "$check_only" -eq 0 ] || exit 0

# This entrypoint always resolves the signed official stable repository.
[ -z "${UPSTREAM_DEB:-}" ] || fail 'UPSTREAM_DEB is unsupported here; use the signed online source.'
[ -z "${CODEX_UPSTREAM_LINUX_REPOSITORY:-}" ] || fail 'Repository overrides are unsupported here.'
export PACKAGE_WITH_UPDATER=0
export MAX_BUILD_THREADS="${MAX_BUILD_THREADS:-4}"
case "$MAX_BUILD_THREADS" in
    ''|*[!0-9]*) fail 'MAX_BUILD_THREADS must be an integer.' ;;
esac

# Start with the original upstream interface; do not rewrite local feature choices.
export CODEX_LINUX_FEATURES_CONFIG="$repo_dir/linux-features/features.example.json"
export TMPDIR="${XDG_CACHE_HOME:-$HOME/.cache}/codex-desktop-dev/tmp"
mkdir -p "$TMPDIR"
if [ "$geohide" -eq 1 ]; then
    feature_config="$(mktemp "$TMPDIR/geohide-features.XXXXXXXX.json")"
    trap 'rm -f -- "$feature_config"' EXIT
    printf '{"enabled":["geohide-dns"]}\n' > "$feature_config"
    export CODEX_LINUX_FEATURES_CONFIG="$feature_config"
fi
cd "$repo_dir"
make build-app
PACKAGE_VERSION="$(node -e 'const fs = require("node:fs"); const info = JSON.parse(fs.readFileSync("codex-app/.codex-linux/build-info.json", "utf8")); const version = info.upstreamLinuxPackage.version; if (!/^\d[0-9A-Za-z.+:~-]*$/.test(version)) throw new Error("Missing or invalid upstream version"); console.log(version.replace(/[:-]/g, "."));')"
export PACKAGE_VERSION
make pacman
printf '\nPackage built: %s/dist/codex-desktop-latest.pkg.tar.zst\n' "$repo_dir"
printf 'Install it explicitly: sudo pacman -U dist/codex-desktop-latest.pkg.tar.zst\n'
