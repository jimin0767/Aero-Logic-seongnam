"""
성남시 드론·로봇 배송 거점 최적화 — Tableau Workbook Builder v2
=============================================================
Programmatically constructs a .twbx with embedded Hyper extracts.

Usage:
  python build_tableau_workbook.py                                    # Build only
  python build_tableau_workbook.py --publish PAT_NAME PAT_SECRET      # Build + publish
"""
import argparse, uuid, zipfile, time
from pathlib import Path
import pandas as pd

BASE = Path(__file__).parent
DATA_DIR = BASE / "tableau_data"
HYPER_DIR = BASE / "hyper_extracts"
OUTPUT_DIR = BASE / "workbook_output"
OUTPUT_DIR.mkdir(exist_ok=True)

SERVER_URL = "https://prod-kr-a.online.tableau.com"
SITE_NAME = "jimin076721-be93e49158"
PROJECT_NAME = "성남시_드론배송_거점최적화"


def uid():
    return uuid.uuid4().hex[:20]

def muuid():
    return "{" + str(uuid.uuid4()).upper() + "}"


def get_col_info(df):
    cols = []
    for c in df.columns:
        dt = df[c].dtype
        if pd.api.types.is_integer_dtype(dt):
            cols.append((c, "integer", "measure", "quantitative", "Sum"))
        elif pd.api.types.is_float_dtype(dt):
            cols.append((c, "real", "measure", "quantitative", "Sum"))
        else:
            cols.append((c, "string", "dimension", "nominal", "Count"))
    return cols


# ═══════════════════════════════════════════════════════════════
# Datasource XML
# ═══════════════════════════════════════════════════════════════

def build_datasource(caption, hyper_file, table_name, df):
    ds_id = f"federated.{uid()}"
    conn_id = f"hyper.{uid()}"
    cols = get_col_info(df)

    col_xml = ""
    for name, datatype, role, typ, agg in cols:
        extra = ""
        if name == "lat":
            extra = " semantic-role='[Geographical].[Latitude]'"
            agg = "Avg"
        elif name == "lon":
            extra = " semantic-role='[Geographical].[Longitude]'"
            agg = "Avg"
        col_xml += f"      <column aggregation='{agg}' datatype='{datatype}' name='[{name}]' role='{role}' type='{typ}'{extra} />\n"

    meta_xml = ""
    for i, (name, datatype, role, typ, agg) in enumerate(cols):
        rtype = {"string": "129", "integer": "20", "real": "5"}[datatype]
        mc = "column" if role == "dimension" else "measure"
        meta_xml += f"""          <metadata-record class='{mc}'>
            <remote-name>{name}</remote-name>
            <remote-type>{rtype}</remote-type>
            <local-name>[{name}]</local-name>
            <parent-name>[Extract].[{table_name}]</parent-name>
            <remote-alias>{name}</remote-alias>
            <ordinal>{i}</ordinal>
            <local-type>{datatype}</local-type>
            <aggregation>{agg}</aggregation>
            <contains-null>true</contains-null>
          </metadata-record>
"""

    xml = f"""    <datasource caption='{caption}' inline='true' name='{ds_id}' version='18.1'>
      <connection class='federated'>
        <named-connections>
          <named-connection caption='{table_name}' name='{conn_id}'>
            <connection authentication='no' class='hyper' dbname='Data/Extracts/{hyper_file}' default-settings='yes' sslmode='' username='' />
          </named-connection>
        </named-connections>
        <relation connection='{conn_id}' name='Extract' table='[Extract].[{table_name}]' type='table' />
      </connection>
      <aliases enabled='yes' />
{col_xml}      <layout dim-ordering='alphabetic' measure-ordering='alphabetic' show-structure='true' />
    </datasource>
"""
    return ds_id, xml


# ═══════════════════════════════════════════════════════════════
# Worksheet XML — each one kept close to the minimal working format
# ═══════════════════════════════════════════════════════════════

def ws_map(ds):
    """Map: hex grid colored by composite_score."""
    return f"""    <worksheet name='거점 적합도 지도'>
      <table>
        <view>
          <datasources>
            <datasource caption='Grid Scores' name='{ds}' />
          </datasources>
          <mapsources>
            <mapsource name='Tableau' />
          </mapsources>
          <datasource-dependencies datasource='{ds}'>
            <column-instance column='[lat]' derivation='Avg' name='[avg:lat:qk]' pivot='key' type='quantitative' />
            <column-instance column='[lon]' derivation='Avg' name='[avg:lon:qk]' pivot='key' type='quantitative' />
            <column-instance column='[composite_score]' derivation='Avg' name='[avg:composite_score:qk]' pivot='key' type='quantitative' />
            <column aggregation='Avg' datatype='real' name='[lat]' role='measure' semantic-role='[Geographical].[Latitude]' type='quantitative' />
            <column aggregation='Avg' datatype='real' name='[lon]' role='measure' semantic-role='[Geographical].[Longitude]' type='quantitative' />
            <column aggregation='Sum' datatype='real' name='[composite_score]' role='measure' type='quantitative' />
            <column aggregation='Count' datatype='string' name='[h3_index]' role='dimension' type='nominal' />
            <column-instance column='[h3_index]' derivation='None' name='[none:h3_index:nk]' pivot='key' type='nominal' />
            <column aggregation='Count' datatype='string' name='[ADM_NM]' role='dimension' type='nominal' />
            <column-instance column='[ADM_NM]' derivation='None' name='[none:ADM_NM:nk]' pivot='key' type='nominal' />
          </datasource-dependencies>
          <aggregation value='true' />
        </view>
        <style>
          <style-rule element='map'>
            <format attr='washout' value='0.0' />
          </style-rule>
        </style>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='Circle' />
            <encodings>
              <color column='[{ds}].[avg:composite_score:qk]' />
              <detail column='[{ds}].[none:ADM_NM:nk]' />
            </encodings>
          </pane>
        </panes>
        <rows>([{ds}].[none:h3_index:nk] * [{ds}].[avg:lat:qk])</rows>
        <cols>[{ds}].[avg:lon:qk]</cols>
      </table>
      <simple-id uuid='{muuid()}' />
    </worksheet>
"""


def ws_bar(ds):
    """Bar chart: dong ranking by avg_composite."""
    return f"""    <worksheet name='동별 종합점수'>
      <table>
        <view>
          <datasources>
            <datasource caption='Dong Summary' name='{ds}' />
          </datasources>
          <datasource-dependencies datasource='{ds}'>
            <column aggregation='Count' datatype='string' name='[ADM_NM]' role='dimension' type='nominal' />
            <column-instance column='[ADM_NM]' derivation='None' name='[none:ADM_NM:nk]' pivot='key' type='nominal' />
            <column aggregation='Count' datatype='string' name='[GU_NM]' role='dimension' type='nominal' />
            <column-instance column='[GU_NM]' derivation='None' name='[none:GU_NM:nk]' pivot='key' type='nominal' />
            <column aggregation='Sum' datatype='real' name='[avg_composite]' role='measure' type='quantitative' />
            <column-instance column='[avg_composite]' derivation='Sum' name='[sum:avg_composite:qk]' pivot='key' type='quantitative' />
          </datasource-dependencies>
          <aggregation value='true' />
        </view>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='Bar' />
            <encodings>
              <color column='[{ds}].[none:GU_NM:nk]' />
            </encodings>
          </pane>
        </panes>
        <rows>[{ds}].[none:ADM_NM:nk]</rows>
        <cols>[{ds}].[sum:avg_composite:qk]</cols>
      </table>
      <simple-id uuid='{muuid()}' />
    </worksheet>
"""


def ws_demand(ds):
    """Area chart: hourly delivery demand."""
    return f"""    <worksheet name='시간대별 배송수요'>
      <table>
        <view>
          <datasources>
            <datasource caption='Hourly Demand' name='{ds}' />
          </datasources>
          <datasource-dependencies datasource='{ds}'>
            <column aggregation='Sum' datatype='integer' name='[hour]' role='measure' type='quantitative' />
            <column-instance column='[hour]' derivation='None' name='[none:hour:qk]' pivot='key' type='quantitative' />
            <column aggregation='Sum' datatype='integer' name='[total_del_cnt]' role='measure' type='quantitative' />
            <column-instance column='[total_del_cnt]' derivation='Sum' name='[sum:total_del_cnt:qk]' pivot='key' type='quantitative' />
          </datasource-dependencies>
          <aggregation value='true' />
        </view>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='Area' />
          </pane>
        </panes>
        <rows>[{ds}].[sum:total_del_cnt:qk]</rows>
        <cols>[{ds}].[none:hour:qk]</cols>
      </table>
      <simple-id uuid='{muuid()}' />
    </worksheet>
"""


def ws_mode(ds):
    """Bar chart: motorcycle vs drone_robot by metric."""
    return f"""    <worksheet name='배송모드 비교'>
      <table>
        <view>
          <datasources>
            <datasource caption='Mode Radar Scores' name='{ds}' />
          </datasources>
          <datasource-dependencies datasource='{ds}'>
            <column aggregation='Count' datatype='string' name='[metric]' role='dimension' type='nominal' />
            <column-instance column='[metric]' derivation='None' name='[none:metric:nk]' pivot='key' type='nominal' />
            <column aggregation='Sum' datatype='real' name='[motorcycle]' role='measure' type='quantitative' />
            <column-instance column='[motorcycle]' derivation='Sum' name='[sum:motorcycle:qk]' pivot='key' type='quantitative' />
            <column aggregation='Sum' datatype='real' name='[drone_robot]' role='measure' type='quantitative' />
            <column-instance column='[drone_robot]' derivation='Sum' name='[sum:drone_robot:qk]' pivot='key' type='quantitative' />
          </datasource-dependencies>
          <aggregation value='true' />
        </view>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='Bar' />
          </pane>
        </panes>
        <rows>[{ds}].[none:metric:nk]</rows>
        <cols>([{ds}].[sum:motorcycle:qk] + [{ds}].[sum:drone_robot:qk])</cols>
      </table>
      <simple-id uuid='{muuid()}' />
    </worksheet>
"""


def ws_hubs(ds):
    """Text table: hub details."""
    return f"""    <worksheet name='허브 상세정보'>
      <table>
        <view>
          <datasources>
            <datasource caption='Final Hubs' name='{ds}' />
          </datasources>
          <datasource-dependencies datasource='{ds}'>
            <column aggregation='Count' datatype='string' name='[name]' role='dimension' type='nominal' />
            <column-instance column='[name]' derivation='None' name='[none:name:nk]' pivot='key' type='nominal' />
            <column aggregation='Count' datatype='string' name='[facility]' role='dimension' type='nominal' />
            <column-instance column='[facility]' derivation='None' name='[none:facility:nk]' pivot='key' type='nominal' />
            <column aggregation='Count' datatype='string' name='[delivery_mode]' role='dimension' type='nominal' />
            <column-instance column='[delivery_mode]' derivation='None' name='[none:delivery_mode:nk]' pivot='key' type='nominal' />
            <column aggregation='Sum' datatype='integer' name='[capacity]' role='measure' type='quantitative' />
            <column-instance column='[capacity]' derivation='Sum' name='[sum:capacity:qk]' pivot='key' type='quantitative' />
            <column aggregation='Sum' datatype='integer' name='[total_covered]' role='measure' type='quantitative' />
            <column-instance column='[total_covered]' derivation='Sum' name='[sum:total_covered:qk]' pivot='key' type='quantitative' />
          </datasource-dependencies>
          <aggregation value='true' />
        </view>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='Automatic' />
          </pane>
        </panes>
        <rows>([{ds}].[none:name:nk] + [{ds}].[none:facility:nk] + [{ds}].[none:delivery_mode:nk])</rows>
        <cols>([{ds}].[sum:capacity:qk] + [{ds}].[sum:total_covered:qk])</cols>
      </table>
      <simple-id uuid='{muuid()}' />
    </worksheet>
"""


# ═══════════════════════════════════════════════════════════════
# Dashboard XML
# ═══════════════════════════════════════════════════════════════

def build_dashboard():
    return """    <dashboard name='드론 로봇 배송 거점 최적화'>
      <style />
      <size maxheight='1080' maxwidth='1920' minheight='1080' minwidth='1920' />
      <zones>
        <zone h='100000' id='2' type-v2='layout-basic' w='100000' x='0' y='0'>
          <zone h='6000' id='3' type-v2='title' w='100000' x='0' y='0' />
          <zone h='56000' id='5' name='거점 적합도 지도' type-v2='worksheet' w='60000' x='0' y='6000' />
          <zone h='28000' id='6' name='동별 종합점수' type-v2='worksheet' w='40000' x='60000' y='6000' />
          <zone h='28000' id='7' name='배송모드 비교' type-v2='worksheet' w='40000' x='60000' y='34000' />
          <zone h='38000' id='8' name='시간대별 배송수요' type-v2='worksheet' w='50000' x='0' y='62000' />
          <zone h='38000' id='9' name='허브 상세정보' type-v2='worksheet' w='50000' x='50000' y='62000' />
        </zone>
      </zones>
    </dashboard>
"""


# ═══════════════════════════════════════════════════════════════
# Windows XML
# ═══════════════════════════════════════════════════════════════

def build_windows():
    sheets = [
        ('거점 적합도 지도', 'worksheet'),
        ('동별 종합점수', 'worksheet'),
        ('시간대별 배송수요', 'worksheet'),
        ('배송모드 비교', 'worksheet'),
        ('허브 상세정보', 'worksheet'),
        ('드론 로봇 배송 거점 최적화', 'dashboard'),
    ]
    xml = ""
    for name, cls in sheets:
        mx = ' maximized="true"' if cls == 'dashboard' else ''
        xml += f"""    <window class='{cls}'{mx} name='{name}'>
      <cards>
        <edge name='left'>
          <strip size='160'>
            <card type='pages' />
            <card type='filters' />
            <card type='marks' />
          </strip>
        </edge>
        <edge name='top'>
          <strip size='31'>
            <card type='columns' />
          </strip>
          <strip size='31'>
            <card type='rows' />
          </strip>
          <strip size='31'>
            <card type='title' />
          </strip>
        </edge>
      </cards>
      <simple-id uuid='{muuid()}' />
    </window>
"""
    return xml


# ═══════════════════════════════════════════════════════════════
# Assemble & package
# ═══════════════════════════════════════════════════════════════

def build():
    print("=== Building Tableau Workbook v2 ===\n")

    # Read CSVs
    grid = pd.read_csv(DATA_DIR / "grid_scores.csv")
    dong = pd.read_csv(DATA_DIR / "dong_summary.csv")
    demand = pd.read_csv(DATA_DIR / "hourly_demand.csv")
    radar = pd.read_csv(DATA_DIR / "mode_radar_scores.csv")
    hubs = pd.read_csv(DATA_DIR / "final_hubs.csv")

    # Build datasources
    ds_grid, xml_grid = build_datasource("Grid Scores", "grid_scores.hyper", "grid_scores", grid)
    ds_dong, xml_dong = build_datasource("Dong Summary", "dong_summary.hyper", "dong_summary", dong)
    ds_demand, xml_demand = build_datasource("Hourly Demand", "hourly_demand.hyper", "hourly_demand", demand)
    ds_radar, xml_radar = build_datasource("Mode Radar Scores", "mode_radar_scores.hyper", "mode_radar_scores", radar)
    ds_hubs, xml_hubs = build_datasource("Final Hubs", "final_hubs.hyper", "final_hubs", hubs)

    print(f"  DS: grid={ds_grid}")
    print(f"  DS: dong={ds_dong}")
    print(f"  DS: demand={ds_demand}")
    print(f"  DS: radar={ds_radar}")
    print(f"  DS: hubs={ds_hubs}")

    # Build worksheets
    w1 = ws_map(ds_grid)
    w2 = ws_bar(ds_dong)
    w3 = ws_demand(ds_demand)
    w4 = ws_mode(ds_radar)
    w5 = ws_hubs(ds_hubs)

    # Assemble TWB
    twb = f"""<?xml version='1.0' encoding='utf-8' ?>
<workbook original-version='18.1' source-build='2026.1.0 (20261.26.0401.1148)' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <document-format-change-manifest>
    <AnimationOnByDefault />
    <MapboxVectorStylesAndLayers />
    <MarkAnimation />
    <ObjectModelEncapsulateLegacy />
    <ObjectModelTableType />
    <SchemaViewerObjectModel />
    <SheetIdentifierTracking />
  </document-format-change-manifest>
  <preferences />
  <datasources>
{xml_grid}{xml_dong}{xml_demand}{xml_radar}{xml_hubs}  </datasources>
  <mapsources>
    <mapsource name='Tableau' />
  </mapsources>
  <worksheets>
{w1}{w2}{w3}{w4}{w5}  </worksheets>
  <dashboards>
{build_dashboard()}  </dashboards>
  <windows source-height='30'>
{build_windows()}  </windows>
</workbook>
"""

    # Write TWB
    twb_path = OUTPUT_DIR / "dashboard.twb"
    twb_path.write_text(twb, encoding="utf-8")
    print(f"\n  [OK] TWB: {twb_path} ({len(twb)} chars)")

    # Package TWBX
    twbx_path = OUTPUT_DIR / "seongnam_drone_hub_v2.twbx"
    hyper_list = ["grid_scores.hyper", "dong_summary.hyper", "hourly_demand.hyper",
                  "mode_radar_scores.hyper", "final_hubs.hyper"]

    with zipfile.ZipFile(twbx_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(twb_path, "dashboard.twb")
        for hf in hyper_list:
            hp = HYPER_DIR / hf
            if hp.exists():
                zf.write(hp, f"Data/Extracts/{hf}")
                print(f"  [OK] Packed: {hf}")

    print(f"\n  [OK] TWBX: {twbx_path} ({twbx_path.stat().st_size / 1024:.1f} KB)")
    return twbx_path


# ═══════════════════════════════════════════════════════════════
# Publish
# ═══════════════════════════════════════════════════════════════

def publish(twbx_path, pat_name, pat_secret):
    try:
        import truststore; truststore.inject_into_ssl()
    except ImportError:
        pass
    import tableauserverclient as TSC
    import certifi

    print("\n=== Publishing to Tableau Cloud ===\n")

    auth = TSC.PersonalAccessTokenAuth(
        token_name=pat_name, personal_access_token=pat_secret, site_id=SITE_NAME)
    server = TSC.Server(SERVER_URL, use_server_version=True)
    server.add_http_options({"verify": certifi.where()})

    with server.auth.sign_in(auth):
        print("  [OK] Signed in")

        # Find project
        projects, _ = server.projects.get()
        pid = None
        for p in projects:
            if p.name == PROJECT_NAME:
                pid = p.id
                break
        if not pid:
            print(f"  [ERROR] Project not found: {PROJECT_NAME}")
            return

        # Publish as async job (sync fails on Cloud with misleading 403)
        wb = TSC.WorkbookItem(project_id=pid, name="성남시 드론배송 거점 최적화 대시보드", show_tabs=True)
        job = server.workbooks.publish(wb, str(twbx_path), TSC.Server.PublishMode.Overwrite, as_job=True)
        print(f"  Job started: {job.id}")

        # Poll job status
        for i in range(20):
            time.sleep(3)
            j = server.jobs.get_by_id(job.id)
            print(f"  [{i*3}s] progress={j.progress}% finish_code={j.finish_code}")
            if j.completed_at:
                if j.finish_code == 0:
                    print("\n  *** SUCCESS ***")
                    wbs, _ = server.workbooks.get()
                    for w in wbs:
                        if '드론배송' in w.name or '거점' in w.name:
                            print(f"  Workbook: {w.name}")
                            print(f"  URL: {w.webpage_url}")
                else:
                    print(f"\n  [ERROR] Job failed (finish_code={j.finish_code})")
                    if hasattr(j, 'notes') and j.notes:
                        for n in j.notes:
                            print(f"  Note: {n}")
                    print("  The .twbx file is ready for manual upload.")
                    print(f"  File: {twbx_path}")
                break


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", nargs=2, metavar=("PAT", "SECRET"))
    args = parser.parse_args()

    twbx = build()

    if args.publish:
        publish(twbx, args.publish[0], args.publish[1])
    else:
        print(f"\n  To publish: python build_tableau_workbook.py --publish PAT_NAME PAT_SECRET")


if __name__ == "__main__":
    main()
