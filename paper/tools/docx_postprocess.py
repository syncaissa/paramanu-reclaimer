"""Post-process pandoc's .docx so tables match LaTeX (standard library only).

pandoc computes column widths against a 5.5in (7920 twip) text block and then
stretches every table to 100% width. LaTeX sets tables at their natural width,
centred. This rescales the grid to the real 451pt (9026 twip) text block and
fixes each table's width to the sum of its columns.
Usage: python3 docx_postprocess.py file.docx
"""
import re
import shutil
import sys
import tempfile
import zipfile

PANDOC_TW, REAL_TW = 7920, 9026


def small_runs(tbl_xml):
    """\\small tables (the wide ones) use 10pt text, as in the PDF."""
    tbl_xml = re.sub(r"<w:r><w:rPr>", '<w:r><w:rPr><w:sz w:val="20" /><w:szCs w:val="20" />', tbl_xml)
    return re.sub(r"<w:r>(?!<w:rPr>)", '<w:r><w:rPr><w:sz w:val="20" /><w:szCs w:val="20" /></w:rPr>', tbl_xml)


def fix_table(m):
    tbl = m.group(0)
    cols = [int(w) for w in re.findall(r'<w:gridCol w:w="(\d+)"', tbl)]
    if not cols:
        return tbl
    scale = REAL_TW / PANDOC_TW
    new = [round(c * scale) for c in cols]
    total = sum(new)
    if total > REAL_TW:                      # never wider than the text block
        new = [round(c * REAL_TW / total) for c in new]
        total = sum(new)
    it = iter(new)
    tbl = re.sub(r'<w:gridCol w:w="\d+"', lambda _: f'<w:gridCol w:w="{next(it)}"', tbl)
    tbl = re.sub(r'<w:tblW w:type="pct" w:w="\d+" ?/>', f'<w:tblW w:type="dxa" w:w="{total}" />', tbl, count=1)
    # cell widths inside rows follow the grid
    return tbl


def main(path):
    tmp = tempfile.mktemp(suffix=".docx")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                xml = data.decode("utf-8")
                xml = re.sub(r"<w:tblPr>.*?</w:tblGrid>", fix_table, xml, flags=re.S)
                xml = re.sub(r"<w:tbl>.*?</w:tbl>",
                             lambda m: small_runs(m.group(0)) if m.group(0).count("<w:gridCol ") >= 7 else m.group(0),
                             xml, flags=re.S)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, path)


if __name__ == "__main__":
    main(sys.argv[1])
