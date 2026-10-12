# GeoHide DNS for CachyOS / Arch

This opt-in feature adds `codex-desktop-geohide` and **ChatGPT Community
(GeoHide DNS)** to pacman packages. The normal `codex-desktop` launcher remains
available. Close existing ChatGPT/Codex desktop instances before switching:
upstream single-instance handling otherwise forwards requests to the already
running instance, which retains its original DNS.

```bash
codex-desktop-geohide --check
codex-desktop-geohide
codex-desktop-geohide --region eu
codex-desktop-geohide --region us --check
```

`CODEX_GEOHIDE_REGION=eu` also selects a region; the default is `ru`. Arguments
after these options are forwarded to the original launcher unchanged.

## Build

```bash
bash scripts/build-cachyos.sh --geohide
sudo pacman -U dist/codex-desktop-latest.pkg.tar.zst
```

Alternatively enable `geohide-dns` in the ignored features configuration before
building. The manifest and committed example configuration remain disabled by
default. The feature needs `bubblewrap` and Python 3; enabled pacman packages
declare both runtime dependencies. This integration is scoped to CachyOS/Arch
pacman outputs. For an unpackaged build, invoke
`codex-app/.codex-linux/features/geohide-dns/launch.sh` directly.

## How it works

Bubblewrap creates a private mount namespace containing a temporary
`resolv.conf` and an NSS hosts lookup route of `files dns`. This avoids sending
lookups to the host's systemd-resolved service. The desktop, its Electron
network processes, and the bundled native Codex inherit the namespace. The
original executable, bundled binaries, and ASAR are unchanged by this feature.
System files are never written. Temporary files are removed when the launcher
exits; the bubblewrap process dies with its parent.
The host's `/dev` is explicitly device-bound so `/dev/null`, random devices,
shared memory and GPU nodes remain accessible with the user's normal permissions.
Every launch checks `/dev/null` and `/dev/urandom` before starting Electron.

The provider addresses are a verified snapshot from
[GeoHide's server metadata](https://dns.geohide.ru/static/metadata/servers.json),
retrieved on 2026-10-12. Only servers marked `unlimit` are included, with at most
three per region (the libc resolver limit). The feature uses **ordinary DNS
on UDP/TCP port 53**, not DoH. GeoHide supports encrypted DNS separately.
Requests for the provider's supported domains may be routed through its
gateways. TLS certificate verification remains enabled and traffic is not
decrypted by this wrapper.

## Limits and cleanup

Unprivileged user namespaces must work; no fallback disables Chromium's
sandbox or changes global DNS. If GeoHide DNS or port 53 is unavailable in
your network, use another region or the normal launcher. `--check` resolves
`chatgpt.com` inside the same namespace and verifies its TLS certificate.
It does not prove successful OpenAI login or a model response.

Proxy variables and an explicit `--proxy-server` are rejected because remote
proxies resolve names themselves. Disable desktop/system proxy settings before
using this DNS route. Externally launched browsers, host D-Bus services, SSH
remote hosts, tools with their own DNS/proxy, and existing processes retain
their own networking. Loopback and names in the host's `/etc/hosts` continue
to resolve locally. A machine's DNS suffix/search settings are not inherited.

To disable it, use `codex-desktop`, or rebuild without `--geohide` to remove
the extra command and menu entry. No DNS rollback is necessary. Interrupted
launches may leave cache directories under `~/.cache/codex-desktop/geohide/`;
these contain only resolver configuration and can be removed after exit.

```bash
node --test linux-features/geohide-dns/test.js
```

Tests cover provider addresses, isolated NSS configuration, fail-closed input,
resource staging, argument forwarding, cleanup, and unchanged system files.
Actual namespace and provider connectivity acceptance runs separately in CI.
CI also starts the real desktop under Xvfb and requires a visible window and
a live Electron renderer without disabling Chromium sandboxing.
