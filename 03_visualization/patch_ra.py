"""
Patch dashboard.html: replace st (score_terrain = 1.0) with Ra values
from processed/constraint_layers_v3_ra.csv
"""
import csv, re, json, os

BASE = r"C:\Users\6152\Desktop\성남시\Aero-Logic-seongnam"
RA_CSV   = os.path.join(BASE, r"processed\constraint_layers_v3_ra.csv")
HTML_IN  = os.path.join(BASE, r"03_visualization\dashboard.html")
HTML_OUT = HTML_IN

# 1. Build h3 → Ra dict
ra_map = {}
with open(RA_CSV, encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        h3 = row["h3_index"].strip()
        try:
            ra_map[h3] = round(float(row["Ra"]), 4)
        except (ValueError, KeyError):
            pass
print(f"Ra values loaded: {len(ra_map)} cells")

# 2. Read HTML
with open(HTML_IN, encoding="utf-8") as f:
    html = f.read()

# 3. Find the GRID constant and parse its JSON array
#    Pattern: const GRID = [...];
m = re.search(r'const GRID\s*=\s*(\[.*?\]);', html, re.DOTALL)
if not m:
    raise RuntimeError("Could not find 'const GRID = [...]' in HTML")

grid_json_str = m.group(1)
grid = json.loads(grid_json_str)
print(f"GRID cells found: {len(grid)}")

# 4. Patch st values
patched = 0
missing = 0
for cell in grid:
    h3 = cell.get("h3", "")
    if h3 in ra_map:
        cell["st"] = ra_map[h3]
        patched += 1
    else:
        missing += 1

print(f"Patched: {patched}, Missing Ra: {missing}")

# 5. Serialize back (compact, no extra spaces to keep file size small)
new_grid_str = json.dumps(grid, ensure_ascii=False, separators=(',', ':'))

# 6. Replace in HTML
new_html = html[:m.start(1)] + new_grid_str + html[m.end(1):]

with open(HTML_OUT, encoding="utf-8", mode="w") as f:
    f.write(new_html)

print(f"Done → {HTML_OUT}")
