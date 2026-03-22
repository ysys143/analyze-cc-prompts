"""
Reads proxy dump files and generates a self-contained message.html viewer.

Usage:
    uv run python analyze.py              # reads from ./dumps, writes ./message.html
    uv run python analyze.py path/to/dumps # custom dumps directory
"""

import json
import os
import sys


def build_dumps(dumps_dir: str) -> dict:
    """Read all *-req.json files and build the DUMPS dict."""
    dumps = {}
    for fname in sorted(os.listdir(dumps_dir)):
        if not fname.endswith("-req.json"):
            continue
        path = os.path.join(dumps_dir, fname)
        with open(path) as f:
            data = json.load(f)
        size = os.path.getsize(path)

        # Load matching response file
        res_fname = fname.replace("-req.json", "-res.json")
        res_path = os.path.join(dumps_dir, res_fname)
        res_data = None
        if os.path.exists(res_path):
            with open(res_path) as f:
                res_data = json.load(f)

        dumps[fname] = {"data": data, "size": size, "response": res_data}
    return dumps


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Code Proxy Analyzer</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #f7f5f0;
    --surface: #faf8f5;
    --surface2: #f4f1ec;
    --border: #eae6e0;
    --text: #2d2b28;
    --text-muted: #9b9590;
    --blue: #4a7fb5;
    --green: #5a9a72;
    --red: #c06058;
    --yellow: #c49a3c;
    --accent: #bf6a42;
    --accent-light: rgba(191,106,66,.06);
    --accent-mid: rgba(191,106,66,.12);
    --radius: 10px;
    --sidebar-w: 300px;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: system-ui, -apple-system, sans-serif;
    font-size: 14px;
    display: flex;
    height: 100vh;
    overflow: hidden;
  }

  /* SIDEBAR */
  #sidebar {
    width: var(--sidebar-w);
    min-width: var(--sidebar-w);
    background: var(--surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  #sidebar-header {
    padding: 16px 14px 12px;
    border-bottom: 1px solid var(--border);
  }
  #sidebar-header h1 {
    font-size: 15px;
    font-weight: 700;
    color: var(--text);
    letter-spacing: .3px;
    cursor: pointer;
    transition: color .15s;
  }
  #sidebar-header h1:hover { color: var(--text-muted); }
  #sidebar-header .sub {
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 3px;
  }
  #sidebar-list {
    overflow-y: auto;
    flex: 1;
    padding: 8px 0;
  }
  .file-item {
    padding: 10px 14px;
    cursor: pointer;
    border-left: 3px solid transparent;
    transition: background .15s, border-color .15s;
  }
  .file-item:hover { background: var(--surface2); }
  .tag-user { background: rgba(74,127,181,.12); color: var(--blue); }
  .file-item.active {
    background: var(--accent-light);
    border-left-color: var(--text);
  }
  .file-item .fname {
    font-size: 11px;
    font-family: monospace;
    color: var(--text-muted);
    word-break: break-all;
    line-height: 1.4;
  }
  .file-item .fmeta {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 5px;
    flex-wrap: wrap;
  }
  .file-item .fsize {
    font-size: 11px;
    color: var(--text-muted);
  }
  .tag {
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    text-transform: uppercase;
    letter-spacing: .5px;
  }
  .tag-normal { background: rgba(192,96,88,.08); color: #b07060; }
  .tag-clean  { background: rgba(74,127,181,.1); color: var(--blue); }
  .tag-internal { background: rgba(155,149,144,.08); color: var(--text-muted); }
  .tag-model {
    background: var(--accent-mid);
    color: var(--accent);
    font-size: 10px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 4px;
    max-width: 160px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* SESSION GROUPS */
  .date-divider {
    padding: 8px 12px 4px;
    font-size: 10px;
    font-weight: 700;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: .08em;
    border-top: 1px solid var(--border);
    margin-top: 4px;
  }
  .session-group { margin-bottom: 2px; }
  .session-header {
    padding: 8px 14px;
    cursor: pointer;
    background: var(--surface2);
    border-left: 3px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 3px;
    transition: background .15s;
    user-select: none;
  }
  .session-header:hover { background: rgba(0,0,0,.02); }
  .session-header .session-label {
    font-size: 10px;
    font-weight: 700;
    color: var(--text);
    text-transform: uppercase;
    letter-spacing: .5px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .session-header .session-label .arrow {
    font-size: 8px;
    transition: transform .15s;
  }
  .session-header .session-label .arrow.open { transform: rotate(90deg); }
  .session-header .session-prompt {
    font-size: 10px;
    color: var(--text);
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .session-header .session-meta {
    font-size: 9px;
    color: var(--text-muted);
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }
  .session-files { display: none; }
  .session-files.open { display: block; }
  .session-files .file-item {
    padding-left: 24px;
    border-left: 3px solid var(--accent-mid);
  }
  .session-files .file-item .turn-badge {
    font-size: 9px;
    font-weight: 700;
    color: var(--text-muted);
    background: rgba(0,0,0,.04);
    padding: 1px 5px;
    border-radius: 3px;
    margin-right: 4px;
  }

  /* MAIN */
  #main {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  #topbar {
    padding: 12px 20px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 10px;
    background: var(--surface);
  }
  #topbar h2 {
    flex: 1;
    font-size: 13px;
    color: var(--text-muted);
    font-weight: 400;
    font-family: monospace;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .btn {
    padding: 6px 14px;
    border-radius: 12px;
    border: 1px solid var(--border);
    background: var(--surface2);
    color: var(--text);
    font-size: 12px;
    cursor: pointer;
    transition: background .15s, border-color .15s;
    white-space: nowrap;
  }
  .btn:hover { background: var(--border); }
  .btn.active { border-color: var(--text); color: var(--text); background: rgba(0,0,0,.04); }
  #content {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
  }

  /* LANDING */
  #empty-state {
    display: flex;
    flex-direction: column;
    padding: 30px;
    max-width: 900px;
    margin: 0 auto;
    gap: 24px;
    color: var(--text);
  }
  #empty-state h2 { font-size: 22px; font-weight: 700; }
  #empty-state .landing-section {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
  }
  #empty-state .landing-section h3 {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: .5px;
    margin: 0 0 12px 0;
  }
  #empty-state .landing-section p,
  #empty-state .landing-section li {
    font-size: 13px;
    line-height: 1.6;
    color: var(--text-muted);
    margin: 0;
  }
  #empty-state .landing-section ul { margin: 8px 0 0 0; padding-left: 18px; }
  #empty-state .landing-section li { margin-bottom: 4px; }
  #empty-state .stat-row { display: flex; gap: 16px; flex-wrap: wrap; }
  #empty-state .stat-card {
    flex: 1;
    min-width: 120px;
    background: var(--surface2);
    border-radius: 8px;
    padding: 14px;
    text-align: center;
  }
  #empty-state .stat-card .val { font-size: 22px; font-weight: 700; color: var(--text); }
  #empty-state .stat-card .lbl {
    font-size: 10px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: .3px;
    margin-top: 4px;
  }
  #empty-state .finding {
    padding: 10px 14px;
    background: var(--surface);
    border-left: 3px solid var(--border);
    border-radius: 0 6px 6px 0;
    margin-bottom: 8px;
    font-size: 12px;
    color: var(--text);
    line-height: 1.5;
  }
  #empty-state .finding b { color: var(--text); }
  #empty-state code {
    background: rgba(0,0,0,.04);
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 12px;
    font-family: 'SF Mono', 'Fira Code', monospace;
  }

  /* SESSION SUMMARY */
  .sess-timeline {
    display: flex;
    flex-direction: column;
    gap: 0;
    position: relative;
    padding-left: 20px;
  }
  .sess-timeline::before {
    content: '';
    position: absolute;
    left: 7px;
    top: 8px;
    bottom: 8px;
    width: 2px;
    background: var(--border);
  }
  .sess-tl-item {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 10px 0;
    position: relative;
    cursor: pointer;
    transition: background .15s;
    padding-right: 10px;
    border-radius: 6px;
  }
  .sess-tl-item:hover { background: rgba(0,0,0,.02); }
  .sess-tl-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: var(--accent);
    border: 2px solid var(--bg);
    flex-shrink: 0;
    margin-left: -26px;
    margin-top: 2px;
    z-index: 1;
  }
  .sess-tl-dot.internal { background: var(--text-muted); }
  .sess-tl-info { flex: 1; }
  .sess-tl-info .tl-label { font-size: 11px; font-weight: 700; color: var(--text); }
  .sess-tl-info .tl-detail { font-size: 10px; color: var(--text-muted); margin-top: 2px; }
  .sess-tl-bar {
    height: 6px;
    border-radius: 3px;
    margin-top: 6px;
    background: var(--surface2);
    overflow: hidden;
  }
  .sess-tl-bar-inner { height: 100%; border-radius: 3px; transition: width .3s; }
  .sess-size-breakdown {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-top: 12px;
  }
  .sess-size-cell {
    text-align: center;
    padding: 12px;
    background: var(--surface2);
    border-radius: 8px;
  }
  .sess-size-cell .val { font-size: 18px; font-weight: 700; }
  .sess-size-cell .lbl { font-size: 10px; color: var(--text-muted); margin-top: 4px; }

  /* TABS */
  .tab-bar {
    display: flex;
    gap: 2px;
    margin-bottom: 16px;
    border-bottom: 2px solid var(--border);
  }
  .tab-btn {
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 600;
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-muted);
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    transition: color .15s;
  }
  .tab-btn.active {
    color: var(--accent);
    border-bottom-color: var(--accent);
  }
  .tab-panel { display: none; }
  .tab-panel.active { display: block; }

  /* CARDS */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px;
    margin-bottom: 16px;
  }
  .card-title {
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .8px;
    color: var(--text-muted);
    margin-bottom: 14px;
  }

  /* OVERVIEW */
  .overview-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    align-items: start;
  }
  .stat-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .stat {
    background: var(--surface2);
    border-radius: 12px;
    padding: 10px 12px;
  }
  .stat-label {
    font-size: 10px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: .6px;
    margin-bottom: 4px;
  }
  .stat-value {
    font-size: 15px;
    font-weight: 700;
    color: var(--text);
    font-family: monospace;
    word-break: break-all;
  }
  .stat-value.blue { color: var(--blue); }
  .stat-value.green { color: var(--green); }

  /* PIE */
  .pie-container { display: flex; flex-direction: column; align-items: center; gap: 12px; }
  .pie { width: 110px; height: 110px; border-radius: 50%; flex-shrink: 0; }
  .pie-legend { display: flex; flex-direction: column; gap: 6px; width: 100%; }
  .legend-item { display: flex; align-items: center; gap: 8px; font-size: 12px; }
  .legend-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
  .legend-pct { color: var(--text-muted); margin-left: auto; font-size: 11px; }

  /* COLLAPSIBLE */
  .collapse-header {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    padding: 10px 12px;
    background: var(--surface2);
    border-radius: 12px;
    margin-bottom: 4px;
    transition: background .15s;
    user-select: none;
  }
  .collapse-header:hover { background: var(--border); }
  .collapse-arrow {
    color: var(--text-muted);
    font-size: 10px;
    transition: transform .2s;
    flex-shrink: 0;
  }
  .collapse-arrow.open { transform: rotate(90deg); }
  .collapse-title { flex: 1; font-size: 13px; font-weight: 500; }
  .collapse-meta { font-size: 11px; color: var(--text-muted); }
  .collapse-body { display: none; padding: 10px 0 4px; }
  .collapse-body.open { display: block; }

  /* CODE */
  .code-block {
    background: #12131f;
    border-radius: 6px;
    padding: 12px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 11px;
    line-height: 1.6;
    color: #c9d0e8;
    white-space: pre-wrap;
    word-break: break-word;
    overflow-x: auto;
    border: 1px solid var(--border);
    margin-top: 6px;
  }
  .show-more-btn {
    font-size: 11px;
    color: var(--blue);
    cursor: pointer;
    margin-top: 6px;
    display: inline-block;
  }
  .show-more-btn:hover { text-decoration: underline; }

  /* TOOLS GRID */
  .tools-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 10px;
  }
  .tool-card {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px;
    cursor: pointer;
    transition: border-color 0.2s, transform 0.15s, box-shadow 0.2s;
  }
  .tool-card:hover {
    border-color: var(--blue);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(74,158,255,0.15);
  }
  .tool-name { font-weight: 700; font-size: 13px; color: var(--blue); margin-bottom: 4px; }
  .tool-desc {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.5;
    margin-bottom: 8px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    cursor: pointer;
  }
  .tool-desc:hover { color: var(--blue); }
  .modal-overlay {
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: transparent;
    z-index: 1000;
    justify-content: center;
    align-items: center;
  }
  .modal-overlay.active { display: flex; }
  .modal {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    width: 700px;
    max-width: 90vw;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 60px rgba(0,0,0,0.5);
  }
  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
  }
  .modal-header h3 { margin: 0; color: var(--blue); font-size: 15px; }
  .modal-close {
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: 20px;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 4px;
  }
  .modal-close:hover { background: var(--border); color: var(--text); }
  .modal-body {
    padding: 20px;
    overflow-y: auto;
    font-size: 12px;
    line-height: 1.7;
    color: var(--text);
  }
  .modal-body pre {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
    font-family: 'SF Mono', Monaco, monospace;
    font-size: 12px;
  }
  .tool-badges { display: flex; gap: 5px; flex-wrap: wrap; }
  .badge { font-size: 10px; padding: 2px 7px; border-radius: 10px; font-weight: 600; }
  .badge-schema { background: rgba(90,154,114,.08); color: var(--green); }
  .badge-size { background: rgba(74,158,255,.12); color: var(--blue); }

  /* MESSAGES */
  .msg-bubble {
    margin-bottom: 14px;
    display: flex;
    flex-direction: column;
    max-width: 80%;
  }
  .msg-bubble.user { align-self: flex-end; align-items: flex-end; margin-left: auto; }
  .msg-bubble.assistant { align-self: flex-start; align-items: flex-start; }
  .msg-bubble.tool-result { align-self: flex-start; align-items: flex-start; max-width: 85%; }
  .msg-bubble.tool-result .bubble-inner {
    background: rgba(191,106,66,.10);
    border: 1px solid rgba(191,106,66,.20);
    border-radius: 12px 12px 12px 4px;
  }
  .msg-meta {
    font-size: 10px;
    color: var(--text-muted);
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: .5px;
  }
  .msg-api-info {
    font-size: 9px;
    color: var(--text-muted);
    opacity: .8;
    margin-bottom: 6px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    letter-spacing: .3px;
  }
  .msg-api-info code {
    background: rgba(0,0,0,.04);
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 9px;
  }
  .msg-explain {
    font-size: 9px;
    color: var(--text-muted);
    opacity: .7;
    margin-top: 4px;
    font-style: italic;
    line-height: 1.4;
  }
  .msg-bubble.user .bubble-inner {
    background: rgba(74,127,181,.12);
    border: 1px solid rgba(74,127,181,.22);
    border-radius: 12px 12px 4px 12px;
  }
  .msg-bubble.assistant .bubble-inner {
    background: rgba(90,154,114,.10);
    border: 1px solid rgba(90,154,114,.18);
    border-radius: 12px 12px 12px 4px;
  }
  .bubble-inner { padding: 12px 14px; }
  .block-item { margin-bottom: 8px; }
  .block-type-badge {
    font-size: 9px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .6px;
    padding: 2px 6px;
    border-radius: 4px;
    display: inline-block;
    margin-bottom: 4px;
  }
  .block-type-text { background: rgba(74,127,181,.1); color: var(--blue); }
  .block-type-thinking { background: rgba(196,154,60,.1); color: var(--yellow); }
  .block-type-tool_use { background: rgba(90,154,114,.1); color: var(--green); }
  .block-type-tool_result { background: rgba(191,106,66,.1); color: var(--accent); }
  .block-type-other { background: rgba(155,149,144,.08); color: var(--text-muted); }
  .block-content {
    font-size: 12px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .msg-list { display: flex; flex-direction: column; }

  /* COMPARE */
  #compare-panel {
    display: none;
    flex: 1;
    overflow-y: auto;
    padding: 20px;
  }
  #compare-panel.visible { display: block; }
  .compare-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .compare-col { }
  .diff-row {
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
    font-size: 12px;
  }
  .diff-label { font-weight: 600; color: var(--text-muted); }
  .diff-val { text-align: right; }
  .diff-added { color: var(--green); font-weight: 600; }
  .diff-removed { color: var(--red); font-weight: 600; }
  .diff-same { color: var(--text-muted); }
  .diff-section { margin-top: 12px; }
  .diff-section-title {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 6px;
  }
  .diff-list { list-style: none; padding: 0; }
  .diff-list li {
    padding: 4px 8px;
    font-size: 12px;
    font-family: monospace;
    border-radius: 4px;
    margin-bottom: 2px;
  }
  .diff-list li.added { background: rgba(90,154,114,.08); color: var(--green); }
  .diff-list li.removed { background: rgba(192,96,88,.08); color: var(--red); }
  .diff-list li.same { color: var(--text-muted); }
  .cmp-selectors {
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
    align-items: center;
  }
  .cmp-selectors select {
    flex: 1;
    padding: 6px 10px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
    font-size: 12px;
    font-family: monospace;
  }
</style>
</head>
<body>

<div id="sidebar">
  <div id="sidebar-header">
    <h1 id="home-btn" title="Home">Claude Code Proxy Analyzer</h1>
    <div class="sub" id="sidebar-count">Loading...</div>
  </div>
  <div id="sidebar-list"></div>
</div>

<div id="main">
  <div id="topbar">
    <h2 id="topbar-filename">Select a dump file to inspect</h2>
    <div style="display:flex;align-items:center;gap:8px;margin-left:auto;">
      <button class="btn" id="btn-compare">Compare</button>
    </div>
  </div>

  <div id="content">
    <div id="empty-state">
      <h2>Claude Code API Request Analyzer</h2>
      <p style="font-size:13px;color:var(--text-muted);margin:-16px 0 0 0;">Captured via transparent reverse proxy (ANTHROPIC_BASE_URL redirect)</p>

      <div class="landing-section">
        <h3>How It Works</h3>
        <p>This dashboard visualizes raw API request bodies captured from <b>Claude Code</b> sessions routed through a local reverse proxy. The proxy intercepts all <code>POST /v1/messages</code> calls, dumps request payloads to disk, and forwards them transparently to the real Anthropic API.</p>
      </div>

      <div id="landing-stats" class="stat-row"></div>

      <div class="landing-section">
        <h3>What To Look For</h3>
        <ul>
          <li><b>System prompts:</b> Full system instructions sent to the model each turn</li>
          <li><b>Tools:</b> All tool definitions (schemas) included in every request</li>
          <li><b>Messages:</b> Complete conversation history, growing each turn</li>
          <li><b>Multi-turn overhead:</b> System + tools are re-sent every turn</li>
          <li><b>Internal calls:</b> Lightweight haiku sub-calls for summarization/titles</li>
        </ul>
      </div>

      <p style="font-size:12px;color:var(--text-muted);">Select a session from the sidebar to inspect individual API requests.</p>
    </div>

    <div id="dump-view" style="display:none;"></div>
  </div>

  <div id="compare-panel">
    <div class="cmp-selectors">
      <select id="cmp-a"><option value="">-- Select file A --</option></select>
      <span style="color:var(--text-muted);">vs</span>
      <select id="cmp-b"><option value="">-- Select file B --</option></select>
    </div>
    <div id="cmp-result"></div>
  </div>
</div>

<script>
const DUMPS = %%DUMPS_JSON%%;

// HELPERS
function fmtBytes(b) {
  if (b < 1024) return b + ' B';
  if (b < 1024*1024) return (b/1024).toFixed(1) + ' KB';
  return (b/(1024*1024)).toFixed(2) + ' MB';
}

function fmtTimestamp(fname) {
  const m = fname.match(/(\d{4}-\d{2}-\d{2})T(\d{2})(\d{2})(\d{2})/);
  if (!m) return fname;
  return m[1] + ' ' + m[2]+':'+m[3]+':'+m[4];
}

function isRealUserText(text) {
  var t = (text || '').trim();
  return t.length > 0 && !t.startsWith('<system-reminder>') && !t.startsWith('<system-reminder');
}

function isSubagentMessage(content) {
  // If any block contains SubagentStart, this is an orchestrator→subagent delegation, not human input
  if (!Array.isArray(content)) return false;
  return content.some(function(b) {
    return b.type === 'text' && (b.text || '').indexOf('SubagentStart') !== -1;
  });
}

function hasNewUserMessage(entry, prevMsgCount) {
  var msgs = entry.data.messages || [];
  if (msgs.length === 0) return false;
  // Check all new messages for a real user text (not tool_result, not system-reminder, not subagent)
  for (var i = prevMsgCount; i < msgs.length; i++) {
    var msg = msgs[i];
    if (msg.role !== 'user') continue;
    var content = msg.content;
    if (isSubagentMessage(content)) continue;
    if (typeof content === 'string' && isRealUserText(content)) return true;
    if (Array.isArray(content)) {
      var hasReal = content.some(function(b) {
        return b.type === 'text' && isRealUserText(b.text);
      });
      if (hasReal) return true;
    }
  }
  return false;
}

function isInternalEntry(entry) {
  var d = entry.data;
  var model = d.model || '';
  var toolCount = (d.tools || []).length;
  // Truly internal: haiku with 0-1 tools (quota check, WebFetch) or sole web_search tool
  if (model.includes('haiku') && toolCount <= 1) return true;
  if (toolCount === 1 && d.tools[0].name === 'web_search') return true;
  return false;
}

function sizeTag(bytes, model, entry) {
  if (entry && isInternalEntry(entry)) return '<span class="tag tag-internal">internal</span>';
  return '<span class="tag tag-model">' + escHtml(model || '?') + '</span>';
}

function truncate(str, n) {
  if (str.length <= n) return [str, false];
  return [str.slice(0, n) + '...', true];
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function getContentStr(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content.map(function(b) {
      if (b.type === 'text') return b.text || '';
      if (b.type === 'thinking') return b.thinking || '';
      if (b.type === 'tool_use') return b.name + '(' + JSON.stringify(b.input||{}).slice(0,100) + ')';
      if (b.type === 'tool_result') {
        var c = b.content;
        if (typeof c === 'string') return c;
        if (Array.isArray(c)) return c.map(function(x){return x.text||''}).join('\n');
        return JSON.stringify(c);
      }
      return JSON.stringify(b);
    }).join('\n');
  }
  return JSON.stringify(content);
}

function calcSizes(d) {
  var sysStr = JSON.stringify(d.system || []);
  var toolStr = JSON.stringify(d.tools || []);
  var msgStr = JSON.stringify(d.messages || []);
  var sysSize = new Blob([sysStr]).size;
  var toolSize = new Blob([toolStr]).size;
  var msgSize = new Blob([msgStr]).size;
  var total = sysSize + toolSize + msgSize;
  return { sysSize: sysSize, toolSize: toolSize, msgSize: msgSize, total: total };
}

// SIDEBAR
var sidebarList = document.getElementById('sidebar-list');
var topbarFilename = document.getElementById('topbar-filename');
var sidebarCount = document.getElementById('sidebar-count');

var sortedFiles = Object.keys(DUMPS).sort();

// Session Grouping
function getUserPrompt(data) {
  var msgs = data.messages || [];
  // Find the last actual user text input (not tool_result)
  for (var i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role !== 'user') continue;
    var content = msgs[i].content;
    if (typeof content === 'string') return content;
    if (Array.isArray(content)) {
      // Skip tool_result blocks
      var hasToolResult = content.some(function(b) { return b.type === 'tool_result'; });
      if (hasToolResult) continue;
      for (var j = 0; j < content.length; j++) {
        if (content[j].type === 'text' && content[j].text) return content[j].text;
      }
    }
  }
  return '(no prompt)';
}

function getSessionPrompt(files) {
  // Find first non-internal file and get its last user prompt
  for (var i = 0; i < files.length; i++) {
    var entry = DUMPS[files[i]];
    if (isInternalEntry(entry)) continue;
    return getUserPrompt(entry.data);
  }
  return getUserPrompt(DUMPS[files[0]].data);
}

var sessions = [];
var curSession = null;

function getFileDate(fname) {
  var m = fname.match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : null;
}

sortedFiles.forEach(function(fname) {
  var entry = DUMPS[fname];
  var d = entry.data;
  var model = d.model || '?';
  var isInternal = isInternalEntry(entry);
  var msgCount = (d.messages || []).length;

  var fileDate = getFileDate(fname);
  var sessionDate = curSession ? getFileDate(curSession.startTime) : null;
  var dateChanged = fileDate && sessionDate && fileDate !== sessionDate;

  if ((msgCount === 1 && !isInternal) || dateChanged) {
    curSession = { prompt: '', files: [fname], startTime: fname };
    sessions.push(curSession);
  } else if (curSession) {
    curSession.files.push(fname);
  } else {
    curSession = { prompt: '', files: [fname], startTime: fname };
    sessions.push(curSession);
  }
});

// Resolve session prompts after all files are grouped
sessions.forEach(function(sess) {
  sess.prompt = getSessionPrompt(sess.files);
});

sidebarCount.textContent = sortedFiles.length + ' requests in ' + sessions.length + ' sessions';

// Landing stats
(function() {
  var totalSize = sortedFiles.reduce(function(s,f){ return s + DUMPS[f].size; }, 0);
  var internalCount = sortedFiles.filter(function(f){ return isInternalEntry(DUMPS[f]); }).length;
  var el = document.getElementById('landing-stats');
  el.innerHTML = [
    { val: sortedFiles.length, lbl: 'Total Requests' },
    { val: sessions.length, lbl: 'Sessions' },
    { val: fmtBytes(totalSize), lbl: 'Total Data' },
    { val: internalCount, lbl: 'Internal (Haiku/WebSearch)' },
  ].map(function(s) {
    return '<div class="stat-card"><div class="val">'+s.val+'</div><div class="lbl">'+s.lbl+'</div></div>';
  }).join('');
})();

// Compare selects
['cmp-a','cmp-b'].forEach(function(id) {
  var sel = document.getElementById(id);
  sortedFiles.forEach(function(f) {
    var opt = document.createElement('option');
    opt.value = f;
    opt.textContent = f.replace('-req.json','');
    sel.appendChild(opt);
  });
});

var currentFile = null;
var currentDateLabel = null;

sessions.forEach(function(sess, si) {
  // Extract date from session start time (fname like "2026-03-12T045626.434-req.json")
  var dateMatch = sess.startTime.match(/^(\d{4}-\d{2}-\d{2})/);
  var dateLabel = dateMatch ? dateMatch[1] : null;
  if (dateLabel && dateLabel !== currentDateLabel) {
    currentDateLabel = dateLabel;
    var dateDivider = document.createElement('div');
    dateDivider.style.cssText = 'padding:8px 12px 4px;font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;border-top:1px solid var(--border);margin-top:4px;';
    dateDivider.textContent = dateLabel;
    sidebarList.appendChild(dateDivider);
  }

  var group = document.createElement('div');
  group.className = 'session-group';

  var header = document.createElement('div');
  header.className = 'session-header';

  var mainFiles = sess.files.filter(function(f){ return !isInternalEntry(DUMPS[f]); });
  var intFiles = sess.files.filter(function(f){ return isInternalEntry(DUMPS[f]); });
  var maxMsgs = Math.max.apply(null, sess.files.map(function(f){ return (DUMPS[f].data.messages||[]).length; }));
  var turns = Math.ceil(maxMsgs / 2);
  var totalSize = sess.files.reduce(function(s,f){ return s + DUMPS[f].size; }, 0);

  var repFile = mainFiles.length > 0 ? mainFiles[0] : sess.files[0];
  var firstModel = DUMPS[repFile].data.model || '';
  var firstSize = DUMPS[repFile].size;
  var sessTag = sizeTag(firstSize, firstModel, DUMPS[repFile]);

  var promptShort = sess.prompt.length > 60 ? sess.prompt.slice(0,60) + '...' : sess.prompt;

  header.innerHTML = ''
    + '<div class="session-label">'
    + '<span class="arrow">&#9654;</span>'
    + 'Session ' + (si+1)
    + ' ' + sessTag
    + '<span style="font-weight:400;color:var(--text-muted);">' + sess.files.length + ' reqs</span>'
    + '</div>'
    + '<div class="session-prompt" title="' + escHtml(sess.prompt) + '">' + escHtml(promptShort) + '</div>'
    + '<div class="session-meta">'
    + '<span>' + mainFiles.length + ' main' + (intFiles.length ? ' + ' + intFiles.length + ' internal' : '') + '</span>'
    + '<span>&bull; ' + turns + ' turns</span>'
    + '<span>&bull; ' + fmtBytes(totalSize) + ' total</span>'
    + '</div>';

  var fileList = document.createElement('div');
  fileList.className = 'session-files';

  var prevMsgCount = 0;
  sess.files.forEach(function(fname, fi) {
    var entry = DUMPS[fname];
    var size = entry.size;
    var model = entry.data.model || '?';
    var isInternal = isInternalEntry(entry);
    var isWebSearch = entry.data.tools && entry.data.tools.length === 1 && entry.data.tools[0].name === 'web_search';
    var msgCount = (entry.data.messages||[]).length;
    var isUserTurn = !isInternal && hasNewUserMessage(entry, prevMsgCount);

    var el = document.createElement('div');
    el.className = 'file-item';
    el.dataset.file = fname;

    var shortName = fname.replace('-req.json','');
    var turnLabel = 'T' + (fi + 1);

    el.innerHTML = ''
      + '<div class="fname"><span class="turn-badge">' + turnLabel + '</span>' + escHtml(shortName) + '</div>'
      + '<div class="fmeta">'
      + '<span class="fsize">' + fmtBytes(size) + '</span>'
      + '<span style="font-size:9px;color:var(--text-muted);">msgs=' + msgCount + '</span>'
      + (isInternal ? '<span class="tag tag-internal">' + (isWebSearch ? 'web_search' : 'internal') + '</span>' : '')
      + (isUserTurn ? '<span class="tag tag-user">user</span>' : '')
      + '</div>';

    el.addEventListener('click', function(e) {
      e.stopPropagation();
      document.querySelectorAll('.file-item').forEach(function(x){ x.classList.remove('active'); });
      el.classList.add('active');
      loadFile(fname);
      if (compareMode) toggleCompare();
    });

    if (!isInternal) prevMsgCount = msgCount;
    fileList.appendChild(el);
  });

  var sessIdx = si;
  header.addEventListener('click', function() {
    var arrow = header.querySelector('.arrow');
    var isOpen = fileList.classList.toggle('open');
    arrow.classList.toggle('open', isOpen);
    document.querySelectorAll('.file-item').forEach(function(x){ x.classList.remove('active'); });
    currentFile = null;
    topbarFilename.textContent = 'Session ' + (sessIdx + 1);
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('dump-view').style.display = 'block';
    renderSessionSummary(sess, sessIdx);
    if (compareMode) toggleCompare();
  });

  group.appendChild(header);
  group.appendChild(fileList);
  sidebarList.appendChild(group);
});

// Restore persisted state
try {
  var saved = localStorage.getItem('proxy_viewer_selected_file');
  if (saved && DUMPS[saved]) {
    var targetEl = sidebarList.querySelector('.file-item[data-file="' + saved + '"]');
    if (targetEl) {
      var sessionFiles = targetEl.closest('.session-files');
      if (sessionFiles) {
        sessionFiles.classList.add('open');
        var arrow = sessionFiles.previousElementSibling && sessionFiles.previousElementSibling.querySelector('.arrow');
        if (arrow) arrow.classList.add('open');
      }
      targetEl.classList.add('active');
      loadFile(saved);
    }
  }
} catch(e) {}

// SESSION SUMMARY
function renderSessionSummary(sess, sessionIndex) {
  var view = document.getElementById('dump-view');
  var mainFiles = sess.files.filter(function(f){ return !isInternalEntry(DUMPS[f]); });
  var intFiles = sess.files.filter(function(f){ return isInternalEntry(DUMPS[f]); });
  var maxMsgs = Math.max.apply(null, sess.files.map(function(f){ return (DUMPS[f].data.messages||[]).length; }));
  var turns = Math.ceil(maxMsgs / 2);
  var totalSize = sess.files.reduce(function(s,f){ return s + DUMPS[f].size; }, 0);
  var maxFileSize = Math.max.apply(null, sess.files.map(function(f){ return DUMPS[f].size; }));

  var firstEntry = DUMPS[sess.files[0]];
  var firstSz = calcSizes(firstEntry.data);
  var lastMainFile = mainFiles[mainFiles.length - 1];
  var lastEntry = DUMPS[lastMainFile];
  var lastSz = calcSizes(lastEntry.data);

  var sysToolsSize = firstSz.sysSize + firstSz.toolSize;
  var firstMsgSize = firstSz.msgSize;
  var lastMsgSize = lastSz.msgSize;
  var firstSize = firstEntry.size;
  var sessTag = sizeTag(firstSize, firstEntry.data.model);
  var promptShort = sess.prompt.length > 120 ? sess.prompt.slice(0,120) + '...' : sess.prompt;

  var timelineItems = sess.files.map(function(fname) {
    var entry = DUMPS[fname];
    var d = entry.data;
    var model = d.model || '?';
    var isInt = isInternalEntry(entry);
    var msgCount = (d.messages||[]).length;
    var sz = calcSizes(d);
    var turnLabel = isInt ? 'INTERNAL' : 'Turn ' + Math.ceil(msgCount/2);
    var pct = Math.round(entry.size / maxFileSize * 100);
    var sysPct = Math.round(sz.sysSize / (sz.total||1) * 100);
    var toolPct = Math.round(sz.toolSize / (sz.total||1) * 100);
    var ts = fname.match(/T(\d{2})(\d{2})(\d{2})/);
    var timeStr = ts ? ts[1]+':'+ts[2]+':'+ts[3] : '';
    var intTag = isInt ? '<span class="tag tag-internal" style="margin-left:4px;">internal</span>' : '';
    var detailStr = !isInt
      ? fmtBytes(entry.size)+' \u2022 '+msgCount+' msgs \u2022 sys:'+fmtBytes(sz.sysSize)+' tools:'+fmtBytes(sz.toolSize)+' msgs:'+fmtBytes(sz.msgSize)
      : fmtBytes(entry.size)+' \u2022 '+msgCount+' msgs \u2022 no tools';
    var barBg = 'linear-gradient(90deg, #4a7fb5 0%, #2b6cb0 '+sysPct+'%, #d97706 '+sysPct+'%, #d97706 '+(sysPct+toolPct)+'%, #2f855a '+(sysPct+toolPct)+'%, #5a9a72 100%)';
    return '<div class="sess-tl-item" data-file="'+fname+'" title="Click to view details">'
      + '<div class="sess-tl-dot '+(isInt?'internal':'')+'"></div>'
      + '<div class="sess-tl-info">'
      + '<div class="tl-label">'+turnLabel+'<span style="font-weight:400;color:var(--text-muted);margin-left:6px;">'+timeStr+'</span>'+intTag+'</div>'
      + '<div class="tl-detail">'+detailStr+'</div>'
      + '<div class="sess-tl-bar"><div class="sess-tl-bar-inner" style="width:'+pct+'%;background:'+barBg+';"></div></div>'
      + '</div></div>';
  }).join('');

  var repeatedHtml = mainFiles.length > 1
    ? '<div class="finding" style="margin-top:12px;"><b>Repeated overhead:</b> System + Tools ('+fmtBytes(sysToolsSize)+') sent '+mainFiles.length+' times = <b>'+fmtBytes(sysToolsSize*mainFiles.length)+'</b> total. Only messages grow between turns.</div>'
    : '';

  view.innerHTML = ''
    + '<div class="card">'
    + '<div class="card-title">Session '+(sessionIndex+1)+' '+sessTag+'</div>'
    + '<div style="margin-top:8px;font-size:13px;color:var(--text);line-height:1.5;">'+escHtml(promptShort)+'</div>'
    + '<div class="sess-size-breakdown" style="margin-top:16px;">'
    + '<div class="sess-size-cell"><div class="val blue">'+sess.files.length+'</div><div class="lbl">Requests ('+mainFiles.length+' main + '+intFiles.length+' internal)</div></div>'
    + '<div class="sess-size-cell"><div class="val green">'+turns+'</div><div class="lbl">Turns</div></div>'
    + '<div class="sess-size-cell"><div class="val" style="color:var(--accent);">'+fmtBytes(totalSize)+'</div><div class="lbl">Total Data Sent</div></div>'
    + '</div></div>'
    + '<div class="card">'
    + '<div class="card-title">Size Breakdown</div>'
    + '<div class="sess-size-breakdown">'
    + '<div class="sess-size-cell"><div class="val" style="color:var(--blue);">'+fmtBytes(firstSz.sysSize)+'</div><div class="lbl">System (per request)</div></div>'
    + '<div class="sess-size-cell"><div class="val" style="color:var(--accent);">'+fmtBytes(firstSz.toolSize)+'</div><div class="lbl">Tools (per request)</div></div>'
    + '<div class="sess-size-cell"><div class="val" style="color:var(--green);">'+fmtBytes(firstMsgSize)+' &rarr; '+fmtBytes(lastMsgSize)+'</div><div class="lbl">Messages (first &rarr; last)</div></div>'
    + '</div>'
    + repeatedHtml
    + '</div>'
    + '<div class="card">'
    + '<div class="card-title">Request Timeline</div>'
    + '<div class="sess-timeline">'+timelineItems+'</div>'
    + '</div>';

  view.querySelectorAll('.sess-tl-item[data-file]').forEach(function(item) {
    item.addEventListener('click', function() {
      var fname = item.dataset.file;
      document.querySelectorAll('.file-item').forEach(function(x){ x.classList.remove('active'); });
      var fileEl = sidebarList.querySelector('.file-item[data-file="'+fname+'"]');
      if (fileEl) fileEl.classList.add('active');
      loadFile(fname);
    });
  });
}

// LOAD FILE
function loadFile(fname) {
  currentFile = fname;
  rawJsonVisible = false;
  var rawEl = document.getElementById('raw-json-view');
  if (rawEl) rawEl.style.display = 'none';
  topbarFilename.textContent = fname;
  document.getElementById('empty-state').style.display = 'none';
  document.getElementById('dump-view').style.display = 'block';
  renderDump(fname, DUMPS[fname]);
  try { localStorage.setItem('proxy_viewer_selected_file', fname); } catch(e) {}
}

function renderDump(fname, entry) {
  var d = entry.data;
  var sz = calcSizes(d);
  var view = document.getElementById('dump-view');

  var total = sz.total || 1;
  var sysPct = Math.round(sz.sysSize / total * 100);
  var toolPct = Math.round(sz.toolSize / total * 100);
  var msgPct = Math.round(sz.msgSize / total * 100);

  var pie = 'conic-gradient(#4a7fb5 0% '+sysPct+'%, #c49a3c '+sysPct+'% '+(sysPct+toolPct)+'%, #5a9a72 '+(sysPct+toolPct)+'% 100%)';

  view.innerHTML = ''
    + '<div class="card"><div class="card-title">Overview</div>'
    + '<div class="overview-grid">'
    + '<div class="stat-grid">'
    + '<div class="stat"><div class="stat-label">Model</div><div class="stat-value" style="font-size:12px;">'+escHtml(d.model||'?')+'</div></div>'
    + '<div class="stat"><div class="stat-label">Max Tokens</div><div class="stat-value blue">'+(d.max_tokens||0).toLocaleString()+'</div></div>'
    + '<div class="stat"><div class="stat-label">Total Size</div><div class="stat-value green">'+fmtBytes(entry.size)+'</div></div>'
    + '<div class="stat"><div class="stat-label">Stream</div><div class="stat-value">'+(d.stream?'Yes':'No')+'</div></div>'
    + '<div class="stat"><div class="stat-label">Timestamp</div><div class="stat-value" style="font-size:11px;">'+fmtTimestamp(fname)+'</div></div>'
    + '<div class="stat"><div class="stat-label">Messages</div><div class="stat-value">'+(d.messages||[]).length+'</div></div>'
    + '</div>'
    + '<div class="pie-container">'
    + '<div class="pie" style="background:'+pie+';"></div>'
    + '<div class="pie-legend">'
    + '<div class="legend-item"><div class="legend-dot" style="background:#4a7fb5;"></div><span>System</span><span class="legend-pct">'+sysPct+'% &bull; '+fmtBytes(sz.sysSize)+'</span></div>'
    + '<div class="legend-item"><div class="legend-dot" style="background:#c49a3c;"></div><span>Tools</span><span class="legend-pct">'+toolPct+'% &bull; '+fmtBytes(sz.toolSize)+'</span></div>'
    + '<div class="legend-item"><div class="legend-dot" style="background:#5a9a72;"></div><span>Messages</span><span class="legend-pct">'+msgPct+'% &bull; '+fmtBytes(sz.msgSize)+'</span></div>'
    + '</div></div></div></div>'
    + '<div class="tab-bar">'
    + '<button class="tab-btn active" data-tab="request">Request</button>'
    + '<button class="tab-btn" data-tab="response">Response</button>'
    + '</div>'
    + '<div class="tab-panel active" id="tab-request">'
    + renderSystem(d.system || [])
    + renderTools(d.tools || [])
    + renderMessages(d.messages || [], d.model, entry)
    + '</div>'
    + '<div class="tab-panel" id="tab-response">'
    + renderRateLimits(entry.response)
    + renderResponse(entry.response)
    + '</div>';

  // Wire collapsibles
  view.querySelectorAll('.collapse-header').forEach(function(hdr) {
    hdr.addEventListener('click', function() {
      var body = hdr.nextElementSibling;
      var arrow = hdr.querySelector('.collapse-arrow');
      var isOpen = body.classList.toggle('open');
      arrow.classList.toggle('open', isOpen);
    });
  });

  // Wire tabs
  view.querySelectorAll('.tab-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      view.querySelectorAll('.tab-btn').forEach(function(b){ b.classList.remove('active'); });
      view.querySelectorAll('.tab-panel').forEach(function(p){ p.classList.remove('active'); });
      btn.classList.add('active');
      var panel = view.querySelector('#tab-' + btn.dataset.tab);
      if (panel) panel.classList.add('active');
    });
  });

  // Wire show-more
  view.querySelectorAll('.show-more-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var target = document.getElementById(btn.dataset.target);
      if (btn.dataset.expanded === 'true') {
        target.textContent = btn.dataset.preview;
        btn.textContent = 'Show more';
        btn.dataset.expanded = 'false';
      } else {
        target.textContent = btn.dataset.full;
        btn.textContent = 'Show less';
        btn.dataset.expanded = 'true';
      }
    });
  });
}

// RESPONSE
function renderResponse(response) {
  if (!response) return '';
  var events = response.events || [];
  if (!events.length) return '';

  // Extract data from events
  var usage = null;
  var stopReason = null;
  var contextMgmt = null;
  var textParts = [];
  var toolCalls = [];
  var currentToolName = null;
  var currentToolInput = [];

  events.forEach(function(ev) {
    if (!ev || typeof ev !== 'object') return;
    if (ev.type === 'message_start' && ev.message && ev.message.usage) {
      usage = ev.message.usage;
    }
    if (ev.type === 'message_delta') {
      if (ev.delta && ev.delta.stop_reason) stopReason = ev.delta.stop_reason;
      if (ev.context_management) contextMgmt = ev.context_management;
      if (ev.usage) usage = Object.assign({}, usage, ev.usage);
    }
    if (ev.type === 'content_block_start' && ev.content_block) {
      if (ev.content_block.type === 'tool_use') {
        currentToolName = ev.content_block.name;
        currentToolInput = [];
      }
    }
    if (ev.type === 'content_block_delta' && ev.delta) {
      if (ev.delta.type === 'text_delta') textParts.push(ev.delta.text || '');
      if (ev.delta.type === 'input_json_delta') currentToolInput.push(ev.delta.partial_json || '');
    }
    if (ev.type === 'content_block_stop') {
      if (currentToolName !== null) {
        var inputStr = currentToolInput.join('');
        toolCalls.push({ name: currentToolName, input: inputStr });
        currentToolName = null;
        currentToolInput = [];
      }
    }
  });

  var html = '<div class="card"><div class="card-title">Response</div>';

  // Token usage row
  if (usage) {
    var inp = (usage.input_tokens || 0);
    var cacheRead = (usage.cache_read_input_tokens || 0);
    var cacheCreate = (usage.cache_creation_input_tokens || 0);
    var out = (usage.output_tokens || 0);
    var totalIn = inp + cacheRead + cacheCreate;
    html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin-bottom:12px;">'
      + '<div class="stat"><div class="stat-label">Input</div><div class="stat-value blue">' + totalIn.toLocaleString() + '</div></div>'
      + '<div class="stat"><div class="stat-label">Cache Read</div><div class="stat-value green">' + cacheRead.toLocaleString() + '</div></div>'
      + '<div class="stat"><div class="stat-label">Cache Write</div><div class="stat-value yellow">' + cacheCreate.toLocaleString() + '</div></div>'
      + '<div class="stat"><div class="stat-label">Output</div><div class="stat-value">' + out.toLocaleString() + '</div></div>'
      + (stopReason ? '<div class="stat"><div class="stat-label">Stop</div><div class="stat-value" style="font-size:11px;">' + escHtml(stopReason) + '</div></div>' : '')
      + (usage.service_tier ? '<div class="stat"><div class="stat-label">Tier</div><div class="stat-value" style="font-size:11px;">' + escHtml(usage.service_tier) + '</div></div>' : '')
      + '</div>';
  }

  // Tool calls
  if (toolCalls.length > 0) {
    html += '<div style="margin-bottom:12px;">';
    html += '<div style="font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:6px;">TOOL CALLS (' + toolCalls.length + ')</div>';
    toolCalls.forEach(function(tc) {
      var tcId = 'tc-' + Math.random().toString(36).slice(2);
      var parsed = null;
      try { parsed = JSON.parse(tc.input); } catch(e) {}
      var rawDisplay = parsed ? JSON.stringify(parsed, null, 2) : tc.input;
      var displayText = rawDisplay.replace(/\\n/g, '\n').replace(/\\t/g, '\t').replace(/\\r/g, '');
      if (!window._tcTexts) window._tcTexts = {};
      window._tcTexts[tcId] = displayText;
      var tcArrowId = tcId + '-arrow';
      html += '<div style="background:var(--surface2);border-radius:6px;padding:8px;margin-bottom:4px;">'
        + '<div onclick="event.stopPropagation();(function(){ var p=document.getElementById(\'' + tcId + '\'); var a=document.getElementById(\'' + tcArrowId + '\'); if(p.style.display===\'none\'){ p.style.display=\'block\'; a.textContent=\'▼\'; } else { p.style.display=\'none\'; a.textContent=\'►\'; } })()" style="font-weight:600;font-size:12px;color:var(--accent);margin-bottom:4px;cursor:pointer;user-select:none;">'
        + escHtml(tc.name) + ' <span id="' + tcArrowId + '" style="font-size:10px;color:var(--text-muted);">►</span></div>'
        + '<pre id="' + tcId + '" style="font-size:11px;white-space:pre-wrap;word-break:break-all;color:var(--text-muted);margin:0;display:none;">'
        + escHtml(displayText) + '</pre>'
        + '</div>';
    });
    html += '</div>';
  }

  // Response text
  var fullText = textParts.join('');
  if (fullText) {
    var preview = fullText.slice(0, 300);
    var hasMore = fullText.length > 300;
    var tid = 'rt-' + Math.random().toString(36).slice(2);
    if (!window._rtTexts) window._rtTexts = {};
    window._rtTexts[tid] = { preview: preview, full: fullText };
    html += '<div>'
      + '<div style="font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:6px;">TEXT (' + fullText.length.toLocaleString() + ' chars)</div>'
      + '<div style="background:var(--surface2);border-radius:6px;padding:10px;">'
      + '<pre id="' + tid + '" style="font-size:12px;white-space:pre-wrap;word-break:break-word;line-height:1.5;">'
      + escHtml(preview) + '</pre>'
      + (hasMore ? '<button onclick="(function(){ var d=window._rtTexts[\'' + tid + '\']; var el=document.getElementById(\'' + tid + '\'); var btn=el.nextElementSibling; if(btn.dataset.exp===\'1\'){ el.textContent=d.preview; btn.textContent=\'Show more\'; btn.dataset.exp=\'0\'; } else { el.textContent=d.full; btn.textContent=\'Show less\'; btn.dataset.exp=\'1\'; } })()" data-exp="0" style="margin-top:6px;font-size:11px;color:var(--accent);background:none;border:none;cursor:pointer;padding:0;">Show more</button>' : '')
      + '</div></div>';
  }

  // context_management
  if (contextMgmt) {
    var edits = contextMgmt.applied_edits || [];
    if (edits.length > 0) {
      html += '<div style="margin-top:10px;font-size:11px;color:var(--text-muted);">'
        + '<b>context_management.applied_edits:</b> ' + escHtml(JSON.stringify(edits)) + '</div>';
    }
  }

  html += '</div>';
  return html;
}

// RAW RESPONSE
function renderRawResponse(response) {
  if (!response) return '';
  var rawId = 'raw-res-' + Math.random().toString(36).slice(2);
  var arrowId = rawId + '-arrow';
  var rawJson = JSON.stringify(response, null, 2);
  return '<div class="card">'
    + '<div onclick="event.stopPropagation();(function(){ var p=document.getElementById(\'' + rawId + '\'); var a=document.getElementById(\'' + arrowId + '\'); if(p.style.display===\'none\'){ p.style.display=\'block\'; a.textContent=\'▼\'; } else { p.style.display=\'none\'; a.textContent=\'►\'; } })()" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center;margin-bottom:0;">'
    + '<span class="card-title" style="margin:0;">Raw res.json</span>'
    + '<span id="' + arrowId + '" style="font-size:10px;color:var(--text-muted);">►</span>'
    + '</div>'
    + '<pre id="' + rawId + '" style="display:none;font-size:11px;white-space:pre-wrap;word-break:break-all;max-height:400px;overflow:auto;margin:0;padding-top:12px;">'
    + escHtml(rawJson) + '</pre>'
    + '</div>';
}

// RATE LIMITS
function renderRateLimits(response) {
  if (!response || !response.headers) return '';
  var headers = response.headers;
  var rlHeaders = {};
  Object.keys(headers).forEach(function(k) {
    if (k.toLowerCase().indexOf('ratelimit') !== -1) {
      rlHeaders[k] = headers[k];
    }
  });
  if (Object.keys(rlHeaders).length === 0) return '';

  // Extract utilization values for visual bars
  var buckets = [];
  var bucketMap = {};
  Object.keys(rlHeaders).forEach(function(k) {
    var m = k.match(/anthropic-ratelimit-unified-(.+?)-(utilization|status|reset)$/);
    if (m) {
      var name = m[1];
      var field = m[2];
      if (!bucketMap[name]) { bucketMap[name] = {}; buckets.push(name); }
      bucketMap[name][field] = rlHeaders[k];
    }
  });

  var barsHtml = '';
  if (buckets.length > 0) {
    barsHtml = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:16px;">';
    buckets.forEach(function(name) {
      var b = bucketMap[name];
      var util = parseFloat(b.utilization || 0);
      var pct = Math.round(util * 100);
      var status = b.status || 'unknown';
      var resetTs = b.reset ? new Date(parseInt(b.reset) * 1000).toLocaleString() : '';
      var barColor = pct >= 90 ? 'var(--red)' : pct >= 70 ? 'var(--yellow)' : 'var(--green)';
      var statusColor = status === 'allowed' ? 'var(--green)' : 'var(--red)';
      barsHtml += '<div style="background:var(--surface2);border-radius:8px;padding:12px;">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
        + '<span style="font-weight:600;font-size:12px;">' + escHtml(name) + '</span>'
        + '<span style="font-size:11px;color:' + statusColor + ';">' + escHtml(status) + '</span>'
        + '</div>'
        + '<div style="background:var(--border);border-radius:4px;height:8px;overflow:hidden;">'
        + '<div style="background:' + barColor + ';height:100%;width:' + pct + '%;border-radius:4px;transition:width .3s;"></div>'
        + '</div>'
        + '<div style="display:flex;justify-content:space-between;margin-top:4px;">'
        + '<span style="font-size:11px;font-weight:600;color:' + barColor + ';">' + pct + '%</span>'
        + (resetTs ? '<span style="font-size:10px;color:var(--text-muted);">reset: ' + escHtml(resetTs) + '</span>' : '')
        + '</div>'
        + '</div>';
    });
    barsHtml += '</div>';
  }

  // Extra fields (fallback-percentage, overage-status, representative-claim, etc.)
  var extras = {};
  Object.keys(rlHeaders).forEach(function(k) {
    if (k.match(/-(utilization|status|reset)$/) && k.match(/anthropic-ratelimit-unified-.+?-(utilization|status|reset)$/)) return;
    extras[k] = rlHeaders[k];
  });
  var extrasHtml = '';
  if (Object.keys(extras).length > 0) {
    extrasHtml = '<div style="font-size:11px;color:var(--text-muted);border-top:1px solid var(--border);padding-top:8px;margin-top:4px;">';
    Object.keys(extras).sort().forEach(function(k) {
      var label = k.replace('anthropic-ratelimit-unified-', '');
      extrasHtml += '<span style="margin-right:16px;"><b>' + escHtml(label) + ':</b> ' + escHtml(extras[k]) + '</span>';
    });
    extrasHtml += '</div>';
  }

  return '<div class="card"><div class="card-title">Rate Limits</div>' + barsHtml + extrasHtml + '</div>';
}

// SYSTEM
var _sysId = 0;
function renderSystem(blocks) {
  if (!blocks.length) return '<div class="card"><div class="card-title">System Prompt</div><p style="color:var(--text-muted);font-size:12px;">No system blocks.</p></div>';
  var items = blocks.map(function(block, i) {
    var text = block.text || JSON.stringify(block);
    var sizeStr = fmtBytes(new Blob([text]).size);
    var cacheStr = block.cache_control ? ' &bull; <span style="color:var(--yellow);">cached</span>' : '';
    var id = 'sys-' + (_sysId++);
    var tr = truncate(text, 500);
    var preview = tr[0], wasTrunc = tr[1];
    var fullSafe = escHtml(text);
    var previewSafe = escHtml(preview);
    var showMore = wasTrunc ? '<span class="show-more-btn" data-target="'+id+'-txt" data-full="'+fullSafe.replace(/"/g,'&quot;')+'" data-preview="'+previewSafe.replace(/"/g,'&quot;')+'" data-expanded="false">Show more</span>' : '';
    return '<div class="collapse-header"><span class="collapse-arrow">&#9658;</span><span class="collapse-title">Block '+(i+1)+' &mdash; '+escHtml(block.type||'text')+'</span><span class="collapse-meta">'+sizeStr+cacheStr+'</span></div>'
      + '<div class="collapse-body"><div class="code-block"><span id="'+id+'-txt">'+previewSafe+'</span></div>'+showMore+'</div>';
  }).join('');
  return '<div class="card"><div class="card-title">System Prompt &mdash; '+blocks.length+' block'+(blocks.length>1?'s':'')+'</div>'+items+'</div>';
}

// TOOLS
function renderTools(tools) {
  if (!tools.length) return '<div class="card"><div class="card-title">Tools</div><p style="color:var(--text-muted);font-size:12px;">No tools.</p></div>';
  var cards = tools.map(function(tool) {
    var name = tool.name || '?';
    var desc = tool.description || '';
    var props = Object.keys((tool.input_schema||{}).properties||{}).length;
    var schemaSize = fmtBytes(new Blob([JSON.stringify(tool)]).size);
    var descPreview = truncate(desc, 120)[0];
    return '<div class="tool-card" onclick="showToolModal(\''+escHtml(name).replace(/'/g,"\\'")+'\', this)" data-desc="'+btoa(unescape(encodeURIComponent(desc)))+'">'
      + '<div class="tool-name">'+escHtml(name)+'</div>'
      + '<div class="tool-desc">'+escHtml(descPreview)+'</div>'
      + '<div class="tool-badges"><span class="badge badge-schema">'+props+' props</span><span class="badge badge-size">'+schemaSize+'</span></div>'
      + '</div>';
  }).join('');
  return '<div class="card"><div class="card-title">Tools &mdash; '+tools.length+'</div><div class="tools-grid">'+cards+'</div></div>';
}

// MESSAGES
var _msgId = 0;
function renderMessages(messages, requestModel, requestEntry) {
  if (!messages.length) return '<div class="card"><div class="card-title">Messages</div><p style="color:var(--text-muted);font-size:12px;">No messages.</p></div>';
  var isInternalReq = requestEntry ? isInternalEntry(requestEntry) : (requestModel && requestModel.includes('haiku'));

  var bubbles = messages.map(function(msg, mi) {
    var rawRole = msg.role || 'unknown';
    var content = msg.content;
    var contentStr = getContentStr(content);
    var sizeStr = fmtBytes(new Blob([JSON.stringify(content)]).size);

    var blockTypes = Array.isArray(content) ? content.map(function(b){return b.type;}).filter(function(v,i,a){return a.indexOf(v)===i;}) : [];
    var isToolResult = rawRole === 'user' && blockTypes.length > 0 && blockTypes.every(function(t){return t === 'tool_result';});
    var hasToolUse = blockTypes.indexOf('tool_use') >= 0;
    var hasThinking = blockTypes.indexOf('thinking') >= 0;

    var role, roleLabel, apiInfo, explain;
    if (isToolResult) {
      role = 'tool-result'; roleLabel = 'tool result';
      apiInfo = 'role: "<b>user</b>" | content.type: "<b>tool_result</b>"';
      explain = 'Tool execution results are sent back as role:"user" in Anthropic API.';
    } else if (isInternalReq && rawRole === 'user') {
      role = 'user'; roleLabel = 'input (internal)';
      apiInfo = 'role: "<b>user</b>" | content.type: "<b>'+escHtml(blockTypes.join(', ')||'text')+'</b>"';
      explain = 'Internal haiku request for summarization/title generation.';
    } else if (rawRole === 'user') {
      role = 'user'; roleLabel = 'user';
      apiInfo = 'role: "<b>user</b>" | content.type: "<b>'+escHtml(blockTypes.join(', ')||'text')+'</b>"';
      explain = 'User prompt sent to the model.';
    } else if (rawRole === 'assistant' && hasToolUse && hasThinking) {
      role = 'assistant'; roleLabel = 'assistant';
      apiInfo = 'role: "<b>assistant</b>" | content.type: "<b>'+escHtml(blockTypes.join(', '))+'</b>"';
      explain = 'Assistant response with extended thinking + tool calls.';
    } else if (rawRole === 'assistant' && hasToolUse) {
      role = 'assistant'; roleLabel = 'assistant';
      apiInfo = 'role: "<b>assistant</b>" | content.type: "<b>'+escHtml(blockTypes.join(', '))+'</b>"';
      explain = 'Assistant requesting tool execution.';
    } else if (rawRole === 'assistant' && hasThinking) {
      role = 'assistant'; roleLabel = 'assistant';
      apiInfo = 'role: "<b>assistant</b>" | content.type: "<b>'+escHtml(blockTypes.join(', '))+'</b>"';
      explain = 'Assistant response with extended thinking.';
    } else if (rawRole === 'assistant') {
      role = 'assistant'; roleLabel = 'assistant';
      apiInfo = 'role: "<b>assistant</b>" | content.type: "<b>'+escHtml(blockTypes.join(', ')||'text')+'</b>"';
      explain = 'Assistant text response.';
    } else {
      role = rawRole; roleLabel = rawRole;
      apiInfo = 'role: "<b>'+escHtml(rawRole)+'</b>"';
      explain = '';
    }

    var blocksHtml = '';
    if (Array.isArray(content)) {
      blocksHtml = content.map(function(block) {
        var t = block.type || 'unknown';
        var text = '';
        if (t === 'text') text = block.text || '';
        else if (t === 'thinking') text = block.thinking || '';
        else if (t === 'tool_use') text = block.name + '(' + JSON.stringify(block.input||{}).slice(0,200) + ')';
        else if (t === 'tool_result') {
          var c = block.content;
          if (typeof c === 'string') text = c;
          else if (Array.isArray(c)) text = c.map(function(x){return x.text||'';}).join('\n');
          else text = JSON.stringify(c);
        } else text = JSON.stringify(block);

        var id = 'msg-' + (_msgId++);
        var tr = truncate(text, 300);
        var preview = tr[0], wasTrunc = tr[1];
        var safeFull = escHtml(text);
        var safePreview = escHtml(preview);
        var typeClass = ['text','tool_use','tool_result','thinking'].indexOf(t) >= 0 ? 'block-type-'+t : 'block-type-other';
        var showMore = wasTrunc ? '<span class="show-more-btn" data-target="'+id+'-txt" data-full="'+safeFull.replace(/"/g,'&quot;')+'" data-preview="'+safePreview.replace(/"/g,'&quot;')+'" data-expanded="false">Show full</span>' : '';
        return '<div class="block-item"><span class="block-type-badge '+typeClass+'">'+t+'</span><div class="block-content"><span id="'+id+'-txt">'+safePreview+'</span></div>'+showMore+'</div>';
      }).join('');
    } else {
      var id = 'msg-' + (_msgId++);
      var text = typeof content === 'string' ? content : JSON.stringify(content);
      var tr = truncate(text, 300);
      var showMore = tr[1] ? '<span class="show-more-btn" data-target="'+id+'-txt" data-full="'+escHtml(text).replace(/"/g,'&quot;')+'" data-preview="'+escHtml(tr[0]).replace(/"/g,'&quot;')+'" data-expanded="false">Show full</span>' : '';
      blocksHtml = '<div class="block-item"><div class="block-content"><span id="'+id+'-txt">'+escHtml(tr[0])+'</span></div>'+showMore+'</div>';
    }

    return '<div class="msg-bubble '+role+'">'
      + '<div class="msg-meta">'+roleLabel+' &bull; '+sizeStr+'</div>'
      + '<div class="msg-api-info">'+apiInfo+'</div>'
      + '<div class="bubble-inner">'+blocksHtml
      + (explain ? '<div class="msg-explain">'+explain+'</div>' : '')
      + '</div></div>';
  }).join('');

  return '<div class="card"><div class="card-title">Messages &mdash; '+messages.length+'</div><div class="msg-list">'+bubbles+'</div></div>';
}

// COMPARE
var compareMode = false;
var btnCompare = document.getElementById('btn-compare');
var comparePanel = document.getElementById('compare-panel');
var contentDiv = document.getElementById('content');

function toggleCompare() {
  compareMode = !compareMode;
  btnCompare.classList.toggle('active', compareMode);
  if (compareMode) {
    contentDiv.style.display = 'none';
    comparePanel.classList.add('visible');
  } else {
    contentDiv.style.display = '';
    comparePanel.classList.remove('visible');
    if (currentFile) {
      document.getElementById('empty-state').style.display = 'none';
      document.getElementById('dump-view').style.display = 'block';
    }
  }
}

btnCompare.addEventListener('click', toggleCompare);

function runCompare() {
  var fa = document.getElementById('cmp-a').value;
  var fb = document.getElementById('cmp-b').value;
  var result = document.getElementById('cmp-result');
  if (!fa || !fb) { result.innerHTML = ''; return; }

  var a = DUMPS[fa].data, b = DUMPS[fb].data;
  var szA = calcSizes(a), szB = calcSizes(b);

  var toolsA = new Set((a.tools||[]).map(function(t){return t.name;}));
  var toolsB = new Set((b.tools||[]).map(function(t){return t.name;}));
  var allTools = new Set([].concat(Array.from(toolsA), Array.from(toolsB)));

  var toolDiff = Array.from(allTools).sort().map(function(t) { return { name: t, inA: toolsA.has(t), inB: toolsB.has(t) }; });
  var addedTools = toolDiff.filter(function(x){ return !x.inA && x.inB; });
  var removedTools = toolDiff.filter(function(x){ return x.inA && !x.inB; });
  var sharedTools = toolDiff.filter(function(x){ return x.inA && x.inB; });

  function diffVal(vA, vB) {
    if (vA === vB) return '<span class="diff-same">'+vA+'</span>';
    return '<span class="diff-removed">'+vA+'</span> &rarr; <span class="diff-added">'+vB+'</span>';
  }
  function sizeDiff(sA, sB) {
    var delta = sB - sA;
    var cls = delta > 0 ? 'diff-added' : delta < 0 ? 'diff-removed' : 'diff-same';
    var sign = delta > 0 ? '+' : '';
    return fmtBytes(sA)+' &rarr; '+fmtBytes(sB)+' <span class="'+cls+'">('+sign+fmtBytes(Math.abs(delta))+')</span>';
  }

  result.innerHTML = ''
    + '<div class="card"><div class="card-title">Side-by-Side Comparison</div>'
    + '<div class="compare-grid">'
    + '<div class="compare-col"><div class="card-title">A: '+escHtml(fa.replace('-req.json',''))+'</div>'
    + '<div class="stat-grid" style="margin-bottom:14px;">'
    + '<div class="stat"><div class="stat-label">Model</div><div class="stat-value" style="font-size:11px;">'+escHtml(a.model||'?')+'</div></div>'
    + '<div class="stat"><div class="stat-label">Total Size</div><div class="stat-value green">'+fmtBytes(DUMPS[fa].size)+'</div></div>'
    + '<div class="stat"><div class="stat-label">Tools</div><div class="stat-value">'+(a.tools||[]).length+'</div></div>'
    + '<div class="stat"><div class="stat-label">Messages</div><div class="stat-value">'+(a.messages||[]).length+'</div></div>'
    + '</div></div>'
    + '<div class="compare-col"><div class="card-title">B: '+escHtml(fb.replace('-req.json',''))+'</div>'
    + '<div class="stat-grid" style="margin-bottom:14px;">'
    + '<div class="stat"><div class="stat-label">Model</div><div class="stat-value" style="font-size:11px;">'+escHtml(b.model||'?')+'</div></div>'
    + '<div class="stat"><div class="stat-label">Total Size</div><div class="stat-value green">'+fmtBytes(DUMPS[fb].size)+'</div></div>'
    + '<div class="stat"><div class="stat-label">Tools</div><div class="stat-value">'+(b.tools||[]).length+'</div></div>'
    + '<div class="stat"><div class="stat-label">Messages</div><div class="stat-value">'+(b.messages||[]).length+'</div></div>'
    + '</div></div></div></div>'
    + '<div class="card"><div class="card-title">Size Diff</div>'
    + '<div class="diff-row"><span class="diff-label">Total File</span><span class="diff-val">'+sizeDiff(DUMPS[fa].size, DUMPS[fb].size)+'</span></div>'
    + '<div class="diff-row"><span class="diff-label">System</span><span class="diff-val">'+sizeDiff(szA.sysSize, szB.sysSize)+'</span></div>'
    + '<div class="diff-row"><span class="diff-label">Tools</span><span class="diff-val">'+sizeDiff(szA.toolSize, szB.toolSize)+'</span></div>'
    + '<div class="diff-row"><span class="diff-label">Messages</span><span class="diff-val">'+sizeDiff(szA.msgSize, szB.msgSize)+'</span></div>'
    + '<div class="diff-row"><span class="diff-label">Model</span><span class="diff-val">'+diffVal(escHtml(a.model||'?'), escHtml(b.model||'?'))+'</span></div>'
    + '<div class="diff-row"><span class="diff-label">Max Tokens</span><span class="diff-val">'+diffVal(a.max_tokens||0, b.max_tokens||0)+'</span></div>'
    + '</div>'
    + '<div class="card"><div class="card-title">Tools Diff &mdash; '+addedTools.length+' added, '+removedTools.length+' removed, '+sharedTools.length+' shared</div>'
    + (addedTools.length ? '<div class="diff-section"><div class="diff-section-title">Added in B</div><ul class="diff-list">'+addedTools.map(function(t){return '<li class="added">'+escHtml(t.name)+'</li>';}).join('')+'</ul></div>' : '')
    + (removedTools.length ? '<div class="diff-section"><div class="diff-section-title">Removed in B</div><ul class="diff-list">'+removedTools.map(function(t){return '<li class="removed">'+escHtml(t.name)+'</li>';}).join('')+'</ul></div>' : '')
    + (sharedTools.length ? '<div class="diff-section"><div class="diff-section-title">Shared ('+sharedTools.length+')</div><ul class="diff-list">'+sharedTools.map(function(t){return '<li class="same">'+escHtml(t.name)+'</li>';}).join('')+'</ul></div>' : '')
    + '</div>';
}

document.getElementById('cmp-a').addEventListener('change', runCompare);
document.getElementById('cmp-b').addEventListener('change', runCompare);

// Tool Modal
function showToolModal(name, el) {
  var encoded = el.getAttribute('data-desc');
  var desc = decodeURIComponent(escape(atob(encoded)));
  var overlay = document.getElementById('tool-modal');
  overlay.querySelector('.modal-header h3').textContent = name;
  overlay.querySelector('.modal-body pre').textContent = desc;
  overlay.classList.add('active');
}
function closeToolModal() {
  document.getElementById('tool-modal').classList.remove('active');
}
document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeToolModal(); });

// Raw JSON toggle on content background click
var rawJsonVisible = false;
document.getElementById('content').addEventListener('click', function(e) {
  if (!currentFile) return;
  // Ignore clicks on interactive elements
  var t = e.target;
  while (t && t !== e.currentTarget) {
    if (t.tagName === 'A' || t.tagName === 'BUTTON' || t.tagName === 'SELECT' ||
        t.classList.contains('collapse-header') || t.classList.contains('show-more-btn') ||
        t.classList.contains('tool-card') || t.classList.contains('tool-desc') ||
        t.classList.contains('sess-tl-item')) return;
    t = t.parentElement;
  }
  var view = document.getElementById('dump-view');
  var rawView = document.getElementById('raw-json-view');
  if (!rawJsonVisible) {
    if (!rawView) {
      rawView = document.createElement('div');
      rawView.id = 'raw-json-view';
      view.parentElement.appendChild(rawView);
    }
    var activeTab = document.querySelector('.tab-btn.active');
    var isResponseTab = activeTab && activeTab.dataset.tab === 'response';
    var rawData = isResponseTab ? DUMPS[currentFile].response : DUMPS[currentFile].data;
    rawView.innerHTML = '<div class="code-block" style="max-height:none;font-size:11px;">' + escHtml(JSON.stringify(rawData, null, 2)) + '</div>';
    rawView.style.display = 'block';
    view.style.display = 'none';
    rawJsonVisible = true;
  } else {
    var rawEl = document.getElementById('raw-json-view');
    if (rawEl) rawEl.style.display = 'none';
    view.style.display = 'block';
    rawJsonVisible = false;
  }
});

// Home button
document.getElementById('home-btn').addEventListener('click', function() {
  currentFile = null;
  try { localStorage.removeItem('proxy_viewer_selected_file'); } catch(e) {}
  document.querySelectorAll('.file-item').forEach(function(x){ x.classList.remove('active'); });
  document.getElementById('dump-view').style.display = 'none';
  document.getElementById('empty-state').style.display = '';
  topbarFilename.textContent = '';
  if (compareMode) toggleCompare();
});
</script>

<div class="modal-overlay" id="tool-modal" onclick="if(event.target===this)closeToolModal()">
  <div class="modal">
    <div class="modal-header">
      <h3></h3>
      <button class="modal-close" onclick="closeToolModal()">&times;</button>
    </div>
    <div class="modal-body"><pre></pre></div>
  </div>
</div>
</body>
</html>"""


def main():
    dumps_dir = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(os.path.dirname(os.path.abspath(__file__)), "dumps")
    )

    if not os.path.isdir(dumps_dir):
        print(f"Error: dumps directory not found: {dumps_dir}")
        sys.exit(1)

    dumps = build_dumps(dumps_dir)
    if not dumps:
        print(f"Error: no *-req.json files found in {dumps_dir}")
        sys.exit(1)

    dumps_json = json.dumps(dumps, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("%%DUMPS_JSON%%", dumps_json)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "message.html")
    with open(out_path, "w") as f:
        f.write(html)

    print(f"Generated {out_path}")
    print(f"  {len(dumps)} request dumps embedded")
    total_size = sum(e["size"] for e in dumps.values())
    print(f"  Total data: {total_size:,} bytes")
    print(f"  HTML size: {os.path.getsize(out_path):,} bytes")
    print(f"\nOpen in browser: file://{out_path}")


if __name__ == "__main__":
    main()
