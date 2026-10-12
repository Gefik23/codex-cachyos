#!/usr/bin/env bash
set -euo pipefail

feature_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
region="${CODEX_GEOHIDE_REGION:-ru}"
check=0
case "${1:-}" in
    --help|-h)
        printf '%s\n' 'Usage: codex-desktop-geohide [--region ru|eu|us] [--check] [app arguments]' \
            'Private DNS for Codex and its children; system DNS is unchanged.' \
            'Default region: ru. --check verifies DNS and the chatgpt.com TLS connection.'
        exit 0 ;;
esac
if [ "${1:-}" = --region ]; then
    [ "$#" -ge 2 ] || { printf 'Missing region\n' >&2; exit 2; }
    region="$2"
    shift 2
fi
case "$region" in ru|eu|us) ;; *) printf 'Expected region ru, eu or us\n' >&2; exit 2 ;; esac
if [ "${1:-}" = --check ]; then check=1; shift; fi
for tool in bwrap python3; do
    command -v "$tool" >/dev/null || { printf 'GeoHide requires %s; install bubblewrap and python with pacman.\n' "$tool" >&2; exit 1; }
done
# An upstream proxy performs its own DNS; do not claim private DNS controls it.
for name in HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy CODEX_LINUX_PROXY_SERVER; do
    [ -z "${!name:-}" ] || { printf 'GeoHide DNS conflicts with %s. Start without that proxy variable.\n' "$name" >&2; exit 1; }
done
for arg in "$@"; do
    case "$arg" in --proxy-server|--proxy-server=*) printf 'GeoHide DNS conflicts with --proxy-server.\n' >&2; exit 2 ;; esac
done

app_dir="$(cd "$feature_dir/../../.." && pwd)"
[ -x "$app_dir/start.sh" ] || { printf 'The packaged desktop launcher is missing.\n' >&2; exit 1; }
scratch_root="${XDG_CACHE_HOME:-$HOME/.cache}/codex-desktop/geohide"
mkdir -p "$scratch_root"
scratch="$(mktemp -d "$scratch_root/launch.XXXXXXXX")"
child=""
cleanup() { rm -rf -- "$scratch"; }
stop() { [ -z "$child" ] || kill -TERM "$child" 2>/dev/null || true; }
trap cleanup EXIT
trap 'stop; exit 130' INT
trap 'stop; exit 143' TERM
python3 "$feature_dir/run.py" --prepare "$feature_dir/servers.json" "$region" "$scratch"
resolv_target="$(readlink -f /etc/resolv.conf)"
[ -f "$resolv_target" ] || { printf 'System resolv.conf is missing.\n' >&2; exit 1; }
# Mounts are visible only inside this process tree. nss-resolve must not send
# child lookups to the host systemd-resolved service over D-Bus.
# Ordinary bind mounts can be nodev; explicitly retain access to /dev/null,
# random devices, shared memory, and GPU devices in the private namespace.
bwrap --bind / / --dev-bind /dev /dev --ro-bind "$scratch/resolv.conf" "$resolv_target" \
    --ro-bind "$scratch/nsswitch.conf" /etc/nsswitch.conf --die-with-parent \
    -- python3 "$feature_dir/run.py" --run "$app_dir/start.sh" "$check" "$region" "$@" &
child=$!
set +e
wait "$child"
status=$?
set -e
if [ "$status" -ne 0 ]; then
    printf 'GeoHide launch failed. No system DNS was changed. Try --check or another --region.\n' >&2
fi
exit "$status"
