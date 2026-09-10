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

globalThis.pacmanWasm = Object.freeze({
    abiVersion: () => module._pac_abi_version(),
    bfsDistances,
});

export default globalThis.pacmanWasm;
