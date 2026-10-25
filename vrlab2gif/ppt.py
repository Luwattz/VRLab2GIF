"""Portable animated-GIF report export, matching LumiDyna/report_style.py.

The application writes native Open XML parts so exporting does not require
an Office installation. GIF bytes are embedded unchanged, not rasterized.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from threading import Event
import uuid
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageFont

from .core import ConversionCancelled
from . import DEVELOPER_NAME

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
for prefix, uri in (("p", P), ("a", A), ("r", R)):
    ET.register_namespace(prefix, uri)

WIDTH, HEIGHT = 960.0, 540.0
CM = 72 / 2.54
LEFT, TITLE_TOP, TITLE_WIDTH, TITLE_HEIGHT = 1.47 * CM, 0.50 * CM, 25 * CM, 1.49 * CM
HEADER_Y, BOTTOM_INSET = 1.99 * CM, 1.33 * CM
TITLE_COLOR, RULE_COLOR, FOOTER_COLOR = "FFA84F", "E6D4C2", "766A60"
FONT = "Microsoft YaHei"


@dataclass(frozen=True)
class PptOptions:
    title: str = "视角合成结果"
    footer: str = DEVELOPER_NAME
    collections_only: bool = False

    def __post_init__(self):
        if not self.title.strip():
            raise ValueError("请填写 PPT 报告标题。")
        for value in (self.title, self.footer):
            if any(ord(c) < 32 or ord(c) in (0xFFFE, 0xFFFF) for c in value):
                raise ValueError("PPT 标题和页脚不能包含换行或控制字符。")
        if _text_width(self.footer, 11) > 300:
            raise ValueError("页脚文字太长，请缩短后再导出。")


@dataclass(frozen=True)
class PptExportResult:
    output_path: Path
    slide_count: int
    gif_paths: tuple[Path, ...]


def _text_width(text: str, size: int, bold=False) -> float:
    font_path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / ("msyhbd.ttc" if bold else "msyh.ttc")
    try:
        return ImageFont.truetype(str(font_path), size * 4).getlength(text) / 4
    except OSError:
        # Conservative bound if the reference typeface is unavailable here.
        return len(text) * size


def _emu(points: float) -> str:
    return str(round(points * 12700))


def _e(parent, ns, tag, **attrs):
    return ET.SubElement(parent, f"{{{ns}}}{tag}", {key: str(value) for key, value in attrs.items()})


def _xml(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _tree(parent):
    tree = _e(parent, P, "spTree")
    nv = _e(tree, P, "nvGrpSpPr")
    _e(nv, P, "cNvPr", id=1, name="")
    _e(nv, P, "cNvGrpSpPr")
    _e(nv, P, "nvPr")
    tr = _e(_e(tree, P, "grpSpPr"), A, "xfrm")
    for name, attrs in (("off", {"x": 0, "y": 0}), ("ext", {"cx": 0, "cy": 0}),
                        ("chOff", {"x": 0, "y": 0}), ("chExt", {"cx": 0, "cy": 0})):
        _e(tr, A, name, **attrs)
    return tree


def _transform(properties, left, top, width, height):
    tr = _e(properties, A, "xfrm")
    _e(tr, A, "off", x=_emu(left), y=_emu(top))
    _e(tr, A, "ext", cx=_emu(width), cy=_emu(height))


def _run_style(parent, size, color, bold=False):
    rp = _e(parent, A, "rPr", lang="zh-CN", sz=size * 100, b=int(bold))
    _e(_e(rp, A, "solidFill"), A, "srgbClr", val=color)
    for script in ("latin", "ea", "cs"):
        _e(rp, A, script, typeface=FONT)


def _text(tree, ident, name, value, left, top, width, height, size, color,
          *, bold=False, align="l", anchor="t", slide_number=False):
    sp = _e(tree, P, "sp")
    nv = _e(sp, P, "nvSpPr")
    _e(nv, P, "cNvPr", id=ident, name=name)
    _e(nv, P, "cNvSpPr", txBox=1)
    _e(nv, P, "nvPr")
    pr = _e(sp, P, "spPr")
    _transform(pr, left, top, width, height)
    _e(_e(pr, A, "prstGeom", prst="rect"), A, "avLst")
    _e(pr, A, "noFill")
    _e(_e(pr, A, "ln"), A, "noFill")
    body = _e(sp, P, "txBody")
    bp = _e(body, A, "bodyPr", wrap="none", anchor=anchor,
            lIns=0, tIns=0, rIns=0, bIns=0)
    _e(bp, A, "noAutofit")
    _e(body, A, "lstStyle")
    paragraph = _e(body, A, "p")
    pp = _e(paragraph, A, "pPr", algn=align)
    _e(_e(pp, A, "spcBef"), A, "spcPts", val=0)
    _e(_e(pp, A, "spcAft"), A, "spcPts", val=0)
    if slide_number:
        run = _e(paragraph, A, "fld", id="{" + str(uuid.uuid4()).upper() + "}", type="slidenum")
    else:
        run = _e(paragraph, A, "r")
    _run_style(run, size, color, bold)
    _e(run, A, "t").text = value


def _line(tree, ident, name, y):
    sp = _e(tree, P, "cxnSp")
    nv = _e(sp, P, "nvCxnSpPr")
    _e(nv, P, "cNvPr", id=ident, name=name)
    _e(nv, P, "cNvCxnSpPr")
    _e(nv, P, "nvPr")
    pr = _e(sp, P, "spPr")
    _transform(pr, LEFT, y, WIDTH-2*LEFT, 0)
    _e(_e(pr, A, "prstGeom", prst="line"), A, "avLst")
    ln = _e(pr, A, "ln", w=9525)
    _e(_e(ln, A, "solidFill"), A, "srgbClr", val=RULE_COLOR)
    _e(ln, A, "prstDash", val="solid")


def _relationships(items):
    root = ET.Element(f"{{{REL}}}Relationships")
    for ident, kind, target in items:
        _e(root, REL, "Relationship", Id=ident, Type=R + "/" + kind, Target=target)
    return _xml(root)


def _master(options):
    root = ET.Element(f"{{{P}}}sldMaster")
    c = _e(root, P, "cSld", name="VRLab2GIF Report")
    _e(_e(_e(c, P, "bg"), P, "bgPr"), A, "solidFill")
    fill = c.find(f"{{{P}}}bg/{{{P}}}bgPr/{{{A}}}solidFill")
    _e(fill, A, "srgbClr", val="FFFFFF")
    tree = _tree(c)
    _line(tree, 2, "VRLab2GIF.HeaderRule", HEADER_Y)
    _line(tree, 3, "VRLab2GIF.FooterRule", HEIGHT-BOTTOM_INSET)
    footer_y = HEIGHT-BOTTOM_INSET+4
    _text(tree, 4, "VRLab2GIF.Brand", options.footer.strip(), LEFT, footer_y, 300, 22, 11, FOOTER_COLOR)
    _text(tree, 5, "VRLab2GIF.SlideNumber", "1", WIDTH-LEFT-60, footer_y, 60, 22,
          11, FOOTER_COLOR, align="r", slide_number=True)
    _e(root, P, "clrMap", bg1="lt1", tx1="dk1", bg2="lt2", tx2="dk2",
       **{f"accent{i}": f"accent{i}" for i in range(1, 7)}, hlink="hlink", folHlink="folHlink")
    layouts = _e(root, P, "sldLayoutIdLst")
    _e(layouts, P, "sldLayoutId", id=2147483649, **{f"{{{R}}}id": "rId1"})
    return _xml(root)


def _layout():
    root = ET.Element(f"{{{P}}}sldLayout", {"type": "blank", "preserve": "1"})
    _tree(_e(root, P, "cSld", name="Blank Report"))
    _e(_e(root, P, "clrMapOvr"), A, "masterClrMapping")
    return _xml(root)


def _theme():
    root = ET.Element(f"{{{A}}}theme", {"name": "VRLab2GIF Report"})
    elements = _e(root, A, "themeElements")
    colors = _e(elements, A, "clrScheme", name="Report")
    values = {"dk1": "000000", "lt1": "FFFFFF", "dk2": "766A60", "lt2": "F5F5F5",
              "accent1": TITLE_COLOR, "accent2": "0071E3", "accent3": "24804B",
              "accent4": "B42318", "accent5": "766A60", "accent6": RULE_COLOR,
              "hlink": "0563C1", "folHlink": "954F72"}
    for name, color in values.items():
        _e(_e(colors, A, name), A, "srgbClr", val=color)
    fonts = _e(elements, A, "fontScheme", name="Microsoft YaHei")
    for name in ("majorFont", "minorFont"):
        group = _e(fonts, A, name)
        for script in ("latin", "ea", "cs"):
            _e(group, A, script, typeface=FONT)
    fmt = _e(elements, A, "fmtScheme", name="Report")
    fills = _e(fmt, A, "fillStyleLst")
    for _ in range(3):
        _e(_e(fills, A, "solidFill"), A, "schemeClr", val="phClr")
    lines = _e(fmt, A, "lnStyleLst")
    for width in (6350, 12700, 19050):
        line = _e(lines, A, "ln", w=width)
        _e(_e(line, A, "solidFill"), A, "schemeClr", val="phClr")
        _e(line, A, "prstDash", val="solid")
    effects = _e(fmt, A, "effectStyleLst")
    for _ in range(3):
        _e(_e(effects, A, "effectStyle"), A, "effectLst")
    fills = _e(fmt, A, "bgFillStyleLst")
    for _ in range(3):
        _e(_e(fills, A, "solidFill"), A, "schemeClr", val="phClr")
    return _xml(root)


def _slide(title, image_size):
    root = ET.Element(f"{{{P}}}sld", {"showMasterSp": "1"})
    tree = _tree(_e(root, P, "cSld"))
    _text(tree, 2, "VRLab2GIF.BodyTitle", title, LEFT, TITLE_TOP, TITLE_WIDTH, TITLE_HEIGHT,
          24, TITLE_COLOR, bold=True, anchor="b")
    top, bottom = HEADER_Y+8, HEIGHT-BOTTOM_INSET-8
    factor = min((WIDTH-2*LEFT)/image_size[0], (bottom-top)/image_size[1])
    width, height = image_size[0]*factor, image_size[1]*factor
    pic = _e(tree, P, "pic")
    nv = _e(pic, P, "nvPicPr")
    _e(nv, P, "cNvPr", id=3, name="VRLab2GIF.AnimatedView", descr=title)
    _e(_e(nv, P, "cNvPicPr"), A, "picLocks", noChangeAspect=1)
    _e(nv, P, "nvPr")
    fill = _e(pic, P, "blipFill")
    _e(fill, A, "blip", **{f"{{{R}}}embed": "rId2"})
    _e(_e(fill, A, "stretch"), A, "fillRect")
    props = _e(pic, P, "spPr")
    _transform(props, (WIDTH-width)/2, top+(bottom-top-height)/2, width, height)
    _e(_e(props, A, "prstGeom", prst="rect"), A, "avLst")
    _e(_e(root, P, "clrMapOvr"), A, "masterClrMapping")
    return _xml(root)


def _title_for(path: Path, options: PptOptions) -> str:
    if path.stem == "collection_all_angles":
        label = "全角度合集"
    elif path.stem == "collection_all_views":
        label = "全视角合集"
    elif path.stem.startswith("vertical_angle_"):
        value = path.stem.removeprefix("vertical_angle_")
        label = f"垂直角度 {value}°"
    else:
        label = path.stem
    title = options.title.strip() + " · " + label
    if _text_width(title, 24, bold=True) > TITLE_WIDTH-6:
        raise ValueError("PPT 标题太长，无法完整放入 25 cm 标题框。请缩短报告标题或 GIF 文件名。")
    return title


def export_gifs_to_pptx(paths: tuple[Path, ...] | list[Path], output_path: Path,
                        options: PptOptions | None = None, log=None, progress=None,
                        cancel_event: Event | None = None) -> PptExportResult:
    options = options or PptOptions()
    output_path = Path(output_path)
    if output_path.suffix.lower() != ".pptx":
        raise ValueError("PPT 保存文件必须使用 .pptx 扩展名。")
    selected = tuple(Path(path) for path in paths if not options.collections_only or Path(path).stem in ("collection_all_angles", "collection_all_views"))
    if not selected:
        raise ValueError("没有可导出的 GIF，请先生成 GIF；仅导出合集时需要存在合集文件。")
    # Present the overview first, preserving the existing order of angle groups.
    priority = {"collection_all_angles": 0, "collection_all_views": 1}
    selected = tuple(sorted(selected, key=lambda path: priority.get(path.stem, 2)))
    emit = log or (lambda message: None)
    report = progress or (lambda done, total, label: None)

    def check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            raise ConversionCancelled()

    records = []
    check_cancel()
    for path in selected:
        check_cancel()
        title = _title_for(path, options)
        try:
            with Image.open(path) as image:
                if image.format != "GIF":
                    raise ValueError("输入不是 GIF 图片。")
                size = image.size
                for index in range(image.n_frames):
                    check_cancel()
                    image.seek(index)
                    image.load()
            stat = path.stat()
        except ConversionCancelled:
            raise
        except Exception as exc:
            raise ValueError(f"无法读取 GIF {path.name}: {exc}") from exc
        records.append((path, title, size, (stat.st_size, stat.st_mtime_ns)))
    check_cancel()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".vrlab2gif-ppt-", suffix=".tmp", dir=output_path.parent)
    os.close(descriptor)
    count = len(records)
    report(0, count, "正在导出 PPT")
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            types = ET.Element(f"{{{CT}}}Types")
            for ext, kind in (("rels", "application/vnd.openxmlformats-package.relationships+xml"),
                              ("xml", "application/xml"), ("gif", "image/gif")):
                _e(types, CT, "Default", Extension=ext, ContentType=kind)
            parts = [("ppt/presentation.xml", "presentationml.presentation.main"),
                     ("ppt/slideMasters/slideMaster1.xml", "presentationml.slideMaster"),
                     ("ppt/slideLayouts/slideLayout1.xml", "presentationml.slideLayout"),
                     ("ppt/theme/theme1.xml", "theme")]
            parts += [(f"ppt/slides/slide{i}.xml", "presentationml.slide") for i in range(1, count+1)]
            for part, kind in parts:
                _e(types, CT, "Override", PartName="/"+part, ContentType=f"application/vnd.openxmlformats-officedocument.{kind}+xml")
            archive.writestr("[Content_Types].xml", _xml(types))
            archive.writestr("_rels/.rels", _relationships([("rId1", "officeDocument", "ppt/presentation.xml")]))
            presentation = ET.Element(f"{{{P}}}presentation", {"firstSlideNum": "1"})
            masters = _e(presentation, P, "sldMasterIdLst")
            _e(masters, P, "sldMasterId", id=2147483648, **{f"{{{R}}}id": "rId1"})
            slides = _e(presentation, P, "sldIdLst")
            for i in range(1, count+1):
                _e(slides, P, "sldId", id=255+i, **{f"{{{R}}}id": f"rId{i+1}"})
            _e(presentation, P, "sldSz", cx=_emu(WIDTH), cy=_emu(HEIGHT), type="screen16x9")
            _e(presentation, P, "notesSz", cx=6858000, cy=9144000)
            archive.writestr("ppt/presentation.xml", _xml(presentation))
            rels = [("rId1", "slideMaster", "slideMasters/slideMaster1.xml")]
            rels += [(f"rId{i+1}", "slide", f"slides/slide{i}.xml") for i in range(1, count+1)]
            archive.writestr("ppt/_rels/presentation.xml.rels", _relationships(rels))
            archive.writestr("ppt/slideMasters/slideMaster1.xml", _master(options))
            archive.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", _relationships([
                ("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml"), ("rId2", "theme", "../theme/theme1.xml")]))
            archive.writestr("ppt/slideLayouts/slideLayout1.xml", _layout())
            archive.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", _relationships([
                ("rId1", "slideMaster", "../slideMasters/slideMaster1.xml")]))
            archive.writestr("ppt/theme/theme1.xml", _theme())
            for i, (path, title, size, expected_stat) in enumerate(records, 1):
                check_cancel()
                archive.writestr(f"ppt/slides/slide{i}.xml", _slide(title, size))
                archive.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", _relationships([
                    ("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml"),
                    ("rId2", "image", f"../media/image{i}.gif")]))
                with path.open("rb") as source, archive.open(f"ppt/media/image{i}.gif", "w", force_zip64=True) as target:
                    while data := source.read(1024*1024):
                        check_cancel()
                        target.write(data)
                stat = path.stat()
                if (stat.st_size, stat.st_mtime_ns) != expected_stat:
                    raise ValueError(f"导出时 GIF 已发生变化，请重试：{path.name}")
                emit(f"已嵌入 GIF：{path.name}（保留原始动画）")
                report(i, count, "正在导出 PPT")
        check_cancel()
        with ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError("PPT 文件完整性检查失败。")
        check_cancel()
        os.replace(temporary, output_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    emit(f"[成功] 已导出 PPT：{output_path.name}（{count} 页）")
    return PptExportResult(output_path, count, selected)
