/** Compare cached WASM BFS against the Python graph on every maze origin. */
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

import engine from "./native-engine.mjs";

const [fixturePath, roundsText] = process.argv.slice(2);
const rounds = Number(roundsText);
if (!fixturePath || !Number.isSafeInteger(rounds) || rounds <= 0) {
    throw new Error("Expected a fixture path and a positive round count");
}
const fixture = JSON.parse(await readFile(fixturePath, "utf8"));
const topology = engine.createTopology(Uint8Array.from(fixture.graph), fixture.tileCount, fixture.width);
if (!topology) throw new Error("Could not create WASM topology");
try {
    function allDistances() {
        const fields = [];
        for (let origin = 0; origin < fixture.tileCount; origin += 1) {
            const distances = engine.topologyBfsDistances(topology, fixture.tileCount, origin);
            if (distances === null) throw new Error(`WASM BFS failed at origin ${origin}`);
            fields.push(distances);
        }
        return fields;
    }
    const digest = createHash("sha256").update(JSON.stringify(allDistances())).digest("hex");
    if (digest !== fixture.digest) throw new Error("WASM BFS differs from Python");
    const samples = [];
    for (let round = 0; round < rounds; round += 1) {
        const started = process.hrtime.bigint();
        allDistances();
        samples.push(Number(process.hrtime.bigint() - started) / fixture.tileCount / 1_000);
    }
    samples.sort((left, right) => left - right);
    const middle = Math.floor(samples.length / 2);
    const median = samples.length % 2 ? samples[middle] : (samples[middle - 1] + samples[middle]) / 2;
    console.log(`WASM selected cached       ${median.toFixed(2).padStart(9)} us/search`);
} finally {
    engine.destroyTopology(topology);
}
