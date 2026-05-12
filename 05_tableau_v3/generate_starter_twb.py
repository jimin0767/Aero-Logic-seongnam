"""
generate_starter_twb.py — Create a starter Tableau workbook with:
  - 5 CSV data source connections (text files, absolute paths)
  - 9 parameters (3 demand toggles + 5 constraint toggles + airspace mode)
  - Calculated fields (Demand Score, Constraint Score, Final Score, etc.)
  - Empty placeholder worksheets (no visual content — user builds those in Tableau)

This is intentionally minimal. It does NOT define marks, pills, or dashboards.
The user only needs to drag fields onto shelves in Tableau Desktop.
"""

import hashlib
import json
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
OUT_TWB = Path(__file__).resolve().parent / "seongnam_drone_hub_v3.twb"

def ds_name(label):
    """Generate a deterministic short hash for datasource name."""
    h = hashlib.md5(label.encode()).hexdigest()[:20]
    return f"textscan.{h}"

def esc(s):
    """XML-escape a string."""
    return s.replace("&", "&amp;").replace("'", "&apos;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

def abspath(fname):
    """Absolute path to a data file (single backslashes — XML doesn't need escaping for \\)."""
    return str(DATA_DIR / fname)

# ── Data source definitions ────────────────────────────────────────────────
DS = {
    "grid_master": {
        "caption": "Grid Master",
        "file": "grid_master.csv",
        "fields": [
            ("h3_index",       "string",  "dimension", "nominal",      None),
            ("lat",            "real",    "measure",   "quantitative", "[Geographical].[Latitude]"),
            ("lon",            "real",    "measure",   "quantitative", "[Geographical].[Longitude]"),
            ("ADM_NM",         "string",  "dimension", "nominal",      None),
            ("GU_NM",          "string",  "dimension", "nominal",      None),
            ("demand_b2b",     "real",    "measure",   "quantitative", None),
            ("demand_b2c",     "real",    "measure",   "quantitative", None),
            ("demand_cv",      "real",    "measure",   "quantitative", None),
            ("Ds",             "real",    "measure",   "quantitative", None),
            ("demand_grade",   "string",  "dimension", "nominal",      None),
            ("score_airspace", "real",    "measure",   "quantitative", None),
            ("score_obstacle", "real",    "measure",   "quantitative", None),
            ("score_noise",    "real",    "measure",   "quantitative", None),
            ("score_robot",    "real",    "measure",   "quantitative", None),
            ("score_weather",  "real",    "measure",   "quantitative", None),
            ("delivery_zone",  "string",  "dimension", "nominal",      None),
            ("drone_score",    "real",    "measure",   "quantitative", None),
            ("robot_score",    "real",    "measure",   "quantitative", None),
            ("hard_exclusion", "boolean", "dimension", "nominal",      None),
        ],
        "calc_fields": [
            {
                "name": "Demand Score",
                "caption": "Demand Score",
                "datatype": "real",
                "formula": (
                    "IIF(\n"
                    "  INT([Parameters].[p_demand_b2b]) + INT([Parameters].[p_demand_b2c]) + INT([Parameters].[p_demand_cv]) = 0,\n"
                    "  1.0,\n"
                    "  (IIF([Parameters].[p_demand_b2b], [demand_b2b], 0)\n"
                    "  + IIF([Parameters].[p_demand_b2c], [demand_b2c], 0)\n"
                    "  + IIF([Parameters].[p_demand_cv], [demand_cv], 0))\n"
                    "  / (INT([Parameters].[p_demand_b2b]) + INT([Parameters].[p_demand_b2c]) + INT([Parameters].[p_demand_cv]))\n"
                    ")"
                ),
            },
            {
                "name": "Constraint Score",
                "caption": "Constraint Score",
                "datatype": "real",
                "formula": (
                    "(IIF([Parameters].[p_con_airspace], [score_airspace], 1.0)\n"
                    "+ IIF([Parameters].[p_con_obstacle], [score_obstacle], 1.0)\n"
                    "+ IIF([Parameters].[p_con_noise],    [score_noise],    1.0)\n"
                    "+ IIF([Parameters].[p_con_robot],    [score_robot],    1.0)\n"
                    "+ IIF([Parameters].[p_con_weather],  [score_weather],  1.0)) / 5"
                ),
            },
            {
                "name": "Final Score",
                "caption": "Final Score",
                "datatype": "real",
                "formula": "[Demand Score] * [Constraint Score]",
            },
            {
                "name": "Is Strict Excluded",
                "caption": "Is Strict Excluded",
                "datatype": "boolean",
                "formula": (
                    "[hard_exclusion] AND [Parameters].[p_con_airspace] "
                    "AND [Parameters].[p_airspace_mode] = \"strict\""
                ),
            },
        ],
    },
    "scenario_hubs": {
        "caption": "Scenario Hubs",
        "file": "scenario_hubs.csv",
        "fields": [
            ("scenario_id",   "string",  "dimension", "nominal",      None),
            ("lot_id",        "string",  "dimension", "nominal",      None),
            ("lot_name",      "string",  "dimension", "nominal",      None),
            ("lat",           "real",    "measure",   "quantitative", "[Geographical].[Latitude]"),
            ("lon",           "real",    "measure",   "quantitative", "[Geographical].[Longitude]"),
            ("gu",            "string",  "dimension", "nominal",      None),
            ("dong",          "string",  "dimension", "nominal",      None),
            ("rank",          "integer", "measure",   "quantitative", None),
            ("cover_n",       "integer", "measure",   "quantitative", None),
            ("cover_ds",      "real",    "measure",   "quantitative", None),
            ("route_fi",      "real",    "measure",   "quantitative", None),
            ("delivery_zone", "string",  "dimension", "nominal",      None),
            ("explanation",   "string",  "dimension", "nominal",      None),
        ],
        "calc_fields": [
            {
                "name": "Current Scenario ID",
                "caption": "Current Scenario ID",
                "datatype": "string",
                "formula": (
                    "\"S\" + RIGHT(\"000\" + STR(\n"
                    "  (IIF(NOT [Parameters].[p_con_weather],  1, 0)\n"
                    "  + IIF(NOT [Parameters].[p_con_robot],   2, 0)\n"
                    "  + IIF(NOT [Parameters].[p_con_noise],   4, 0)\n"
                    "  + IIF(NOT [Parameters].[p_con_obstacle],8, 0)\n"
                    "  + IIF(NOT [Parameters].[p_con_airspace],16, 0))\n"
                    "  * 2\n"
                    "  + IIF([Parameters].[p_airspace_mode] = \"strict\", 1, 0)\n"
                    "  + 1\n"
                    "), 3)"
                ),
            },
            {
                "name": "Is Active Scenario",
                "caption": "Is Active Scenario",
                "datatype": "boolean",
                "formula": "[scenario_id] = [Current Scenario ID]",
            },
        ],
    },
    "scenario_routes": {
        "caption": "Scenario Routes",
        "file": "scenario_routes.csv",
        "fields": [
            ("scenario_id",  "string",  "dimension", "nominal",      None),
            ("route_id",     "string",  "dimension", "nominal",      None),
            ("lot_id",       "string",  "dimension", "nominal",      None),
            ("dong",         "string",  "dimension", "nominal",      None),
            ("path_order",   "integer", "dimension", "ordinal",      None),
            ("route_lat",    "real",    "measure",   "quantitative", "[Geographical].[Latitude]"),
            ("route_lon",    "real",    "measure",   "quantitative", "[Geographical].[Longitude]"),
            ("approval",     "boolean", "dimension", "nominal",      None),
            ("drone_t",      "real",    "measure",   "quantitative", None),
            ("time_saving",  "real",    "measure",   "quantitative", None),
            ("co2_saving",   "real",    "measure",   "quantitative", None),
            ("hub_rank",     "integer", "measure",   "quantitative", None),
        ],
        "calc_fields": [
            {
                "name": "Current Scenario ID",
                "caption": "Current Scenario ID",
                "datatype": "string",
                "formula": (
                    "\"S\" + RIGHT(\"000\" + STR(\n"
                    "  (IIF(NOT [Parameters].[p_con_weather],  1, 0)\n"
                    "  + IIF(NOT [Parameters].[p_con_robot],   2, 0)\n"
                    "  + IIF(NOT [Parameters].[p_con_noise],   4, 0)\n"
                    "  + IIF(NOT [Parameters].[p_con_obstacle],8, 0)\n"
                    "  + IIF(NOT [Parameters].[p_con_airspace],16, 0))\n"
                    "  * 2\n"
                    "  + IIF([Parameters].[p_airspace_mode] = \"strict\", 1, 0)\n"
                    "  + 1\n"
                    "), 3)"
                ),
            },
            {
                "name": "Is Active Scenario",
                "caption": "Is Active Scenario",
                "datatype": "boolean",
                "formula": "[scenario_id] = [Current Scenario ID]",
            },
            {
                "name": "CO2 Ton",
                "caption": "CO2 Ton",
                "datatype": "real",
                "formula": "SUM([co2_saving]) / 1000000.0",
            },
            {
                "name": "Drone Faster Flag",
                "caption": "Drone Faster Flag",
                "datatype": "integer",
                "formula": "IIF([time_saving] > 0, 1, 0)",
            },
        ],
    },
    "scenario_lookup": {
        "caption": "Scenario Lookup",
        "file": "scenario_lookup.csv",
        "fields": [
            ("scenario_id",   "string",  "dimension", "nominal", None),
            ("use_airspace",  "boolean", "dimension", "nominal", None),
            ("use_obstacle",  "boolean", "dimension", "nominal", None),
            ("use_noise",     "boolean", "dimension", "nominal", None),
            ("use_robot",     "boolean", "dimension", "nominal", None),
            ("use_weather",   "boolean", "dimension", "nominal", None),
            ("airspace_mode", "string",  "dimension", "nominal", None),
        ],
        "calc_fields": [],
    },
    "charts_bundle": {
        "caption": "Charts Bundle",
        "file": "charts_bundle.csv",
        "fields": [
            ("chart_id",  "string",  "dimension", "nominal",      None),
            ("rank",      "integer", "measure",   "quantitative", None),
            ("label",     "string",  "dimension", "nominal",      None),
            ("GU_NM",     "string",  "dimension", "nominal",      None),
            ("value1",    "real",    "measure",   "quantitative", None),
            ("value2",    "real",    "measure",   "quantitative", None),
            ("value3",    "real",    "measure",   "quantitative", None),
            ("category",  "string",  "dimension", "nominal",      None),
        ],
        "calc_fields": [],
    },
}

# ── Parameters ─────────────────────────────────────────────────────────────
PARAMS = [
    # (name, caption, datatype, domain_type, default_value)
    ("p_demand_b2b",    "B2B 기업수요",  "boolean", "boolean", "true"),
    ("p_demand_b2c",    "B2C 소비수요",  "boolean", "boolean", "true"),
    ("p_demand_cv",     "상권활력지수",  "boolean", "boolean", "true"),
    ("p_con_airspace",  "공역",          "boolean", "boolean", "true"),
    ("p_con_obstacle",  "장애물",    "boolean", "boolean", "true"),
    ("p_con_noise",     "소음",          "boolean", "boolean", "true"),
    ("p_con_robot",     "로봇접근","boolean","boolean", "true"),
    ("p_con_weather",   "기상",          "boolean", "boolean", "true"),
    ("p_airspace_mode", "공역 모드", "string",  "list",    "approval"),
]
# Members for string list param
AIRSPACE_MODE_MEMBERS = ["approval", "strict"]

# ── Placeholder worksheet names ─────────────────────────────────────────────
SHEETS = [
    "Map - H3 Grid",
    "Map - Hubs",
    "Map - Routes",
    "Hub Roster",
    "KPI - Hubs",
    "KPI - Routes",
    "KPI - Time Saving",
    "KPI - CO2",
    "KPI - Weather",
    "KPI - Drone Faster",
    "KPI - ESG",
    "Chart - Dong Top15",
    "Chart - Hourly",
    "Chart - Mode Compare",
    "Chart - ESG",
    "Chart - Drone Zone Pct",
    "Chart - B2B",
    "Chart - B2C",
    "Chart - Robot",
]

# ── Build XML ───────────────────────────────────────────────────────────────
# Native Tableau 2026.1 structure confirmed from saving a fresh blank workbook.
# Critical requirements (missing any of these causes error 501CF476):
#   1. original-version='18.1' on <workbook> element
#   2. Exact document-format-change-manifest entries from native workbook
#   3. <windows> section with a <window> entry for EVERY worksheet
#   4. <datasources> child inside each worksheet's <view> element
#   5. Parameters datasource: hasconnection='false', version='18.1', value= not default-value=

# Pre-generate UUIDs for all sheets so we can reference them in both
# <worksheets> and <windows> sections.
# Each sheet gets two UUIDs: one for the worksheet <simple-id>, one for the window <simple-id>.
sheet_uuids = {}   # sheet_name -> (table_uuid, window_uuid)
for sheet_name in SHEETS:
    sheet_uuids[sheet_name] = (
        str(uuid.uuid4()).upper(),
        str(uuid.uuid4()).upper(),
    )

lines = []
lines.append("<?xml version='1.0' encoding='utf-8' ?>")
lines.append("<workbook original-version='18.1'")
lines.append("          source-build='2026.1.1 (20261.26.0410.0924)'")
lines.append("          source-platform='win'")
lines.append("          version='18.1'")
lines.append("          xmlns:user='http://www.tableausoftware.com/xml/user'>")
lines.append("  <document-format-change-manifest>")
lines.append("    <AnimationOnByDefault />")
lines.append("    <MarkAnimation />")
# ObjectModel entries are required when data sources are connected.
# Without them Tableau uses the legacy schema which requires dim-percentage
# and measure-percentage on <layout> elements (error D2E8DA72).
lines.append("    <ObjectModelEncapsulateLegacy />")
lines.append("    <ObjectModelTableType />")
lines.append("    <SchemaViewerObjectModel />")
lines.append("    <SheetIdentifierTracking />")
lines.append("    <WindowsPersistSimpleIdentifiers />")
lines.append("  </document-format-change-manifest>")
lines.append("  <preferences>")
lines.append("    <preference name='ui.encoding.shelf.height' value='24' />")
lines.append("    <preference name='ui.shelf.height' value='26' />")
lines.append("  </preferences>")
lines.append("  <datasources>")

# Parameters datasource — correct Tableau 2026.1 format
lines.append("    <datasource hasconnection='false' inline='true' name='Parameters' version='18.1'>")
lines.append("      <aliases enabled='yes' />")
for pname, pcaption, pdt, pdomain, pdefault in PARAMS:
    if pdomain == "list":
        # String list parameter: value must be quoted (&quot;approval&quot;)
        val_esc = esc(f'"{pdefault}"')   # → &quot;approval&quot;
        lines.append(f"      <column caption='{esc(pcaption)}' datatype='{pdt}'")
        lines.append(f"              name='[{pname}]' param-domain-type='list' role='measure' type='nominal' value='{val_esc}'>")
        lines.append(f"        <calculation class='tableau' formula='{val_esc}' />")
        lines.append("        <members>")
        for m in AIRSPACE_MODE_MEMBERS:
            m_val = esc(f'"{m}"')        # → &quot;approval&quot;
            lines.append(f"          <member value='{m_val}' />")
        lines.append("        </members>")
        lines.append("      </column>")
    else:
        # Boolean parameter: use param-domain-type='list' with true/false members
        # (Tableau 2026.1 only accepts 'list' and 'range' for param-domain-type)
        lines.append(f"      <column caption='{esc(pcaption)}' datatype='{pdt}'")
        lines.append(f"              name='[{pname}]' param-domain-type='list' role='measure' type='nominal' value='{pdefault}'>")
        lines.append(f"        <calculation class='tableau' formula='{pdefault}' />")
        lines.append(f"        <members>")
        lines.append(f"          <member value='true' />")
        lines.append(f"          <member value='false' />")
        lines.append(f"        </members>")
        lines.append(f"      </column>")
lines.append("    </datasource>")

# Data source connections
# Correct Tableau 2026.1 format for CSV files (from PerformanceRecording_new.twb):
#   class='federated' wraps a named-connection with class='textscan'
#   relation uses type='table' (NOT type='text') to avoid "Custom SQL" warning
#   <columns> inside relation define schema with ordinal positions
for ds_key, ds_info in DS.items():
    name = ds_name(ds_key)
    caption = ds_info["caption"]
    fname  = ds_info["file"]
    # Native Tableau uses forward slashes and minimal connection attributes
    fdir_fwd = str(DATA_DIR).replace("\\", "/")   # forward slashes required
    leaf_name = f"textscan.{hashlib.md5(ds_key.encode()).hexdigest()[:32]}"  # matches native format
    rel_nm = fname           # e.g. grid_master.csv (Tableau uses .csv in relation name)
    tbl    = esc(f"[{fname.replace('.csv', '#csv')}]")   # e.g. [grid_master#csv]

    lines.append(f"    <datasource caption='{esc(caption)}' inline='true' name='{name}' version='18.1'>")
    lines.append(f"      <connection class='federated'>")
    lines.append(f"        <named-connections>")
    # caption on named-connection matches native Tableau format
    lines.append(f"          <named-connection caption='{ds_key}' name='{leaf_name}'>")
    # Native uses only class, directory, filename, password, server (no extra attrs)
    lines.append(f"            <connection class='textscan' directory='{esc(fdir_fwd)}'")
    lines.append(f"                        filename='{esc(fname)}' password='' server='' />")
    lines.append(f"          </named-connection>")
    lines.append(f"        </named-connections>")
    lines.append(f"        <relation connection='{leaf_name}' name='{esc(rel_nm)}' table='{tbl}' type='table'>")
    lines.append(f"          <columns character-set='UTF-8' header='yes' locale='ko_KR' separator=','>")
    for i, (col_name, col_dt, _, _, _) in enumerate(ds_info["fields"]):
        lines.append(f"            <column datatype='{col_dt}' name='{esc(col_name)}' ordinal='{i}' />")
    lines.append(f"          </columns>")
    lines.append(f"        </relation>")
    lines.append(f"      </connection>")
    lines.append(f"      <aliases enabled='yes' />")

    # Field declarations
    for fname, fdt, frole, ftype, sem in ds_info["fields"]:
        agg = "Avg" if fdt == "real" else ("Count" if fdt == "string" else "Sum")
        if frole == "dimension":
            agg = "Count" if ftype in ("nominal", "ordinal") else "Min"
        sem_attr = f" semantic-role='{esc(sem)}'" if sem else ""
        lines.append(f"      <column aggregation='{agg}' datatype='{fdt}' name='[{fname}]'")
        lines.append(f"              role='{frole}' type='{ftype}'{sem_attr} />")

    # Calculated fields
    for cf in ds_info["calc_fields"]:
        cf_type = "quantitative" if cf["datatype"] in ("real",) else ("nominal" if cf["datatype"] == "boolean" else "nominal")
        cf_role = "measure" if cf["datatype"] in ("real", "integer") else "dimension"
        formula_esc = esc(cf["formula"])
        cf_caption = esc(cf["caption"])
        cf_dt = cf["datatype"]
        cf_nm = cf["name"]
        lines.append(f"      <column caption='{cf_caption}' datatype='{cf_dt}'")
        lines.append(f"              name='[{cf_nm}]' role='{cf_role}' type='{cf_type}'>")
        lines.append(f"        <calculation class='tableau' formula='{formula_esc}' />")
        lines.append(f"      </column>")

    lines.append(f"      <layout dim-ordering='alphabetic' measure-ordering='alphabetic' show-structure='true' />")
    lines.append(f"    </datasource>")

lines.append("  </datasources>")
lines.append("  <mapsources><mapsource name='Tableau' /></mapsources>")

# Empty worksheets — <view> must have <datasources> child (confirmed from native workbook)
lines.append("  <worksheets>")
for sheet_name in SHEETS:
    ds_key_for_sheet = (
        "grid_master"     if "H3" in sheet_name or "Weather" in sheet_name
        else "scenario_hubs"   if "Hub" in sheet_name
        else "scenario_routes" if "Route" in sheet_name or "Time" in sheet_name
                                   or "CO2" in sheet_name or "Drone Faster" in sheet_name
        else "charts_bundle"   if "Chart" in sheet_name or "ESG" in sheet_name
        else "grid_master"
    )
    ds_caption = DS.get(ds_key_for_sheet, {}).get("caption", "Grid Master")
    ds_n = ds_name(ds_key_for_sheet)
    table_uuid, _ = sheet_uuids[sheet_name]
    lines.append(f"    <worksheet name='{esc(sheet_name)}'>")
    lines.append(f"      <table>")
    lines.append(f"        <view>")
    lines.append(f"          <datasources>")
    lines.append(f"            <datasource caption='{esc(ds_caption)}' name='{ds_n}' />")
    lines.append(f"          </datasources>")
    lines.append(f"          <aggregation value='true' />")
    lines.append(f"        </view>")
    lines.append(f"        <style />")
    lines.append(f"        <panes>")
    lines.append(f"          <pane selection-relaxation-option='selection-relaxation-allow'>")
    lines.append(f"            <view><breakdown value='auto' /></view>")
    lines.append(f"            <mark class='Automatic' />")
    lines.append(f"          </pane>")
    lines.append(f"        </panes>")
    lines.append(f"        <rows />")
    lines.append(f"        <cols />")
    lines.append(f"      </table>")
    lines.append(f"      <simple-id uuid='{{{table_uuid}}}' />")
    lines.append(f"    </worksheet>")
lines.append("  </worksheets>")

# ── Windows section ─────────────────────────────────────────────────────────
# CRITICAL: Tableau 2026.1 requires a <window> entry for every worksheet.
# Without this section, Tableau throws internal error 501CF476 on open.
# Structure confirmed from native blank workbook saved by Tableau itself.
lines.append("  <windows saved-dpi-scale-factor='1.25'>")
for i, sheet_name in enumerate(SHEETS):
    _, window_uuid = sheet_uuids[sheet_name]
    # First sheet is maximized and active; rest are normal
    maximized_attr = " maximized='true'" if i == 0 else ""
    lines.append(f"    <window class='worksheet'{maximized_attr} name='{esc(sheet_name)}'>")
    lines.append(f"      <cards>")
    lines.append(f"        <edge name='left'>")
    lines.append(f"          <strip size='160'>")
    lines.append(f"            <card type='pages' />")
    lines.append(f"            <card type='filters' />")
    lines.append(f"            <card type='marks' />")
    lines.append(f"          </strip>")
    lines.append(f"        </edge>")
    lines.append(f"        <edge name='top'>")
    lines.append(f"          <strip size='2147483647'>")
    lines.append(f"            <card type='columns' />")
    lines.append(f"          </strip>")
    lines.append(f"          <strip size='2147483647'>")
    lines.append(f"            <card type='rows' />")
    lines.append(f"          </strip>")
    lines.append(f"          <strip size='30'>")
    lines.append(f"            <card type='title' />")
    lines.append(f"          </strip>")
    lines.append(f"        </edge>")
    lines.append(f"      </cards>")
    lines.append(f"      <simple-id uuid='{{{window_uuid}}}' />")
    lines.append(f"    </window>")
lines.append("  </windows>")
lines.append("</workbook>")

xml = "\n".join(lines)
OUT_TWB.write_text(xml, encoding="utf-8")
print(f"Written: {OUT_TWB}")
print(f"Size: {OUT_TWB.stat().st_size // 1024} KB")
print(f"Worksheets: {len(SHEETS)}")
print(f"Data sources: {len(DS) + 1} (including Parameters)")
