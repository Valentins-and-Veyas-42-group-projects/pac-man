/** Load the C++ engine and expose its small synchronous browser contract. */
import createPacmanNative from "../build/wasm/wasm32/release/pacman-wasm.mjs";

const module = await createPacmanNative();
const MOVE_SIZE = 4;
const MOVES_PER_TILE = 4;
const TILE_SIZE = MOVE_SIZE * MOVES_PER_TILE + 2;
const UNREACHABLE = 0xffffffff;

function bfsDistances(flatMoves, tileCount, width, origin) {
    const graphSize = tileCount * TILE_SIZE;
    const outputSize = tileCount * Uint32Array.BYTES_PER_ELEMENT;
    const graphPointer = module._malloc(graphSize);
    const outputPointer = module._malloc(outputSize);

    if (graphPointer === 0 || outputPointer === 0) {
        module._free(graphPointer);
        module._free(outputPointer);
        return null;
    }

    try {
        const graph = module.HEAPU8.subarray(graphPointer, graphPointer + graphSize);
        graph.fill(0);
        for (let index = 0; index < flatMoves.length; index += 1) {
            graph[index] = flatMoves[index];
        }

        const status = module._pac_bfs_distances(
            graphPointer,
            tileCount,
            width,
            origin,
            outputPointer,
            tileCount,
        );
        if (status !== 0) {
            return null;
        }

        const firstWord = outputPointer / Uint32Array.BYTES_PER_ELEMENT;
        return Array.from(
            module.HEAPU32.subarray(firstWord, firstWord + tileCount),
            (distance) => (distance === UNREACHABLE ? -1 : distance),
        );
    } finally {
        module._free(outputPointer);
        module._free(graphPointer);
    }
}

function createTopology(flatMoves, tileCount, width) {
    const graphSize = tileCount * TILE_SIZE;
    const graphPointer = module._malloc(graphSize);
    const resultPointer = module._malloc(Uint32Array.BYTES_PER_ELEMENT);
    if (graphPointer === 0 || resultPointer === 0) {
        module._free(graphPointer);
        module._free(resultPointer);
        return 0;
    }
    try {
        const graph = module.HEAPU8.subarray(graphPointer, graphPointer + graphSize);
        graph.fill(0);
        graph.set(flatMoves);
        module.HEAPU32[resultPointer / 4] = 0;
        const status = module._pac_topology_create(
            graphPointer, tileCount, width, resultPointer,
        );
        return status === 0 ? module.HEAPU32[resultPointer / 4] : 0;
    } finally {
        module._free(resultPointer);
        module._free(graphPointer);
    }
}

function topologyBfsDistances(topology, tileCount, origin) {
    const outputSize = tileCount * Uint32Array.BYTES_PER_ELEMENT;
    const outputPointer = module._malloc(outputSize);
    if (outputPointer === 0) {
        return null;
    }
    try {
        const status = module._pac_topology_bfs_distances(
            topology, origin, outputPointer, tileCount,
        );
        if (status !== 0) {
            return null;
        }
        const firstWord = outputPointer / 4;
        return Array.from(
            module.HEAPU32.subarray(firstWord, firstWord + tileCount),
            (distance) => (distance === UNREACHABLE ? -1 : distance),
        );
    } finally {
        module._free(outputPointer);
    }
}

globalThis.pacmanWasm = Object.freeze({
    abiVersion: () => module._pac_abi_version(),
    bfsDistances,
    createTopology,
    destroyTopology: (topology) => module._pac_topology_destroy(topology),
    topologyBfsDistances,
});

export default globalThis.pacmanWasm;
