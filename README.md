# graph-traversal-target-html

Build a single, **self-contained** interactive graph-visualization HTML file from a
JSON dataset. The output embeds both your data and the [vis-network](https://visjs.github.io/vis-network/)
library inline, so it works fully offline in any browser and can be shared as one file.

## Features

- **Interactive graph** of nodes and edges, colored by node `type` (muted palette;
  unknown types get a stable color derived from the type name).
- **Targets & traversals** sidebar — toggle each independently to highlight a target's
  nodes or a traversal's path.
- **Neighbor budget (N)** — reveal up to N extra 1-hop neighbors of the shown nodes,
  picked randomly or by edge score.
- **Sorting** of the target list by name, no-reach rate, or traversal hop count, with a
  primary + secondary (tie-breaker) sort.
- **No-reach detection** — flags traversals whose path never lands on their target's nodes.

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python project/runner)
- Internet access on first run only — `build.py` downloads vis-network once and caches it
  next to the script as `.vis-network.min.js`.

The build script uses only the Python standard library; there are no third-party
dependencies to install.

## Usage

```bash
# data.json -> data.html
uv run python build.py

# explicit input and output
uv run python build.py data_linearRAG5.json data_linearRAG5.html
```

If no output path is given, the input's extension is replaced with `.html`.
Open the resulting `.html` file in any browser.

## Input format

The input is a JSON object with three top-level keys:

```jsonc
{
  "graph": {
    "nodes": [{ "id": "...", "label": "...", "type": "..." }],
    "edges": [{ "id": "...", "source": "...", "target": "...", "label": "...", "score": 0.0 }]
  },
  "targets": [
    { "id": "...", "name": "...", "nodeIds": ["..."], "description": "..." }
  ],
  "traversals": [
    {
      "id": "...",
      "targetId": "...",          // must match a target id
      "name": "...",
      "start": "...",             // a node id
      "paths": [{ "nodes": ["..."], "edges": ["..."], "endpoint": "..." }]
    }
  ]
}
```

`build.py` validates the dataset before building and warns about traversals whose
paths never reach any of their assigned target's nodes.

## Project layout

| Path                 | Purpose                                                        |
|----------------------|----------------------------------------------------------------|
| `build.py`           | Generator: JSON → self-contained HTML (source of truth).       |
| `*.json`             | Datasets.                                                      |
| `*.html`             | Generated output (rebuilt from JSON — do not edit by hand).    |
| `.vis-network.min.js`| Cached vis-network library (downloaded on first run).          |

> **Note:** the `*.html` files are build artifacts. Edit `build.py` and re-run the build;
> hand edits to the generated HTML are lost on the next build.
