/** Async Web Worker boundary for cached WASM safety analysis. */
export class WasmAnalysisWorker {
    constructor(worker, tileCount) {
        this.worker = worker;
        this.tileCount = tileCount;
        this.nextId = 0;
        this.pending = new Map();
        const receive = (message) => {
            const result = message.data ?? message;
            const resolve = this.pending.get(result.id);
            if (resolve) {
                this.pending.delete(result.id);
                resolve(result.ok);
            }
        };
        const fail = () => {
            for (const resolve of this.pending.values()) resolve(false);
            this.pending.clear();
        };
        if (worker.addEventListener) worker.addEventListener("message", receive);
        else worker.on("message", receive);
        if (worker.addEventListener) worker.addEventListener("error", fail);
        else {
            worker.on("error", fail);
            worker.on("exit", fail);
        }
    }

    static async create(graph, tileCount, width, worker = new Worker(
        new URL("./analysis-worker.mjs", import.meta.url), { type: "module" },
    )) {
        if (typeof SharedArrayBuffer === "undefined" ||
            (typeof window !== "undefined" && !globalThis.crossOriginIsolated)) {
            throw new Error("SharedArrayBuffer requires a cross-origin-isolated browser page");
        }
        const client = new WasmAnalysisWorker(worker, tileCount);
        const sharedGraph = new SharedArrayBuffer(graph.byteLength);
        new Uint8Array(sharedGraph).set(graph);
        if (!await client.request({ kind: "init", graph: sharedGraph, tileCount, width })) {
            await worker.terminate();
            throw new Error("Could not create WASM analysis topology");
        }
        return client;
    }

    request(command) {
        const id = this.nextId++;
        return new Promise((resolve) => {
            this.pending.set(id, resolve);
            this.worker.postMessage({ id, ...command });
        });
    }

    async analyze(playerTile, ghosts, horizon) {
        if (ghosts.byteLength % 8 !== 0) {
            throw new RangeError("Predicted ghost records must be 8 bytes each");
        }
        const sharedGhosts = new SharedArrayBuffer(ghosts.byteLength);
        new Uint8Array(sharedGhosts).set(ghosts);
        const tileCount = this.tileCount;
        const output = new SharedArrayBuffer(4 + tileCount * 4 + 4 * 20 + 4 * tileCount * 2);
        if (!await this.request({
            kind: "analyze", playerTile, ghosts: sharedGhosts, horizon, output,
        })) {
            throw new Error("WASM safety analysis failed");
        }
        const view = new DataView(output);
        const count = view.getUint32(0, true);
        if (count > 4) throw new Error("WASM returned too many actions");
        const actionOffset = 4 + tileCount * 4;
        const reachableOffset = actionOffset + 4 * 20;
        const threatEtas = Array.from({ length: tileCount }, (_, tile) =>
            view.getInt32(4 + tile * 4, true));
        const actions = Array.from({ length: count }, (_, index) => {
            const offset = actionOffset + index * 20;
            const safeTiles = view.getUint32(offset, true);
            if (safeTiles > tileCount) throw new Error("WASM returned invalid reachability");
            return {
                safeTiles,
                safeIntersections: view.getUint32(offset + 4, true),
                horizonTicks: view.getUint32(offset + 8, true),
                minimumMargin: view.getUint8(offset + 19) ? view.getInt32(offset + 12, true) : null,
                firstTile: view.getUint16(offset + 16, true),
                direction: view.getUint8(offset + 18),
                reachableTiles: Array.from({ length: safeTiles }, (_, tile) =>
                    view.getUint16(reachableOffset + (index * tileCount + tile) * 2, true)),
            };
        });
        return { threatEtas, actions };
    }

    async close() {
        await this.request({ kind: "close" });
        await this.worker.terminate();
    }
}
