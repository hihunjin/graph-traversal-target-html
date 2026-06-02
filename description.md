# Graph HTML — Data & Viewer Reference

A self-contained, emailable graph visualization. One Python script (`build.py`) reads a
JSON dataset (`data.json`) and produces a single offline HTML file (`graph.html`) that
your colleagues can open in any browser — no server, no internet, no install.

```
data.json  ──▶  python3 build.py  ──▶  graph.html  (open in browser)
```

---

## 1. The data

Everything lives in **one JSON object** with three top-level keys: `graph`, `targets`,
`traversals`. `graph` is the single source of truth; `targets` and `traversals` only
*reference* ids that already exist in `graph` — they never define new nodes or edges.

```jsonc
{
  "graph":      { "nodes": [...], "edges": [...] },  // the universe of nodes/edges
  "targets":    [ ... ],                             // named sets of nodes you care about
  "traversals": [ ... ]                              // concrete walks that lead into a target
}
```

### 1.1 `graph.nodes`

```jsonc
{
  "id": "u1",                 // REQUIRED. Unique string. Everything references nodes by this.
  "label": "Alice",           // REQUIRED. Text drawn on the node.
  "type": "user",             // optional. Drives node color + appears in the legend.
  "properties": {             // optional. Free-form key/values shown on hover & on click.
    "email": "alice@x.com"
  }
}
```

- `type` is the styling hook. Each distinct `type` gets a color (see `TYPE_COLORS` in
  `build.py`); an unknown/missing type falls back to grey. Keep the set of types small.
- `properties` is just displayed, never queried. Keep it flat.

### 1.2 `graph.edges`

```jsonc
{
  "id": "e7",                 // optional but RECOMMENDED. Unique. Lets traversals name exact edges.
  "source": "a1",             // REQUIRED. Must be a node id.
  "target": "a2",             // REQUIRED. Must be a node id.
  "label": "transfer",        // optional. Text drawn on the edge.
  "type": "...",              // optional. (Reserved for edge styling.)
  "directed": true,           // optional. Default true → arrowhead source→target. false = no arrow.
  "score": 0.91,              // optional. Number. Edge weight/relevance. Enables "sorted" neighbor mode (§3.4).
  "properties": { ... }       // optional. Shown when the edge is clicked.
}
```

- If an edge has no `id`, the builder auto-assigns `__e0`, `__e1`, … by position. You then
  can't reference it explicitly from a traversal, so prefer giving edges real ids.
- `score` is optional and may be set on some edges only. When present it's shown in the
  edge label as `(0.91)`, on hover, and on click. It also unlocks the **sorted** neighbor
  mode (§3.4). The build **errors** if a `score` is present but not a number. If *no* edge
  in the dataset has a `score`, the sorted toggle is hidden entirely.

### 1.3 `targets`

A **target is a named set of node ids** — "the nodes I care about." Multiple traversals
(with different start nodes) can flow *into* one target.

```jsonc
{
  "id": "t1",                       // REQUIRED. Unique among targets (NOT a node id).
  "name": "Mule cluster",           // REQUIRED. Human label shown in the sidebar.
  "nodeIds": ["x1", "x2", "x3"],    // REQUIRED. The nodes this target groups. Must be node ids.
  "description": "Suspected mules"  // optional. Shown under the target in the sidebar.
}
```

- One node can belong to multiple targets.
- A single-node target is just a one-element `nodeIds`.

### 1.4 `traversals`

A **traversal is a concrete walk** through the graph that ends at a target. Each traversal
declares which target it belongs to via `targetId`. Paths are stored explicitly (the exact
node/edge sequence) so the viewer just *draws* them — it never re-runs graph algorithms.

```jsonc
{
  "id": "tr1",                  // REQUIRED. Unique among traversals.
  "targetId": "t1",            // REQUIRED. Which target this traversal belongs to. Must be a target id.
  "name": "Alice -> Mule",     // optional. Human label.
  "start": "u1",               // REQUIRED. Starting node id.
  "paths": [                   // REQUIRED. One or more concrete walks.
    {
      "nodes": ["u1","d1","a1","a2","a7","x1"],   // ordered node ids. length = hops + 1.
      "edges": ["e1","e4","e7","e8","e13"],        // ordered edge ids between consecutive nodes.
      "endpoint": "x1"                              // optional. The node this path aims at.
    }
  ]
}
```

- `path.edges[i]` is the edge from `nodes[i]` to `nodes[i+1]`, so
  **`edges.length === nodes.length - 1`**. The builder enforces this.
- If `edges` is omitted, the viewer infers each step's edge from the adjacency map
  (first edge connecting the two nodes). Listing them explicitly avoids ambiguity when two
  nodes share more than one edge.
- Multiple `paths` under one traversal = a fan-out (one start, several endpoints).
- **Every traversal belongs to a target** (`targetId` is required and must resolve). But
  belonging to a target does **not** guarantee it *reaches* that target — see the next note.

#### "Assigned but never reaches" traversals

A traversal can be assigned to a target whose nodes its path **never actually touches**:
none of the ids in any `paths[].nodes` appear in that `target.nodeIds`. This is **valid
data** — the traversal walks the graph but stops short of / beside the target — and the
builder only **warns** (it does not fail). The viewer flags it with a red `✗ no reach`
badge (see §3.6). Example — `tr8` is assigned to `t2` (whose only node is `a7`) but walks
a social chain that never includes `a7`:

```jsonc
{
  "id": "tr8",
  "targetId": "t2",                          // belongs to t2 (target node: a7)
  "name": "Social chain (never reaches Hub)",
  "start": "u3",
  "paths": [
    { "nodes": ["u3", "u2", "u1"], "edges": ["e22", "e21"], "endpoint": "u1" }
  ]                                            // none of u3/u2/u1 is a7 -> never reaches
}
```

### 1.5 Referential integrity (enforced at build time)

`build.py` aborts with a clear error if any reference dangles:

| Field | Must already exist in |
|-------|------------------------|
| `edges[].source`, `edges[].target` | `graph.nodes[].id` |
| `targets[].nodeIds[]` | `graph.nodes[].id` |
| `traversals[].targetId` | `targets[].id` |
| `traversals[].start` | `graph.nodes[].id` |
| `traversals[].paths[].nodes[]` | `graph.nodes[].id` |
| `traversals[].paths[].endpoint` | `graph.nodes[].id` |
| `traversals[].paths[].edges[]` | `graph.edges[].id` |
| `traversals[].paths[].edges.length` | must equal `nodes.length - 1` |

The only ids that are *not* node/edge references are the overlays' own identities:
`targets[].id` (e.g. `t1`) and `traversals[].id` (e.g. `tr1`).

**Non-fatal warning (does not stop the build):** if a traversal is assigned to a target
but its path reaches none of that target's nodes (§1.4), `build.py` prints a
`warning: traversal … reaches none of that target's nodes` to stderr and continues.

---

## 2. The build step (`build.py`)

```
python3 build.py                      # data.json  -> graph.html
python3 build.py mydata.json out.html # custom input/output
```

What it does, in order:

1. **Loads & validates** `data.json` (the integrity table above). Any dangling reference
   stops the build.
2. **Fetches the graph library** (`vis-network`) once from a CDN and caches it locally as
   `.vis-network.min.js`. Subsequent builds reuse the cache and need no internet.
3. **Inlines everything** into the HTML template:
   - the dataset as `const DATA = {...}`,
   - the entire vis-network library as an inline `<script>`,
   - the color constants.
4. **Writes `graph.html`** (~680 KB) — a single file with zero external dependencies.
   There are no `<script src=...>` tags, so it works fully offline and survives being
   emailed as an attachment.

Color configuration lives at the top of `build.py`:

```python
TYPE_COLORS = { "user": "#4e79a7", "device": "#59a14f", "account": "#f28e2b", "_default": "#9c9c9c" }
TARGET_COLOR    = "#e15759"   # target nodes (red)
TRAVERSAL_COLOR = "#b07aa1"   # traversal path nodes/edges (purple)
```

---

## 3. How the HTML viewer works

### 3.1 Layout

```
┌──────────────────────────────┬──────────────────────┐
│                              │  Legend               │  node types → colors
│                              │  Neighbor budget (N)  │  slider, 0–50
│        graph canvas          │  Targets & traversals │  one card per target
│        (vis-network)         │  Detail               │  click a node/edge
└──────────────────────────────┴──────────────────────┘
```

### 3.2 The key idea: nothing is drawn until you pick a target

The full dataset could be huge, so the viewer **never loads the whole graph into the
renderer**. On load it builds three in-memory indexes from `DATA` but leaves the canvas
empty:

- `NODE` — node id → node object
- `EDGE` — edge id → edge object
- `adj` — node id → list of `{neighbor, edgeId}` (the adjacency map, for 1-hop lookups)

vis-network only ever holds the **subset currently revealed**. This is what keeps a large
graph from overloading the browser.

### 3.3 Independent target & traversal toggles

Targets and traversals are **independent checkboxes** — there is no radio/replace behavior
and ticking a target does **not** auto-enable its traversals. You toggle each on/off
separately and the canvas shows the **union of everything currently ticked**, plus the
neighbor ring. This lets you isolate a single traversal when several overlap.

The visible node set is built from three groups:

1. **Target nodes** — `nodeIds` of every *ticked* target — drawn **red**, largest.
2. **Traversal nodes** — the path nodes of every *ticked* traversal — drawn in that
   **traversal's own color** (each traversal gets a distinct hue, see §3.8), with its path
   edges thickened in the same color. Target coloring wins where they overlap.
3. **Neighbor ring** — the 1-hop neighbors of all the above (the "core") not already shown
   — drawn small/faded in their normal type color.

Groups 1 + 2 are the **core** and are always shown completely; only the **neighbor ring is
capped by N**. Edges are drawn only when **both endpoints are visible**: an edge on a
ticked traversal's path takes that traversal's color and width 3, everything else is thin
grey. After assembling, `network.fit()` frames the result.

Because each traversal has its own color, overlapping traversals stay distinguishable —
toggle them on one at a time, or compare two side by side.

### 3.4 The N slider (neighbor budget) and selection mode

`N` (0–50, default 5) caps **only the neighbor ring** — never the core.

- The viewer collects all candidate neighbors (1-hop from any core node, excluding core
  nodes themselves).
- If there are `≤ N` candidates, all are shown. Otherwise it picks `N` of them by the
  current **mode**:
  - **random** (default) — uniform sample without replacement (Fisher–Yates). Re-rolled on
    every change, so each adjustment may show a different set.
  - **sorted by score** — the top `N` candidates ranked by the **highest `score` among the
    edges that connect them to the core** (descending). Deterministic. Candidates reachable
    only through unscored edges sort last.

The **random / sorted** radio appears right under the slider — but **only when at least one
edge in the dataset has a `score`** (§1.2). With no scores anywhere, the toggle is hidden
and selection is always random.

Dragging the slider (or switching mode) re-renders the current selection live. The Detail
panel reports e.g. `2 target(s), 3 traversal(s) shown` and
`16 core nodes + 4/4 neighbors (N=5, sorted by score)`.

> **Why a cap at all?** With thousands of high-degree nodes, showing *every* neighbor would
> re-create the overload. **Random** gives a representative peek; **sorted** surfaces the
> strongest-scoring connections first when your edges carry weights.

### 3.6 "No reach" traversals and per-target rate

Every traversal is attached to a target, but some never actually land on a target node
(§1.4). Such a traversal is tagged with a red **`✗ no reach`** badge next to its checkbox
in the target card, so you can see at a glance which assigned traversals stop short. The
badge is computed by checking whether any node in the traversal's paths appears in the
target's `nodeIds`.

Each target header also shows its **no-reach rate** — a red `NN%` = (traversals that never
reach) / (total traversals for that target), `0%` when all reach, omitted when the target
has no traversals.

### 3.7 Sorting the target list

A **Sort** dropdown above the target list reorders the cards (it does not change the graph).
Options:

- **Name (A→Z)** / **Name (Z→A)** — lexical by target `name`.
- **No-reach rate (high→low)** / **(low→high)** — by the per-target rate above; ties broken
  by name. Use high→low to surface the targets whose retrieval paths most often miss.

Re-sorting preserves which targets/traversals are currently ticked, so changing the order
never disturbs the graph view.

### 3.8 Interactions summary

| Action | Result |
|--------|--------|
| Tick a target checkbox | Add that target's nodes to the view (does **not** enable its traversals) |
| Tick a traversal checkbox | Add that traversal's path to the view, in its own color |
| Untick any checkbox | Remove it from the view; canvas empties when nothing is ticked |
| "Clear / hide all" | Untick everything and empty the canvas |
| Drag the **N** slider | Re-sample the neighbor ring for the current selection, live |
| Switch **random / sorted** | Re-pick the neighbor ring (score toggle, §3.4) |
| Change the **Sort** dropdown | Reorder the target list by name or no-reach rate (§3.7) |
| Hover a node | Tooltip with label, type, and all `properties` |
| Click a node | Detail panel shows id, type, and `properties` |
| Click an edge | Detail panel shows label, `source → target`, and `properties` |
| Drag a node / scroll | Reposition / zoom (standard vis-network) |

The sidebar lists each target as a card: a target checkbox + name + `(N nodes, M in)`
counts + its no-reach `NN%`, the optional description, and — nested below — **one checkbox
per traversal**, each with its own color swatch, start-node name, hop count, and a
`✗ no reach` badge where applicable. Targets and traversals toggle independently, and the
list order follows the **Sort** dropdown.

### 3.9 Visual encoding cheat-sheet

| Element | Color | Size / width | Meaning |
|---------|-------|--------------|---------|
| Target node | red `#e15759` | largest (22), border 3 | in a ticked target's `nodeIds` |
| Traversal node | that traversal's color (palette, §3.8) | large (20), border 3 | on a ticked traversal's path |
| Neighbor node | type color, 60% opacity | small (13), border 1 | sampled 1-hop context |
| Path edge | matching traversal color | width 3 | edge walked by a ticked traversal |
| Other visible edge | grey `#ccc` | width 1 | connects two visible nodes |

Each traversal is assigned a distinct color by its order in `traversals` (a 10-hue palette,
cycled if there are more than 10). Overlapping traversals therefore render in different
colors so they can be told apart.

---

## 4. Files

| File | Role |
|------|------|
| `data.json` | Sample dataset (fraud/accounts theme). Edit this. |
| `data2.json` | GraphRAG-style sample (see §5). Build with `python3 build.py data2.json graph2.html`. |
| `build.py` | Reads a dataset, validates it, inlines the library, writes the HTML. |
| `graph.html` / `graph2.html` | The generated, self-contained viewers. Send these to colleagues. |
| `.vis-network.min.js` | Local cache of the graph library (so builds work offline). |
| `plan.md` | Original design notes / schema rationale. |
| `description.md` | This document. |

---

## 5. GraphRAG-style example (`data2.json`)

`data2.json` reuses the exact same schema to model a **GraphRAG retrieval** over the
"Attention Is All You Need" topic — a worked mapping of RAG concepts onto the three datasets:

| Dataset piece | GraphRAG meaning |
|---------------|------------------|
| `graph.nodes` | **Entities extracted from the documents** (concepts, people, orgs, tasks). |
| `graph.edges` | Extracted relations between entities (`introduced`, `based on`, `replaces`, …). |
| `targets` | **Retrieved document chunks.** `nodeIds` are the entities that chunk covers; `description` holds the **document snippet** (the quoted passage) that was retrieved. |
| `traversals` | **Multi-hop reasoning paths** that start at the **query entity** (the `start` — the document entity the query matched) and follow relations to a retrieved chunk (the `targetId`). Each hop is a relation followed during retrieval. |

The query entity is **not** a separate node: the query is assumed to have been matched to an
existing document entity, so each traversal's `start` is just that matched entity (e.g. the
query "what problem did the transformer solve?" enters the graph at `e_transformer`). This
keeps the graph purely document-derived.

So the viewer reads naturally for RAG: tick a target to see *which chunk was retrieved and
its text*, tick a traversal to see *the reasoning path from the query entity to that
evidence*. `hop4` is intentionally a path that wanders from `Vaswani et al.` to
`Google Brain` and never reaches its chunk's entities — it shows up with the `✗ no reach`
badge (a retrieved path that didn't actually hit the evidence). The node types
(`concept`, `person`, `org`, `document`, `task`) are configured in `TYPE_COLORS` in `build.py`.
