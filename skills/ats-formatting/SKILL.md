---
name: ats-formatting
description: Format a resume so applicant-tracking systems parse it cleanly. Load when producing the final resume version.
---

# ATS-safe formatting

## Rules
- Single-column layout only — no tables, text boxes, columns, or sidebars.
- No images, icons, logos, headshots, or charts (parsers drop them).
- Standard section headers: "Experience", "Education", "Skills", "Projects".
- Use standard fonts (Arial, Calibri, Times New Roman) at 10–12pt.
- Plain bullet characters (•, -); avoid custom glyphs and Wingdings.
- Put contact info in the body, not the header/footer (many parsers ignore those).
- Save as `.docx` or text-based `.pdf` — never a scanned/image PDF.
- Spell out an acronym at least once alongside its short form (e.g. "Natural Language Processing (NLP)").

## Procedure
1. Flatten any multi-column or table-based layout into a single column.
2. Normalize section headers to the standard names above.
3. Keep dates in a consistent `MMM YYYY` format.
4. Verify the exported file's text can be copied/selected (a proxy for parseability).
