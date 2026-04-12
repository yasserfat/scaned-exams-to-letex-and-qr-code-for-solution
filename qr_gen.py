#!/usr/bin/env python3
"""
Generate a QR code PNG from a URL.

Usage:
    python qr_gen.py https://drive.google.com/file/d/.../view
    python qr_gen.py https://drive.google.com/file/d/.../view --out qr.png

Outputs the saved file path to stdout.
"""
import argparse
from pipeline import generate_qr_code


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate QR code PNG from a URL")
    parser.add_argument("url", help="URL to encode in the QR code")
    parser.add_argument("--out", default="qr_code.png", help="Output PNG path (default: qr_code.png)")
    args = parser.parse_args()

    out = generate_qr_code(args.url, args.out)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
