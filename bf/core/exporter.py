"""
PDF 报表导出。

使用 ReportLab 渲染，支持:
    - 资产负债表
    - 利润表
    - 明细账导出
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


# 注册中文字体
def _register_chinese_fonts() -> None:
    """注册系统中文字体到 ReportLab。"""
    # Windows 常见中文字体路径（按优先级排序）
    font_paths = [
        (r"C:\Windows\Fonts\simhei.ttf", "SimHei"),  # 黑体
        (r"C:\Windows\Fonts\simsun.ttc", "SimSun"),  # 宋体
        (r"C:\Windows\Fonts\msyh.ttc", "MicrosoftYaHei"),  # 微软雅黑
        (r"C:\Windows\Fonts\msyh.ttf", "MicrosoftYaHei"),  # 微软雅黑（备用路径）
    ]
    
    for font_path, font_name in font_paths:
        if os.path.exists(font_path):
            try:
                # 检查是否已注册
                if font_name not in [f[0] for f in pdfmetrics.getRegisteredFontNames()]:
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
            except Exception as e:
                pass  # 静默失败，继续尝试下一个
    
    # 创建一个别名，让 SimHei 也可以作为粗体使用
    try:
        if "SimHei" in [f[0] for f in pdfmetrics.getRegisteredFontNames()]:
            if "MicrosoftYaHei-Bold" not in [f[0] for f in pdfmetrics.getRegisteredFontNames()]:
                pdfmetrics.registerFont(TTFont("MicrosoftYaHei-Bold", r"C:\Windows\Fonts\simhei.ttf"))
    except Exception:
        pass


class PDFExporter:
    """PDF 会计账簿导出器。"""

    def __init__(self, output_path: Path) -> None:
        if not HAS_REPORTLAB:
            raise RuntimeError("需要安装 reportlab: pip install reportlab")
        self.output_path = Path(output_path).resolve()
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 注册中文字体
        _register_chinese_fonts()
        
        # 创建支持中文的样式
        self.styles = getSampleStyleSheet()
        self._setup_chinese_styles()
        self._story = []
    
    def _setup_chinese_styles(self) -> None:
        """设置支持中文的 Paragraph 样式。"""
        # 获取已注册的字体列表
        registered_fonts = [f[0] for f in pdfmetrics.getRegisteredFontNames()]
        
        # 强制使用 SimHei（和表格字体一致）
        chinese_font = "SimHei" if "SimHei" in registered_fonts else None
        
        if not chinese_font:
            # 如果没有 SimHei，尝试其他字体
            for font_name in ["MicrosoftYaHei", "SimSun"]:
                if font_name in registered_fonts:
                    chinese_font = font_name
                    break
        
        if chinese_font:
            # 标题样式 - 使用 SimHei
            self.styles.add(ParagraphStyle(
                name='ChineseTitle',
                parent=self.styles['Title'],
                fontName=chinese_font,
                fontSize=18,
                leading=22,
            ))
            # 副标题样式
            self.styles.add(ParagraphStyle(
                name='ChineseHeading2',
                parent=self.styles['Heading2'],
                fontName=chinese_font,
                fontSize=14,
                leading=18,
            ))
            self.styles.add(ParagraphStyle(
                name='ChineseHeading3',
                parent=self.styles['Heading3'],
                fontName=chinese_font,
                fontSize=12,
                leading=14,
            ))
            # 正文样式
            self.styles.add(ParagraphStyle(
                name='ChineseNormal',
                parent=self.styles['Normal'],
                fontName=chinese_font,
                fontSize=10,
                leading=12,
            ))
            # 表格样式
            self.styles.add(ParagraphStyle(
                name='ChineseTable',
                parent=self.styles['Normal'],
                fontName=chinese_font,
                fontSize=9,
                leading=11,
            ))
        else:
            # 如果没有中文字体，使用默认样式（但中文会显示为方块）
            self.styles.add(ParagraphStyle(name='ChineseTitle', parent=self.styles['Title']))
            self.styles.add(ParagraphStyle(name='ChineseHeading2', parent=self.styles['Heading2']))
            self.styles.add(ParagraphStyle(name='ChineseHeading3', parent=self.styles['Heading3']))
            self.styles.add(ParagraphStyle(name='ChineseNormal', parent=self.styles['Normal']))
            self.styles.add(ParagraphStyle(name='ChineseTable', parent=self.styles['Normal']))

    def add_title(self, text: str) -> None:
        """添加标题 - 使用 Table 而非 Paragraph 以确保中文正常显示。"""
        # 使用单格表格来显示标题，确保字体正确应用
        title_table = Table([[text]])
        title_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "SimHei"),
            ("FONTSIZE", (0, 0), (-1, -1), 18),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        self._story.append(title_table)
        self._story.append(Spacer(1, 6 * mm))

    def add_heading(self, text: str, level: int = 2) -> None:
        """添加副标题 - 使用 Table 确保中文正常显示。"""
        font_size = 14 if level == 2 else 12
        heading_table = Table([[text]])
        heading_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "SimHei"),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        self._story.append(heading_table)
        self._story.append(Spacer(1, 3 * mm))

    def add_paragraph(self, text: str) -> None:
        """添加段落 - 使用 Table 确保中文正常显示。"""
        para_table = Table([[text]])
        para_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "SimHei"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        self._story.append(para_table)
        self._story.append(Spacer(1, 2 * mm))

    def add_table(self, headers: list[str], rows: list[list[str]], title: str = "") -> None:
        if title:
            self.add_heading(title, 3)
        data = [headers] + rows
        table = Table(data, repeatRows=1)
        # 使用黑体作为表头（粗体效果），微软雅黑作为表格正文
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "SimHei"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f5f6fa")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 1), (-1, -1), "MicrosoftYaHei"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ]))
        self._story.append(table)
        self._story.append(Spacer(1, 4 * mm))

    def add_balance_sheet(self, assets: list[tuple[str, str]], liabilities: list[tuple[str, str]], equity: list[tuple[str, str]]) -> None:
        """添加资产负债表。

        Args:
            assets: [(科目名, 金额), ...]
            liabilities: [(科目名, 金额), ...]
            equity: [(科目名, 金额), ...]
        """
        self.add_heading("资产负债表")
        self.add_table(
            ["科目", "金额"],
            [(a, v) for a, v in assets] + [("资产总计", "")]
            + [(l, v) for l, v in liabilities] + [("负债总计", "")]
            + [(e, v) for e, v in equity] + [("权益总计", "")]
        )

    def add_income_statement(self, income: list[tuple[str, str]], expenses: list[tuple[str, str]], net_profit: str) -> None:
        """添加利润表。"""
        self.add_heading("利润表")
        self.add_table(
            ["科目", "金额"],
            [(i, v) for i, v in income]
            + [("收入合计", "")]
            + [(e, v) for e, v in expenses]
            + [("费用合计", "")]
            + [("净利润", net_profit)]
        )

    def add_detail_ledger(self, entries: list[dict]) -> None:
        """添加明细账。

        Args:
            entries: [{"date": "...", "narration": "...", "account": "...", "debit": "...", "credit": "..."}, ...]
        """
        self.add_heading("明细账")
        self.add_table(
            ["日期", "摘要", "科目", "借方", "贷方"],
            [[e.get("date", ""), e.get("narration", ""), e.get("account", ""),
              e.get("debit", ""), e.get("credit", "")] for e in entries]
        )

    def render(self) -> Path:
        """渲染并保存 PDF。"""
        doc = SimpleDocTemplate(
            str(self.output_path),
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
        )
        doc.build(self._story)
        return self.output_path