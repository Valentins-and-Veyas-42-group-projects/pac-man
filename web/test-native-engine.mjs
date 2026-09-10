import assert from "node:assert/strict";

import engine from "./native-engine.mjs";

const tileSize = 18;
const graph = new Uint8Array(3 * tileSize);

function addMove(tile, move, destination, direction) {
    const offset = tile * tileSize + move * 4;
    graph[offset] = destination & 0xff;
    graph[offset + 1] = destination >> 8;
    graph[offset + 2] = direction;
    graph[tile * tileSize + 16] += 1;
}

addMove(0, 0, 1, 1);
addMove(1, 0, 0, 3);
addMove(1, 1, 2, 1);
addMove(2, 0, 1, 3);

assert.equal(engine.abiVersion(), 2);
assert.deepEqual(engine.bfsDistances(graph, 3, 3, 0), [0, 1, 2]);
console.log("Browser bridge: WASM BFS returned [0, 1, 2]");
