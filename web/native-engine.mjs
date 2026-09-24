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

function topologyAnalyzeDistances(topology, tileCount, playerOrigin, ghosts) {
    const ghostPointer = module._malloc(ghosts.length);
    const distanceSize = tileCount * Uint32Array.BYTES_PER_ELEMENT;
    const playerPointer = module._malloc(distanceSize);
    const etaPointer = module._malloc(distanceSize);
    const ownersPointer = module._malloc(tileCount);
    if ((ghosts.length !== 0 && ghostPointer === 0) || playerPointer === 0 || etaPointer === 0 || ownersPointer === 0) {
        module._free(ghostPointer);
        module._free(playerPointer);
        module._free(etaPointer);
        module._free(ownersPointer);
        return null;
    }
    try {
        module.HEAPU8.set(ghosts, ghostPointer);
        const status = module._pac_topology_analyze_distances(
            topology,
            playerOrigin,
            ghostPointer,
            ghosts.length / 4,
            playerPointer,
            tileCount,
            etaPointer,
            ownersPointer,
            tileCount,
        );
        if (status !== 0) {
            return null;
        }
        const decodeDistances = (pointer) => Array.from(
            module.HEAPU32.subarray(pointer / 4, pointer / 4 + tileCount),
            (distance) => (distance === UNREACHABLE ? -1 : distance),
        );
        return {
            playerDistances: decodeDistances(playerPointer),
            threatEtas: decodeDistances(etaPointer),
            threatOwnerMasks: Array.from(module.HEAPU8.subarray(ownersPointer, ownersPointer + tileCount)),
        };
    } finally {
        module._free(ownersPointer);
        module._free(etaPointer);
        module._free(playerPointer);
        module._free(ghostPointer);
    }
}

function topologyThreatField(topology, tileCount, ghosts) {
    const ghostPointer = module._malloc(ghosts.length);
    const etaPointer = module._malloc(tileCount * Uint32Array.BYTES_PER_ELEMENT);
    const ownersPointer = module._malloc(tileCount);
    if ((ghosts.length !== 0 && ghostPointer === 0) || etaPointer === 0 || ownersPointer === 0) {
        module._free(ghostPointer);
        module._free(etaPointer);
        module._free(ownersPointer);
        return null;
    }
    try {
        module.HEAPU8.set(ghosts, ghostPointer);
        const status = module._pac_topology_threat_field(
            topology,
            ghostPointer,
            ghosts.length / 4,
            etaPointer,
            ownersPointer,
            tileCount,
        );
        if (status !== 0) {
            return null;
        }
        return {
            etas: Array.from(
                module.HEAPU32.subarray(etaPointer / 4, etaPointer / 4 + tileCount),
                (distance) => (distance === UNREACHABLE ? -1 : distance),
            ),
            ownerMasks: Array.from(
                module.HEAPU8.subarray(ownersPointer, ownersPointer + tileCount),
            ),
        };
    } finally {
        module._free(ownersPointer);
        module._free(etaPointer);
        module._free(ghostPointer);
    }
}

function topologyPredictThreat(topology, tileCount, ghosts, horizon) {
    const ghostPointer = module._malloc(ghosts.length);
    const etaPointer = module._malloc(tileCount * Uint32Array.BYTES_PER_ELEMENT);
    const ownersPointer = module._malloc(tileCount);
    if ((ghosts.length !== 0 && ghostPointer === 0) || etaPointer === 0 || ownersPointer === 0) {
        module._free(ghostPointer);
        module._free(etaPointer);
        module._free(ownersPointer);
        return null;
    }
    try {
        module.HEAPU8.set(ghosts, ghostPointer);
        const status = module._pac_topology_predict_threat(
            topology,
            ghostPointer,
            ghosts.length / 8,
            horizon,
            etaPointer,
            ownersPointer,
            tileCount,
        );
        if (status !== 0) {
            return null;
        }
        return {
            etas: Array.from(
                module.HEAPU32.subarray(etaPointer / 4, etaPointer / 4 + tileCount),
                (distance) => (distance === UNREACHABLE ? -1 : distance),
            ),
            ownerMasks: Array.from(
                module.HEAPU8.subarray(ownersPointer, ownersPointer + tileCount),
            ),
        };
    } finally {
        module._free(ownersPointer);
        module._free(etaPointer);
        module._free(ghostPointer);
    }
}

function topologyEvaluateActions(topology, tileCount, playerTile, threatEtas) {
    const etaPointer = module._malloc(tileCount * 4);
    const actionsPointer = module._malloc(4 * 20);
    const reachablePointer = module._malloc(tileCount * 4 * 2);
    const countPointer = module._malloc(4);
    if (!etaPointer || !actionsPointer || !reachablePointer || !countPointer) {
        for (const pointer of [etaPointer, actionsPointer, reachablePointer, countPointer]) module._free(pointer);
        return null;
    }
    try {
        module.HEAPU32.set(
            Array.from(threatEtas, (eta) => eta < 0 ? UNREACHABLE : eta),
            etaPointer / 4,
        );
        const status = module._pac_topology_evaluate_actions(
            topology, playerTile, etaPointer, tileCount, actionsPointer, 4,
            reachablePointer, tileCount * 4, countPointer,
        );
        if (status !== 0) return null;
        const count = module.HEAPU32[countPointer / 4];
        if (count > 4) return null;
        const view = new DataView(module.HEAPU8.buffer);
        return Array.from({ length: count }, (_, index) => {
            const offset = actionsPointer + index * 20;
            const safeTiles = view.getUint32(offset, true);
            return {
                safeTiles,
                safeIntersections: view.getUint32(offset + 4, true),
                horizonTicks: view.getUint32(offset + 8, true),
                minimumMargin: view.getUint8(offset + 19) ? view.getInt32(offset + 12, true) : null,
                firstTile: view.getUint16(offset + 16, true),
                direction: view.getUint8(offset + 18),
                reachableTiles: Array.from({ length: safeTiles }, (_, tile) =>
                    view.getUint16(reachablePointer + (index * tileCount + tile) * 2, true)),
            };
        });
    } finally {
        for (const pointer of [countPointer, reachablePointer, actionsPointer, etaPointer]) module._free(pointer);
    }
}

function topologySimulateAction(
    topology, tileCount, collectibles, predictionGrid, ghostOrder,
    origin, action, horizon, pacgumScore, powerPelletScore,
    frightenedTicks, comboScores,
) {
    if (collectibles.length !== tileCount ||
        predictionGrid.length !== (horizon + 1) * 4 * tileCount ||
        ghostOrder.length > 4 || horizon < 1) return null;
    const itemPointer = module._malloc(tileCount);
    const gridPointer = module._malloc(predictionGrid.length);
    const comboPointer = module._malloc(Math.max(1, comboScores.length * 4));
    const inputPointer = module._malloc(56);
    const resultPointer = module._malloc(40);
    const pathPointer = module._malloc((horizon + 1) * 2);
    const pointers = [itemPointer, gridPointer, comboPointer, inputPointer, resultPointer, pathPointer];
    if (pointers.some((pointer) => !pointer)) {
        for (const pointer of pointers) module._free(pointer);
        return null;
    }
    try {
        module.HEAPU8.set(collectibles, itemPointer);
        module.HEAPU8.set(predictionGrid, gridPointer);
        module.HEAPU32.set(comboScores, comboPointer / 4);
        const view = new DataView(module.HEAPU8.buffer);
        view.setUint32(inputPointer, itemPointer, true);
        view.setUint32(inputPointer + 4, tileCount, true);
        view.setUint32(inputPointer + 8, gridPointer, true);
        view.setUint32(inputPointer + 12, predictionGrid.length, true);
        view.setUint32(inputPointer + 16, comboPointer, true);
        view.setUint32(inputPointer + 20, comboScores.length, true);
        view.setUint32(inputPointer + 24, horizon, true);
        view.setUint32(inputPointer + 28, 4096, true);
        view.setUint32(inputPointer + 32, pacgumScore, true);
        view.setUint32(inputPointer + 36, powerPelletScore, true);
        view.setUint32(inputPointer + 40, frightenedTicks, true);
        view.setUint16(inputPointer + 44, origin, true);
        view.setUint8(inputPointer + 46, action);
        view.setUint8(inputPointer + 47, ghostOrder.length);
        for (let index = 0; index < 4; index += 1) {
            view.setUint8(inputPointer + 48 + index, ghostOrder[index] ?? 0);
        }
        view.setUint16(inputPointer + 52, 0, true);
        const status = module._pac_topology_simulate_action(
            topology, inputPointer, resultPointer, pathPointer, horizon + 1,
        );
        if (status !== 0) return null;
        const output = new DataView(module.HEAPU8.buffer);
        const pathLength = output.getUint32(resultPointer + 28, true);
        const score = output.getBigUint64(resultPointer, true);
        if (pathLength > horizon + 1 || score > BigInt(Number.MAX_SAFE_INTEGER)) return null;
        return {
            scoreGained: Number(score),
            survivalHorizon: output.getUint32(resultPointer + 8, true),
            pacgumsEaten: output.getUint32(resultPointer + 12, true),
            powerPelletsEaten: output.getUint32(resultPointer + 16, true),
            ghostsEaten: output.getUint32(resultPointer + 20, true),
            remainingPowerTicks: output.getUint32(resultPointer + 24, true),
            died: Boolean(output.getUint8(resultPointer + 32)),
            path: Array.from({ length: pathLength }, (_, index) =>
                output.getUint16(pathPointer + index * 2, true)),
        };
    } finally {
        for (const pointer of pointers) module._free(pointer);
    }
}

globalThis.pacmanWasm = Object.freeze({
    abiVersion: () => module._pac_abi_version(),
    bfsDistances,
    createTopology,
    destroyTopology: (topology) => module._pac_topology_destroy(topology),
    topologyBfsDistances,
    topologyAnalyzeDistances,
    topologyThreatField,
    topologyPredictThreat,
    topologyEvaluateActions,
    topologySimulateAction,
});

export default globalThis.pacmanWasm;
