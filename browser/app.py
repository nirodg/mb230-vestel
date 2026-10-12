#!/usr/bin/env python3
"""
OIPF Interactive Explorer for MB230 (Vestel/Novatek) TV Browser
================================================================
Serves a page with buttons that trigger OIPF API calls. Every result
is POSTed to /log and appended to device_research.log.

Usage:
    sudo python3 app.py
Then navigate the TV browser to http://<your-ip>/
"""

from flask import Flask, request, jsonify
import json
import os
from datetime import datetime

app = Flask(__name__)
LOG_FILE = "device_research.log"


# =============================================================================
# THE HTML PAGE
# =============================================================================
DASHBOARD_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OIPF Interactive Explorer</title>
<style>
    * { box-sizing: border-box; }
    body {
        font-family: Arial, sans-serif;
        background-color: #0f0f0f;
        color: #e0e0e0;
        padding: 12px;
        margin: 0;
        font-size: 13px;
    }
    h2 { color: #4CAF50; margin: 4px 0 8px 0; font-size: 16px; }
    h3 { color: #FFA500; margin: 10px 0 6px 0; font-size: 13px; }
    h4 { color: #FFD700; margin: 8px 0 4px 0; font-size: 12px; }

    #button-panel {
        background-color: #1a1a1a;
        border: 1px solid #333;
        border-radius: 5px;
        padding: 8px;
        margin-bottom: 10px;
    }
    .button-row {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        margin-bottom: 6px;
    }
    .button-row:last-child { margin-bottom: 0; }

    .btn {
        background-color: #2a2a2a;
        color: #00ffff;
        border: 1px solid #444;
        border-radius: 3px;
        padding: 6px 10px;
        font-size: 11px;
        cursor: pointer;
        font-family: monospace;
        transition: background 0.15s;
        white-space: nowrap;
    }
    .btn:hover { background-color: #3a3a3a; }
    .btn:active { background-color: #4CAF50; color: #000; }
    .btn.primary { border-color: #4CAF50; color: #4CAF50; }
    .btn.warn    { border-color: #FFA500; color: #FFA500; }
    .btn.danger  { border-color: #ff5555; color: #ff5555; }

    #status {
        background-color: #1a1a1a;
        border: 1px solid #333;
        border-radius: 3px;
        padding: 6px 10px;
        margin-bottom: 10px;
        font-family: monospace;
        font-size: 12px;
        min-height: 22px;
    }
    .status-ok   { color: #4CAF50; }
    .status-err  { color: #ff5555; }
    .status-busy { color: #FFA500; }

    #latest-result {
        background-color: #1a1a1a;
        border: 1px solid #333;
        border-radius: 5px;
        padding: 10px;
        margin-bottom: 10px;
        font-family: monospace;
        font-size: 12px;
        white-space: pre-wrap;
        word-break: break-all;
        max-height: 400px;
        overflow-y: auto;
    }

    #all-results {
        background-color: #0a0a0a;
        border: 1px solid #222;
        border-radius: 5px;
        padding: 10px;
        font-family: monospace;
        font-size: 11px;
        max-height: 400px;
        overflow-y: auto;
    }
    .result-entry {
        border-bottom: 1px dotted #333;
        padding: 6px 0;
    }
    .result-entry .label {
        color: #888;
        font-weight: bold;
    }
    .result-entry .value { color: #00ffff; }
    .result-entry .error { color: #ff5555; }
    .result-entry pre {
        color: #88ff88;
        margin: 4px 0;
        padding-left: 12px;
        white-space: pre-wrap;
        word-break: break-all;
    }

    .section-label {
        color: #666;
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin: 6px 0 2px 0;
    }
</style>
</head>
<body>

<h2>OIPF Interactive Explorer — MB230</h2>

<div id="button-panel">
    <div class="section-label">Factory Methods (createXObject)</div>
    <div class="button-row">
        <button class="btn primary" onclick="callFactory('createApplicationManagerObject')">ApplicationManager</button>
        <button class="btn primary" onclick="callFactory('createCapabilitiesObject')">Capabilities</button>
        <button class="btn primary" onclick="callFactory('createConfigurationObject')">Configuration</button>
        <button class="btn primary" onclick="callFactory('createDrmAgentObject')">DrmAgent</button>
        <button class="btn primary" onclick="callFactory('createParentalControlManagerObject')">ParentalControl</button>
        <button class="btn primary" onclick="callFactory('createRecordingSchedulerObject')">RecordingScheduler</button>
        <button class="btn primary" onclick="callFactory('createSearchManagerObject')">SearchManager</button>
        <button class="btn primary" onclick="callFactory('createVideoBroadcastObject')">VideoBroadcast</button>
        <button class="btn primary" onclick="callFactory('createVideoMpegObject')">VideoMpeg</button>
        <button class="btn primary" onclick="callFactory('createChannelConfig')">ChannelConfig</button>
    </div>

    <div class="section-label">Capabilities &amp; Support</div>
    <div class="button-row">
        <button class="btn warn" onclick="queryCapabilities()">Query Capabilities</button>
        <button class="btn warn" onclick="readCapabilitiesXML()">Raw Capabilities XML</button>
        <button class="btn warn" onclick="checkObjectSupport()">isObjectSupported (all)</button>
    </div>

    <div class="section-label">Live TV &amp; System</div>
    <div class="button-row">
        <button class="btn" onclick="probeBroadcastChannel()">Current Channel</button>
        <button class="btn" onclick="probeSignalStrength()">Signal Strength</button>
        <button class="btn" onclick="probeDvbTime()">DVB Time</button>
        <button class="btn" onclick="probeConfiguration()">Read Configuration</button>
    </div>

    <div class="section-label">Bulk / Global</div>
    <div class="button-row">
        <button class="btn danger" onclick="runAllProbes()">RUN ALL PROBES</button>
        <button class="btn danger" onclick="dumpGlobals()">Dump Globals</button>
        <button class="btn danger" onclick="probeAllMimeTypes()">Probe All MIME Types</button>
        <button class="btn danger" onclick="clearResults()">Clear Display</button>
    </div>

    <div class="section-label">Custom</div>
    <div class="button-row">
        <input id="custom-expr" type="text" placeholder="JS expression e.g. navigator.userAgent" style="flex:1; background:#2a2a2a; color:#0ff; border:1px solid #444; padding:5px; font-family:monospace; font-size:11px;">
        <button class="btn warn" onclick="evalCustom()">Eval</button>
    </div>
</div>

<div id="status">Ready.</div>
<div id="latest-result">No result yet. Click a button above.</div>
<div id="all-results"></div>

<script>
// =============================================================================
// STATE
// =============================================================================
const allResults = [];

function setStatus(msg, kind) {
    const el = document.getElementById("status");
    el.className = kind === "ok" ? "status-ok" : kind === "err" ? "status-err" : "status-busy";
    el.textContent = msg;
}

function showLatest(label, data) {
    const el = document.getElementById("latest-result");
    let text;
    try {
        text = typeof data === "string" ? data : JSON.stringify(data, null, 2);
    } catch (e) {
        text = String(data);
    }
    if (text.length > 4000) text = text.substring(0, 4000) + "\n…(truncated)";
    el.textContent = `[${label}]\n${text}`;
}

function appendResult(label, data, isError) {
    const entry = {
        timestamp: new Date().toISOString(),
        label: label,
        error: !!isError,
        data: data,
    };
    allResults.push(entry);

    const container = document.getElementById("all-results");
    const div = document.createElement("div");
    div.className = "result-entry";
    const labelSpan = `<span class="label">[${entry.timestamp.substring(11, 19)}] ${label}: </span>`;
    let body;
    try {
        body = typeof data === "string" ? data : JSON.stringify(data, null, 2);
    } catch (e) {
        body = String(data);
    }
    if (body.length > 2000) body = body.substring(0, 2000) + "\n…(truncated)";
    const cls = isError ? "error" : "value";
    div.innerHTML = labelSpan + `<pre class="${cls}">${escapeHTML(body)}</pre>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;

    sendToBackend(entry);
}

function escapeHTML(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function sendToBackend(entry) {
    try {
        await fetch("/log", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(entry)
        });
    } catch (e) {
        setStatus("Backend POST failed: " + e, "err");
    }
}

// =============================================================================
// FACTORY METHOD CALLS
// =============================================================================
function describeObject(obj) {
    const out = {
        typeof: typeof obj,
        isNull: obj === null,
    };
    if (!obj) return out;
    try { out.keys = Object.keys(obj); } catch (e) { out.keys_error = e.toString(); }
    try { out.ownProps = Object.getOwnPropertyNames(obj).slice(0, 100); } catch (e) {}
    try {
        const proto = Object.getPrototypeOf(obj);
        if (proto) out.protoProps = Object.getOwnPropertyNames(proto).slice(0, 100);
    } catch (e) {}
    return out;
}

function callFactory(methodName) {
    setStatus("Calling " + methodName + "…", "busy");
    try {
        if (typeof oipfObjectFactory === "undefined") {
            const err = "oipfObjectFactory is undefined";
            appendResult(methodName, err, true);
            setStatus(err, "err");
            return;
        }
        if (typeof oipfObjectFactory[methodName] !== "function") {
            const err = "Not a function: " + methodName;
            appendResult(methodName, err, true);
            setStatus(err, "err");
            return;
        }
        const obj = oipfObjectFactory[methodName]();
        const desc = describeObject(obj);
        appendResult(methodName, desc, false);
        showLatest(methodName, desc);
        setStatus("OK: " + methodName, "ok");
    } catch (e) {
        appendResult(methodName, "Exception: " + e, true);
        showLatest(methodName, "Exception: " + e);
        setStatus("Exception: " + e, "err");
    }
}

// =============================================================================
// CAPABILITIES
// =============================================================================
function queryCapabilities() {
    setStatus("Querying capabilities…", "busy");
    try {
        const caps = oipfObjectFactory.createCapabilitiesObject();
        if (!caps || typeof caps.hasCapability !== "function") {
            appendResult("capabilities", "hasCapability not available", true);
            setStatus("hasCapability not available", "err");
            return;
        }
        const tokens = [
            "+PVR", "+DRM", "+HD", "+UHD", "+HDR", "+HbbTV",
            "+DLNA", "+CSP", "+CORS", "+OITF", "+TS", "+VIDEO",
            "+AUDIO", "+DVB-T", "+DVB-C", "+DVB-S", "+CI",
            "+CI+", "+MHEG", "+DVB-T2", "+DVB-S2",
        ];
        const results = {};
        for (const t of tokens) {
            try { results[t] = caps.hasCapability(t); } catch (e) { results[t] = "err:" + e; }
        }
        appendResult("capabilities.hasCapability", results, false);
        showLatest("capabilities", results);
        setStatus("Capabilities queried", "ok");
    } catch (e) {
        appendResult("capabilities", "Exception: " + e, true);
        setStatus("Exception: " + e, "err");
    }
}

function readCapabilitiesXML() {
    setStatus("Reading xmlCapabilities…", "busy");
    try {
        const caps = oipfObjectFactory.createCapabilitiesObject();
        if (!caps) { appendResult("xmlCapabilities", "null", true); return; }
        let xml = "";
        try { xml = caps.xmlCapabilities || ""; } catch (e) { xml = "err: " + e; }
        if (xml.length > 8000) xml = xml.substring(0, 8000) + "\n…(truncated)";
        appendResult("xmlCapabilities", xml || "(empty)", false);
        showLatest("xmlCapabilities", xml || "(empty)");
        setStatus("xmlCapabilities read", "ok");
    } catch (e) {
        appendResult("xmlCapabilities", "Exception: " + e, true);
        setStatus("Exception: " + e, "err");
    }
}

function checkObjectSupport() {
    setStatus("Checking isObjectSupported…", "busy");
    try {
        if (!oipfObjectFactory || typeof oipfObjectFactory.isObjectSupported !== "function") {
            appendResult("isObjectSupported", "not available", true);
            setStatus("not available", "err");
            return;
        }
        const types = [
            "application/oipfapplicationmanager",
            "application/oipfcapabilities",
            "application/oipfconfiguration",
            "application/oipfdrmagent",
            "application/oipfparentalcontrolmanager",
            "application/oipfrecordingscheduler",
            "application/oipfsearchmanager",
            "video/broadcast",
            "video/mpeg",
            "application/oipfremotemanagement",
            "application/oipfdownloadmanager",
            "application/oipfgatewayinfo",
        ];
        const results = {};
        for (const t of types) {
            try { results[t] = oipfObjectFactory.isObjectSupported(t); }
            catch (e) { results[t] = "err:" + e; }
        }
        appendResult("isObjectSupported", results, false);
        showLatest("isObjectSupported", results);
        setStatus("Support checked", "ok");
    } catch (e) {
        appendResult("isObjectSupported", "Exception: " + e, true);
        setStatus("Exception: " + e, "err");
    }
}

// =============================================================================
// LIVE TV / SYSTEM
// =============================================================================
function probeBroadcastChannel() {
    setStatus("Probing broadcast channel…", "busy");
    try {
        const tv = oipfObjectFactory.createVideoBroadcastObject();
        if (!tv) { appendResult("video/broadcast", "null", true); return; }
        const out = {
            keys: Object.getOwnPropertyNames(tv).slice(0, 60),
            playState: tv.playState,
        };
        try {
            if (typeof tv.bindToCurrentChannel === "function") {
                tv.bindToCurrentChannel();
                out.boundToCurrentChannel = true;
            }
        } catch (e) { out.bindError = e.toString(); }
        try {
            const ch = tv.currentChannel;
            out.currentChannel = ch ? {
                id: ch.id, name: ch.name, onid: ch.onid,
                tsid: ch.tsid, sid: ch.sid, type: ch.type,
            } : null;
        } catch (e) { out.currentChannelError = e.toString(); }
        appendResult("video/broadcast", out, false);
        showLatest("video/broadcast", out);
        setStatus("Broadcast probed", "ok");
    } catch (e) {
        appendResult("video/broadcast", "Exception: " + e, true);
        setStatus("Exception: " + e, "err");
    }
}

function probeSignalStrength() {
    setStatus("Probing signal strength…", "busy");
    try {
        const tv = oipfObjectFactory.createVideoBroadcastObject();
        if (!tv || typeof tv.getSignalStrength !== "function") {
            appendResult("signalStrength", "not available", true);
            setStatus("not available", "err");
            return;
        }
        const s = tv.getSignalStrength();
        appendResult("signalStrength", s, false);
        showLatest("signalStrength", s);
        setStatus("Signal strength read", "ok");
    } catch (e) {
        appendResult("signalStrength", "Exception: " + e, true);
        setStatus("Exception: " + e, "err");
    }
}

function probeDvbTime() {
    setStatus("Probing DVB time…", "busy");
    try {
        const tv = oipfObjectFactory.createVideoBroadcastObject();
        if (!tv || typeof tv.getDvbTime !== "function") {
            appendResult("dvbTime", "not available", true);
            setStatus("not available", "err");
            return;
        }
        const t = tv.getDvbTime();
        appendResult("dvbTime", t, false);
        showLatest("dvbTime", t);
        setStatus("DVB time read", "ok");
    } catch (e) {
        appendResult("dvbTime", "Exception: " + e, true);
        setStatus("Exception: " + e, "err");
    }
}

function probeConfiguration() {
    setStatus("Reading configuration…", "busy");
    try {
        const cfgObj = oipfObjectFactory.createConfigurationObject();
        if (!cfgObj) { appendResult("configuration", "null", true); return; }
        const cfg = cfgObj.configuration;
        if (!cfg) { appendResult("configuration", "null config", true); return; }
        let data;
        try {
            data = (typeof cfg.getConfig === "function") ? cfg.getConfig() : "no getConfig";
        } catch (e) {
            data = "getConfig error: " + e;
        }
        appendResult("configuration.getConfig", data, false);
        showLatest("configuration", data);
        setStatus("Configuration read", "ok");
    } catch (e) {
        appendResult("configuration", "Exception: " + e, true);
        setStatus("Exception: " + e, "err");
    }
}

// =============================================================================
// BULK
// =============================================================================
function runAllProbes() {
    const methods = [
        "createApplicationManagerObject",
        "createCapabilitiesObject",
        "createConfigurationObject",
        "createDrmAgentObject",
        "createParentalControlManagerObject",
        "createRecordingSchedulerObject",
        "createSearchManagerObject",
        "createVideoBroadcastObject",
        "createVideoMpegObject",
        "createChannelConfig",
    ];
    setStatus("Running all " + methods.length + " factory probes…", "busy");
    methods.forEach((m, i) => setTimeout(() => callFactory(m), i * 200));
    setTimeout(queryCapabilities, methods.length * 200 + 100);
    setTimeout(probeBroadcastChannel, methods.length * 200 + 400);
    setStatus("Bulk probe started", "ok");
}

function dumpGlobals() {
    setStatus("Dumping globals…", "busy");
    const names = [
        "hbbtv", "oipf", "oipfObjectFactory", "cobalt", "webapis",
        "screenshot", "rs232", "lanCommand", "macid", "smarttva",
        "tvpreferences", "profilestatus", "systeminfo", "childlock",
        "avsclient", "freestreammedia", "maxdome", "tivibu", "freeview",
        "drmdata", "ott_api", "oipf_dae", "window_binding_plugin",
    ];
    const out = {};
    for (const n of names) {
        try {
            const v = window[n];
            if (typeof v === "undefined") out[n] = { exists: false };
            else out[n] = { exists: true, type: typeof v, keys: describeObject(v) };
        } catch (e) {
            out[n] = { error: e.toString() };
        }
    }
    appendResult("dumpGlobals", out, false);
    showLatest("dumpGlobals", out);
    setStatus("Globals dumped", "ok");
}

function probeAllMimeTypes() {
    setStatus("Probing all MIME types…", "busy");
    const types = [
        "application/oipfapplicationmanager",
        "application/oipfcapabilities",
        "application/oipfconfiguration",
        "application/oipfdownloadmanager",
        "application/oipfdownloadtrigger",
        "application/oipfdrmagent",
        "application/oipfgatewayinfo",
        "application/oipfobjectfactory",
        "application/oipfparentalcontrolmanager",
        "application/oipfrecordingscheduler",
        "application/oipfremotemanagement",
        "application/oipfsearchmanager",
        "application/opappproprietaryfunctionprovider",
        "application/hbbtvcsmanager",
        "application/hbbtvmediasynchroniser",
        "application/paneldetails",
        "application/macid",
        "application/drmdataobject",
        "application/freeviewobject",
        "application/tivibuobject",
        "systeminfoobject",
        "childlockstatus",
        "profilestatus",
        "tvpreferencesstatus",
        "freestreammedia_object",
        "avsclient",
        "video/broadcast",
    ];
    const out = {};
    for (const t of types) {
        try {
            const obj = document.createElement("object");
            obj.type = t;
            obj.style.position = "absolute";
            obj.style.left = "-9999px";
            obj.style.width = "1px";
            obj.style.height = "1px";
            document.body.appendChild(obj);
            out[t] = describeObject(obj);
            // Cleanup after a tick
            setTimeout(() => { try { document.body.removeChild(obj); } catch (e) {} }, 500);
        } catch (e) {
            out[t] = { error: e.toString() };
        }
    }
    appendResult("allMimeTypes", out, false);
    showLatest("allMimeTypes", out);
    setStatus("MIME types probed (" + Object.keys(out).length + ")", "ok");
}

function clearResults() {
    allResults.length = 0;
    document.getElementById("all-results").innerHTML = "";
    document.getElementById("latest-result").textContent = "Cleared.";
    setStatus("Cleared", "ok");
}

// =============================================================================
// CUSTOM EVAL
// =============================================================================
function evalCustom() {
    const expr = document.getElementById("custom-expr").value;
    if (!expr) return;
    setStatus("Evaluating: " + expr, "busy");
    try {
        // eslint-disable-next-line no-eval
        const result = eval(expr);
        appendResult("custom:" + expr, result, false);
        showLatest(expr, result);
        setStatus("OK", "ok");
    } catch (e) {
        appendResult("custom:" + expr, "Exception: " + e, true);
        showLatest(expr, "Exception: " + e);
        setStatus("Exception: " + e, "err");
    }
}

// =============================================================================
// INIT
// =============================================================================
document.addEventListener("DOMContentLoaded", () => {
    setStatus("Ready. Click a button.", "ok");
    appendResult("init", {
        userAgent: navigator.userAgent,
        oipfObjectFactory: typeof oipfObjectFactory,
    }, false);
});
</script>

</body>
</html>
'''


# =============================================================================
# ROUTES
# =============================================================================
@app.route('/')
def index():
    return DASHBOARD_HTML


@app.route('/log', methods=['POST'])
def log_data():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        print(f"[!] JSON parse failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

    ts = datetime.now().isoformat()

    # Console output — compact, one line per event
    label = data.get("label", "?")
    is_error = data.get("error", False)
    marker = "✗" if is_error else "✓"
    print(f"\n[{ts}] {marker} {label}")
    body = data.get("data")
    if isinstance(body, (dict, list)):
        try:
            s = json.dumps(body)
            if len(s) > 500:
                s = s[:500] + "…"
            print(f"    {s}")
        except Exception:
            print(f"    {body}")
    else:
        s = str(body)
        if len(s) > 500:
            s = s[:500] + "…"
        print(f"    {s}")

    # File output — full JSON line
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "received_at": ts,
                "label": label,
                "error": is_error,
                "data": body,
            }, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[!] File write failed: {e}")

    return jsonify({"status": "success", "received_at": ts})


# =============================================================================
# MAIN
# =============================================================================
if __name__ == '__main__':
    print("=" * 72)
    print(" OIPF Interactive Explorer — MB230")
    print("=" * 72)
    print(f" Log file: {os.path.abspath(LOG_FILE)}")
    print(" Listening on 0.0.0.0:80")
    print(" Point the TV browser at: http://<this-host-ip>/")
    print("=" * 72)
    print()
    app.run(host='0.0.0.0', port=80, debug=False)
