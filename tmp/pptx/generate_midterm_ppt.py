from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE, MSO_CONNECTOR
from pptx.enum.text import MSO_VERTICAL_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


OUT_PATH = Path("/Users/guoguoguo/Desktop/douban-kg-system/output/pptx/基于知识图谱的电影推荐系统_中期答辩汇报.pptx")


PRIMARY = RGBColor(0x1E, 0x3A, 0x5F)
PRIMARY_DARK = RGBColor(0x16, 0x2B, 0x45)
SECONDARY = RGBColor(0x4F, 0x67, 0x7F)
TEXT = RGBColor(0x21, 0x2C, 0x3A)
MUTED = RGBColor(0x6A, 0x75, 0x83)
LIGHT = RGBColor(0xF4, 0xF7, 0xFB)
LIGHT_BLUE = RGBColor(0xE8, 0xEF, 0xF7)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BORDER = RGBColor(0xD5, 0xDE, 0xEA)
SUCCESS_BG = RGBColor(0xE8, 0xF0, 0xF8)
WARN_BG = RGBColor(0xF3, 0xF6, 0xF9)


prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
prs.core_properties.author = "OpenAI Codex"
prs.core_properties.title = "基于知识图谱的电影推荐系统中期答辩汇报"
prs.core_properties.subject = "本科毕设中期答辩"
prs.core_properties.keywords = "Knowledge Graph, Recommendation, FastAPI, Vue3, Neo4j"


def set_slide_bg(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_textbox(
    slide,
    x,
    y,
    w,
    h,
    text="",
    *,
    font_size=18,
    font_face="微软雅黑",
    color=TEXT,
    bold=False,
    align=PP_ALIGN.LEFT,
    valign=MSO_VERTICAL_ANCHOR.TOP,
    margin=0.06,
):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = Inches(margin)
    tf.margin_right = Inches(margin)
    tf.margin_top = Inches(margin)
    tf.margin_bottom = Inches(margin)
    tf.vertical_anchor = valign
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    font = run.font
    font.name = font_face
    font.size = Pt(font_size)
    font.bold = bold
    font.color.rgb = color
    return box, tf


def add_rich_textbox(slide, x, y, w, h, lines, *, font_face="微软雅黑", font_size=18, color=TEXT):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = Inches(0.05)
    tf.margin_right = Inches(0.05)
    tf.margin_top = Inches(0.04)
    tf.margin_bottom = Inches(0.04)
    for idx, line in enumerate(lines):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        for seg_text, seg_bold, seg_color in line:
            run = p.add_run()
            run.text = seg_text
            font = run.font
            font.name = font_face
            font.size = Pt(font_size)
            font.bold = seg_bold
            font.color.rgb = seg_color or color
    return box


def add_bullets(slide, x, y, w, h, items, *, font_size=18, color=TEXT, level=0):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = Inches(0.04)
    tf.margin_right = Inches(0.02)
    tf.margin_top = Inches(0.02)
    tf.margin_bottom = Inches(0.02)
    for idx, item in enumerate(items):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.level = level
        p.bullet = True
        run = p.add_run()
        run.text = item
        font = run.font
        font.name = "微软雅黑"
        font.size = Pt(font_size)
        font.color.rgb = color
    return box


def add_round_card(slide, x, y, w, h, fill_color=WHITE, line_color=BORDER, radius=True):
    shape_type = MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE if radius else MSO_AUTO_SHAPE_TYPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.line.color.rgb = line_color
    shape.line.width = Pt(1.2)
    return shape


def add_title(slide, title, idx, *, dark=False):
    if dark:
        set_slide_bg(slide, PRIMARY_DARK)
        slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.RECTANGLE, Inches(0), Inches(0), Inches(0.35), Inches(7.5)
        ).fill.solid()
        slide.shapes[-1].fill.fore_color.rgb = PRIMARY
        slide.shapes[-1].line.fill.background()
        add_textbox(slide, 0.75, 0.45, 9.5, 0.7, title, font_size=28, color=WHITE, bold=True)
        page = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.OVAL, Inches(12.2), Inches(0.35), Inches(0.7), Inches(0.7))
        page.fill.solid()
        page.fill.fore_color.rgb = WHITE
        page.line.fill.background()
        add_textbox(slide, 12.28, 0.47, 0.5, 0.3, str(idx), font_size=15, color=PRIMARY_DARK, bold=True, align=PP_ALIGN.CENTER)
        return

    set_slide_bg(slide, WHITE)
    tag = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, Inches(0.55), Inches(0.45), Inches(0.26), Inches(0.26))
    tag.fill.solid()
    tag.fill.fore_color.rgb = PRIMARY
    tag.line.fill.background()
    add_textbox(slide, 0.9, 0.27, 10.5, 0.55, title, font_size=24, color=PRIMARY_DARK, bold=True)
    page = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.OVAL, Inches(12.2), Inches(0.27), Inches(0.6), Inches(0.6))
    page.fill.solid()
    page.fill.fore_color.rgb = PRIMARY
    page.line.fill.background()
    add_textbox(slide, 12.27, 0.38, 0.46, 0.22, str(idx), font_size=13, color=WHITE, bold=True, align=PP_ALIGN.CENTER)


def add_network_motif(slide, *, x_shift=0.0, y_shift=0.0, dark=False):
    line_color = LIGHT_BLUE if dark else BORDER
    node_fill = PRIMARY if not dark else WHITE
    node_alt = SECONDARY if not dark else LIGHT_BLUE
    lines = [
        (9.1, 1.3, 11.6, 2.0),
        (11.6, 2.0, 10.8, 3.1),
        (10.8, 3.1, 12.0, 4.2),
        (9.1, 1.3, 9.7, 4.0),
        (9.7, 4.0, 12.0, 4.2),
    ]
    for x1, y1, x2, y2 in lines:
        add_line(
            slide,
            x1 + x_shift,
            y1 + y_shift,
            x2 + x_shift,
            y2 + y_shift,
            color=line_color,
            width=1.6,
        )
    nodes = [
        (9.0, 1.15, 0.22, node_fill),
        (11.55, 1.95, 0.28, node_alt),
        (10.75, 3.0, 0.22, node_fill),
        (9.62, 3.9, 0.18, node_alt),
        (11.95, 4.12, 0.24, node_fill),
    ]
    for x, y, s, color in nodes:
        node = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.OVAL, Inches(x + x_shift), Inches(y + y_shift), Inches(s), Inches(s))
        node.fill.solid()
        node.fill.fore_color.rgb = color
        node.line.fill.background()


def add_card_with_title(slide, x, y, w, h, title, items, *, fill_color=WHITE):
    add_round_card(slide, x, y, w, h, fill_color=fill_color)
    add_textbox(slide, x + 0.18, y + 0.15, w - 0.36, 0.34, title, font_size=17, color=PRIMARY_DARK, bold=True)
    add_bullets(slide, x + 0.16, y + 0.55, w - 0.32, h - 0.72, items, font_size=15, color=TEXT)


def add_stat_card(slide, x, y, w, h, value, label):
    add_round_card(slide, x, y, w, h, fill_color=LIGHT_BLUE, line_color=LIGHT_BLUE)
    add_textbox(slide, x + 0.08, y + 0.15, w - 0.16, 0.55, value, font_size=24, color=PRIMARY_DARK, bold=True)
    add_textbox(slide, x + 0.08, y + 0.68, w - 0.16, 0.32, label, font_size=12.5, color=MUTED)


def add_table(slide, x, y, w, h, data, col_widths, *, header_fill=PRIMARY_DARK):
    rows = len(data)
    cols = len(data[0])
    table = slide.shapes.add_table(rows, cols, Inches(x), Inches(y), Inches(w), Inches(h)).table
    total = sum(col_widths)
    for c, width in enumerate(col_widths):
        table.columns[c].width = Inches(w * width / total)
    row_h = h / rows
    for r in range(rows):
        table.rows[r].height = Inches(row_h)
        for c in range(cols):
            cell = table.cell(r, c)
            cell.text = data[r][c]
            cell.fill.solid()
            cell.fill.fore_color.rgb = header_fill if r == 0 else WHITE
            if r > 0 and data[r][0].startswith("ItemCF"):
                cell.fill.fore_color.rgb = SUCCESS_BG
            if r > 0 and data[r][0].startswith("KG-Embed"):
                cell.fill.fore_color.rgb = WARN_BG
            for paragraph in cell.text_frame.paragraphs:
                paragraph.alignment = PP_ALIGN.CENTER
                for run in paragraph.runs:
                    run.font.name = "微软雅黑"
                    run.font.size = Pt(12.5 if r == 0 else 12)
                    run.font.bold = r == 0 or data[r][0].startswith("ItemCF") or (data[r][0].startswith("KG-Embed") and c == 0)
                    run.font.color.rgb = WHITE if r == 0 else TEXT
            cell.margin_left = Inches(0.02)
            cell.margin_right = Inches(0.02)
            cell.margin_top = Inches(0.03)
            cell.margin_bottom = Inches(0.03)
    return table


def add_chevron(slide, x, y, w=0.35, h=0.48):
    shape = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.CHEVRON, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = BORDER
    shape.line.fill.background()
    return shape


def add_line(slide, x1, y1, x2, y2, *, color=BORDER, width=1.3):
    line = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2)
    )
    line.line.color.rgb = color
    line.line.width = Pt(width)
    return line


def build_title_slide():
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, WHITE)
    band = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, Inches(0), Inches(0), Inches(3.2), Inches(7.5))
    band.fill.solid()
    band.fill.fore_color.rgb = PRIMARY_DARK
    band.line.fill.background()
    add_textbox(slide, 0.55, 0.68, 2.0, 0.3, "本科毕设中期答辩", font_size=13, color=LIGHT_BLUE, bold=True)
    add_textbox(slide, 0.55, 1.15, 2.3, 1.4, "基于知识图谱的\n电影推荐系统", font_size=28, color=WHITE, bold=True)
    add_textbox(slide, 0.55, 2.55, 2.2, 0.5, "Research & Implementation", font_size=14, color=LIGHT_BLUE)

    add_textbox(slide, 3.7, 0.92, 6.2, 0.55, "中期进展汇报", font_size=28, color=PRIMARY_DARK, bold=True)
    add_textbox(slide, 3.7, 1.55, 6.6, 0.6, "基于 MySQL + Neo4j + FastAPI + Vue3 的端到端推荐系统", font_size=16, color=SECONDARY)

    add_round_card(slide, 3.7, 2.25, 3.0, 1.75, fill_color=WHITE)
    add_textbox(slide, 3.95, 2.45, 0.9, 0.25, "学生", font_size=13, color=MUTED, bold=True)
    add_textbox(slide, 4.55, 2.36, 1.9, 0.35, "郭远信", font_size=22, color=PRIMARY_DARK, bold=True)
    add_textbox(slide, 3.95, 2.96, 0.9, 0.25, "学号", font_size=13, color=MUTED, bold=True)
    add_textbox(slide, 4.55, 2.90, 1.9, 0.3, "2022317220303", font_size=16, color=TEXT)
    add_textbox(slide, 3.95, 3.42, 1.1, 0.25, "专业班级", font_size=13, color=MUTED, bold=True)
    add_textbox(slide, 5.0, 3.36, 1.45, 0.3, "计科2201班", font_size=16, color=TEXT)

    add_round_card(slide, 6.95, 2.25, 3.0, 1.75, fill_color=WHITE)
    add_textbox(slide, 7.18, 2.45, 0.95, 0.25, "指导教师", font_size=13, color=MUTED, bold=True)
    add_textbox(slide, 8.1, 2.36, 1.5, 0.35, "李芳芳", font_size=22, color=PRIMARY_DARK, bold=True)
    add_textbox(slide, 7.18, 2.96, 0.95, 0.25, "职称", font_size=13, color=MUTED, bold=True)
    add_textbox(slide, 8.1, 2.90, 1.3, 0.3, "副教授", font_size=16, color=TEXT)
    add_textbox(slide, 7.18, 3.42, 0.95, 0.25, "时间", font_size=13, color=MUTED, bold=True)
    add_textbox(slide, 8.1, 3.36, 1.5, 0.3, "2026年3月", font_size=16, color=TEXT)

    add_stat_card(slide, 3.7, 4.45, 1.6, 1.1, "50+", "FastAPI 服务")
    add_stat_card(slide, 5.5, 4.45, 1.6, 1.1, "5", "推荐模块")
    add_stat_card(slide, 7.3, 4.45, 1.6, 1.1, "13", "Vue3 前端")
    add_stat_card(slide, 9.1, 4.45, 1.6, 1.1, "42/168", "验证/测试用户")

    add_network_motif(slide, x_shift=0.35, y_shift=0.6)


def build_background_slide():
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "研究背景与目标", 2)
    add_card_with_title(slide, 0.65, 1.1, 4.0, 2.2, "研究背景", ["评分数据稀疏", "冷启动较明显", "推荐解释不足"], fill_color=LIGHT)
    add_card_with_title(slide, 4.85, 1.1, 4.0, 2.2, "知识图谱优势", ["结构语义更强", "关联路径可解释", "适合多源融合"], fill_color=LIGHT)
    add_card_with_title(slide, 9.05, 1.1, 3.6, 2.2, "课题目标", ["构建电影图谱", "设计推荐方法", "实现完整系统"], fill_color=LIGHT)

    add_round_card(slide, 0.65, 3.65, 12.0, 2.95, fill_color=WHITE)
    add_textbox(slide, 0.92, 3.88, 2.0, 0.28, "本课题聚焦", font_size=16, color=MUTED, bold=True)
    add_rich_textbox(
        slide,
        0.92,
        4.2,
        11.0,
        1.9,
        [
            [("在电影推荐场景下，引入 ", False, None), ("Knowledge Graph", True, PRIMARY_DARK), (" 的结构化信息，", False, None)],
            [("同时结合 ", False, None), ("ItemCF", True, PRIMARY_DARK), ("、", False, None), ("KG-Path", True, PRIMARY_DARK), ("、", False, None), ("KG-Embed", True, PRIMARY_DARK), (" 和 ", False, None), ("CFKG", True, PRIMARY_DARK), ("，", False, None)],
            [("实现从数据采集、图谱构建到推荐服务与前端展示的端到端系统。", False, None)],
        ],
        font_size=21,
    )
    add_textbox(slide, 0.92, 6.05, 3.3, 0.28, "中期核心结论", font_size=16, color=MUTED, bold=True)
    add_textbox(slide, 3.0, 5.98, 8.8, 0.34, "系统主链路已贯通，实验框架已建立，下一阶段进入算法优化与论文撰写。", font_size=18, color=PRIMARY_DARK, bold=True)


def build_route_slide():
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "总体技术路线", 3)
    steps = [
        ("数据采集", "Playwright\n豆瓣页面"),
        ("数据清洗", "MySQL\n规则标准化"),
        ("图谱构建", "Neo4j\n节点与关系"),
        ("推荐计算", "5 种算法\nCFKG 融合"),
        ("系统展示", "FastAPI + Vue3\n解释与评测"),
    ]
    x = 0.75
    for idx, (title, body) in enumerate(steps):
        add_round_card(slide, x, 2.1, 2.1, 1.55, fill_color=LIGHT if idx % 2 == 0 else WHITE)
        add_textbox(slide, x + 0.16, 2.3, 1.7, 0.28, title, font_size=18, color=PRIMARY_DARK, bold=True, align=PP_ALIGN.CENTER)
        add_textbox(slide, x + 0.16, 2.72, 1.7, 0.52, body, font_size=15, color=TEXT, align=PP_ALIGN.CENTER)
        if idx < len(steps) - 1:
            add_chevron(slide, x + 2.22, 2.62)
        x += 2.55

    add_round_card(slide, 0.85, 4.35, 12.0, 1.8, fill_color=WHITE)
    add_textbox(slide, 1.08, 4.6, 1.9, 0.25, "方法特点", font_size=16, color=MUTED, bold=True)
    add_bullets(slide, 1.06, 4.95, 11.2, 0.9, ["数据链路闭环", "图谱与协同过滤并行", "支持推荐解释与离线评测"], font_size=17)
    add_network_motif(slide, x_shift=0.1, y_shift=0.1)


def build_graph_slide():
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "数据与图谱构建", 4)
    add_round_card(slide, 0.68, 1.15, 5.1, 5.75, fill_color=WHITE)
    add_textbox(slide, 0.95, 1.35, 2.0, 0.25, "数据流水线", font_size=17, color=PRIMARY_DARK, bold=True)

    pipeline = [
        ("豆瓣页面", 1.1, 1.8, 1.35, 0.6),
        ("crawl_movie.py", 1.1, 2.7, 1.75, 0.6),
        ("MySQL 清洗层", 1.1, 3.6, 1.75, 0.6),
        ("etl_to_neo4j.py", 1.1, 4.5, 1.85, 0.6),
        ("Neo4j 图谱", 1.1, 5.4, 1.45, 0.6),
    ]
    for idx, (label, x, y, w, h) in enumerate(pipeline):
        add_round_card(slide, x, y, w, h, fill_color=LIGHT if idx % 2 == 0 else LIGHT_BLUE)
        add_textbox(slide, x + 0.06, y + 0.13, w - 0.12, 0.25, label, font_size=15, color=PRIMARY_DARK, bold=True, align=PP_ALIGN.CENTER)
        if idx < len(pipeline) - 1:
            arrow = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.DOWN_ARROW, Inches(1.62), Inches(y + 0.65), Inches(0.3), Inches(0.24))
            arrow.fill.solid()
            arrow.fill.fore_color.rgb = BORDER
            arrow.line.fill.background()
    add_bullets(slide, 3.2, 1.8, 2.1, 3.5, ["主题页采集", "字段清洗标准化", "实体关系导入", "支持图谱查询"], font_size=15)

    add_round_card(slide, 6.05, 1.15, 6.55, 5.75, fill_color=WHITE)
    add_textbox(slide, 6.32, 1.35, 2.4, 0.25, "图谱模式", font_size=17, color=PRIMARY_DARK, bold=True)
    data = [
        ["类型", "内容"],
        ["节点", "Movie / Person / Genre / Region"],
        ["节点", "Language / YearBucket / ContentType"],
        ["关系", "DIRECTED / ACTED_IN / HAS_GENRE"],
        ["关系", "HAS_REGION / HAS_LANGUAGE / IN_YEAR_BUCKET"],
    ]
    add_table(slide, 6.32, 1.75, 5.8, 2.45, data, [1.1, 4.7])
    add_textbox(slide, 6.32, 4.45, 2.0, 0.24, "设计要点", font_size=16, color=MUTED, bold=True)
    add_bullets(slide, 6.25, 4.8, 5.9, 1.25, ["统一电影与影人 ID", "保留结构关系与属性", "为路径与嵌入方法服务"], font_size=16)


def build_arch_slide():
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "系统实现架构", 5)
    add_round_card(slide, 0.75, 1.2, 5.25, 5.6, fill_color=WHITE)
    add_textbox(slide, 1.02, 1.38, 2.3, 0.25, "系统分层", font_size=17, color=PRIMARY_DARK, bold=True)

    layers = [
        ("前端展示层", "Vue3 + Vite + Pinia", LIGHT_BLUE, 1.1),
        ("服务接口层", "FastAPI + 50+ APIs", LIGHT, 2.35),
        ("数据存储层", "MySQL + Neo4j", LIGHT_BLUE, 3.6),
        ("采集处理层", "Playwright + ETL", LIGHT, 4.85),
    ]
    for title, body, color, y in layers:
        add_round_card(slide, 1.1, y, 3.85, 0.88, fill_color=color)
        add_textbox(slide, 1.28, y + 0.12, 1.35, 0.22, title, font_size=15.5, color=PRIMARY_DARK, bold=True)
        add_textbox(slide, 2.68, y + 0.12, 2.0, 0.22, body, font_size=15, color=TEXT, align=PP_ALIGN.RIGHT)

    add_round_card(slide, 6.25, 1.2, 6.35, 5.6, fill_color=WHITE)
    add_textbox(slide, 6.52, 1.38, 2.7, 0.25, "模块完成情况", font_size=17, color=PRIMARY_DARK, bold=True)
    add_card_with_title(slide, 6.5, 1.78, 2.85, 1.75, "后端模块", ["movies / persons", "graph / stats", "auth / users"], fill_color=LIGHT)
    add_card_with_title(slide, 9.45, 1.78, 2.85, 1.75, "推荐模块", ["content", "ItemCF", "KG-Path / KG-Embed"], fill_color=LIGHT)
    add_card_with_title(slide, 6.5, 3.78, 2.85, 1.75, "前端模块", ["推荐页", "搜索与详情", "图谱与统计"], fill_color=LIGHT)
    add_card_with_title(slide, 9.45, 3.78, 2.85, 1.75, "验证模块", ["离线评测", "算法对比", "回归测试"], fill_color=LIGHT)
    add_stat_card(slide, 6.58, 5.95, 1.55, 0.78, "50+", "FastAPI 接口")
    add_stat_card(slide, 8.35, 5.95, 1.55, 0.78, "5", "推荐算法")
    add_stat_card(slide, 10.12, 5.95, 1.55, 0.78, "13", "前端页面")


def build_method_slide():
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "推荐方法设计", 6)
    add_round_card(slide, 0.7, 1.15, 7.0, 5.7, fill_color=WHITE)
    add_textbox(slide, 0.96, 1.34, 2.3, 0.25, "CFKG 主链路", font_size=17, color=PRIMARY_DARK, bold=True)

    start = add_round_card(slide, 1.0, 2.15, 1.6, 0.82, fill_color=LIGHT_BLUE)
    add_textbox(slide, 1.07, 2.37, 1.45, 0.22, "用户行为", font_size=16, color=PRIMARY_DARK, bold=True, align=PP_ALIGN.CENTER)
    add_textbox(slide, 0.98, 2.63, 1.6, 0.2, "评分 / 偏好 / Wish", font_size=11.5, color=MUTED, align=PP_ALIGN.CENTER)

    branches = [
        ("content", 3.0, 1.75),
        ("ItemCF", 3.0, 2.7),
        ("KG-Path", 3.0, 3.65),
        ("KG-Embed", 3.0, 4.6),
    ]
    for label, x, y in branches:
        add_round_card(slide, x, y, 1.8, 0.62, fill_color=LIGHT)
        add_textbox(slide, x + 0.07, y + 0.14, 1.65, 0.2, label, font_size=14.5, color=PRIMARY_DARK, bold=True, align=PP_ALIGN.CENTER)
        add_line(slide, 2.6, 2.55, 3.0, y + 0.31, color=BORDER, width=1.3)

    fusion = add_round_card(slide, 5.45, 2.65, 1.55, 1.05, fill_color=LIGHT_BLUE)
    add_textbox(slide, 5.55, 2.93, 1.35, 0.22, "CFKG", font_size=20, color=PRIMARY_DARK, bold=True, align=PP_ALIGN.CENTER)
    add_textbox(slide, 5.52, 3.2, 1.35, 0.18, "融合排序", font_size=11.5, color=MUTED, align=PP_ALIGN.CENTER)
    for _, x, y in branches:
        add_line(slide, x + 1.8, y + 0.31, 5.45, 3.18, color=BORDER, width=1.3)
    result_box = add_round_card(slide, 5.35, 4.55, 1.75, 0.85, fill_color=LIGHT)
    add_textbox(slide, 5.47, 4.84, 1.5, 0.2, "推荐结果 + 解释", font_size=14, color=PRIMARY_DARK, bold=True, align=PP_ALIGN.CENTER)

    add_round_card(slide, 7.95, 1.15, 4.7, 5.7, fill_color=WHITE)
    add_textbox(slide, 8.2, 1.34, 2.0, 0.25, "各方法角色", font_size=17, color=PRIMARY_DARK, bold=True)
    add_card_with_title(slide, 8.15, 1.8, 4.25, 0.98, "content / ItemCF", ["基线对照", "保证稳定召回"], fill_color=LIGHT)
    add_card_with_title(slide, 8.15, 2.95, 4.25, 0.98, "KG-Path", ["利用显式关系", "支持路径解释"], fill_color=LIGHT)
    add_card_with_title(slide, 8.15, 4.1, 4.25, 0.98, "KG-Embed", ["学习潜在语义", "增强泛化能力"], fill_color=LIGHT)
    add_card_with_title(slide, 8.15, 5.25, 4.25, 0.98, "CFKG", ["多分支融合", "平衡精度与解释"], fill_color=LIGHT)


def build_progress_slide():
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "阶段成果概览", 7)
    add_card_with_title(slide, 0.7, 1.15, 3.0, 2.1, "数据链路", ["采集脚本完成", "清洗流程完成", "图谱 ETL 可用"], fill_color=LIGHT)
    add_card_with_title(slide, 3.95, 1.15, 3.0, 2.1, "服务能力", ["50+ APIs", "推荐解释接口", "评测报告接口"], fill_color=LIGHT)
    add_card_with_title(slide, 7.2, 1.15, 2.8, 2.1, "前端展示", ["推荐页完成", "搜索详情完成", "图谱统计可用"], fill_color=LIGHT)
    add_card_with_title(slide, 10.25, 1.15, 2.35, 2.1, "验证保障", ["11 个测试文件", "离线评测流程", "回归检查"], fill_color=LIGHT)

    add_round_card(slide, 0.7, 3.55, 11.9, 2.95, fill_color=WHITE)
    add_textbox(slide, 0.95, 3.78, 2.2, 0.25, "已完成工作", font_size=17, color=PRIMARY_DARK, bold=True)
    add_bullets(slide, 0.92, 4.15, 5.5, 1.8, ["完成系统总体架构", "完成 5 种推荐算法", "完成推荐页与评测页", "完成中期材料整理"], font_size=18)
    add_textbox(slide, 6.45, 3.78, 2.5, 0.25, "中期判断", font_size=17, color=PRIMARY_DARK, bold=True)
    add_rich_textbox(
        slide,
        6.45,
        4.15,
        5.5,
        1.75,
        [
            [("系统主链路已打通，", False, None), ("中期阶段目标基本达成。", True, PRIMARY_DARK)],
            [("当前重点从“功能实现”转向“效果优化 + 论文撰写”。", False, None)],
        ],
        font_size=20,
    )


def build_eval_slide():
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "实验设置与评测协议", 8)
    add_round_card(slide, 0.68, 1.15, 5.3, 5.8, fill_color=WHITE)
    add_textbox(slide, 0.95, 1.35, 2.5, 0.25, "评测设置", font_size=17, color=PRIMARY_DARK, bold=True)
    data = [
        ["项目", "配置"],
        ["用户来源", "公开豆瓣用户"],
        ["验证 / 测试", "42 / 168"],
        ["协议", "sampled leave-one-out"],
        ["候选集", "1 positive + 99 negatives"],
        ["指标", "HR@K / NDCG@K / Time"],
    ]
    add_table(slide, 0.95, 1.75, 4.75, 3.05, data, [1.65, 3.1])
    add_bullets(slide, 0.93, 5.0, 4.85, 1.2, ["多 seed 评测", "支持消融实验", "支持报告导出"], font_size=16)

    add_round_card(slide, 6.25, 1.15, 6.35, 5.8, fill_color=WHITE)
    add_textbox(slide, 6.52, 1.35, 3.0, 0.25, "评测流程", font_size=17, color=PRIMARY_DARK, bold=True)
    flow = [
        ("行为数据", 6.55, 2.0, 1.55),
        ("正样本抽取", 8.25, 2.0, 1.75),
        ("负采样", 10.2, 2.0, 1.2),
        ("指标计算", 8.25, 3.35, 1.75),
        ("报告输出", 10.2, 3.35, 1.55),
    ]
    for idx, (label, x, y, w) in enumerate(flow):
        add_round_card(slide, x, y, w, 0.72, fill_color=LIGHT if idx % 2 else LIGHT_BLUE)
        add_textbox(slide, x + 0.06, y + 0.18, w - 0.12, 0.2, label, font_size=14.5, color=PRIMARY_DARK, bold=True, align=PP_ALIGN.CENTER)
    for x1, y1, x2, y2 in [(8.1, 2.36, 8.2, 2.36), (10.0, 2.36, 10.2, 2.36), (11.0, 2.72, 10.9, 3.35), (10.0, 3.72, 10.2, 3.72)]:
        add_line(slide, x1, y1, x2, y2, color=BORDER, width=1.2)
    add_rich_textbox(
        slide,
        6.55,
        4.7,
        5.5,
        1.35,
        [
            [("协议版本：", False, None), ("v2", True, PRIMARY_DARK)],
            [("主表展示：", False, None), ("HR@K 与 NDCG@K", True, PRIMARY_DARK)],
            [("补充分析：", False, None), ("Coverage / Diversity / Time", True, PRIMARY_DARK)],
        ],
        font_size=18,
    )


def build_result_slide():
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "离线结果对比", 9)
    add_round_card(slide, 0.68, 1.15, 8.2, 5.75, fill_color=WHITE)
    add_textbox(slide, 0.95, 1.35, 2.6, 0.25, "K = 10 结果", font_size=17, color=PRIMARY_DARK, bold=True)
    table_data = [
        ["算法", "HR@10", "NDCG@10", "Avg Time (s)"],
        ["CFKG", "0.4393", "0.3156", "18.59"],
        ["content", "0.3678", "0.1846", "0.25"],
        ["ItemCF", "0.8083", "0.5992", "0.54"],
        ["KG-Path", "0.3702", "0.2573", "3.34"],
        ["KG-Embed", "0.5333", "0.3330", "5.98"],
    ]
    add_table(slide, 0.95, 1.75, 7.7, 3.35, table_data, [2.3, 1.6, 1.8, 2.0])
    add_bullets(slide, 0.92, 5.3, 7.75, 0.95, ["ItemCF 当前整体最优", "KG-Embed 是当前最佳图谱方法", "CFKG 仍有优化空间"], font_size=18)

    add_round_card(slide, 9.1, 1.15, 3.45, 5.75, fill_color=WHITE)
    add_textbox(slide, 9.35, 1.35, 2.4, 0.25, "核心观察", font_size=17, color=PRIMARY_DARK, bold=True)
    add_stat_card(slide, 9.35, 1.85, 2.95, 1.05, "0.8083", "ItemCF 的 HR@10")
    add_stat_card(slide, 9.35, 3.05, 2.95, 1.05, "0.5333", "KG-Embed 的 HR@10")
    add_round_card(slide, 9.35, 4.33, 2.95, 1.45, fill_color=LIGHT)
    add_rich_textbox(
        slide,
        9.5,
        4.52,
        2.65,
        1.1,
        [
            [("结论：", True, PRIMARY_DARK), ("图谱方法已体现效果，", False, None)],
            [("但需要继续提升 ", False, None), ("CFKG", True, PRIMARY_DARK), (" 的融合质量。", False, None)],
        ],
        font_size=16,
    )


def build_issue_slide():
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "当前问题与中期判断", 10)
    add_card_with_title(slide, 0.68, 1.15, 5.8, 5.7, "当前问题", ["CFKG 精度偏低", "融合耗时偏长", "论文正文待启动"], fill_color=WHITE)
    add_round_card(slide, 0.95, 3.2, 5.25, 2.95, fill_color=LIGHT)
    add_bullets(slide, 1.08, 3.45, 4.95, 2.25, ["问题一：主链路效果仍低于 ItemCF", "问题二：图谱缓存与评测耗时较高", "问题三：论文只完成提纲与材料梳理"], font_size=17)

    add_card_with_title(slide, 6.75, 1.15, 5.9, 5.7, "中期判断", ["系统已基本成型", "实验框架已可复用", "具备继续优化条件"], fill_color=WHITE)
    add_round_card(slide, 7.02, 3.2, 5.35, 2.95, fill_color=LIGHT_BLUE)
    add_rich_textbox(
        slide,
        7.18,
        3.48,
        4.95,
        2.2,
        [
            [("中期阶段已完成：", True, PRIMARY_DARK)],
            [("数据链路、图谱构建、算法实现、系统展示。", False, None)],
            [("下一阶段重点：", True, PRIMARY_DARK)],
            [("算法优化、实验分析、论文写作。", False, None)],
        ],
        font_size=20,
    )


def build_plan_slide():
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "下一阶段计划", 11)
    items = [
        ("算法优化", ["调 CFKG 权重", "完善 ablation", "压缩响应时间"]),
        ("论文写作", ["完成摘要与绪论", "撰写系统设计", "整理实验分析"]),
        ("答辩准备", ["补充截图图表", "优化汇报逻辑", "整理问答要点"]),
    ]
    x_positions = [0.78, 4.55, 8.32]
    for (title, bullets), x in zip(items, x_positions):
        add_round_card(slide, x, 1.55, 3.35, 4.65, fill_color=WHITE)
        badge = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.OVAL, Inches(x + 0.18), Inches(1.72), Inches(0.52), Inches(0.52))
        badge.fill.solid()
        badge.fill.fore_color.rgb = PRIMARY
        badge.line.fill.background()
        add_textbox(slide, x + 0.82, 1.73, 2.1, 0.28, title, font_size=19, color=PRIMARY_DARK, bold=True)
        add_bullets(slide, x + 0.2, 2.45, 2.95, 1.3, bullets, font_size=17)
        add_textbox(slide, x + 0.2, 4.2, 1.6, 0.22, "阶段目标", font_size=14, color=MUTED, bold=True)
        goal = {
            "算法优化": "提升主链路效果",
            "论文写作": "形成前几章初稿",
            "答辩准备": "完成中后期展示材料",
        }[title]
        add_textbox(slide, x + 0.2, 4.48, 2.75, 0.52, goal, font_size=18, color=PRIMARY_DARK, bold=True)

    add_round_card(slide, 0.78, 6.45, 10.9, 0.6, fill_color=LIGHT)
    add_textbox(slide, 0.98, 6.57, 10.5, 0.25, "预期结果：算法进一步优化，论文正文启动，答辩材料逐步完善。", font_size=18, color=PRIMARY_DARK, bold=True, align=PP_ALIGN.CENTER)


def build_end_slide():
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "汇报结束", 12, dark=True)
    add_textbox(slide, 0.85, 2.05, 6.3, 0.85, "感谢各位老师指正", font_size=30, color=WHITE, bold=True)
    add_textbox(slide, 0.88, 3.05, 6.1, 0.5, "Questions & Discussion", font_size=18, color=LIGHT_BLUE)
    add_textbox(slide, 0.88, 4.35, 6.8, 0.55, "基于知识图谱的电影推荐系统", font_size=20, color=WHITE, bold=True)
    add_textbox(slide, 0.88, 4.95, 4.5, 0.3, "郭远信  |  指导教师：李芳芳", font_size=14, color=LIGHT_BLUE)
    add_network_motif(slide, x_shift=0.2, y_shift=0.25, dark=True)


build_title_slide()
build_background_slide()
build_route_slide()
build_graph_slide()
build_arch_slide()
build_method_slide()
build_progress_slide()
build_eval_slide()
build_result_slide()
build_issue_slide()
build_plan_slide()
build_end_slide()

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
prs.save(str(OUT_PATH))
print(OUT_PATH)
