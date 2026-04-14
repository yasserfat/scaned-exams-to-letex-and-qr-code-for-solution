#!/usr/bin/env python3
"""
Upload a PDF to Google Drive via OAuth2 (user account).

Usage:
    python drive_upload.py solution.pdf
    python drive_upload.py solution.pdf --name "exam_2025_solution.pdf"
    python drive_upload.py solution.pdf --folder <FOLDER_ID>

Requires oauth_client.json (Desktop app credentials) in the project root.
On first run a browser window opens for Google login; token.json is saved for future runs.

Optional env vars:
    GOOGLE_DRIVE_FOLDER_ID=<folder_id>   # target folder (root if absent)
    GOOGLE_DRIVE_PUBLIC=true             # make file publicly readable (default: true)
"""
import argparse, os, sys
from dotenv import load_dotenv

load_dotenv()

from src.drive import upload_to_drive


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload PDF to Google Drive")
    parser.add_argument("pdf", help="Path to PDF file")
    parser.add_argument("--name", help="Filename on Drive (default: same as local file)")
    parser.add_argument("--folder", help="Drive folder ID (overrides GOOGLE_DRIVE_FOLDER_ID)")
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        print(f"ERROR: file not found: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    name = args.name or os.path.basename(args.pdf)

    try:
        url = upload_to_drive(args.pdf, name, folder_id=args.folder or None)
        print(url)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
