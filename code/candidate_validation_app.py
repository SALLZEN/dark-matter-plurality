#!/usr/bin/env python3
"""Local, blinded browser interface for candidate-dictionary validation.

The server binds to localhost, reads only the annotation CSVs and the public
candidate ontology, and never reads or exposes ``candidate_validation_system_key.csv``.
Annotations are saved atomically. A timestamped session snapshot is made when
the app starts and the immediately previous CSV is retained as ``.bak``.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import tempfile
import threading
import urllib.parse
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from dm_term_normalization.candidate_ontology import SPECIES_LABEL_MAP


DATASETS = {
    "development": {
        "filename": "candidate_validation_development.csv",
        "label": "Development sample",
        "description": "Use these records to refine the dictionary before freezing it.",
    },
    "holdout_positive": {
        "filename": "candidate_validation_holdout_positive.csv",
        "label": "System-positive holdout",
        "description": "Blinded, candidate-enriched sample for precision and family-level checks.",
    },
    "holdout_population": {
        "filename": "candidate_validation_holdout_population.csv",
        "label": "Population holdout",
        "description": "Blinded field-by-period sample for missed mentions and differential error.",
    },
}

ANNOTATION_COLUMNS = ("gold_any_candidate", "gold_candidates", "notes")
CANDIDATE_FAMILIES = sorted(set(SPECIES_LABEL_MAP.values()), key=str.casefold)


def _is_complete(row: dict[str, str]) -> bool:
    return row.get("gold_any_candidate", "").strip().lower() in {"yes", "no"}


class ValidationStore:
    """Read and safely update the three blinded annotation tables."""

    def __init__(self, validation_dir: Path):
        self.validation_dir = validation_dir.resolve()
        self._lock = threading.RLock()
        self._validate_inputs()
        self.session_backup_dir = self._make_session_backup()

    def _validate_inputs(self) -> None:
        missing = [
            config["filename"]
            for config in DATASETS.values()
            if not (self.validation_dir / config["filename"]).is_file()
        ]
        if missing:
            raise FileNotFoundError(
                "Missing validation annotation file(s): " + ", ".join(missing)
            )

    def _path(self, dataset: str) -> Path:
        try:
            filename = DATASETS[dataset]["filename"]
        except KeyError as exc:
            raise ValueError(f"Unknown dataset: {dataset}") from exc
        return self.validation_dir / filename

    def _make_session_backup(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = self.validation_dir / ".annotation-backups" / stamp
        suffix = 1
        while backup_dir.exists():
            backup_dir = self.validation_dir / ".annotation-backups" / f"{stamp}-{suffix}"
            suffix += 1
        backup_dir.mkdir(parents=True)
        for config in DATASETS.values():
            source = self.validation_dir / config["filename"]
            shutil.copy2(source, backup_dir / source.name)
        return backup_dir

    def _read(self, dataset: str) -> tuple[list[str], list[dict[str, str]]]:
        path = self._path(dataset)
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError(f"No CSV header found in {path}")
            rows = [dict(row) for row in reader]
            fieldnames = list(reader.fieldnames)
        missing = [name for name in ANNOTATION_COLUMNS if name not in fieldnames]
        if missing:
            raise ValueError(f"Missing annotation columns in {path.name}: {missing}")
        return fieldnames, rows

    def status(self) -> dict[str, Any]:
        with self._lock:
            datasets: list[dict[str, Any]] = []
            for key, config in DATASETS.items():
                _, rows = self._read(key)
                completed = sum(_is_complete(row) for row in rows)
                first_incomplete = next(
                    (index for index, row in enumerate(rows) if not _is_complete(row)), None
                )
                datasets.append(
                    {
                        "key": key,
                        "label": config["label"],
                        "description": config["description"],
                        "total": len(rows),
                        "completed": completed,
                        "remaining": len(rows) - completed,
                        "first_incomplete": first_incomplete,
                    }
                )
            return {
                "datasets": datasets,
                "candidate_families": CANDIDATE_FAMILIES,
                "backup_dir": str(self.session_backup_dir),
            }

    def record(self, dataset: str, index: int) -> dict[str, Any]:
        with self._lock:
            _, rows = self._read(dataset)
            if not rows:
                raise ValueError(f"Dataset {dataset} is empty")
            index = max(0, min(index, len(rows) - 1))
            row = rows[index]
            completed = sum(_is_complete(item) for item in rows)
            next_incomplete = next(
                (i for i in range(index + 1, len(rows)) if not _is_complete(rows[i])),
                next((i for i, item in enumerate(rows) if not _is_complete(item)), None),
            )
            return {
                "dataset": dataset,
                "index": index,
                "total": len(rows),
                "completed": completed,
                "remaining": len(rows) - completed,
                "next_incomplete": next_incomplete,
                "record": row,
            }

    def save_annotation(
        self,
        dataset: str,
        sample_id: str,
        gold_any_candidate: str,
        gold_candidates: list[str],
        notes: str,
    ) -> dict[str, Any]:
        answer = gold_any_candidate.strip().lower()
        if answer not in {"", "yes", "no"}:
            raise ValueError("gold_any_candidate must be yes, no, or blank")
        unknown = sorted(set(gold_candidates) - set(CANDIDATE_FAMILIES))
        if unknown:
            raise ValueError("Unknown canonical candidate family: " + ", ".join(unknown))
        selected = [] if answer == "no" else sorted(set(gold_candidates), key=str.casefold)

        with self._lock:
            fieldnames, rows = self._read(dataset)
            matches = [i for i, row in enumerate(rows) if row.get("sample_id") == sample_id]
            if len(matches) != 1:
                raise ValueError(f"Expected exactly one row for sample_id {sample_id!r}")
            row = rows[matches[0]]
            row["gold_any_candidate"] = answer
            row["gold_candidates"] = ";".join(selected)
            row["notes"] = notes.strip()
            self._atomic_write(self._path(dataset), fieldnames, rows)
            return self.record(dataset, matches[0])

    @staticmethod
    def _atomic_write(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Candidate validation</title>
<style>
:root { color-scheme: light; --ink:#202322; --muted:#69706d; --line:#d6dbd8;
  --paper:#fbfcfa; --panel:#fff; --yes:#16735b; --no:#a13a43; --accent:#315d86; }
* { box-sizing:border-box; }
body { margin:0; background:var(--paper); color:var(--ink); font:16px/1.5 system-ui,-apple-system,sans-serif; }
main { width:min(1180px, calc(100% - 32px)); margin:24px auto 80px; }
header { display:grid; grid-template-columns:1fr auto; gap:20px; align-items:end; margin-bottom:18px; }
h1 { font:600 28px/1.2 Georgia,serif; margin:0 0 5px; }
p { margin:0; }
.muted { color:var(--muted); }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:12px; box-shadow:0 2px 12px #0000000a; }
.toolbar { display:grid; grid-template-columns:minmax(250px,1fr) auto; gap:18px; padding:16px; margin-bottom:14px; align-items:end; }
label { display:block; font-weight:600; font-size:14px; }
select,input[type="search"],textarea { width:100%; margin-top:6px; padding:9px 10px; border:1px solid #bcc5c1; border-radius:7px; background:#fff; color:var(--ink); font:inherit; }
.progress-text { text-align:right; font-variant-numeric:tabular-nums; }
.bar { width:230px; height:8px; margin-top:7px; background:#e8ece9; border-radius:20px; overflow:hidden; }
.bar > span { display:block; height:100%; background:var(--yes); width:0; transition:width .2s; }
.record { padding:20px; }
.meta { display:flex; gap:7px; flex-wrap:wrap; margin-bottom:14px; }
.badge { background:#edf1ef; border-radius:999px; padding:3px 9px; font-size:13px; }
.abstract { white-space:pre-wrap; font:18px/1.65 Georgia,serif; padding:18px; border:1px solid #e1e5e2; background:#fcfdfc; border-radius:8px; max-height:42vh; overflow:auto; }
.question { margin-top:20px; display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
.question strong { margin-right:8px; }
button { border:1px solid #aeb8b3; border-radius:7px; background:#fff; color:var(--ink); padding:9px 14px; font:600 14px/1 system-ui,sans-serif; cursor:pointer; }
button:hover { background:#f0f3f1; }
button.active.yes { color:#fff; background:var(--yes); border-color:var(--yes); }
button.active.no { color:#fff; background:var(--no); border-color:var(--no); }
button.primary { color:#fff; background:var(--accent); border-color:var(--accent); }
button:disabled { cursor:not-allowed; opacity:.45; }
.candidate-head { display:grid; grid-template-columns:1fr minmax(220px,320px); gap:16px; align-items:end; margin-top:20px; }
.candidates { display:grid; grid-template-columns:repeat(auto-fill,minmax(190px,1fr)); gap:7px 14px; margin-top:12px; padding:14px; border:1px solid var(--line); border-radius:8px; max-height:250px; overflow:auto; }
.candidate { display:flex; gap:8px; align-items:flex-start; font-weight:400; font-size:14px; }
.candidate input { margin-top:4px; }
.candidate.disabled { opacity:.42; }
.notes { margin-top:18px; }
textarea { min-height:76px; resize:vertical; }
.footer { position:sticky; bottom:0; display:flex; gap:10px; justify-content:space-between; align-items:center; padding:12px 16px; margin-top:14px; }
.nav { display:flex; gap:8px; flex-wrap:wrap; }
.save-state { min-width:135px; color:var(--muted); font-size:14px; }
.warning { margin-top:12px; padding:10px 13px; border-left:3px solid #c8902e; background:#fff8e9; font-size:14px; }
kbd { padding:1px 5px; border:1px solid #bbc2bf; border-bottom-width:2px; border-radius:4px; background:#fff; font-size:12px; }
@media (min-width:900px) {
  .record { display:grid; grid-template-columns:minmax(0,1.2fr) minmax(390px,.8fr); gap:14px 20px; align-items:start; }
  .meta { grid-column:1 / -1; margin-bottom:0; }
  .abstract { grid-column:1; grid-row:2 / span 5; max-height:64vh; }
  .question { grid-column:2; grid-row:2; margin-top:0; }
  .question strong { flex-basis:100%; }
  .candidate-head { grid-column:2; grid-row:3; margin-top:0; grid-template-columns:1fr 180px; }
  .candidates { grid-column:2; grid-row:4; margin-top:0; max-height:245px; grid-template-columns:repeat(2,minmax(0,1fr)); }
  .notes { grid-column:2; grid-row:5; margin-top:0; }
  .warning { grid-column:2; grid-row:6; margin-top:0; }
}
@media (max-width:720px) { header,.toolbar,.candidate-head { grid-template-columns:1fr; } .progress-text{text-align:left}.bar{width:100%}.abstract{font-size:16px}.footer{align-items:flex-start;flex-direction:column}.nav{width:100%}button{flex:1} }
</style>
</head>
<body>
<main>
  <header>
    <div><h1>Candidate-dictionary validation</h1><p class="muted">Blinded local annotation; system predictions are never loaded.</p></div>
    <div class="muted"><kbd>Y</kbd>/<kbd>N</kbd> classify &nbsp; <kbd>Ctrl</kbd>+<kbd>Enter</kbd> save and next</div>
  </header>
  <section class="toolbar panel">
    <label>Validation set<select id="dataset"></select><span id="dataset-description" class="muted"></span></label>
    <div class="progress-text"><strong id="progress-count">–</strong><div class="bar"><span id="progress-bar"></span></div></div>
  </section>
  <section class="record panel">
    <div class="meta" id="meta"></div>
    <div class="abstract" id="abstract">Loading…</div>
    <div class="question"><strong>Does the abstract mention a physical dark-matter candidate?</strong>
      <button type="button" id="yes" class="yes">Yes <kbd>Y</kbd></button>
      <button type="button" id="no" class="no">No <kbd>N</kbd></button>
      <button type="button" id="clear">Clear</button>
    </div>
    <div class="candidate-head"><strong>Canonical candidate family or families</strong><label>Filter families<input type="search" id="family-filter" placeholder="Type to filter…"></label></div>
    <div class="candidates" id="candidates"></div>
    <label class="notes">Notes or proposed missing family<textarea id="notes" placeholder="Optional ambiguity note…"></textarea></label>
    <div class="warning">Annotate the abstract as written. Count mentions, not endorsement or viability. Do not consult <code>candidate_validation_system_key.csv</code>.</div>
  </section>
  <section class="footer panel">
    <div class="save-state" id="save-state">Ready</div>
    <div class="nav">
      <button type="button" id="previous">Previous</button>
      <button type="button" id="next-incomplete">Next incomplete</button>
      <button type="button" id="next">Next</button>
      <button type="button" id="save-next" class="primary">Save and next</button>
    </div>
  </section>
</main>
<script>
const state = {config:null, dataset:localStorage.getItem('candidateValidationDataset') || 'development', index:0, payload:null, dirty:false, saving:false, timer:null, selectedFamilies:new Set()};
const $ = id => document.getElementById(id);
async function api(url, options={}) { const response = await fetch(url, options); const body = await response.json(); if (!response.ok) throw new Error(body.error || response.statusText); return body; }
function selectedFamilies() { return [...state.selectedFamilies]; }
function answer() { return $('yes').classList.contains('active') ? 'yes' : ($('no').classList.contains('active') ? 'no' : ''); }
function setAnswer(value, mark=true) {
  $('yes').classList.toggle('active', value==='yes'); $('no').classList.toggle('active', value==='no');
  const disabled = value==='no'; if(disabled) state.selectedFamilies.clear(); document.querySelectorAll('#candidates input').forEach(input=>{ input.disabled=disabled; if(disabled) input.checked=false; input.closest('.candidate').classList.toggle('disabled',disabled); });
  if(mark) changed();
}
function changed() { state.dirty=true; $('save-state').textContent='Unsaved changes…'; clearTimeout(state.timer); state.timer=setTimeout(()=>save(false,true),700); }
function renderFamilies(selected=null) {
  if(selected!==null) state.selectedFamilies=new Set(selected);
  const query=$('family-filter').value.trim().toLowerCase(); $('candidates').replaceChildren();
  state.config.candidate_families.filter(name=>name.toLowerCase().includes(query)).forEach(name=>{
    const label=document.createElement('label'); label.className='candidate'; const input=document.createElement('input'); input.type='checkbox'; input.value=name; input.checked=state.selectedFamilies.has(name); input.addEventListener('change',()=>{ if(input.checked){state.selectedFamilies.add(name);setAnswer('yes',false);}else{state.selectedFamilies.delete(name);} changed(); });
    const span=document.createElement('span'); span.textContent=name; label.append(input,span); $('candidates').append(label);
  });
  setAnswer(answer(),false);
}
function renderRecord(payload) {
  state.payload=payload; state.index=payload.index; state.dirty=false;
  const row=payload.record; $('meta').replaceChildren();
  [`${payload.index+1} of ${payload.total}`,row.field,row.period,row.year,row.bibcode,row.sample_id].filter(Boolean).forEach(value=>{const badge=document.createElement('span');badge.className='badge';badge.textContent=value;$('meta').append(badge);});
  $('abstract').textContent=row.abstract || '[No abstract]'; $('notes').value=row.notes || '';
  const selected=(row.gold_candidates || '').split(';').map(x=>x.trim()).filter(Boolean); renderFamilies(selected); setAnswer((row.gold_any_candidate||'').toLowerCase(),false);
  updateProgress(payload); $('save-state').textContent='Saved'; $('previous').disabled=payload.index===0; $('next').disabled=payload.index>=payload.total-1;
}
function updateProgress(payload) { $('progress-count').textContent=`${payload.completed} of ${payload.total} completed (${payload.remaining} remaining)`; $('progress-bar').style.width=`${payload.total ? 100*payload.completed/payload.total : 0}%`; }
async function load(index=0) { clearTimeout(state.timer); if(state.dirty) await save(false,true); $('save-state').textContent='Loading…'; renderRecord(await api(`/api/record?dataset=${encodeURIComponent(state.dataset)}&index=${index}`)); }
async function save(advance=false,silent=false) {
  if(state.saving) { while(state.saving) await new Promise(resolve=>setTimeout(resolve,30)); if(advance) await load(Math.min(state.index+1,state.payload.total-1)); return; }
  if(!state.payload || (!state.dirty && !advance)) { if(advance) await load(Math.min(state.index+1,state.payload.total-1)); return; }
  clearTimeout(state.timer); state.saving=true; $('save-state').textContent='Saving…';
  try { const payload=await api('/api/annotation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset:state.dataset,sample_id:state.payload.record.sample_id,gold_any_candidate:answer(),gold_candidates:selectedFamilies(),notes:$('notes').value})}); state.dirty=false; updateProgress(payload); $('save-state').textContent='Saved'; if(advance) await load(Math.min(state.index+1,state.payload.total-1)); }
  catch(error) { $('save-state').textContent=`Save failed: ${error.message}`; if(!silent) alert(error.message); }
  finally { state.saving=false; }
}
async function start() {
  state.config=await api('/api/config'); const select=$('dataset'); state.config.datasets.forEach(item=>{const option=document.createElement('option');option.value=item.key;option.textContent=`${item.label} — ${item.completed}/${item.total}`;select.append(option);});
  if(!state.config.datasets.some(x=>x.key===state.dataset)) state.dataset='development'; select.value=state.dataset;
  const item=state.config.datasets.find(x=>x.key===state.dataset); $('dataset-description').textContent=` ${item.description}`; await load(item.first_incomplete ?? 0);
}
$('dataset').addEventListener('change',async event=>{const nextDataset=event.target.value;if(state.dirty)await save(false,true);state.dataset=nextDataset;localStorage.setItem('candidateValidationDataset',state.dataset);state.config=await api('/api/config');const item=state.config.datasets.find(x=>x.key===state.dataset);$('dataset-description').textContent=` ${item.description}`;await load(item.first_incomplete ?? 0);});
$('yes').addEventListener('click',()=>setAnswer('yes')); $('no').addEventListener('click',()=>setAnswer('no')); $('clear').addEventListener('click',()=>{state.selectedFamilies.clear();setAnswer('');document.querySelectorAll('#candidates input').forEach(x=>x.checked=false);$('notes').value='';changed();});
$('notes').addEventListener('input',changed); $('family-filter').addEventListener('input',()=>renderFamilies());
$('previous').addEventListener('click',()=>load(Math.max(0,state.index-1))); $('next').addEventListener('click',()=>load(Math.min(state.payload.total-1,state.index+1))); $('save-next').addEventListener('click',()=>save(true));
$('next-incomplete').addEventListener('click',()=>{if(state.payload.next_incomplete===null){alert('This validation set is complete.');return;}load(state.payload.next_incomplete);});
document.addEventListener('keydown',event=>{if(event.ctrlKey && event.key==='Enter'){event.preventDefault();save(true);return;}const tag=document.activeElement.tagName;if(['INPUT','TEXTAREA','SELECT'].includes(tag))return;if(event.key.toLowerCase()==='y')setAnswer('yes');if(event.key.toLowerCase()==='n')setAnswer('no');});
window.addEventListener('beforeunload',event=>{if(state.dirty){event.preventDefault();event.returnValue='';}}); start().catch(error=>{$('abstract').textContent=`Could not start: ${error.message}`;});
</script>
</body>
</html>
"""


class ValidationHandler(BaseHTTPRequestHandler):
    store: ValidationStore

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, error: Exception, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        self._json({"error": str(error)}, status)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/":
                payload = HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
                return
            if parsed.path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
                return
            if parsed.path == "/api/config":
                self._json(self.store.status())
                return
            if parsed.path == "/api/record":
                query = urllib.parse.parse_qs(parsed.query)
                dataset = query.get("dataset", [""])[0]
                index = int(query.get("index", ["0"])[0])
                self._json(self.store.record(dataset, index))
                return
            self._error(FileNotFoundError("Not found"), HTTPStatus.NOT_FOUND)
        except Exception as error:
            self._error(error)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/annotation":
            self._error(FileNotFoundError("Not found"), HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_000_000:
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            result = self.store.save_annotation(
                dataset=str(data.get("dataset", "")),
                sample_id=str(data.get("sample_id", "")),
                gold_any_candidate=str(data.get("gold_any_candidate", "")),
                gold_candidates=[str(value) for value in data.get("gold_candidates", [])],
                notes=str(data.get("notes", "")),
            )
            self._json(result)
        except Exception as error:
            self._error(error)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    project_root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--validation-dir",
        type=Path,
        default=project_root / "data" / "validation",
        help="Directory containing the blinded candidate-validation CSVs.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = ValidationStore(args.validation_dir)
    handler = type("ConfiguredValidationHandler", (ValidationHandler,), {"store": store})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Candidate validation interface: {url}")
    print(f"Session backup: {store.session_backup_dir}")
    print("Press Ctrl-C to stop.")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
