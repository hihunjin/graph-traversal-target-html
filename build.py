#!/usr/bin/env python3
"""Build a single, self-contained graph-visualization HTML file from data.json.

The output HTML embeds both the dataset and the vis-network library inline, so it
works offline in any browser and can be emailed as one file.

Usage:
    python3 build.py                      # data.json -> graph.html
    python3 build.py mydata.json out.html
"""

import json
import sys
import urllib.request
from pathlib import Path

VIS_URL = "https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"
VIS_CACHE = Path(__file__).with_name(".vis-network.min.js")

# Color per node `type`. Unknown types fall back to the last entry.
# Muted / low-saturation palette — calm, neutral tones that stay distinguishable.
TYPE_COLORS = {
    "user": "#8fa8c4",
    "device": "#94b58c",
    "account": "#dcae84",
    # GraphRAG-style types (used by data2.json)
    "query": "#6b6b6b",
    "concept": "#8fa8c4",
    "person": "#94b58c",
    "org": "#dcae84",
    "document": "#b39bb0",
    "task": "#9fc2bf",
    "_default": "#bdbdbd",
}
TARGET_COLOR = "#e15759"      # highlight color for target nodes
TRAVERSAL_COLOR = "#b07aa1"   # highlight color for traversal paths


def fetch_vis_library() -> str:
    """Return the vis-network JS source, caching it next to this script."""
    if VIS_CACHE.exists():
        return VIS_CACHE.read_text(encoding="utf-8")
    print(f"Downloading vis-network from {VIS_URL} ...", file=sys.stderr)
    with urllib.request.urlopen(VIS_URL, timeout=30) as resp:
        src = resp.read().decode("utf-8")
    VIS_CACHE.write_text(src, encoding="utf-8")
    return src


def validate(data: dict) -> None:
    """Check referential integrity per plan.md; raise on any dangling reference."""
    graph = data.get("graph", {})
    node_ids = {n["id"] for n in graph.get("nodes", [])}
    edge_ids = {e.get("id") for e in graph.get("edges", []) if e.get("id")}

    errors = []

    def need_node(ref, where):
        if ref not in node_ids:
            errors.append(f"{where}: node id '{ref}' not found in graph.nodes")

    def need_edge(ref, where):
        if ref not in edge_ids:
            errors.append(f"{where}: edge id '{ref}' not found in graph.edges")

    for e in graph.get("edges", []):
        need_node(e["source"], f"edge {e.get('id', '?')}.source")
        need_node(e["target"], f"edge {e.get('id', '?')}.target")
        if "score" in e and not isinstance(e["score"], (int, float)):
            errors.append(f"edge {e.get('id', '?')}.score must be a number, got {e['score']!r}")

    target_ids = {t["id"] for t in data.get("targets", [])}
    for t in data.get("targets", []):
        for nid in t.get("nodeIds", []):
            need_node(nid, f"target {t['id']}.nodeIds")

    target_nodes = {t["id"]: set(t.get("nodeIds", [])) for t in data.get("targets", [])}
    warnings = []

    for tr in data.get("traversals", []):
        need_node(tr["start"], f"traversal {tr['id']}.start")
        tgt = tr.get("targetId")
        if tgt is not None and tgt not in target_ids:
            errors.append(f"traversal {tr['id']}.targetId '{tgt}' not found in targets")
        traversal_nodes = set()
        for i, p in enumerate(tr.get("paths", [])):
            for nid in p.get("nodes", []):
                need_node(nid, f"traversal {tr['id']}.paths[{i}].nodes")
                traversal_nodes.add(nid)
            if "endpoint" in p:
                need_node(p["endpoint"], f"traversal {tr['id']}.paths[{i}].endpoint")
            for eid in p.get("edges", []):
                need_edge(eid, f"traversal {tr['id']}.paths[{i}].edges")
            n_nodes = len(p.get("nodes", []))
            n_edges = len(p.get("edges", []))
            if n_edges and n_edges != n_nodes - 1:
                errors.append(
                    f"traversal {tr['id']}.paths[{i}]: edges length {n_edges} "
                    f"should be nodes length - 1 ({n_nodes - 1})"
                )
        # Non-fatal: a traversal assigned to a target whose path touches none of
        # that target's nodes never actually reaches it. Valid, but worth flagging.
        if tgt in target_nodes and not (traversal_nodes & target_nodes[tgt]):
            warnings.append(
                f"traversal {tr['id']} is assigned to target '{tgt}' but its path "
                f"reaches none of that target's nodes ({sorted(target_nodes[tgt])})"
            )

    if errors:
        raise ValueError("Referential integrity errors:\n  - " + "\n  - ".join(errors))
    for w in warnings:
        print(f"  warning: {w}", file=sys.stderr)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Graph</title>
<style>
  html, body {{ margin: 0; height: 100%; font-family: system-ui, sans-serif; }}
  #app {{ display: flex; height: 100vh; }}
  #net {{ flex: 1; min-width: 0; }}
  #side {{
    width: 280px; box-sizing: border-box; padding: 14px 16px;
    border-left: 1px solid #ddd; overflow-y: auto; background: #fafafa;
  }}
  #side h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .05em;
    color: #666; margin: 18px 0 8px; }}
  #side h2:first-child {{ margin-top: 0; }}
  .item {{ display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 14px; }}
  .item input {{ margin: 0; }}
  .swatch {{ width: 12px; height: 12px; border-radius: 3px; flex: none; }}
  .legend .item {{ cursor: default; }}
  #detail {{ font-size: 13px; color: #333; white-space: pre-wrap; word-break: break-word;
    background: #fff; border: 1px solid #e2e2e2; border-radius: 6px; padding: 10px;
    min-height: 40px; }}
  .muted {{ color: #999; }}
  button.reset {{ font-size: 12px; padding: 4px 10px; margin-top: 6px; cursor: pointer; }}
  .tgt {{ border: 1px solid #e4e4e4; border-radius: 6px; margin-bottom: 10px; background: #fff; }}
  .tgt > .item {{ padding: 6px 10px; font-weight: 600; border-bottom: 1px solid #eee; }}
  .tgt .trav {{ padding-left: 26px; }}
  .tgt .trav .item {{ font-weight: 400; padding: 3px 10px; }}
  .desc {{ font-size: 12px; color: #888; padding: 0 10px 6px 30px; }}
  .noreach {{ font-size: 11px; color: #c0392b; font-weight: 600; }}
</style>
</head>
<body>
<div id="app">
  <div id="net"></div>
  <div id="side">
    <h2>Legend</h2>
    <div id="legend" class="legend"></div>

    <h2>Neighbor budget (N)</h2>
    <div class="item">
      <input type="range" id="nslider" min="0" max="50" value="5" style="flex:1"
             oninput="onN(this.value)">
      <span id="nval" style="width:2.5em; text-align:right">5</span>
    </div>
    <div id="modeRow" class="item" style="display:none">
      <label class="item" style="padding:0">
        <input type="radio" name="nmode" value="random" checked onchange="render()"> random</label>
      <label class="item" style="padding:0">
        <input type="radio" name="nmode" value="sorted" onchange="render()"> sorted by score</label>
    </div>
    <div class="desc" style="padding-left:0">Extra 1-hop neighbors of the shown
      nodes. Target &amp; traversal nodes always show.</div>

    <h2>Targets &amp; traversals</h2>
    <div class="item" style="padding-top:0">
      <label class="muted" style="font-size:12px">Sort</label>
      <select id="tsort" onchange="renderTargetList()" style="flex:1; font-size:12px">
        <option value="name-asc">Name (A→Z)</option>
        <option value="name-desc">Name (Z→A)</option>
        <option value="noreach-desc">No-reach rate (high→low)</option>
        <option value="noreach-asc">No-reach rate (low→high)</option>
        <option value="hops-desc">Hops (high→low)</option>
        <option value="hops-asc">Hops (low→high)</option>
      </select>
    </div>
    <div class="item" style="padding-top:0">
      <label class="muted" style="font-size:12px">Then</label>
      <select id="tsort2" onchange="renderTargetList()" style="flex:1; font-size:12px">
        <option value="">— none —</option>
        <option value="name-asc">Name (A→Z)</option>
        <option value="name-desc">Name (Z→A)</option>
        <option value="noreach-desc">No-reach rate (high→low)</option>
        <option value="noreach-asc">No-reach rate (low→high)</option>
        <option value="hops-desc">Hops (high→low)</option>
        <option value="hops-asc">Hops (low→high)</option>
      </select>
    </div>
    <div class="desc" style="padding-left:0">Toggle each independently — a target
      shows only its own nodes; each traversal toggles its own path.</div>
    <div id="targets"></div>
    <button class="reset" onclick="clearOverlays()">Clear / hide all</button>

    <h2>Detail</h2>
    <div id="detail" class="muted">Tick a target or a traversal to show it.</div>
  </div>
</div>

<script>{vis_js}</script>
<script>
const DATA = {data_json};
const TYPE_COLORS = {type_colors};
const TARGET_COLOR = {target_color!r};
const TRAVERSAL_COLOR = {traversal_color!r};

// Muted fallback palette: any type not explicitly in TYPE_COLORS gets a color
// from here, chosen by a stable hash of the type name so the same type always
// maps to the same color (no all-gray legends, no flicker between renders).
const FALLBACK_PALETTE = [
  "#8fa8c4", "#94b58c", "#dcae84", "#b39bb0", "#9fc2bf",
  "#c4a48f", "#a8c48f", "#8f9fc4", "#c48fa8", "#a99fc4",
  "#bdb98c", "#8cbdb0", "#bd8c9f", "#9fbd8c", "#b0a8bd",
];
const colorOf = t => {{
  if (TYPE_COLORS[t]) return TYPE_COLORS[t];
  if (!t) return TYPE_COLORS._default;
  let h = 0;
  for (let i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) | 0;
  return FALLBACK_PALETTE[Math.abs(h) % FALLBACK_PALETTE.length];
}};

// --- index the full dataset, but DO NOT load it into vis ---
// vis only ever holds the subset currently revealed, so a huge graph never
// overloads the browser.
const NODE = {{}};                       // id -> node object
DATA.graph.nodes.forEach(n => {{ NODE[n.id] = n; }});

const EDGE = {{}};                       // edge id -> edge object
const adj = {{}};                        // node id -> [{{nid, eid, score}}] (1-hop neighbors)
let HAS_SCORES = false;                 // any edge carries a numeric score?
DATA.graph.edges.forEach((e, i) => {{
  const id = e.id || ("__e" + i);
  e.__id = id;
  EDGE[id] = e;
  const score = typeof e.score === "number" ? e.score : null;
  if (score !== null) HAS_SCORES = true;
  (adj[e.source] = adj[e.source] || []).push({{ nid: e.target, eid: id, score }});
  (adj[e.target] = adj[e.target] || []).push({{ nid: e.source, eid: id, score }});
}});

// Show the random/sorted toggle only when at least one edge has a score.
if (HAS_SCORES) document.getElementById("modeRow").style.display = "flex";

// empty datasets — populated on demand
const nodes = new vis.DataSet([]);
const edges = new vis.DataSet([]);

const network = new vis.Network(
  document.getElementById("net"),
  {{ nodes, edges }},
  {{
    physics: {{ stabilization: true, barnesHut: {{ springLength: 140 }} }},
    interaction: {{ hover: true, tooltipDelay: 120 }},
    nodes: {{ font: {{ size: 14 }} }},
  }}
);

const detail = document.getElementById("detail");

function tooltip(n) {{
  const lines = [n.label, "type: " + (n.type || "—")];
  if (n.properties) for (const [k, v] of Object.entries(n.properties)) lines.push(k + ": " + v);
  return lines.join("\\n");
}}

// role: 'target' | 'traversal' | 'neighbor' — drives styling.
// travCol (optional) overrides the traversal-node fill with its traversal's color.
function nodeView(id, role, travCol) {{
  const n = NODE[id];
  const style = {{
    target:    {{ bg: TARGET_COLOR,             border: "#7a1f20", bw: 3, size: 22 }},
    traversal: {{ bg: travCol || TRAVERSAL_COLOR, border: "#444",  bw: 3, size: 20 }},
    neighbor:  {{ bg: colorOf(n.type),          border: "#999",    bw: 1, size: 13 }},
  }}[role];
  return {{
    id, label: n.label, title: tooltip(n), shape: "dot",
    size: style.size, borderWidth: style.bw,
    color: {{ background: style.bg, border: style.border }},
    opacity: role === "neighbor" ? 0.6 : 1,
  }};
}}

// pathCol: the traversal color if this edge lies on a ticked path, else null/undefined.
function edgeView(id, pathCol) {{
  const e = EDGE[id];
  const scored = typeof e.score === "number";
  return {{
    id, from: e.source, to: e.target,
    label: scored ? `${{e.label || ""}} (${{e.score}})`.trim() : e.label,
    title: scored ? `${{e.label || "edge"}} · score ${{e.score}}` : e.label,
    arrows: e.directed === false ? "" : "to",
    color: {{ color: pathCol || "#ccc" }},
    width: pathCol ? 3 : 1,
    font: {{ size: 11, color: "#888", align: "middle" }},
  }};
}}

// sample k items from arr without replacement (Fisher–Yates prefix)
function sample(arr, k) {{
  if (k >= arr.length) return arr.slice();
  const a = arr.slice();
  for (let i = 0; i < k; i++) {{
    const j = i + Math.floor(Math.random() * (a.length - i));
    [a[i], a[j]] = [a[j], a[i]];
  }}
  return a.slice(0, k);
}}

// edge ids along a path's node sequence (uses explicit edges, else infers)
function pathEdges(p) {{
  if (p.edges && p.edges.length) return p.edges;
  const out = [];
  for (let i = 0; i < p.nodes.length - 1; i++) {{
    const a = p.nodes[i], b = p.nodes[i + 1];
    const hit = (adj[a] || []).find(x => x.nid === b);
    if (hit) out.push(hit.eid);
  }}
  return out;
}}

// Does this traversal's path actually land on any of its target's nodes?
function reachesTarget(tr) {{
  const tnodes = targetNodes[tr.targetId];
  if (!tnodes) return false;
  return tr.paths.some(p => p.nodes.some(id => tnodes.has(id)));
}}

// distinct color per traversal id, so overlapping paths stay distinguishable
const TRAV_PALETTE = [
  "#b07aa1", "#4e79a7", "#f28e2b", "#59a14f", "#e15759",
  "#76b7b2", "#edc948", "#9c755f", "#ff9da7", "#af7aa1",
];
function travColor(trId) {{
  let i = 0;
  for (const tr of (DATA.traversals || [])) {{ if (tr.id === trId) break; i++; }}
  return TRAV_PALETTE[i % TRAV_PALETTE.length];
}}

// The currently ticked targets and traversals.
function selectedTargets() {{
  return [...document.querySelectorAll('.tgt-toggle:checked')]
    .map(c => DATA.targets.find(t => t.id === c.value)).filter(Boolean);
}}
function selectedTraversals() {{
  return [...document.querySelectorAll('.trav-toggle:checked')]
    .map(c => DATA.traversals.find(t => t.id === c.value)).filter(Boolean);
}}

// Re-render the union of everything currently ticked + the N neighbor ring.
function render() {{
  const N = +document.getElementById("nslider").value;
  const targets = selectedTargets();
  const travs = selectedTraversals();

  if (!targets.length && !travs.length) {{ clearCanvas(); return; }}

  const role = {{}};                 // id -> 'target' | 'traversal' | 'neighbor'
  const edgeColor = {{}};            // edge id -> color (per traversal)

  // each ticked traversal: color its own path nodes + edges
  travs.forEach(tr => {{
    const col = travColor(tr.id);
    tr.paths.forEach(p => {{
      p.nodes.forEach(id => {{ if (role[id] !== "target") role[id] = "traversal"; }});
      pathEdges(p).forEach(eid => {{ edgeColor[eid] = col; }});
    }});
  }});
  // ticked targets win the node coloring
  targets.forEach(t => t.nodeIds.forEach(id => role[id] = "target"));

  // neighbor ring around the union (capped at N).
  // bestScore: for each candidate, the highest score among edges linking it to the core.
  const core = new Set(Object.keys(role));
  const bestScore = {{}};
  core.forEach(id => (adj[id] || []).forEach(({{ nid, score }}) => {{
    if (core.has(nid)) return;
    if (!(nid in bestScore) || (score !== null && score > bestScore[nid])) {{
      bestScore[nid] = score !== null ? score : (bestScore[nid] ?? -Infinity);
    }}
  }}));
  const candidates = Object.keys(bestScore);

  const mode = (document.querySelector('input[name="nmode"]:checked') || {{}}).value;
  let picked;
  if (HAS_SCORES && mode === "sorted") {{
    // top-N by best connecting-edge score (highest first); unscored sort last
    picked = candidates.slice()
      .sort((a, b) => (bestScore[b] - bestScore[a]))
      .slice(0, N);
  }} else {{
    picked = sample(candidates, N);   // random
  }}
  picked.forEach(id => {{ if (!role[id]) role[id] = "neighbor"; }});

  // assemble nodes; traversal nodes use their traversal's color
  const visNodes = Object.keys(role).map(id => nodeView(id, role[id], travNodeColor(id, travs, role)));

  const visibleIds = new Set(Object.keys(role));
  const visEdges = [];
  Object.keys(EDGE).forEach(eid => {{
    const e = EDGE[eid];
    if (visibleIds.has(e.source) && visibleIds.has(e.target)) {{
      visEdges.push(edgeView(eid, edgeColor[eid]));   // colored if on a ticked path
    }}
  }});

  nodes.clear(); edges.clear();
  nodes.add(visNodes); edges.add(visEdges);
  network.fit();

  detail.className = "";
  const modeLabel = (HAS_SCORES && mode === "sorted") ? "sorted by score" : "random";
  detail.textContent =
    `${{targets.length}} target(s), ${{travs.length}} traversal(s) shown\\n` +
    `${{core.size}} core nodes + ${{picked.length}}/${{candidates.length}} neighbors (N=${{N}}, ${{modeLabel}})`;
}}

// color for a traversal-role node: the color of the (first ticked) traversal it lies on
function travNodeColor(id, travs, role) {{
  if (role[id] !== "traversal") return null;
  for (const tr of travs) {{
    if (tr.paths.some(p => p.nodes.includes(id))) return travColor(tr.id);
  }}
  return null;
}}

function clearCanvas() {{
  nodes.clear(); edges.clear();
  detail.className = "muted";
  detail.textContent = "Tick a target or a traversal to show it.";
}}

function clearOverlays() {{
  document.querySelectorAll('.tgt-toggle, .trav-toggle').forEach(c => c.checked = false);
  clearCanvas();
}}

// N slider: re-roll the neighbor sample for the current selection live
function onN(v) {{
  document.getElementById("nval").textContent = v;
  render();
}}

// --- sidebar ---
function swatch(color) {{
  return `<span class="swatch" style="background:${{color}}"></span>`;
}}

const legend = document.getElementById("legend");
const types = [...new Set(DATA.graph.nodes.map(n => n.type).filter(Boolean))];
legend.innerHTML = types.map(t =>
  `<div class="item">${{swatch(colorOf(t))}}${{t}}</div>`).join("")
  || '<div class="item muted">no types</div>';

// target id -> Set of its node ids (for the "does it reach?" check)
const targetNodes = {{}};
(DATA.targets || []).forEach(t => {{ targetNodes[t.id] = new Set(t.nodeIds); }});

// group traversals by their targetId
const byTarget = {{}};
(DATA.traversals || []).forEach(tr => {{
  (byTarget[tr.targetId] = byTarget[tr.targetId] || []).push(tr);
}});

const startLabel = id => {{
  const n = NODE[id];
  return n ? n.label : id;
}};
// hop count derived from the longest path (nodes - 1)
const hops = tr => Math.max(0, ...tr.paths.map(p => p.nodes.length - 1));

// No-reach rate for a target: fraction of its traversals whose path never lands
// on a target node. 0 when the target has no traversals.
function noReachRate(t) {{
  const travs = byTarget[t.id] || [];
  if (!travs.length) return 0;
  const missed = travs.filter(tr => !reachesTarget(tr)).length;
  return missed / travs.length;
}}

// Hop metric for a target: the max hop count across its traversals (0 if none).
function targetHops(t) {{
  const travs = byTarget[t.id] || [];
  return travs.length ? Math.max(...travs.map(hops)) : 0;
}}

// Each sorter is a pure comparator on two targets. They're composed by
// renderTargetList(): the primary runs first, the secondary breaks ties.
const TARGET_SORTERS = {{
  "name-asc":     (a, b) => a.name.localeCompare(b.name),
  "name-desc":    (a, b) => b.name.localeCompare(a.name),
  "noreach-desc": (a, b) => noReachRate(b) - noReachRate(a),
  "noreach-asc":  (a, b) => noReachRate(a) - noReachRate(b),
  "hops-desc":    (a, b) => targetHops(b) - targetHops(a),
  "hops-asc":     (a, b) => targetHops(a) - targetHops(b),
}};

// Render the target cards in the chosen sort order, preserving checkbox state.
function renderTargetList() {{
  const checked = new Set(
    [...document.querySelectorAll('.tgt-toggle:checked, .trav-toggle:checked')].map(c => c.value)
  );
  const primary   = TARGET_SORTERS[document.getElementById("tsort").value] || TARGET_SORTERS["name-asc"];
  const secondary = TARGET_SORTERS[document.getElementById("tsort2").value]; // undefined when "— none —"
  // Primary first; secondary breaks ties; name keeps the order stable as a last resort.
  const sorter = (a, b) =>
    primary(a, b) || (secondary && secondary(a, b)) || a.name.localeCompare(b.name);
  const sorted = (DATA.targets || []).slice().sort(sorter);

  document.getElementById("targets").innerHTML = sorted.map(t => {{
    const travs = byTarget[t.id] || [];
    const travHtml = travs.map(tr => {{
      // A traversal assigned to this target whose path never lands on a target node.
      const badge = reachesTarget(tr) ? ""
        : ` <span class="noreach" title="path never reaches a target node">✗ no reach</span>`;
      const on = checked.has(tr.id) ? " checked" : "";
      return `<label class="item">${{swatch(travColor(tr.id))}}
         <input type="checkbox" class="trav-toggle" value="${{tr.id}}"${{on}} onchange="render()">
         ${{startLabel(tr.start)}} <span class="muted">(${{hops(tr)}}h)</span>${{badge}}</label>`;
    }}).join("") || '<div class="item muted">no traversals</div>';
    const rate = noReachRate(t);
    const rateTxt = travs.length
      ? ` <span class="noreach" title="no-reach rate">${{Math.round(rate * 100)}}%</span>` : "";
    const on = checked.has(t.id) ? " checked" : "";
    return `<div class="tgt">
      <label class="item">${{swatch(TARGET_COLOR)}}
        <input type="checkbox" class="tgt-toggle" value="${{t.id}}"${{on}} onchange="render()">
        ${{t.name}} <span class="muted">(${{t.nodeIds.length}} nodes, ${{travs.length}} in)</span>${{rateTxt}}</label>
      ${{t.description ? `<div class="desc">${{t.description}}</div>` : ""}}
      <div class="trav">${{travHtml}}</div>
    </div>`;
  }}).join("") || '<div class="item muted">none</div>';
}}

renderTargetList();

// --- detail panel on click ---
network.on("click", params => {{
  if (params.nodes.length) {{
    const n = NODE[params.nodes[0]];
    let txt = `${{n.label}}\\nid: ${{n.id}}\\ntype: ${{n.type || "—"}}`;
    if (n.properties) for (const [k, v] of Object.entries(n.properties)) txt += `\\n${{k}}: ${{v}}`;
    detail.textContent = txt; detail.className = "";
  }} else if (params.edges.length) {{
    const e = EDGE[params.edges[0]];
    let txt = e ? `${{e.label || "edge"}}\\n${{e.source}} -> ${{e.target}}` : "edge";
    if (e && typeof e.score === "number") txt += `\\nscore: ${{e.score}}`;
    if (e && e.properties) for (const [k, v] of Object.entries(e.properties)) txt += `\\n${{k}}: ${{v}}`;
    detail.textContent = txt; detail.className = "";
  }}
}});
</script>
</body>
</html>
"""


def build(data_path: Path, out_path: Path) -> None:
    data = json.loads(data_path.read_text(encoding="utf-8"))
    validate(data)
    vis_js = fetch_vis_library()

    html = HTML_TEMPLATE.format(
        vis_js=vis_js,
        data_json=json.dumps(data, ensure_ascii=False),
        type_colors=json.dumps(TYPE_COLORS),
        target_color=TARGET_COLOR,
        traversal_color=TRAVERSAL_COLOR,
    )
    out_path.write_text(html, encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"Wrote {out_path} ({size_kb:.0f} KB) — open it in any browser.")


def main() -> None:
    data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data.json")
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else data_path.with_suffix(".html")
    build(data_path, out_path)


if __name__ == "__main__":
    main()
