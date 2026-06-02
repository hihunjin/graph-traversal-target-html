# Pure? Graph HTML.

* goal is to have a pure graph visualization html file to send this to my colleagues. I want to be able to open this file in a browser and see the graph visualization, and also have some way to represent multi hop traversal targets and target datasets.

## Dataset schemas

The whole thing is one JSON object, embedded in the HTML (so it stays a single self-contained file you can email). Three top-level keys: `graph`, `targets`, `traversals`.

### 1. Graph dataset

The base structure: what nodes exist and how they connect.

```jsonc
{
  "graph": {
    "nodes": [
      {
        "id": "n1",            // required, unique string. Everything else refers to nodes by this id.
        "label": "User: Alice", // required, what's drawn on the node
        "type": "user",        // optional, drives color/shape/grouping (e.g. user, account, device)
        "properties": {        // optional, free-form key/values shown on hover or click
          "email": "alice@x.com",
          "created": "2026-01-04"
        }
      },
      {
        "id": "n2",
        "label": "Device: iPhone",
        "type": "device",
        "properties": { "os": "iOS 18" }
      }
    ],
    "edges": [
      {
        "id": "e1",            // optional, unique string (useful for highlighting an exact edge)
        "source": "n1",        // required, must match a node id
        "target": "n2",        // required, must match a node id
        "label": "owns",       // optional, drawn on the edge
        "type": "ownership",   // optional, drives edge color/style
        "directed": true,      // optional, default true. arrowhead source -> target
        "properties": {        // optional, free-form
          "since": "2026-02"
        }
      }
    ]
  }
}
```

Notes:
- `id` is the contract. Targets and traversals reference nodes/edges purely by these ids.
- `type` is the hook for visual styling (color legend, shapes). Keep the set small and consistent.
- Keep `properties` flat-ish; it's just displayed, not queried.

### 2. Target dataset

"These are the nodes I care about / want to highlight." A target is just a reference to one or more node ids, plus optional grouping/metadata so colleagues understand *why* it's a target.

```jsonc
{
  "targets": [
    {
      "id": "t1",                  // required, unique target id
      "name": "Suspicious accounts", // required, human label for this target set
      "nodeIds": ["n1", "n5", "n9"], // required, the nodes this target highlights
      "description": "Flagged in review 2026-05" // optional
    }
  ]
}
```

Notes:
- A target is a *named set of node ids* — that's the simplest thing that's still useful.
- One node can belong to multiple targets; the UI can show that overlap.
- If you only ever care about single nodes, a target with a one-element `nodeIds` works fine.

### 3. Multi-hop traversal target dataset

"Starting somewhere, follow edges N hops, and these are the paths/endpoints I want to show." Represent each traversal as an explicit path (the sequence of nodes/edges actually walked) so it can be drawn deterministically — don't make the HTML re-run graph algorithms.

```jsonc
{
  "traversals": [
    {
      "id": "tr1",                 // required, unique
      "name": "Alice -> fraud ring", // required, human label
      "start": "n1",               // required, starting node id
      "paths": [                   // required, one or more concrete walks
        {
          "nodes": ["n1", "n2", "n5"],   // ordered node ids, length = hops + 1
          "edges": ["e1", "e7"],          // ordered edge ids between consecutive nodes (optional but recommended)
          "endpoint": "n5"                // optional, the node this path is "aiming at"
        }
      ]
    }
  ]
}
```

Notes:
- Each `path.nodes` is an ordered list; `path.edges[i]` is the edge from `nodes[i]` to `nodes[i+1]`. `edges.length === nodes.length - 1`.
- Listing `edges` explicitly avoids ambiguity when two nodes have multiple edges between them. If you omit it, the viewer can fall back to "any edge connecting these two."
- Multiple `paths` under one traversal = a fan-out (one start, several reachable targets).
- `endpoint` lets you mark *which* node is the goal vs. just intermediate hops.

### How they fit together

```jsonc
{
  "graph":      { "nodes": [...], "edges": [...] },  // the canvas
  "targets":    [ ... ],                             // highlight sets of nodes
  "traversals": [ ... ]                              // highlight ordered paths
}
```

All cross-references are by id. The HTML only needs to: render the graph, then on demand overlay a target (recolor its `nodeIds`) or a traversal (recolor its `paths`).

### Referential integrity rule

`graph` is the single source of truth. `targets` and `traversals` **do not define any new nodes or edges** — they only reference ids that already exist in `graph`. Every reference below must resolve to something in `graph`:

| Field | Must already exist in |
|-------|------------------------|
| `edges[].source`, `edges[].target` | `graph.nodes[].id` |
| `targets[].nodeIds[]` | `graph.nodes[].id` |
| `traversals[].start` | `graph.nodes[].id` |
| `traversals[].paths[].nodes[]` | `graph.nodes[].id` |
| `traversals[].paths[].endpoint` | `graph.nodes[].id` |
| `traversals[].paths[].edges[]` | `graph.edges[].id` |

The only ids that are *not* node/edge references are the overlay's own identity: `targets[].id` (e.g. `t1`) and `traversals[].id` (e.g. `tr1`). Those are unique within their own list and unrelated to node ids.

