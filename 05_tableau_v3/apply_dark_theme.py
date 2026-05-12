# apply_dark_theme.py  – dark-theme patch for seongnam_drone_hub_v3.twb
# Run: python apply_dark_theme.py

import re

PATH = r"C:\Users\jimin\Desktop\1_BITAmin_16기\1_Seongnam_reset\05_tableau_v3\seongnam_drone_hub_v3.twb"

with open(PATH, "r", encoding="utf-8") as f:
    txt = f.read()

changes = 0

# ── 1. Dashboard <style /> → add background-color ───────────────────────────
# Replace empty style tag inside <dashboard> elements
DARK_DASH_STYLE = (
    "<style>\n"
    "        <style-rule element='dashboard'>\n"
    "          <format attr='background-color' value='#0F0F1A' />\n"
    "        </style-rule>\n"
    "        <style-rule element='pane'>\n"
    "          <format attr='background-color' value='#1A1A2E' />\n"
    "        </style-rule>\n"
    "      </style>"
)

# Match the empty <style /> that appears inside a <dashboard> opening tag context
# The pattern is: inside <dashboard ...>  ...  <style />
old_empty_style = "      <style />"
count = txt.count(old_empty_style)
txt = txt.replace(old_empty_style, DARK_DASH_STYLE)
print(f"Dashboard <style />  →  dark style block: {count} replacement(s)")
changes += count

# ── 2. Zone-style border-color #000000 → #0F3460 (dark blue border) ─────────
txt_new = txt.replace(
    "attr='border-color' value='#000000'",
    "attr='border-color' value='#0F3460'",
)
n = txt.count("attr='border-color' value='#000000'")
# Actually let's count before replacement
n2 = txt_new.count("attr='border-color' value='#0F3460'") - txt.count("attr='border-color' value='#0F3460'")
txt = txt_new
print(f"Zone border #000000 → #0F3460: ~{n} replacement(s)")
changes += n

# ── 3. Map - H3 Grid: add worksheet-level background shading ─────────────────
# In the worksheet <style> (the outer one, not the pane style), add shading
# We target the style-rule for 'map' in H3 격자 지도 and append a worksheet shading rule
# We look for the specific map-style='dark' rule near the H3 sheet

OLD_MAP_STYLE = (
    "          <style-rule element='map'>\n"
    "            <format attr='washout' value='0.80000001192092896' />\n"
    "            <format attr='map-style' value='dark' />\n"
    "          </style-rule>"
)
NEW_MAP_STYLE = (
    "          <style-rule element='map'>\n"
    "            <format attr='washout' value='0.80000001192092896' />\n"
    "            <format attr='map-style' value='dark' />\n"
    "          </style-rule>\n"
    "          <style-rule element='worksheet'>\n"
    "            <format attr='background-color' value='#1A1A2E' />\n"
    "          </style-rule>"
)

count = txt.count(OLD_MAP_STYLE)
txt = txt.replace(OLD_MAP_STYLE, NEW_MAP_STYLE)
print(f"Map worksheet background added: {count} replacement(s)")
changes += count

# ── 4. KPI pane color override ────────────────────────────────────────────────
# KPI sheets need dark pane background; their style sections have a mark style
# We patch the pane <style> blocks in KPI sheets to add dark pane color
# Each KPI pane style has: <format attr='mark-text-size' ... /> or similar
# Instead add a worksheet-level shading to KPI window sections
# This is better done at runtime, skip for now

print(f"\nTotal changes: {changes}")
with open(PATH, "w", encoding="utf-8") as f:
    f.write(txt)
print("File saved.")
