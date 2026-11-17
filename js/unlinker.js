// Bert's Tools - Unlinker: a pass-through with a Link / Unlink button.
//
// Unlink: remembers where the output was wired, then removes those links so the
//         target input's own widget (e.g. a prompt box) becomes editable again.
// Link:   reconnects the remembered links.
//
// Frontend-only: state and saved links live in node.properties, so they're saved
// with the workflow.

import { app } from "../../scripts/app.js";

const NODE_TYPE = "BertsUnlinker";
const PROP_UNLINKED = "berts_unlinked";
const PROP_SAVED = "berts_saved_links";
const OUTPUT = 2; // LiteGraph.OUTPUT

function getLink(graph, id) {
    if (id == null) return null;
    if (typeof graph.getLink === "function") return graph.getLink(id);
    const links = graph.links;
    if (!links) return null;
    return typeof links.get === "function" ? links.get(id) : links[id];
}

function toast(severity, detail) {
    const t = app.extensionManager?.toast;
    if (t?.add) t.add({ severity, summary: "Unlinker", detail, life: 3000 });
    else console.warn(`[Bert's Tools] Unlinker: ${detail}`);
}

function unlink(node) {
    const graph = node.graph;
    const out = node.outputs?.[0];
    const saved = [];
    for (const id of [...(out?.links || [])]) {
        const link = getLink(graph, id);
        if (!link) continue;
        const target = graph.getNodeById(link.target_id);
        saved.push({
            target_id: link.target_id,
            target_slot: link.target_slot,
            target_input: target?.inputs?.[link.target_slot]?.name ?? null,
        });
    }
    if (!saved.length) {
        toast("warn", "Nothing to unlink — connect the output to an input first.");
        return false;
    }
    node.disconnectOutput(0);
    node.properties[PROP_SAVED] = saved;
    return true;
}

function relink(node) {
    const graph = node.graph;
    const saved = node.properties[PROP_SAVED] || [];
    const missed = [];
    for (const s of saved) {
        const target = graph.getNodeById(s.target_id);
        if (!target) {
            missed.push(s);
            continue;
        }
        let tslot = -1;
        if (s.target_input && typeof target.findInputSlot === "function") {
            tslot = target.findInputSlot(s.target_input);
        }
        if (tslot < 0) tslot = s.target_slot;
        if (!node.connect(0, target, tslot)) missed.push(s);
    }
    if (missed.length) {
        console.warn("[Bert's Tools] Unlinker could not restore some links:", missed);
        toast("warn", "Couldn't restore a wire — the target node may have been deleted.");
    }
    node.properties[PROP_SAVED] = [];
}

app.registerExtension({
    name: "berts_tools.unlinker",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_TYPE) return;

        nodeType.prototype.updateUnlinkerLabel = function () {
            const w = this._bertsUnlinkButton;
            if (!w) return;
            const label = this.properties?.[PROP_UNLINKED] ? "🔗 Link" : "✂️ Unlink";
            w.name = label;
            w.label = label;
            this.setDirtyCanvas?.(true, true);
        };

        nodeType.prototype.toggleUnlinker = function () {
            if (!this.graph) return;
            this._bertsBusy = true;
            try {
                if (!this.properties[PROP_UNLINKED]) {
                    if (unlink(this)) this.properties[PROP_UNLINKED] = true;
                } else {
                    relink(this);
                    this.properties[PROP_UNLINKED] = false;
                }
            } finally {
                this._bertsBusy = false;
                this.updateUnlinkerLabel();
                this.graph?.setDirtyCanvas?.(true, true);
                app.graph?.setDirtyCanvas?.(true, true);
            }
        };

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated?.apply(this, arguments);
            this.properties = this.properties || {};
            if (this.properties[PROP_UNLINKED] === undefined) this.properties[PROP_UNLINKED] = false;
            if (!this.properties[PROP_SAVED]) this.properties[PROP_SAVED] = [];

            const w = this.addWidget("button", "✂️ Unlink", null, () => this.toggleUnlinker(), {
                serialize: false,
            });
            w.serialize = false; // state is kept in node.properties instead
            w.tooltip = "Unlink: remove the output wire so the target box can be typed in. Link: put it back.";
            this._bertsUnlinkButton = w;
            this.updateUnlinkerLabel();
            return r;
        };

        // Restore the button label from the saved workflow.
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = onConfigure?.apply(this, arguments);
            this.updateUnlinkerLabel();
            return r;
        };

        // Wiring the output by hand while unlinked resets the node to linked.
        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type, index, connected) {
            const r = onConnectionsChange?.apply(this, arguments);
            if (!this._bertsBusy && type === OUTPUT && connected && this.properties?.[PROP_UNLINKED]) {
                this.properties[PROP_UNLINKED] = false;
                this.properties[PROP_SAVED] = [];
                this.updateUnlinkerLabel();
            }
            return r;
        };
    },
});
