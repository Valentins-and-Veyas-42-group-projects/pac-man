/** Compare every WASM BFS kernel against Python on every maze origin. */
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
    function allDistances(search) {
        const fields = [];
        for (let origin = 0; origin < fixture.tileCount; origin += 1) {
            const distances = search(origin);
            if (distances === null) throw new Error(`WASM BFS failed at origin ${origin}`);
            fields.push(distances);
        }
        return fields;
    }
    function batchedDistances() {
        const fields = [];
        for (let start = 0; start < fixture.tileCount; start += 5) {
            const origins = Array.from(
                { length: Math.min(5, fixture.tileCount - start) }, (_, index) => start + index,
            );
            const batch = engine.topologyBfsMany(topology, fixture.tileCount, origins);
            if (batch === null) throw new Error(`WASM batch BFS failed at origin ${start}`);
            fields.push(...batch);
        }
        return fields;
    }
    const graph = Uint8Array.from(fixture.graph);
    const modes = [
        ["graph one-shot", () => allDistances((origin) =>
            engine.bfsDistancesGraph(graph, fixture.tileCount, fixture.width, origin))],
        ["masked one-shot", () => allDistances((origin) =>
            engine.bfsDistances(graph, fixture.tileCount, fixture.width, origin))],
        ["graph cached", () => allDistances((origin) =>
            engine.topologyBfsDistancesGraph(topology, fixture.tileCount, origin))],
        ["masked cached", () => allDistances((origin) =>
            engine.topologyBfsDistancesMasked(topology, fixture.tileCount, origin))],
        ["selected cached", () => allDistances((origin) =>
            engine.topologyBfsDistances(topology, fixture.tileCount, origin))],
        ["selected batch", batchedDistances],
    ];
    for (const [name, search] of modes) {
        const digest = createHash("sha256").update(JSON.stringify(search())).digest("hex");
        if (digest !== fixture.digest) throw new Error(`WASM ${name} differs from Python`);
        const samples = [];
        for (let round = 0; round < rounds; round += 1) {
            const started = process.hrtime.bigint();
            search();
            samples.push(Number(process.hrtime.bigint() - started) / fixture.tileCount / 1_000);
        }
        samples.sort((left, right) => left - right);
        const middle = Math.floor(samples.length / 2);
        const median = samples.length % 2 ? samples[middle] : (samples[middle - 1] + samples[middle]) / 2;
        const unit = name === "selected batch" ? "field" : "search";
        console.log(`WASM ${name.padEnd(19)} ${median.toFixed(2).padStart(9)} us/${unit}`);
    }
} finally {
    engine.destroyTopology(topology);
}
