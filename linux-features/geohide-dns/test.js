"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");
const { stageEnabledLinuxFeatureInstall, loadLinuxFeaturePatchDescriptors } = require("../../scripts/lib/linux-features.js");
const feature = __dirname;

function fixture(fn) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "geohide-test-"));
  try { fn(dir); } finally { fs.rmSync(dir, { recursive: true, force: true }); }
}

test("feature stages only opted-in resources and adds no ASAR patches", () => fixture(dir => {
  const configPath = path.join(dir, "features.json");
  fs.writeFileSync(configPath, JSON.stringify({ enabled: [] }));
  const options = { featuresRoot: path.resolve(feature, ".."), featuresConfigPath: configPath };
  stageEnabledLinuxFeatureInstall(path.join(dir, "app"), options);
  assert.equal(fs.existsSync(path.join(dir, "app/.codex-linux/features/geohide-dns/launch.sh")), false);
  fs.writeFileSync(configPath, JSON.stringify({ enabled: ["geohide-dns"] }));
  assert.deepEqual(loadLinuxFeaturePatchDescriptors(options), []);
  stageEnabledLinuxFeatureInstall(path.join(dir, "app"), options);
  assert.match(fs.readFileSync(path.join(dir, "app/.codex-linux/features/geohide-dns/servers.json"), "utf8"), /159\.194\.200\.33/);
}));

test("private DNS preserves other NSS databases and the source files", () => fixture(dir => {
  const nss = path.join(dir, "system-nss");
  const original = "passwd: files systemd\nhosts: files mymachines resolve [!UNAVAIL=return] dns\nnetworks: files\n";
  fs.writeFileSync(nss, original);
  const code = "import sys; sys.path.insert(0, sys.argv[1]); from run import prepare; prepare(*sys.argv[2:])";
  const result = spawnSync("python3", ["-c", code, feature, path.join(feature, "servers.json"), "eu", dir, nss], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const resolv = fs.readFileSync(path.join(dir, "resolv.conf"), "utf8");
  assert.equal((resolv.match(/^nameserver /gm) || []).length, 3);
  assert.match(resolv, /nameserver 5\.175\.161\.3/);
  assert.equal(fs.readFileSync(nss, "utf8"), original);
  assert.equal(fs.readFileSync(path.join(dir, "nsswitch.conf"), "utf8"), "passwd: files systemd\nhosts: files dns\nnetworks: files\n");
}));

test("malformed DNS addresses and ambiguous NSS hosts rules fail closed", () => fixture(dir => {
  const metadata = path.join(dir, "servers.json");
  const nss = path.join(dir, "system-nss");
  const code = "import sys; sys.path.insert(0, sys.argv[1]); from run import prepare; prepare(*sys.argv[2:])";
  fs.writeFileSync(nss, "hosts: files dns\n");
  fs.writeFileSync(metadata, JSON.stringify({ regions: { ru: ["127.0.0.1\nnameserver evil"] } }));
  let result = spawnSync("python3", ["-c", code, feature, metadata, "ru", dir, nss], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  fs.writeFileSync(metadata, JSON.stringify({ regions: { ru: ["159.194.200.33"] } }));
  fs.writeFileSync(nss, "hosts: files\nhosts: dns\n");
  result = spawnSync("python3", ["-c", code, feature, metadata, "ru", dir, nss], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.equal(fs.readFileSync(nss, "utf8"), "hosts: files\nhosts: dns\n");
}));

test("launcher uses private binds, forwards arguments, cleans up, and refuses proxies", () => fixture(dir => {
  const app = path.join(dir, "app");
  const featureDir = path.join(app, ".codex-linux/features/geohide-dns");
  fs.mkdirSync(featureDir, { recursive: true });
  for (const name of ["launch.sh", "run.py", "servers.json"]) fs.copyFileSync(path.join(feature, name), path.join(featureDir, name));
  fs.writeFileSync(path.join(app, "start.sh"), '#!/bin/bash\nprintf "ARG:%s\\n" "$@"\n', { mode: 0o755 });
  const bin = path.join(dir, "bin"); fs.mkdirSync(bin);
  // A fixture wrapper records mount arguments; real namespace acceptance is CI.
  fs.writeFileSync(path.join(bin, "bwrap"), '#!/bin/bash\nprintf "BWRAP:%s\\n" "$@"\nwhile [ "$1" != -- ]; do shift; done\nshift\nexec "$@"\n', { mode: 0o755 });
  const env = { ...process.env, PATH: `${bin}:${process.env.PATH}`, XDG_CACHE_HOME: path.join(dir, "cache") };
  for (const name of ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy", "CODEX_LINUX_PROXY_SERVER"]) delete env[name];
  const before = fs.readFileSync("/etc/resolv.conf");
  const result = spawnSync("bash", [path.join(featureDir, "launch.sh"), "--region", "eu", "codex://test", "two words"], { env, encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /BWRAP:--ro-bind/);
  assert.match(result.stdout, /BWRAP:--bind\nBWRAP:\/\nBWRAP:\/\nBWRAP:--dev-bind\nBWRAP:\/dev\nBWRAP:\/dev\n/);
  assert.match(result.stdout, /BWRAP:--die-with-parent/);
  assert.match(result.stdout, /ARG:codex:\/\/test\nARG:two words/);
  assert.deepEqual(fs.readFileSync("/etc/resolv.conf"), before);
  assert.deepEqual(fs.readdirSync(path.join(env.XDG_CACHE_HOME, "codex-desktop/geohide")), []);
  const bad = spawnSync("bash", [path.join(featureDir, "launch.sh")], { env: { ...env, HTTPS_PROXY: "http://example.invalid" }, encoding: "utf8" });
  assert.notEqual(bad.status, 0);
  assert.match(bad.stderr, /conflicts with HTTPS_PROXY/);
}));

test("runtime preflight rejects inaccessible devices before executing the app", () => {
  const code = `
import sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
import run
with patch('builtins.open', side_effect=PermissionError('/dev/null: permission denied')):
    with patch('os.execv') as launch:
        try:
            run.main(['--run', '/app/start.sh', '0', 'ru'])
        except PermissionError:
            pass
        else:
            raise AssertionError('Device failure was ignored')
        launch.assert_not_called()
`;
  const result = spawnSync("python3", ["-c", code, feature], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
});
