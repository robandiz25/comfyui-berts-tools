// Bert's Tools - prompt text preview for Load Image (Extract Prompts + Preview).
//
// Adds read-only "positive" / "negative" text boxes to the node. They fill in as soon
// as an image is picked or uploaded (asks the backend route /berts/extract_prompts),
// and are refreshed with the exact strings the node output whenever it runs.
// The boxes are display-only: not saved in the workflow, not sent with the prompt.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

const NODE_TYPE = "BertsLoadImageExtractPromptsPreview";

function addPreviewBox(node, name, placeholder) {
    const w = ComfyWidgets["STRING"](node, name, ["STRING", { multiline: true }], app).widget;
    w.serialize = false;                       // not in widgets_values
    w.options = { ...(w.options || {}), serialize: false };  // not sent to the backend
    const el = w.inputEl || w.element;
    if (el) {
        el.readOnly = true;
        el.placeholder = placeholder;
        el.style.opacity = "0.85";
        el.style.fontSize = "11px";
    }
    return w;
}

function setText(w, text) {
    w.value = text || "";
    const el = w.inputEl || w.element;
    if (el) el.value = w.value;
}

function showPrompts(node, data, note) {
    const { positive = "", negative = "", source = "" } = data || {};
    setText(node._bertsPos, positive);
    setText(node._bertsNeg, negative);
    const label = note || (source === "none" ? "no prompt found in metadata" : source);
    for (const w of [node._bertsPos, node._bertsNeg]) {
        const el = w.inputEl || w.element;
        if (el) el.title = label ? `source: ${label}` : "";
    }
    if (!positive && !negative) {
        const el = node._bertsPos.inputEl || node._bertsPos.element;
        if (el) el.placeholder = label ? `(${label})` : "(positive prompt)";
    }
    node.graph?.setDirtyCanvas?.(true, true);
}

async function fetchPreview(node, imageName) {
    if (!imageName) {
        showPrompts(node, {}, "");
        return;
    }
    const token = (node._bertsFetchToken = (node._bertsFetchToken || 0) + 1);
    try {
        const res = await api.fetchApi(
            `/berts/extract_prompts?image=${encodeURIComponent(imageName)}`
        );
        const data = await res.json();
        if (token !== node._bertsFetchToken) return; // a newer pick already won
        if (!res.ok) showPrompts(node, {}, data?.error || `error ${res.status}`);
        else showPrompts(node, data);
    } catch (e) {
        if (token === node._bertsFetchToken) showPrompts(node, {}, "preview unavailable");
        console.warn("[Bert's Tools] prompt preview failed:", e);
    }
}

app.registerExtension({
    name: "berts_tools.prompt_preview",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_TYPE) return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated?.apply(this, arguments);
            this._bertsPos = addPreviewBox(this, "positive_text", "(positive prompt)");
            this._bertsNeg = addPreviewBox(this, "negative_text", "(negative prompt)");
            this._bertsLastImage = undefined;
            const [w, h] = this.size;
            this.setSize([Math.max(w, 360), Math.max(h, this.computeSize()[1] + 220)]);
            return r;
        };

        // Watch the image widget. Covers the dropdown, drag-and-drop, paste and the
        // upload button (they all end up changing this widget's value), plus workflow load.
        const onDrawForeground = nodeType.prototype.onDrawForeground;
        nodeType.prototype.onDrawForeground = function () {
            const r = onDrawForeground?.apply(this, arguments);
            const imgW = this.widgets?.find((w) => w.name === "image");
            const value = imgW?.value;
            if (value !== this._bertsLastImage) {
                this._bertsLastImage = value;
                clearTimeout(this._bertsTimer);
                this._bertsTimer = setTimeout(() => fetchPreview(this, value), 150);
            }
            return r;
        };

        // After a run: show exactly what the node output.
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const r = onExecuted?.apply(this, arguments);
            const data = message?.berts_prompts?.[0];
            if (data) showPrompts(this, data);
            return r;
        };
    },
});
