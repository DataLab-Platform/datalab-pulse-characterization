/** Run the Pulse benchmark in DataLab-Web's pinned browser-main-thread Pyodide. */

import { createHash } from "node:crypto";
import {
  existsSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PULSE_ROOT = resolve(HERE, "..");
const DEV_ROOT = resolve(PULSE_ROOT, "..");
const WEB_ROOT = resolve(
  process.env.DATALAB_WEB_ROOT || resolve(DEV_ROOT, "DataLab-Web"),
);
const SIGIMA_ROOT = resolve(
  process.env.SIGIMA_ROOT || resolve(DEV_ROOT, "Sigima"),
);

function findWheel(directory, prefix) {
  if (!existsSync(directory)) {
    throw new Error(`Wheel directory does not exist: ${directory}`);
  }
  const matches = readdirSync(directory)
    .filter((name) => name.startsWith(prefix) && name.endsWith(".whl"))
    .sort();
  if (matches.length === 0) {
    throw new Error(`No ${prefix}*.whl found under ${directory}`);
  }
  return resolve(directory, matches.at(-1));
}

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

const pulseWheelPath = findWheel(resolve(PULSE_ROOT, "dist"), "datalab_pulse_");
const sigimaWheelPath = findWheel(resolve(SIGIMA_ROOT, "dist"), "sigima-1.1.6-");
const htmlPath = resolve(
  WEB_ROOT,
  "tests",
  "benchmark",
  "bench1",
  "browser",
  "index.html",
);
const benchmarkSource = readFileSync(
  resolve(HERE, "benchmark_alignment.py"),
  "utf8",
);
const pulseWheel = readFileSync(pulseWheelPath).toString("base64");
const sigimaWheel = readFileSync(sigimaWheelPath).toString("base64");
const requireFromWeb = createRequire(resolve(WEB_ROOT, "package.json"));
const { chromium } = requireFromWeb("playwright");

const browser = await chromium.launch({
  headless: true,
  args: [
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-features=CalculateNativeWinOcclusion",
  ],
});

let report;
try {
  const page = await browser.newPage();
  await page.addInitScript(
    ({ b64, name }) => {
      window.__chainRunner = "";
      window.__sigimaWheelB64 = b64;
      window.__sigimaWheelName = name;
    },
    {
      b64: sigimaWheel,
      name: sigimaWheelPath.split(/[\\/]/).at(-1),
    },
  );
  await page.goto(`file://${htmlPath.replace(/\\/g, "/")}`);
  await page.evaluate(() => window.benchBoot());
  report = await page.evaluate(
    async ({ wheelB64, source }) => {
      const py = window.bench.runtime;
      const binary = atob(wheelB64);
      const wheelBytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) {
        wheelBytes[index] = binary.charCodeAt(index);
      }
      const wheelPath = "/tmp/pulse_benchmark.whl";
      py.FS.writeFile(wheelPath, wheelBytes);
      py.globals.set("__pulse_wheel", wheelPath);
      py.globals.set("__pulse_benchmark_source", source);
      const wasmBefore = py._module.HEAP8.buffer.byteLength;
      const startedAt = performance.now();
      const jsonReport = await py.runPythonAsync(`
import json
import sys
import types

if __pulse_wheel not in sys.path:
    sys.path.insert(0, __pulse_wheel)
_pulse_benchmark_module = types.ModuleType("pulse_benchmark")
sys.modules[_pulse_benchmark_module.__name__] = _pulse_benchmark_module
exec(__pulse_benchmark_source, _pulse_benchmark_module.__dict__)
_pulse_configuration = _pulse_benchmark_module.BenchmarkConfiguration()
_pulse_report = _pulse_benchmark_module.run_benchmark(_pulse_configuration)
json.dumps(_pulse_report, sort_keys=True)
      `);
      const wasmAfter = py._module.HEAP8.buffer.byteLength;
      return {
        ...JSON.parse(String(jsonReport)),
        backend: "pyodide_browser_main_thread",
        pyodide_version: py.version,
        browser_wall_elapsed_s: (performance.now() - startedAt) / 1000,
        wasm_bytes_before: wasmBefore,
        wasm_bytes_after: wasmAfter,
        wasm_growth_bytes: wasmAfter - wasmBefore,
      };
    },
    { wheelB64: pulseWheel, source: benchmarkSource },
  );
  report.measured_at = new Date().toISOString();
  report.chromium_version = browser.version();
  report.pulse_wheel_sha256 = sha256(pulseWheelPath);
  report.sigima_wheel_sha256 = sha256(sigimaWheelPath);
} finally {
  await browser.close();
}

const serialized = `${JSON.stringify(report, null, 2)}\n`;
const outputIndex = process.argv.indexOf("--output");
if (outputIndex >= 0) {
  const outputPath = process.argv[outputIndex + 1];
  if (!outputPath) throw new Error("--output requires a JSON path");
  writeFileSync(resolve(outputPath), serialized);
} else {
  process.stdout.write(serialized);
}