/** Run cached WASM safety analysis off the browser main thread. */
import engine from "./native-engine.mjs";

let topology = 0;
let tileCount = 0;
let parentPort;

if (typeof process !== "undefined" && process.versions?.node) {
    ({ parentPort } = await import("node:worker_threads"));
}

function reply(message) {
    if (parentPort) parentPort.postMessage(message);
    else globalThis.postMessage(message);
}

function handle(message) {
    const { id, kind } = message;
    try {
        if (kind === "init") {
            if (topology) engine.destroyTopology(topology);
            tileCount = message.tileCount;
            topology = engine.createTopology(
                new Uint8Array(message.graph), tileCount, message.width,
            );
            reply({ id, ok: topology !== 0 });
            return;
        }
        if (kind === "close") {
            if (topology) engine.destroyTopology(topology);
            topology = 0;
            reply({ id, ok: true });
            return;
        }
        if (kind !== "analyze" || !topology) {
            reply({ id, ok: false });
            return;
        }

        const ghosts = new Uint8Array(message.ghosts);
        const threat = engine.topologyPredictThreat(
            topology, tileCount, ghosts, message.horizon,
        );
        const actions = threat && engine.topologyEvaluateActions(
            topology, tileCount, message.playerTile, threat.etas,
        );
        if (!threat || !actions) {
            reply({ id, ok: false });
            return;
        }

        const view = new DataView(message.output);
        view.setUint32(0, actions.length, true);
        const etaOffset = 4;
        const actionOffset = etaOffset + tileCount * 4;
        const reachableOffset = actionOffset + 4 * 20;
        for (let tile = 0; tile < tileCount; tile += 1) {
            view.setInt32(etaOffset + tile * 4, threat.etas[tile], true);
        }
        for (let index = 0; index < actions.length; index += 1) {
            const action = actions[index];
            const offset = actionOffset + index * 20;
            view.setUint32(offset, action.safeTiles, true);
            view.setUint32(offset + 4, action.safeIntersections, true);
            view.setUint32(offset + 8, action.horizonTicks, true);
            view.setInt32(offset + 12, action.minimumMargin ?? 0, true);
            view.setUint16(offset + 16, action.firstTile, true);
            view.setUint8(offset + 18, action.direction);
            view.setUint8(offset + 19, action.minimumMargin === null ? 0 : 1);
            for (let tile = 0; tile < action.reachableTiles.length; tile += 1) {
                view.setUint16(
                    reachableOffset + (index * tileCount + tile) * 2,
                    action.reachableTiles[tile], true,
                );
            }
        }
        reply({ id, ok: true });
    } catch {
        reply({ id, ok: false });
    }
}

if (parentPort) parentPort.on("message", handle);
else globalThis.onmessage = (event) => handle(event.data);
