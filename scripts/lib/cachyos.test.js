"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { detectLinuxTargetContext } = require("./linux-target-context.js");

const repoDir = path.resolve(__dirname, "../..");

for (const [id, idLike] of [["cachyos", ""], ["cachyos", "arch"], ["arch", ""]]) {
  test(`${id} with ID_LIKE=${idLike || "absent"} selects pacman despite available Debian tools`, () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "cachyos-detect-"));
    try {
      // Mixed-tool hosts must follow the distro, rather than the dpkg fallback.
      for (const command of ["pacman", "apt-get", "dpkg-deb"]) {
        fs.writeFileSync(path.join(root, command), "#!/bin/sh\nexit 0\n", { mode: 0o755 });
      }
      const env = { PATH: root, OS_RELEASE_ID: id, OS_RELEASE_ID_LIKE: idLike };
      const target = detectLinuxTargetContext({
        env,
        osReleaseFields: { ID: id, ID_LIKE: idLike },
      });
      assert.equal(target.packageFormat, "pacman");
      assert.equal(target.packageManager, "pacman");

      const shell = spawnSync("/bin/bash", ["-c", [
        'source "$1"',
        "detect_package_format",
        "detect_package_manager",
      ].join("\n"), "bash", path.join(__dirname, "linux-target-detect.sh")], {
        env, encoding: "utf8",
      });
      assert.equal(shell.status, 0, shell.stderr);
      assert.equal(shell.stdout, "pacman\npacman\n");
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  });
}

test("CachyOS entrypoint documents a build-only default without starting a build", () => {
  const run = spawnSync("/bin/bash", [path.join(repoDir, "scripts/build-cachyos.sh"), "--help"], {
    encoding: "utf8",
  });
  assert.equal(run.status, 0, run.stderr);
  assert.match(run.stdout, /does not install it/);
  assert.match(run.stdout, /--check/);
});

test("CachyOS entrypoint rejects unknown arguments before any download", () => {
  const run = spawnSync("/bin/bash", [path.join(repoDir, "scripts/build-cachyos.sh"), "--unverified-source"], {
    encoding: "utf8",
  });
  assert.equal(run.status, 2);
  assert.match(run.stderr, /Usage:/);
});
