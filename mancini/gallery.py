"""
Generate an HTML gallery with prev/next navigation for review frames.
"""
from pathlib import Path


def generate_gallery(frame_paths: list[Path], output_dir: Path,
                     title: str = "Mancini Review") -> Path:
    """Write index.html with image slideshow and keyboard nav."""
    output_dir.mkdir(parents=True, exist_ok=True)

    filenames = [p.name for p in frame_paths]

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #111; color: #eee; font-family: monospace;
         display: flex; flex-direction: column; align-items: center;
         height: 100vh; justify-content: center; }}
  .viewer {{ position: relative; max-width: 95vw; max-height: 85vh; }}
  .viewer img {{ max-width: 95vw; max-height: 85vh; object-fit: contain;
                 border: 1px solid #333; border-radius: 4px; }}
  .controls {{ margin-top: 12px; display: flex; gap: 16px; align-items: center; }}
  button {{ background: #333; color: #eee; border: 1px solid #555;
            padding: 8px 20px; font-size: 16px; cursor: pointer;
            border-radius: 4px; font-family: monospace; }}
  button:hover {{ background: #555; }}
  .counter {{ font-size: 14px; color: #888; }}
  .hint {{ position: fixed; bottom: 12px; color: #555; font-size: 12px; }}
</style>
</head>
<body>
<div class="viewer">
  <img id="frame" src="{filenames[0] if filenames else ''}" />
</div>
<div class="controls">
  <button onclick="prev()">&larr; Prev</button>
  <span class="counter" id="counter">1 / {len(filenames)}</span>
  <button onclick="next()">Next &rarr;</button>
</div>
<div class="hint">Arrow keys or click to navigate</div>
<script>
const frames = {filenames};
let idx = 0;
const img = document.getElementById('frame');
const counter = document.getElementById('counter');

function show() {{
  img.src = frames[idx];
  counter.textContent = (idx + 1) + ' / ' + frames.length;
}}
function next() {{ idx = Math.min(idx + 1, frames.length - 1); show(); }}
function prev() {{ idx = Math.max(idx - 1, 0); show(); }}

document.addEventListener('keydown', e => {{
  if (e.key === 'ArrowRight' || e.key === ' ') next();
  if (e.key === 'ArrowLeft') prev();
}});
</script>
</body>
</html>"""

    index_path = output_dir / "index.html"
    index_path.write_text(html)
    return index_path
