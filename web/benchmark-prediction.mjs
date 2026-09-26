/** Verify and time the same ghost prediction through the WASM bridge. */
import assert from "node:assert/strict";
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
    const ghosts = new Uint8Array(fixture.ghosts.length * 8);
    fixture.ghosts.forEach(([tile, direction, ghost, dangerous], index) => {
        const offset = index * 8;
        ghosts[offset] = tile & 0xff;
        ghosts[offset + 1] = tile >> 8;
        ghosts[offset + 2] = direction;
        ghosts[offset + 3] = ghost;
        ghosts[offset + 4] = dangerous;
    });
    function predict() {
        const result = engine.topologyPredictThreat(topology, fixture.tileCount, ghosts, fixture.horizon);
        if (result === null) throw new Error("WASM ghost prediction failed");
        return result;
    }
    assert.deepEqual(predict(), fixture.expected);
    const samples = [];
    for (let round = 0; round < rounds; round += 1) {
        const started = process.hrtime.bigint();
        predict();
        samples.push(Number(process.hrtime.bigint() - started) / 1_000);
    }
    samples.sort((left, right) => left - right);
    const middle = Math.floor(samples.length / 2);
    const median = samples.length % 2 ? samples[middle] : (samples[middle - 1] + samples[middle]) / 2;
    console.log(`WASM cached prediction    ${median.toFixed(2).padStart(9)} us/call`);
} finally {
    engine.destroyTopology(topology);
}
