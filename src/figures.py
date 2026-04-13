import re
import os
import fitz


def parse_figure_placeholders(latex: str) -> list[dict]:
    """
    Returns [{"name": str, "label": str, "page": int, "top": float, "left": float,
              "bottom": float, "right": float}, ...]
    label is the Arabic human-readable display name (may be absent in old format).
    All bbox fields default to full-page (0.0/1.0) when absent.
    """
    # New format: [FIGURE:name:label:pageN:top:left:bottom:right]
    # Old format: [FIGURE:name:pageN:top:left:bottom:right]  (no label)
    pattern = r'\[FIGURE:([\w_-]+):((?:[^:\]]*?):)?page(\d+)(?::([0-9.]+):([0-9.]+):([0-9.]+):([0-9.]+))?\]'
    results = []
    for m in re.finditer(pattern, latex):
        label_raw = m.group(2) or ""
        label = label_raw.rstrip(":").strip()
        results.append({
            "name":   m.group(1),
            "label":  label,
            "page":   int(m.group(3)),
            "top":    float(m.group(4) or 0.0),
            "left":   float(m.group(5) or 0.0),
            "bottom": float(m.group(6) or 1.0),
            "right":  float(m.group(7) or 1.0),
        })
    return results


def extract_figures_from_pdf(pdf_path: str, figure_specs: list[dict],
                              work_dir: str, dpi: int = 200) -> dict[str, str]:
    """
    Crop figures from PDF using Claude-provided fractional bounding boxes.
    Returns {name: png_path} for each successfully cropped figure.
    """
    doc = fitz.open(pdf_path)
    figure_map: dict[str, str] = {}

    for spec in figure_specs:
        name = spec["name"]
        page_idx = spec["page"] - 1
        if page_idx >= len(doc):
            continue

        page = doc[page_idx]
        rect = page.rect  # full page rect in points

        # Convert fractional bbox to absolute points
        x0 = rect.x0 + spec["left"]   * rect.width
        y0 = rect.y0 + spec["top"]    * rect.height
        x1 = rect.x0 + spec["right"]  * rect.width
        y1 = rect.y0 + spec["bottom"] * rect.height
        clip = fitz.Rect(x0, y0, x1, y1)

        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
        out_path = os.path.join(work_dir, f"figure_{name}.png")
        pix.save(out_path)
        figure_map[name] = out_path

    doc.close()
    return figure_map


def replace_figure_placeholders(latex: str, figure_map: dict[str, str]) -> str:
    """
    Replace [FIGURE:name:pageN] fbox blocks with \\includegraphics for resolved figures.
    Unresolved placeholders left as-is.
    """
    pattern = r'\\begin\{center\}\s*\\fbox\{.*?\[FIGURE:([\w_-]+):[^\]]*\].*?\}\s*\\end\{center\}'
    def replacer(m: re.Match) -> str:
        name = m.group(1)
        if name in figure_map:
            fname = os.path.basename(figure_map[name])
            return rf"\begin{{center}}\includegraphics[width=0.5\textwidth]{{{fname}}}\end{{center}}"
        return m.group(0)  # keep placeholder
    return re.sub(pattern, replacer, latex, flags=re.DOTALL)
