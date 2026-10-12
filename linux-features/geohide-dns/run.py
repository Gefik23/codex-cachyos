"""Private resolver configuration and preflight; no third-party dependencies."""
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import sys


def prepare(metadata, region, directory, nss_path="/etc/nsswitch.conf"):
    servers = json.loads(Path(metadata).read_text())["regions"][region]
    if not 1 <= len(servers) <= 3:
        raise ValueError("Expected one to three provider servers")
    servers = [str(ipaddress.ip_address(server)) for server in servers]
    directory = Path(directory)
    (directory / "resolv.conf").write_text(
        "# Private GeoHide DNS; system configuration is unchanged\n"
        + "".join(f"nameserver {server}\n" for server in servers)
        + "options timeout:2 attempts:2\n"
    )
    # Preserve every other NSS database; replace only the hosts lookup route.
    nss = Path(nss_path).read_text()
    nss, count = re.subn(r"(?m)^hosts\s*:.*$", "hosts: files dns", nss)
    if count != 1:
        raise ValueError("Expected exactly one hosts entry in nsswitch.conf")
    (directory / "nsswitch.conf").write_text(nss)


def check():
    addresses = sorted({result[4][0] for result in socket.getaddrinfo(
        "chatgpt.com", 443, type=socket.SOCK_STREAM
    )})
    if not addresses:
        raise RuntimeError("GeoHide returned no addresses for chatgpt.com")
    print("chatgpt.com: " + ", ".join(addresses), flush=True)
    with socket.create_connection(("chatgpt.com", 443), timeout=12) as stream:
        with ssl.create_default_context().wrap_socket(stream, server_hostname="chatgpt.com") as tls:
            print("chatgpt.com: TLS certificate verified", flush=True)


def main(argv):
    if argv[0] == "--prepare":
        prepare(*argv[1:])
        return
    if argv[0] != "--run":
        raise ValueError("Unknown mode")
    launcher, diagnostic, region, *arguments = argv[1:]
    if diagnostic == "1":
        print(f"GeoHide region: {region}", flush=True)
        check()
        return
    print(f"Starting ChatGPT Community with private GeoHide DNS ({region})", file=sys.stderr)
    os.execv(launcher, [launcher, *arguments])


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"GeoHide: {error}", file=sys.stderr)
        sys.exit(1)
