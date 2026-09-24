/** Time the real WASM worker on snapshots from the Python FakeGame. */
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { Worker } from "node:worker_threads";

import { WasmAnalysisWorker } from "./analysis-worker-client.mjs";

const [fixturePath, roundsText, expectedDigest, pythonUsText] = process.argv.slice(2);
if (!fixturePath || !expectedDigest || !pythonUsText) {
    throw new Error("Expected fixture path, rounds, Python digest, and baseline time");
}
const rounds = Number(roundsText);
const pythonUs = Number(pythonUsText);
if (!Number.isSafeInteger(rounds) || rounds <= 0) throw new Error("Rounds must be positive");
if (!Number.isFinite(pythonUs) || pythonUs <= 0) throw new Error("Python baseline must be positive");
const fixture = JSON.parse(await readFile(fixturePath, "utf8"));
const snapshots = fixture.snapshots.map((snapshot) => {
    const ghosts = new Uint8Array(snapshot.ghosts.length * 8);
    snapshot.ghosts.forEach(([tile, direction, ghost, dangerous], index) => {
        const offset = index * 8;
        ghosts[offset] = tile & 0xff;
        ghosts[offset + 1] = tile >> 8;
        ghosts[offset + 2] = direction;
        ghosts[offset + 3] = ghost;
        ghosts[offset + 4] = dangerous;
    });
    return { playerTile: snapshot.playerTile, ghosts };
});
const worker = new Worker(new URL("./analysis-worker.mjs", import.meta.url));
const analysis = await WasmAnalysisWorker.create(
    Uint8Array.from(fixture.graph), fixture.tileCount, fixture.width, worker,
);
try {
    async function runAll() {
        const results = [];
        for (const snapshot of snapshots) {
            const result = await analysis.analyze(
                snapshot.playerTile, snapshot.ghosts, fixture.horizon,
            );
            results.push([
                result.threatEtas,
                result.actions.map((action) => [
                    action.direction,
                    action.firstTile,
                    action.reachableTiles,
                    action.safeTiles,
                    action.safeIntersections,
                    action.horizonTicks,
                    action.minimumMargin,
                ]),
            ]);
        }
        return results;
    }

    const actual = await runAll();
    const digest = createHash("sha256").update(JSON.stringify(actual)).digest("hex");
    if (digest !== expectedDigest) {
        throw new Error(`WASM result differs from Python: ${digest} != ${expectedDigest}`);
    }
    const samples = [];
    for (let round = 0; round < rounds; round += 1) {
        const started = process.hrtime.bigint();
        await runAll();
        samples.push(Number(process.hrtime.bigint() - started) / snapshots.length / 1_000);
    }
    samples.sort((left, right) => left - right);
    const middle = Math.floor(samples.length / 2);
    const median = samples.length % 2 ? samples[middle] : (samples[middle - 1] + samples[middle]) / 2;
    console.log(`  WASM Web Worker    ${median.toFixed(2).padStart(9)}  ${(pythonUs / median).toFixed(2)}x, matches Python`);
} finally {
    await analysis.close();
}
