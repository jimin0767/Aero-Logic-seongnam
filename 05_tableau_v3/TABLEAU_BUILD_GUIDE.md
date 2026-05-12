# Tableau Dashboard v3 - Build Guide

## Prerequisites

1. **Tableau Desktop** installed (2024.x or later)
2. **Noto Sans KR** font installed from [Google Fonts](https://fonts.google.com/specimen/Noto+Sans+KR)
3. Run `prepare_tableau_data.py` first to generate the 5 CSVs in `data/`

---

## Phase 1: Connect Data Sources

Open Tableau Desktop. For each CSV, do: **Data > New Data Source > Text file**

| # | File | Geographic Roles |
|---|------|-----------------|
| 1 | `data/grid_master.csv` | lat = Latitude, lon = Longitude |
| 2 | `data/scenario_hubs.csv` | lat = Latitude, lon = Longitude |
| 3 | `data/scenario_routes.csv` | route_lat = Latitude, route_lon = Longitude |
| 4 | `data/scenario_lookup.csv` | *(none)* |
| 5 | `data/charts_bundle.csv` | *(none)* |

**Important:** Each CSV is a **separate** data source. Do NOT join them.

To set geographic roles: Right-click the field > Geographic Role > Latitude/Longitude.

---

## Phase 2: Create Parameters (9 total)

Go to any data source. Right-click in the Data pane > **Create Parameter...**

Parameters are global (shared across all data sources).

| Parameter Name | Display Name | Data Type | Allowable Values | Default |
|----------------|-------------|-----------|-----------------|---------|
| `p_demand_b2b` | B2B | Boolean | — | True |
| `p_demand_b2c` | B2C | Boolean | — | True |
| `p_demand_cv` | CV | Boolean | — | True |
| `p_con_airspace` | Airspace | Boolean | — | True |
| `p_con_obstacle` | Obstacle | Boolean | — | True |
| `p_con_noise` | Noise | Boolean | — | True |
| `p_con_robot` | Robot | Boolean | — | True |
| `p_con_weather` | Weather | Boolean | — | True |
| `p_airspace_mode` | Airspace Mode | String | List: `approval`, `strict` | `approval` |

---

## Phase 3: Create Calculated Fields

### 3A: On `grid_master` data source

Create these calculated fields (right-click in Data pane > Create Calculated Field):

#### `[Demand Score]`
```
IIF(
  INT([p_demand_b2b]) + INT([p_demand_b2c]) + INT([p_demand_cv]) = 0,
  1.0,
  (IIF([p_demand_b2b], [demand_b2b], 0)
  + IIF([p_demand_b2c], [demand_b2c], 0)
  + IIF([p_demand_cv], [demand_cv], 0))
  / (INT([p_demand_b2b]) + INT([p_demand_b2c]) + INT([p_demand_cv]))
)
```

#### `[Constraint Score]`
```
(IIF([p_con_airspace], [score_airspace], 1.0)
+ IIF([p_con_obstacle], [score_obstacle], 1.0)
+ IIF([p_con_noise], [score_noise], 1.0)
+ IIF([p_con_robot], [score_robot], 1.0)
+ IIF([p_con_weather], [score_weather], 1.0)) / 5
```

#### `[Final Score]`
```
[Demand Score] * [Constraint Score]
```

#### `[Is Strict Excluded]`
```
[hard_exclusion] AND [p_con_airspace] AND [p_airspace_mode] = "strict"
```

### 3B: On `scenario_hubs` data source

#### `[Current Scenario ID]`
```
"S" + RIGHT("000" + STR(
  (IIF(NOT [p_con_weather], 1, 0)
  + IIF(NOT [p_con_robot], 2, 0)
  + IIF(NOT [p_con_noise], 4, 0)
  + IIF(NOT [p_con_obstacle], 8, 0)
  + IIF(NOT [p_con_airspace], 16, 0))
  * 2
  + IIF([p_airspace_mode] = "strict", 1, 0)
  + 1
), 3)
```

#### `[Is Active Scenario]`
```
[scenario_id] = [Current Scenario ID]
```

### 3C: On `scenario_routes` data source

Create the **exact same** two calculated fields:

#### `[Current Scenario ID]`
*(same formula as 3B)*

#### `[Is Active Scenario]`
*(same formula as 3B)*

---

## Phase 4: Build Sheets

### Sheet 1: "Map - H3 Grid" (data source: `grid_master`)

1. Drag `lon` to Columns, `lat` to Rows (both as AVG, continuous)
2. Drag `h3_index` to Detail
3. Change Mark type to **Circle**
4. Drag `[Final Score]` to Color
5. Edit color: Custom Diverging palette
   - 3 stops: Red `#D32F2F` at 0.0, Yellow `#FDD835` at 0.5, Green `#4CAF50` at 1.0
   - Range: Fixed, Start: 0, End: 1
6. Set Size to a small fixed value (click Size > adjust slider left)
7. Add to Tooltip: `ADM_NM`, `GU_NM`, `demand_b2b`, `demand_b2c`, `demand_cv`, `[Demand Score]`, `[Constraint Score]`, `[Final Score]`, `delivery_zone`
8. Edit Tooltip:
```
<b><ADM_NM> (<GU_NM>)</b>
B2B: <demand_b2b>  B2C: <demand_b2c>
CV: <demand_cv>
Demand: <ATTR(Demand Score)>
Constraint: <ATTR(Constraint Score)>
Final: <b><ATTR(Final Score)></b>
Zone: <delivery_zone>
```
9. Map > Background Maps > Dark
10. Map > Map Layers > Washout: 80%

### Sheet 2: "Map - Hubs" (data source: `scenario_hubs`)

1. Drag `lon` to Columns, `lat` to Rows (both as AVG, continuous)
2. Drag `lot_id` to Detail
3. Mark type: **Circle**
4. Drag `delivery_zone` to Color
   - Assign: Blue `#2196F3`, Purple `#9C27B0`, Grey `#78909C`
5. Drag `rank` to Label
6. Set Size to a large fixed value
7. Drag `[Is Active Scenario]` to Filters > select True only
8. Add to Tooltip: `lot_name`, `gu`, `dong`, `cover_n`, `cover_ds`, `delivery_zone`
9. Map > Background Maps > Dark, Washout: 80%

### Sheet 3: "Map - Routes" (data source: `scenario_routes`)

1. Drag `route_lon` to Columns, `route_lat` to Rows (both as AVG, continuous)
2. Drag `route_id` to Detail
3. Mark type: **Line**
4. Drag `path_order` to **Path** (as Dimension)
5. Drag `approval` to Color
   - True: Orange `#FFB74D`, False: Green `#53D769`
6. Drag `[Is Active Scenario]` to Filters > select True only
7. Set opacity to ~55%
8. Map > Background Maps > Dark, Washout: 80%

### Sheet 4: "Hub Roster" (data source: `scenario_hubs`)

1. Drag `lot_name` to Rows, `cover_ds` (SUM) to Columns
2. Sort `lot_name` by `rank` ascending
3. Drag `delivery_zone` to Color (same color assignment as Sheet 2)
4. Drag `rank`, `dong`, `cover_n` to Label
5. Drag `[Is Active Scenario]` to Filters > True only

### Sheets 5-11: KPI Cards (7 sheets)

For each KPI, create a sheet with Mark type = **Text**, showing a single big number.

| Sheet | Data Source | Measure | Filter |
|-------|-----------|---------|--------|
| KPI: Hubs | scenario_hubs | `COUNTD([lot_id])` | [Is Active Scenario]=True |
| KPI: Routes | scenario_routes | `COUNTD([route_id])` | [Is Active Scenario]=True |
| KPI: Time Saving | scenario_routes | `MEDIAN([time_saving])` | [Is Active Scenario]=True, path_order=1 |
| KPI: CO2 | scenario_routes | `SUM([co2_saving])/1000000` | [Is Active Scenario]=True, path_order=1 |
| KPI: Weather | grid_master | `AVG([score_weather])*100` | *(none)* |
| KPI: Drone Faster | scenario_routes | See formula below | [Is Active Scenario]=True, path_order=1 |
| KPI: ESG | charts_bundle | `AVG([value1])` | chart_id = "esg" |

**KPI: Drone Faster calculated field** (on scenario_routes):
```
SUM(IIF([time_saving] > 0, 1, 0)) / COUNTD([route_id]) * 100
```

**Important for route KPIs:** Filter `path_order = 1` to avoid double-counting (each route has 2 rows).

Format each KPI:
- Text size: 22-28pt, Bold, Color: `#4FC3F7`
- Add a subtitle with the unit (text object)
- Remove all headers, axes, gridlines

### Sheets 12-19: Charts (8 sheets, all from `charts_bundle`)

For each chart, first add a filter: `chart_id` = [specific value].

| # | Sheet Name | chart_id | Type | Rows/Columns | Color |
|---|-----------|----------|------|-------------|-------|
| 12 | Dong Top 15 | dong_top15 | Horiz. bar | Rows: `label` (sorted by `rank`), Cols: `value1` | `GU_NM` or fixed `#4FC3F7` |
| 13 | Hourly Pattern | hourly | Vertical bar | Cols: `label`, Rows: `value1` | `category` (period) |
| 14 | Mode Compare | mode_compare | Grouped bar | Cols: `label`, Rows: `value1` + `value2` | Measure Names |
| 15 | ESG Index | esg | Horiz. bar | Rows: `label` (sorted by `rank`), Cols: `value1` | Fixed `#53D769` |
| 16 | Drone Zone % | dong_zone_pct | Horiz. bar | Rows: `label` (sorted by `rank`), Cols: `value1` | Fixed `#53D769` |
| 17 | B2B Top 15 | b2b | Horiz. bar | Rows: `label` (sorted by `rank`), Cols: `value1` | `GU_NM` or fixed `#FF6B35` |
| 18 | B2C Top 15 | b2c | Horiz. bar | Rows: `label` (sorted by `rank`), Cols: `value1` | `GU_NM` or fixed `#A855F7` |
| 19 | Robot Top 15 | robot | Horiz. bar | Rows: `label` (sorted by `rank`), Cols: `value1` | `GU_NM` or fixed `#42A5F5` |

**Mode Compare special setup:**
1. Drag `value1` to Columns (rename: "Drone")
2. Drag `value2` to Columns (rename: "Motorcycle")  
3. Select both pills > right-click > Dual Axis > Synchronize Axis
4. Or: use Measure Names/Measure Values with filter on value1, value2

---

## Phase 5: Assemble Dashboard 1 - "Map & Controls" (1600 x 900)

1. **New Dashboard** > Size: Fixed 1600 x 900
2. **Layout:**
   ```
   +-------------------------------------------------------------------+
   | Text: "Seongnam Drone/Robot Hub Analysis" (hero banner)   [60px]  |
   +-------------------------------------------------------------------+
   | KPI1 | KPI2 | KPI3 | KPI4 | KPI5 | KPI6 | KPI7         [80px]   |
   +----------+--------------------------------------------------------+
   | Sidebar  | Map - H3 Grid (tiled, fills remaining space)           |
   | (300px)  |                                                        |
   |          |                                                        |
   +----------+--------------------------------------------------------+
   ```

3. **Sidebar contents** (vertical layout container, 300px wide):
   - Text object: "Demand Layers"
   - Show parameters: `p_demand_b2b`, `p_demand_b2c`, `p_demand_cv`
   - Text object: "Constraint Layers"
   - Show parameters: `p_con_airspace`, `p_con_obstacle`, `p_con_noise`, `p_con_robot`, `p_con_weather`
   - Show parameter: `p_airspace_mode`
   - Text object: "Final Score = Demand x Constraint"
   - Hub Roster sheet (Sheet 4)

4. **Map overlays** (optional, for advanced users):
   - Place "Map - Hubs" as floating over the H3 grid map
   - Place "Map - Routes" as floating over the H3 grid map
   - Set both floating sheets to have transparent backgrounds
   - Match their position and size exactly to the H3 grid map
   - *Alternative:* Skip overlays and rely on the Hub Roster + KPIs for hub/route info

5. **Show parameter controls**: Right-click each parameter > Show Parameter Control

---

## Phase 6: Assemble Dashboard 2 - "Charts" (1600 x 1200)

1. **New Dashboard** > Size: Fixed 1600 x 1200
2. **Layout** (3 rows x 3 columns):
   ```
   +---------------------+---------------------+---------------------+
   | Dong Top 15         | Hourly Pattern      | Mode Compare        |
   | (Sheet 12)          | (Sheet 13)          | (Sheet 14)          |
   +---------------------+---------------------+---------------------+
   | ESG Index           | Drone Zone %        | B2B Top 15          |
   | (Sheet 15)          | (Sheet 16)          | (Sheet 17)          |
   +---------------------+---------------------+---------------------+
   | B2C Top 15          | Robot Top 15        | (empty or text)     |
   | (Sheet 18)          | (Sheet 19)          |                     |
   +---------------------+---------------------+---------------------+
   ```

---

## Phase 7: Apply Dark Theme

### Dashboard Background
- Dashboard > Format > Shading: `#0F0F1A`

### Each Sheet Container
- Select container > Layout pane > Background: `#16213E`
- Border: `#0F3460` 1px

### Sheet Formatting (apply to every sheet)
1. Format > Shading > Worksheet: `#16213E`, Pane: `#1A1A2E`
2. Format > Font > All: `Noto Sans KR`, Color: `#E0E0E0`
3. Format > Lines > Grid Lines: `#1A3A5C`
4. Format > Borders > Row/Column Divider: None or `#1A3A5C`

### KPI Cards
- Value font: 26pt Bold, Color: `#4FC3F7`
- Label font: 11pt, Color: `#AABBCC`

### Map Settings
- Background Maps: Dark
- Map Layers > Washout: 80%

---

## Phase 8: Verification

### Data Check
- [ ] H3 grid shows ~1,947 circles on the map
- [ ] All circles are colored on a red-yellow-green gradient
- [ ] Default scenario (S001) shows 6 hubs and 353 routes

### Toggle Tests
1. **Demand toggles:**
   - [ ] Turn OFF all 3 demand toggles -> all cells shift greener (demand=1.0, only constraints matter)
   - [ ] Turn ON only B2B -> cells with low B2B score go red
   
2. **Constraint toggles:**
   - [ ] Turn OFF all 5 constraint toggles -> cells colored purely by demand score
   - [ ] Turn ON only airspace -> many cells go red (airspace restrictions)
   
3. **Airspace mode:**
   - [ ] Switch to "strict" -> cells with hard_exclusion go grey/low

### Scenario Tests
- [ ] All ON + approval = S001 (6 hubs, 353 routes)
- [ ] All ON + strict = S002
- [ ] All OFF + approval = S063
- [ ] Weather OFF only + approval = S003

### Visual Match
- [ ] Map colors match the HTML dashboard approximately
- [ ] Hub markers are blue/purple/grey based on delivery_zone
- [ ] KPI numbers match HTML dashboard defaults

---

## Scenario ID Reference

The bit-pattern formula maps parameter state to scenario ID:

```
S + zero_pad_3(
  (NOT weather)*1 + (NOT robot)*2 + (NOT noise)*4 + (NOT obstacle)*8 + (NOT airspace)*16
  ) * 2
  + (strict ? 1 : 0)
  + 1
)
```

Examples:
| Parameters | Scenario |
|-----------|----------|
| All ON, approval | S001 |
| All ON, strict | S002 |
| Weather OFF, rest ON, approval | S003 |
| Robot OFF, rest ON, approval | S005 |
| All OFF, approval | S063 |
| All OFF, strict | S064 |

---

## File Summary

| File | Rows | Size | Used By |
|------|------|------|---------|
| grid_master.csv | 1,947 | 490 KB | Map, KPI: Weather |
| scenario_hubs.csv | 384 | 65 KB | Hub markers, Hub roster, KPI: Hubs |
| scenario_routes.csv | 37,436 | 3,045 KB | Route lines, KPI: Routes/Time/CO2/Drone% |
| scenario_lookup.csv | 64 | 3 KB | Reference only |
| charts_bundle.csv | 162 | 8 KB | All 8 chart sheets, KPI: ESG |
