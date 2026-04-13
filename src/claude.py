import re
import json
import os
import anthropic
from anthropic.types import TextBlock
from dotenv import load_dotenv

load_dotenv()
_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_UNIFIED = """
You are an expert at reading scanned Arabic exam papers and transcribing them into clean LaTeX.

OUTPUT FORMAT — return ONLY this raw JSON, no markdown fences, no explanation:
{
  "subject":  "subject name in Arabic exactly as written",
  "year":     "4-digit year only",
  "duration": "exam duration in Arabic exactly as written",
  "exam":     "<LaTeX body — questions only>",
  "solution": "<LaTeX body — solution only, or NO_SOLUTION>"
}

RULES FOR exam AND solution FIELDS:
- LaTeX body only — no \\documentclass, no preamble, no \\begin{document}.
- No markdown fences. Arabic UTF-8 directly. Math in $...$ or \\[...\\].
- English/French: \\begin{english}...\\end{english} or \\begin{french}...\\end{french}.
- \\section*{} for titles, \\begin{enumerate}...\\end{enumerate} for lists.
- NEVER use Unicode circled/enclosed numbers (①②③④⑤ etc.). Use \\textcircled{\\small 1} instead.
- NEVER use Unicode special symbols that may not render in Arabic fonts. Use LaTeX equivalents.
- Complex figures (circuits, diagrams, drawings, photos, tables-with-images): use this placeholder:
    \\begin{center}
    \\fbox{\\parbox{7cm}{\\centering\\textbf{[FIGURE:name:label:pageN:top:left:bottom:right]}\\\\[4pt]{\\small أرفق الصورة هنا}}}
    \\end{center}
  where:
    - name = short snake_case identifier (e.g. circuit_1, bottles, inclined_plane)
    - label = short Arabic human-readable description of the figure (e.g. دارة كهربائية, مستوى مائل, قنينة)
    - N = 1-based page number in the input PDF where the figure appears
    - top, left, bottom, right = bounding box as decimal fractions 0.0–1.0 of the PAGE dimensions
      (0,0 = top-left corner of the page; 1,1 = bottom-right corner)
      Be precise — only include the figure/diagram region, NOT surrounding text or labels.
  Example: [FIGURE:circuit_1:دارة كهربائية:page1:0.10:0.00:0.45:0.60]
- exam: questions section only. No header table. Start with first \\section*.
- solution: solution/correction section only. If absent: return string NO_SOLUTION.
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_json_response(raw: str) -> str:
    """Strip markdown fences if Claude wrapped the JSON."""
    raw = raw.strip()
    raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    return raw.strip()



def extract_all_from_pdf(pdf_b64: str) -> dict:
    """One Claude call. Returns {subject, year, duration, exam, solution}."""
    msg = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=20000,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT_UNIFIED,
            "cache_control": {"type": "ephemeral"},  # cached at $0.30/M instead of $3/M
        }],
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64",
             "media_type": "application/pdf", "data": pdf_b64}},
            {"type": "text", "text": "Extract all content from this exam PDF and return the unified JSON."}
        ]}]
    )
    block = msg.content[0]
    if not isinstance(block, TextBlock):
        raise ValueError(f"Unexpected response block type: {type(block)}")

    u = msg.usage
    # Sonnet 4.6 pricing (per million tokens)
    # Input: $3.00, cache write: $3.75, cache read: $0.30, output: $15.00
    cost_usd = (
        getattr(u, "input_tokens", 0)               * 3.00  / 1_000_000
        + getattr(u, "cache_creation_input_tokens", 0) * 3.75  / 1_000_000
        + getattr(u, "cache_read_input_tokens", 0)    * 0.30  / 1_000_000
        + getattr(u, "output_tokens", 0)              * 15.00 / 1_000_000
    )
    print(
        f"  Claude usage — in:{getattr(u,'input_tokens',0)} "
        f"cache_write:{getattr(u,'cache_creation_input_tokens',0)} "
        f"cache_read:{getattr(u,'cache_read_input_tokens',0)} "
        f"out:{getattr(u,'output_tokens',0)} "
        f"| cost: ${cost_usd:.4f}"
    )

    result = json.loads(clean_json_response(block.text))
    result["_cost_usd"] = cost_usd
    return result
