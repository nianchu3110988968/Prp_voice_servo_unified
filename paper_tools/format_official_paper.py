"""Apply PRP body formatting while preserving the cover section and resources."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
import os
import re
import shutil
import sys

from lxml import etree as ET

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "论文初稿/毛绒陪伴机器人语音与动作系统设计_正式版.docx"
OLD = ROOT / "论文初稿/毛绒陪伴机器人语音与动作系统设计_已废弃.docx"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"w": W, "r": R}


def tag(name):
    return f"{{{W}}}{name}"


def child(parent, name, **attrs):
    e = parent.find(tag(name))
    if e is None:
        e = ET.SubElement(parent, tag(name))
    for k, v in attrs.items():
        e.set(tag(k), str(v))
    return e


def remove(parent, *names):
    for name in names:
        for e in parent.findall(tag(name)):
            parent.remove(e)


def text(e):
    return "".join(e.xpath(".//w:t/text()", namespaces=NS))


def rformat(run, east="宋体", size=21, bold=False):
    rp = run.find(tag("rPr"))
    if rp is None:
        rp = ET.Element(tag("rPr"))
        run.insert(0, rp)
    remove(rp, "rStyle", "rFonts", "sz", "szCs", "b", "bCs", "i", "iCs", "spacing", "w", "position", "snapToGrid", "color", "u", "kern")
    child(rp, "rFonts", ascii="Times New Roman", hAnsi="Times New Roman", eastAsia=east, cs="Times New Roman")
    child(rp, "sz", val=size)
    child(rp, "szCs", val=size)
    child(rp, "b", val=int(bold))
    child(rp, "bCs", val=int(bold))
    child(rp, "i", val=0)
    child(rp, "iCs", val=0)
    child(rp, "spacing", val=0)
    child(rp, "w", val=100)
    child(rp, "position", val=0)
    child(rp, "snapToGrid", val=0)
    child(rp, "color", val="000000")


def pformat(p, *, indent=True, align="both", size=21, east="宋体", bold=False, level=None, half_space=False, keep=False):
    pp = p.find(tag("pPr"))
    if pp is None:
        pp = ET.Element(tag("pPr"))
        p.insert(0, pp)
    remove(pp, "pStyle", "spacing", "ind", "jc", "snapToGrid", "outlineLvl", "contextualSpacing", "keepNext", "keepLines", "widowControl", "rPr", "tabs")
    child(pp, "keepNext", val=int(keep))
    child(pp, "keepLines", val=int(level is not None))
    child(pp, "widowControl", val=1)
    child(pp, "snapToGrid", val=0)
    space = child(pp, "spacing", before=0, after=0, line=240, lineRule="auto")
    if half_space:
        space.set(tag("beforeLines"), "50")
        space.set(tag("afterLines"), "50")
    child(pp, "ind", left=0, right=0, firstLine=size * 20 if indent else 0, firstLineChars=200 if indent else 0)
    child(pp, "jc", val=align)
    if level is not None:
        child(pp, "outlineLvl", val=level)
    for run in p.findall(".//" + tag("r")):
        rformat(run, east, size, bold)
    # Explicit paragraph-mark formatting also controls blank lines and new typing.
    dummy = ET.Element(tag("r"))
    rformat(dummy, east, size, bold)
    pp.append(deepcopy(dummy.find(tag("rPr"))))


def paragraph(t):
    p = ET.Element(tag("p"))
    r = ET.SubElement(p, tag("r"))
    e = ET.SubElement(r, tag("t"))
    e.text = t
    return p


def serialize(root):
    return ET.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


original_hash = hashlib.sha256(PAPER.read_bytes()).hexdigest()
with ZipFile(PAPER) as z:
    infos = z.infolist()
    data = {i.filename: z.read(i.filename) for i in infos}
doc = ET.fromstring(data["word/document.xml"])
body = doc.find(tag("body"))
boundary = next(i for i, e in enumerate(body) if e.find("w:pPr/w:sectPr", NS) is not None)
cover_snapshot = [ET.tostring(e) for e in list(body)[:boundary + 1]]
body_start = boundary + 1
chapter = next(i for i, e in enumerate(body) if text(e).strip() == "1 绪论")
chapter_text = [text(e) for e in list(body)[chapter:] if e.tag != tag("sectPr")]
restored = False

# The previous merge used a physical page break instead of the abstract boundary.
# Restore only the demonstrably truncated front matter from the preserved draft.
if text(body[body_start]).strip() == "ion control, companion robot":
    with ZipFile(OLD) as z:
        old_body = ET.fromstring(z.read("word/document.xml")).find(tag("body"))
    a = next(i for i, e in enumerate(old_body) if text(e).strip() == "摘要")
    b = next(i for i, e in enumerate(old_body) if text(e).strip() == "1 绪论")
    front = [deepcopy(e) for e in list(old_body)[a:b]]
    assert not any(e.xpath(".//*[@r:id or @r:embed or @r:link]", namespaces=NS) for e in front)
    for e in list(body)[body_start:chapter]:
        body.remove(e)
    for i, e in enumerate(front):
        # Avoid duplicate Word paragraph identifiers inherited from another file.
        for node in e.iter():
            for key in list(node.attrib):
                if key.endswith("}paraId") or key.endswith("}textId"):
                    del node.attrib[key]
        body.insert(body_start + i, e)
    restored = True

mode = "body"
paragraph_count = 0
for block in list(body)[body_start:]:
    if block.tag == tag("sectPr"):
        continue
    if block.tag == tag("tbl"):
        for row_index, row in enumerate(block.findall(tag("tr"))):
            trp = child(row, "trPr")
            child(trp, "cantSplit")
            if row_index == 0:
                child(trp, "tblHeader")
            for p in row.findall(".//" + tag("p")):
                pformat(p, indent=False, align="center" if row_index == 0 else "left", bold=row_index == 0)
        continue
    if block.tag != tag("p"):
        continue
    t = text(block).strip()
    has_image = bool(block.xpath(".//w:drawing | .//w:pict | .//w:object", namespaces=NS))
    if t in ("摘要", "ABSTRACT"):
        mode = "en_abstract" if t == "ABSTRACT" else "cn_abstract"
        pformat(block, indent=False, align="center", size=28, east="Times New Roman" if t == "ABSTRACT" else "黑体", bold=t == "摘要", keep=True)
    elif t.startswith("关键词") or t.startswith("KEY WORDS"):
        english = t.startswith("KEY WORDS")
        pformat(block, indent=False, align="left", east="Times New Roman" if english else "宋体")
        for run in block.findall(tag("r")):
            rt = text(run).strip()
            if rt.startswith("关键词") or rt.startswith("KEY WORDS"):
                rformat(run, "Times New Roman" if english else "黑体", 24, True)
    elif re.match(r"^\d+\s+", t) or t in ("参考文献", "致谢"):
        mode = "references" if t == "参考文献" else "body"
        pformat(block, align="left", east="黑体", size=24, bold=True, level=0, half_space=True, keep=True)
    elif re.match(r"^\d+\.\d+(?:\.\d+)?\s", t):
        level = len(t.split()[0].split(".")) - 1
        pformat(block, align="left", bold=True, level=level, keep=True)
    elif has_image:
        pformat(block, indent=False, align="center", keep=True)
    elif re.match(r"^[图表]\s*\d", t):
        pformat(block, indent=False, align="center")
    elif not t:
        pformat(block, indent=False, align="left")
    elif mode == "references":
        pformat(block, indent=False, align="left")
    else:
        pformat(block, east="Times New Roman" if mode == "en_abstract" else "宋体")
    for cached_break in block.findall(".//" + tag("lastRenderedPageBreak")):
        cached_break.getparent().remove(cached_break)
    paragraph_count += 1

section = body.find(tag("sectPr"))
assert section is not None
child(section, "pgSz", w=11906, h=16838, code=9)
child(section, "pgMar", top=1814, bottom=1440, left=1417, right=1417, header=850, footer=992, gutter=0)
child(section, "docGrid", type="default")

# Cover header/footer references are distinct from the body references.
rels = ET.fromstring(data["word/_rels/document.xml.rels"])
targets = {e.get("Id"): "word/" + e.get("Target") for e in rels}
cover_section = body[boundary].find("w:pPr/w:sectPr", NS)
cover_parts = {targets[e.get(f"{{{R}}}id")] for e in cover_section if e.tag in (tag("headerReference"), tag("footerReference"))}
body_refs = [e for e in section if e.tag in (tag("headerReference"), tag("footerReference"))]
changed_parts = {"word/document.xml"}
for ref in body_refs:
    part = targets[ref.get(f"{{{R}}}id")]
    assert part not in cover_parts, "Cannot modify a header/footer shared with the cover"
    root = ET.fromstring(data[part])
    for e in list(root):
        root.remove(e)
    if ref.tag == tag("headerReference"):
        p = paragraph("上海交通大学第    期PRP学生研究论文")
        pformat(p, indent=False, align="center", east="楷体", size=18)
    else:
        p = paragraph("")
        pformat(p, indent=False, align="center", size=18)
        f = ET.SubElement(p, tag("fldSimple"))
        f.set(tag("instr"), " PAGE ")
        r = ET.SubElement(f, tag("r"))
        rformat(r, size=18)
        ET.SubElement(r, tag("t")).text = "1"
    root.append(p)
    data[part] = serialize(root)
    changed_parts.add(part)

# Ensure even-page body headers cannot inherit the cover's separate resources.
settings = ET.fromstring(data["word/settings.xml"])
if settings.find(tag("evenAndOddHeaders")) is not None:
    for name in ("headerReference", "footerReference"):
        default_ref = next(e for e in section.findall(tag(name)) if e.get(tag("type")) == "default")
        if not any(e.get(tag("type")) == "even" for e in section.findall(tag(name))):
            copy = deepcopy(default_ref)
            copy.set(tag("type"), "even")
            section.insert(0, copy)

assert [ET.tostring(e) for e in list(body)[:boundary + 1]] == cover_snapshot
chapter = next(i for i, e in enumerate(body) if text(e).strip() == "1 绪论")
assert [text(e) for e in list(body)[chapter:] if e.tag != tag("sectPr")] == chapter_text
data["word/document.xml"] = serialize(doc)

backup_dir = PAPER.parent / "备份"
backup_dir.mkdir(exist_ok=True)
backup = backup_dir / (PAPER.stem + "_正文排版前_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".docx")
assert hashlib.sha256(PAPER.read_bytes()).hexdigest() == original_hash, "File changed while formatting"
shutil.copy2(PAPER, backup)
temp = PAPER.with_suffix(".formatting.tmp")
with ZipFile(temp, "w") as z:
    for info in infos:
        z.writestr(info, data[info.filename])
with ZipFile(temp) as z, ZipFile(backup) as before:
    assert z.testzip() is None
    for name in z.namelist():
        if name not in changed_parts:
            assert z.read(name) == before.read(name), name
    verify_doc = ET.fromstring(z.read("word/document.xml"))
    verify_body = verify_doc.find(tag("body"))
    assert [ET.tostring(e) for e in list(verify_body)[:boundary + 1]] == cover_snapshot
os.replace(temp, PAPER)
print(json.dumps({"file": str(PAPER), "backup": str(backup), "restored_abstracts": restored, "formatted_paragraphs": paragraph_count, "changed_parts": sorted(changed_parts), "cover_xml_and_resources_unchanged": True, "chapter_text_unchanged": True}, ensure_ascii=False, indent=2))
