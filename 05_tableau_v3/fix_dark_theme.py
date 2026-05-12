# fix_dark_theme.py  – revert bad worksheet styles, correctly apply dark theme
import re

PATH = r"C:\Users\jimin\Desktop\1_BITAmin_16기\1_Seongnam_reset\05_tableau_v3\seongnam_drone_hub_v3.twb"

with open(PATH, "r", encoding="utf-8") as f:
    txt = f.read()

# ── STEP 1: Revert ALL incorrectly applied dark style blocks ─────────────────
# The bad replacement changed `      <style />` to a block starting with `<style>`
# Pattern: the incorrectly applied dark block (any indentation before <style>)
BAD_DARK = re.compile(
    r"<style>\s*\n\s*<style-rule element='dashboard'>\s*\n"
    r"\s*<format attr='background-color' value='#0F0F1A' />\s*\n"
    r"\s*</style-rule>\s*\n"
    r"\s*<style-rule element='pane'>\s*\n"
    r"\s*<format attr='background-color' value='#1A1A2E' />\s*\n"
    r"\s*</style-rule>\s*\n"
    r"\s*</style>"
)

def revert_bad_style(m):
    return "      <style />"

n_reverted = len(BAD_DARK.findall(txt))
txt = BAD_DARK.sub(revert_bad_style, txt)
print(f"Reverted bad dark style blocks: {n_reverted}")

# ── STEP 2: Correctly apply dark background ONLY to <dashboard> elements ──────
# Pattern: inside <dashboard ...> block, the <style /> right after it
# The dashboard element starts with: <dashboard ... name='대시보드...'>
#   then next non-empty line is: <style />
DASH_STYLE = re.compile(
    r"(<dashboard[^>]*>\s*\n)"   # group 1: opening dashboard tag + newline
    r"(\s*<style />)"             # group 2: the empty style
)

CORRECT_DASH_STYLE = (
    r"\1"
    r"      <style>\n"
    r"        <style-rule element='dashboard'>\n"
    r"          <format attr='background-color' value='#0F0F1A' />\n"
    r"        </style-rule>\n"
    r"      </style>"
)

n_dash = len(DASH_STYLE.findall(txt))
txt = DASH_STYLE.sub(CORRECT_DASH_STYLE, txt)
print(f"Dashboard dark backgrounds applied: {n_dash}")

# ── STEP 3: Map washout already has dark style – just ensure map worksheet ─────
# This was correctly done: 3 map-style='dark' sheets got worksheet bg added
# Check how many we have
n_ws = txt.count("element='worksheet'")
print(f"Worksheet background rules present: {n_ws}")

# ── STEP 4: Zone border already updated to #0F3460 – verify count ─────────────
n_border = txt.count("attr='border-color' value='#0F3460'")
print(f"Dark borders (#0F3460): {n_border}")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(txt)
print("\nFile saved.")
