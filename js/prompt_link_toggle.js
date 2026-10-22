// Bert's Tools - "link prompts" toggle for Load Image (Extract Prompts).
//
// Off: remembers where the positive/negative outputs were wired, then removes those
//      links, so the downstream prompt boxes show their own text again.
// On:  reconnects the remembered links.
//
// Frontend-only: the toggle state and saved links live in node.properties, so they're
// saved with the workflow and nothing changes in what gets sent to the backend.

import { app } from "../../scripts/app.js";

const NODE_TYPE = "BertsLoadImageExtractPrompts";
const PROMPT_OUTPUTS = ["positive", "negative"];
const PROP_ON = "berts_link_prompts";
const PROP_SAVED = "berts_saved_prompt_links";

function getLink(graph, id) {
    if (id == null) return null;
    if (typeof graph.getLink === "function") return graph.getLink(id);
    const links = graph.links;
    if (!links) return null;
    return typeof links.get === "function" ? links.get(id) : links[id];
}

function outputSlot(node, name) {
    return (node.outputs || []).findIndex((o) => o.name === name);
}

function unlinkPrompts(node) {
    const graph = node.graph;
    const saved = [];
    for (const name of PROMPT_OUTPUTS) {
        const slot = outputSlot(node, name);
        if (slot < 0) continue;
        for (const id of [...(node.outputs[slot].links || [])]) {
            const link = getLink(graph, id);
            if (!link) continue;
            const target = graph.getNodeById(link.target_id);
            saved.push({
                output: name,
                target_id: link.target_id,
                target_slot: link.target_slot,
                target_input: target?.inputs?.[link.target_slot]?.name ?? null,
            });
        }
        if (node.outputs[slot].links?.length) node.disconnectOutput(slot);
    }
    // Keep earlier saved links that weren't reconnected (e.g. toggled off twice via load)
    const prior = node.properties[PROP_SAVED] || [];
    node.properties[PROP_SAVED] = saved.length ? saved : prior;
}

function relinkPrompts(node) {
    const graph = node.graph;
    const saved = node.properties[PROP_SAVED] || [];
    const missed = [];
    for (const s of saved) {
        const slot = outputSlot(node, s.output);
        const target = graph.getNodeById(s.target_id);
        if (slot < 0 || !target) {
            missed.push(s);
            continue;
        }
        let tslot = -1;
        if (s.target_input && typeof target.findInputSlot === "function") {
            tslot = target.findInputSlot(s.target_input);
        }
        if (tslot < 0) tslot = s.target_slot;
        const ok = node.connect(slot, target, tslot);
        if (!ok) missed.push(s);
    }
    if (missed.length) {
        console.warn("[Bert's Tools] Could not restore some prompt links:", missed);
    }
    node.properties[PROP_SAVED] = [];
}

app.registerExtension({
    name: "berts_tools.prompt_link_toggle",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_TYPE) return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated?.apply(this, arguments);
            this.properties = this.properties || {};
            if (this.properties[PROP_ON] === undefined) this.properties[PROP_ON] = true;
            if (!this.properties[PROP_SAVED]) this.properties[PROP_SAVED] = [];

            const node = this;
            const w = this.addWidget(
                "toggle",
                "link prompts",
                this.properties[PROP_ON],
                (value) => {
                    if (value === node.properties[PROP_ON]) return;
                    node.properties[PROP_ON] = value;
                    if (value) relinkPrompts(node);
                    else unlinkPrompts(node);
                    node.graph?.setDirtyCanvas?.(true, true);
                    app.graph?.setDirtyCanvas?.(true, true);
                },
                { on: "linked", off: "unlinked", serialize: false }
            );
            w.serialize = false; // state is kept in node.properties instead
            w.tooltip = "Off: remove the positive/negative links so the prompt boxes they feed come back. On: reconnect them.";
            this._bertsLinkToggle = w;
            return r;
        };

        // Restore the toggle's position from the saved workflow.
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = onConfigure?.apply(this, arguments);
            if (this._bertsLinkToggle && this.properties) {
                const on = this.properties[PROP_ON] !== false;
                this._bertsLinkToggle.value = on;
            }
            return r;
        };
    },
});
