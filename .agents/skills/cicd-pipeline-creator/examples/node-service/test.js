const assert = require("node:assert/strict");
const packageJson = require("./package.json");

assert.equal(packageJson.name, "node-service");
assert.equal(typeof packageJson.scripts.build, "string");
