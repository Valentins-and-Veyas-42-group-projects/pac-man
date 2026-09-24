import assert from "node:assert/strict";
import { Worker } from "node:worker_threads";

import { WasmAnalysisWorker } from "./analysis-worker-client.mjs";

const graph = new Uint8Array(3 * 18);
function addMove(tile, move, destination, direction) {
    const offset = tile * 18 + move * 4;
    graph[offset] = destination;
    graph[offset + 2] = direction;
    graph[tile * 18 + 16] += 1;
}
addMove(0, 0, 1, 1);
addMove(1, 0, 0, 3);
addMove(1, 1, 2, 1);
addMove(2, 0, 1, 3);

const worker = new Worker(new URL("./analysis-worker.mjs", import.meta.url));
const analysis = await WasmAnalysisWorker.create(graph, 3, 3, worker);
try {
    const result = await analysis.analyze(0, new Uint8Array(), 2);
    assert.deepEqual(result.threatEtas, [-1, -1, -1]);
    assert.deepEqual(result.actions, [{
        direction: 1,
        firstTile: 1,
        reachableTiles: [1, 0, 2],
        safeTiles: 3,
        safeIntersections: 0,
        horizonTicks: 2,
        minimumMargin: null,
    }]);
} finally {
    await analysis.close();
}
console.log("Worker bridge: shared-memory WASM safety analysis passed");
