const fs = require("node:fs");
const path = require("node:path");

const output = path.join(__dirname, "dist");
fs.mkdirSync(output, { recursive: true });
fs.writeFileSync(
  path.join(output, "build-info.json"),
  JSON.stringify({ name: "node-service", status: "built" }, null, 2) + "\n",
);
