"""Download existing workbook from Tableau Cloud and extract TWB XML."""
import sys, os, zipfile, shutil
from pathlib import Path

# SSL fix
try:
    import truststore; truststore.inject_into_ssl()
except ImportError:
    pass

import tableauserverclient as TSC
import certifi

SERVER_URL = "https://prod-kr-a.online.tableau.com"
SITE_NAME = "jimin076721-be93e49158"
WORKBOOK_ID = "f2e36e25-e75d-4efa-a654-3554a94c4e1f"

BASE = Path(__file__).parent
DOWNLOAD_DIR = BASE / "workbook_download"
DOWNLOAD_DIR.mkdir(exist_ok=True)

def main():
    pat_name = sys.argv[1] if len(sys.argv) > 1 else "Claude_connect"
    pat_secret = sys.argv[2] if len(sys.argv) > 2 else None

    if not pat_secret:
        print("Usage: python download_workbook.py PAT_NAME PAT_SECRET")
        return

    tableau_auth = TSC.PersonalAccessTokenAuth(
        token_name=pat_name,
        personal_access_token=pat_secret,
        site_id=SITE_NAME,
    )
    server = TSC.Server(SERVER_URL, use_server_version=True)
    server.add_http_options({"verify": certifi.where()})

    with server.auth.sign_in(tableau_auth):
        print("[OK] Signed in")

        # Download workbook
        file_path = server.workbooks.download(
            WORKBOOK_ID,
            filepath=str(DOWNLOAD_DIR),
            include_extract=False  # Skip extract to save time
        )
        print(f"[OK] Downloaded: {file_path}")

        # Also try with extract
        file_path_full = server.workbooks.download(
            WORKBOOK_ID,
            filepath=str(DOWNLOAD_DIR / "with_extract"),
            include_extract=True
        )
        print(f"[OK] Downloaded with extract: {file_path_full}")

    # Extract TWB from TWBX
    for fp in [file_path, file_path_full]:
        fp = Path(fp)
        if fp.suffix == '.twbx':
            extract_dir = fp.parent / fp.stem
            extract_dir.mkdir(exist_ok=True)
            with zipfile.ZipFile(fp) as z:
                z.extractall(extract_dir)
            print(f"[OK] Extracted to: {extract_dir}")
            for f in extract_dir.rglob('*.twb'):
                print(f"  TWB file: {f}")
                print(f"  Size: {f.stat().st_size} bytes")
        elif fp.suffix == '.twb':
            print(f"[OK] TWB file directly: {fp}")
            print(f"  Size: {fp.stat().st_size} bytes")

if __name__ == "__main__":
    main()
