import uuid
from pathlib import Path

DATA_DIR = Path(r'C:\Users\jimin\Desktop\1_BITAmin_16기\1_Seongnam_reset\05_tableau_v3\data')
OUT = Path(r'C:\Users\jimin\Desktop\1_BITAmin_16기\1_Seongnam_reset\05_tableau_v3\test_minimal.twb')

def esc(s):
    return str(s).replace('&','&amp;').replace("'","&apos;").replace('"','&quot;')

rel  = 'grid_master#csv'
tbl  = esc('[' + rel + ']')
leaf = 'gm_leaf'
ddir = esc(str(DATA_DIR))
uid  = str(uuid.uuid4()).upper()

lines = [
"<?xml version='1.0' encoding='utf-8' ?>",
"<workbook source-build='2026.1.0 (20261.26.0401.1148)' source-platform='win' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>",
"  <document-format-change-manifest><SheetIdentifierTracking /></document-format-change-manifest>",
"  <preferences />",
"  <datasources>",
"    <datasource hasconnection='false' inline='true' name='Parameters' version='18.1'>",
"      <aliases enabled='yes' />",
"      <column caption='Bool Test' datatype='boolean' name='[p_test]' param-domain-type='list' role='measure' type='nominal' value='true'>",
"        <calculation class='tableau' formula='true' />",
"        <members><member value='true' /><member value='false' /></members>",
"      </column>",
"    </datasource>",
f"    <datasource caption='Grid Master' inline='true' name='textscan.test001' version='18.1'>",
f"      <connection class='federated'>",
f"        <named-connections>",
f"          <named-connection name='{leaf}'>",
f"            <connection character-set='UTF-8' class='textscan'",
f"                        directory='{ddir}' driver=''",
f"                        filename='grid_master.csv'",
f"                        force-character-set='no' force-header='no'",
f"                        force-separator='no' header='yes'",
f"                        locale='en_US' separator=','",
f"                        text-qualifier='&quot;' />",
f"          </named-connection>",
f"        </named-connections>",
f"        <relation connection='{leaf}' name='{esc(rel)}' table='{tbl}' type='table'>",
f"          <columns character-set='UTF-8' header='yes' locale='en_US' separator=',' text-qualifier='&quot;'>",
f"            <column datatype='string' name='h3_index' ordinal='0' />",
f"            <column datatype='real' name='lat' ordinal='1' />",
f"            <column datatype='real' name='lon' ordinal='2' />",
f"          </columns>",
f"        </relation>",
f"        <refresh increment-key='' incremental-updates='false' />",
f"      </connection>",
f"      <aliases enabled='yes' />",
f"      <column aggregation='Count' datatype='string' name='[h3_index]' role='dimension' type='nominal' />",
f"      <column aggregation='Avg' datatype='real' name='[lat]' role='measure' type='quantitative' semantic-role='[Geographical].[Latitude]' />",
f"      <column aggregation='Avg' datatype='real' name='[lon]' role='measure' type='quantitative' semantic-role='[Geographical].[Longitude]' />",
f"    </datasource>",
"  </datasources>",
"  <worksheets>",
"    <worksheet name='Test Sheet'>",
"      <table>",
"        <view>",
"          <datasources>",
"            <datasource caption='Grid Master' name='textscan.test001' />",
"          </datasources>",
"          <aggregation value='true' />",
"        </view>",
"        <style />",
"        <panes>",
"          <pane selection-relaxation-option='selection-relaxation-allow'>",
"            <view><breakdown value='auto' /></view>",
"            <mark class='Automatic' />",
"          </pane>",
"        </panes>",
"        <rows />",
"        <cols />",
"      </table>",
f"      <simple-id uuid='{{{uid}}}' />",
"    </worksheet>",
"  </worksheets>",
"</workbook>",
]

OUT.write_text('\n'.join(lines), encoding='utf-8')
print(f"Written: {OUT} ({OUT.stat().st_size} bytes)")
