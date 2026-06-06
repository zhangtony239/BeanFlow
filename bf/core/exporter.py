"""
PDF 与 Excel 报表导出器。

采用 Provider-Exporter 模式，解耦报表数据源与导出格式。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..project import Project
    from .config import MappingDictionary

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
HAS_REPORTLAB = True


# 注册中文字体
def _register_chinese_fonts() -> None:
    """注册系统中文字体到 ReportLab。"""
    if not HAS_REPORTLAB:
        return
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
                if font_name not in [f[0] for f in pdfmetrics.getRegisteredFontNames()]:
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
            except Exception:
                pass
    
    try:
        if "SimHei" in [f[0] for f in pdfmetrics.getRegisteredFontNames()]:
            if "MicrosoftYaHei-Bold" not in [f[0] for f in pdfmetrics.getRegisteredFontNames()]:
                pdfmetrics.registerFont(TTFont("MicrosoftYaHei-Bold", r"C:\Windows\Fonts\simhei.ttf"))
    except Exception:
        pass


# ═══════════════════════════════════════════════════
# 1. Report Data Model
# ═══════════════════════════════════════════════════

class ReportData(BaseModel):
    """报表数据模型。"""
    title: str
    headers: List[str]
    rows: List[List[str]]
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════
# 2. Base & Special Report Providers
# ═══════════════════════════════════════════════════

class BaseReportProvider(ABC):
    """报表数据源抽象基类。"""
    
    def __init__(self, project: Project) -> None:
        self.project = project
        self.mapping = project.mapping

    @abstractmethod
    def get_balance_sheet_data(self) -> ReportData:
        """获取资产负债表数据。"""
        pass

    @abstractmethod
    def get_income_statement_data(self) -> ReportData:
        """获取利润表数据。"""
        pass

    @abstractmethod
    def get_detail_ledger_data(self) -> ReportData:
        """获取明细账数据。"""
        pass


class EnterpriseReportProvider(BaseReportProvider):
    """企业标准报表数据源。"""

    def _get_friendly_name(self, account_id: str) -> str:
        if self.mapping:
            # 尝试通过 ID 获取
            entry = self.mapping.get_by_id(account_id)
            if not entry:
                # 尝试通过别名解析
                try:
                    entry = self.mapping.resolve_alias(account_id)
                except KeyError:
                    pass
            if entry and entry.names:
                for name in reversed(entry.names):
                    if any('\u4e00' <= char <= '\u9fff' for char in name):
                        return name
                return entry.names[0]
        return account_id

    def _get_standard_id(self, account_id: str) -> str:
        if self.mapping:
            try:
                entry = self.mapping.resolve_alias(account_id)
                return entry.id
            except KeyError:
                pass
        return account_id

    def _parse_balances(self) -> dict[str, float]:
        from decimal import Decimal
        from collections import defaultdict
        balances = defaultdict(Decimal)
        content = self.project.read_bean()
        for line in content.splitlines():
            raw_line = line
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            
            # 排除交易头部
            parts = line.split()
            if len(parts) >= 2 and parts[0].count("-") == 2 and parts[0].replace("-", "").isdigit():
                continue
                
            if raw_line.startswith((" ", "\t")):
                if len(parts) >= 2:
                    acc = parts[0]
                    if acc in ("open", "close", "balance", "commodity", "custom", "document", "note", "event", "query"):
                        continue
                    for p in parts[1:]:
                        if p.replace(".", "").replace("-", "").isdigit():
                            try:
                                balances[acc] += Decimal(p)
                            except Exception:
                                pass
                            break
        return {k: float(v) for k, v in balances.items()}

    def get_balance_sheet_data(self) -> ReportData:
        balances = self._parse_balances()
        assets = []
        liabilities = []
        equity = []
        
        total_assets = 0.0
        total_liabilities = 0.0
        total_equity = 0.0

        for acc, val in balances.items():
            friendly = self._get_friendly_name(acc)
            standard_id = self._get_standard_id(acc)
            if standard_id.lower().startswith("assets"):
                assets.append([friendly, f"{val:.2f}"])
                total_assets += val
            elif standard_id.lower().startswith("liabilities"):
                liabilities.append([friendly, f"{-val:.2f}"])  # 贷方科目取反显示
                total_liabilities += -val
            elif standard_id.lower().startswith("equity"):
                equity.append([friendly, f"{-val:.2f}"])  # 贷方科目取反显示
                total_equity += -val

        rows = []
        rows.extend(assets)
        rows.append(["资产总计", f"{total_assets:.2f}"])
        rows.extend(liabilities)
        rows.append(["负债总计", f"{total_liabilities:.2f}"])
        rows.extend(equity)
        rows.append(["权益总计", f"{total_equity:.2f}"])

        return ReportData(
            title=f"资产负债表 - {self.project.name}",
            headers=["科目", "金额"],
            rows=rows,
            metadata={"project": self.project.name, "type": "balance_sheet"}
        )

    def get_income_statement_data(self) -> ReportData:
        balances = self._parse_balances()
        income = []
        expenses = []
        
        total_income = 0.0
        total_expenses = 0.0

        for acc, val in balances.items():
            friendly = self._get_friendly_name(acc)
            standard_id = self._get_standard_id(acc)
            if standard_id.lower().startswith("income"):
                income.append([friendly, f"{-val:.2f}"])  # 贷方科目取反显示
                total_income += -val
            elif standard_id.lower().startswith("expenses") or standard_id.lower().startswith("fee"):
                expenses.append([friendly, f"{val:.2f}"])
                total_expenses += val

        net_profit = total_income - total_expenses

        rows = []
        rows.extend(income)
        rows.append(["收入合计", f"{total_income:.2f}"])
        rows.extend(expenses)
        rows.append(["费用合计", f"{total_expenses:.2f}"])
        rows.append(["净利润", f"{net_profit:.2f}"])

        return ReportData(
            title=f"利润表 - {self.project.name}",
            headers=["科目", "金额"],
            rows=rows,
            metadata={"project": self.project.name, "type": "income_statement"}
        )

    def get_detail_ledger_data(self) -> ReportData:
        content = self.project.read_bean()
        rows = []
        current_date = ""
        current_narration = ""
        
        for line in content.splitlines():
            raw_line = line
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            
            parts = line.split(None, 2)
            if len(parts) >= 2 and parts[0].count("-") == 2 and parts[0].replace("-", "").isdigit():
                current_date = parts[0]
                narr = parts[2] if len(parts) > 2 else ""
                current_narration = narr.strip('"')
                continue
                
            if raw_line.startswith((" ", "\t")):
                parts = line.split()
                if len(parts) >= 2:
                    acc = parts[0]
                    if acc in ("open", "close", "balance", "commodity", "custom", "document", "note", "event", "query"):
                        continue
                    friendly = self._get_friendly_name(acc)
                    val_str = ""
                    for p in parts[1:]:
                        if p.replace(".", "").replace("-", "").isdigit():
                            val_str = p
                            break
                    
                    debit = ""
                    credit = ""
                    if val_str:
                        val = float(val_str)
                        if val >= 0:
                            debit = f"{val:.2f}"
                        else:
                            credit = f"{-val:.2f}"
                            
                    rows.append([current_date, current_narration, friendly, debit, credit])

        return ReportData(
            title=f"明细账 - {self.project.name}",
            headers=["日期", "摘要", "科目", "借方", "贷方"],
            rows=rows,
            metadata={"project": self.project.name, "type": "detail_ledger"}
        )


class CashFlowReportProvider(BaseReportProvider):
    """现金流量表数据源。"""

    def get_balance_sheet_data(self) -> ReportData:
        return ReportData(title="现金流量表-资产负债数据", headers=["科目", "金额"], rows=[])

    def get_income_statement_data(self) -> ReportData:
        return ReportData(title="现金流量表-利润数据", headers=["科目", "金额"], rows=[])

    def get_detail_ledger_data(self) -> ReportData:
        # 简单归类经营、投资、筹资活动
        content = self.project.read_bean()
        rows = []
        current_date = ""
        current_narration = ""
        
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            
            parts = line.split(None, 2)
            if len(parts) >= 2 and parts[0].count("-") == 2 and parts[0].replace("-", "").isdigit():
                current_date = parts[0]
                narr = parts[2] if len(parts) > 2 else ""
                current_narration = narr.strip('"')
                continue
                
            if ":" in line:
                parts = line.split()
                if len(parts) >= 2:
                    acc = parts[0]
                    val_str = ""
                    for p in parts[1:]:
                        if p.replace(".", "").replace("-", "").isdigit():
                            val_str = p
                            break
                    
                    if val_str:
                        val = float(val_str)
                        # 归类逻辑
                        category = "经营活动"
                        if "loan" in acc.lower() or "equity" in acc.lower() or "capital" in acc.lower():
                            category = "筹资活动"
                        elif "equipment" in acc.lower() or "invest" in acc.lower():
                            category = "投资活动"
                            
                        rows.append([current_date, current_narration, acc, f"{val:.2f}", category])

        return ReportData(
            title=f"现金流量明细 - {self.project.name}",
            headers=["日期", "摘要", "科目", "金额", "流量类别"],
            rows=rows,
            metadata={"project": self.project.name, "type": "cash_flow"}
        )


class TaxReportProvider(BaseReportProvider):
    """财税报表数据源。"""

    def get_balance_sheet_data(self) -> ReportData:
        return ReportData(title="财税报表-资产负债数据", headers=["科目", "金额"], rows=[])

    def get_income_statement_data(self) -> ReportData:
        return ReportData(title="财税报表-利润数据", headers=["科目", "金额"], rows=[])

    def get_detail_ledger_data(self) -> ReportData:
        # 自动计算增值税辅助数据
        tax_rate = self.project.env.project.tax_rate
        content = self.project.read_bean()
        rows = []
        current_date = ""
        current_narration = ""
        
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            
            parts = line.split(None, 2)
            if len(parts) >= 2 and parts[0].count("-") == 2 and parts[0].replace("-", "").isdigit():
                current_date = parts[0]
                narr = parts[2] if len(parts) > 2 else ""
                current_narration = narr.strip('"')
                continue
                
            if ":" in line:
                parts = line.split()
                if len(parts) >= 2:
                    acc = parts[0]
                    val_str = ""
                    for p in parts[1:]:
                        if p.replace(".", "").replace("-", "").isdigit():
                            val_str = p
                            break
                    
                    if val_str:
                        val = float(val_str)
                        tax_amount = val * tax_rate
                        rows.append([current_date, current_narration, acc, f"{val:.2f}", f"{tax_rate*100}%", f"{tax_amount:.2f}"])

        return ReportData(
            title=f"财税申报辅助表 - {self.project.name}",
            headers=["日期", "摘要", "科目", "不含税金额", "税率", "估算税额"],
            rows=rows,
            metadata={"project": self.project.name, "type": "tax_report"}
        )


# ═══════════════════════════════════════════════════
# 3. Base & Special Exporters
# ═══════════════════════════════════════════════════

class BaseExporter(ABC):
    """报表导出器抽象基类。"""

    def __init__(self, output_path: Path) -> None:
        self.output_path = Path(output_path).resolve()

    @abstractmethod
    def export_report(self, report_data: ReportData) -> None:
        """导出单张报表。"""
        pass


class PDFExporter(BaseExporter):
    """PDF 会计账簿导出器。"""

    def __init__(self, output_path: Path) -> None:
        super().__init__(output_path)
        if not HAS_REPORTLAB:
            raise RuntimeError("需要安装 reportlab: pip install reportlab")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        
        _register_chinese_fonts()
        self.styles = getSampleStyleSheet()
        self._setup_chinese_styles()
        self._story = []
    
    def _setup_chinese_styles(self) -> None:
        """设置支持中文的 Paragraph 样式。"""
        registered_fonts = [f[0] for f in pdfmetrics.getRegisteredFontNames()]
        chinese_font = "SimHei" if "SimHei" in registered_fonts else None
        
        if not chinese_font:
            for font_name in ["MicrosoftYaHei", "SimSun"]:
                if font_name in registered_fonts:
                    chinese_font = font_name
                    break
        
        if chinese_font:
            self.styles.add(ParagraphStyle(
                name='ChineseTitle',
                parent=self.styles['Title'],
                fontName=chinese_font,
                fontSize=18,
                leading=22,
            ))
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
            self.styles.add(ParagraphStyle(
                name='ChineseNormal',
                parent=self.styles['Normal'],
                fontName=chinese_font,
                fontSize=10,
                leading=12,
            ))
            self.styles.add(ParagraphStyle(
                name='ChineseTable',
                parent=self.styles['Normal'],
                fontName=chinese_font,
                fontSize=9,
                leading=11,
            ))
        else:
            self.styles.add(ParagraphStyle(name='ChineseTitle', parent=self.styles['Title']))
            self.styles.add(ParagraphStyle(name='ChineseHeading2', parent=self.styles['Heading2']))
            self.styles.add(ParagraphStyle(name='ChineseHeading3', parent=self.styles['Heading3']))
            self.styles.add(ParagraphStyle(name='ChineseNormal', parent=self.styles['Normal']))
            self.styles.add(ParagraphStyle(name='ChineseTable', parent=self.styles['Normal']))

    def export_report(self, report_data: ReportData) -> None:
        self._story = []
        
        # 标题
        title_table = Table([[report_data.title]])
        title_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "SimHei"),
            ("FONTSIZE", (0, 0), (-1, -1), 18),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        self._story.append(title_table)
        self._story.append(Spacer(1, 6 * mm))

        # 元数据
        for k, v in report_data.metadata.items():
            meta_table = Table([[f"{k}: {v}"]])
            meta_table.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), "SimHei"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            self._story.append(meta_table)
            self._story.append(Spacer(1, 2 * mm))

        # 数据表格
        if report_data.rows:
            data = [report_data.headers] + report_data.rows
            table = Table(data, repeatRows=1)
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
        else:
            empty_table = Table([["（暂无数据）"]])
            empty_table.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), "SimHei"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ]))
            self._story.append(empty_table)

        doc = SimpleDocTemplate(
            str(self.output_path),
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
        )
        doc.build(self._story)


class ExcelExporter(BaseExporter):
    """Excel 会计账簿导出器。"""

    def export_report(self, report_data: ReportData) -> None:
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError("需要安装 openpyxl: pip install openpyxl")

        wb = openpyxl.Workbook()
        ws: Any = wb.active
        if ws is None:
            raise RuntimeError("无法创建 Excel 工作表")

        ws.title = report_data.metadata.get("type", "Report")[:30]

        # 写入标题
        ws.append([report_data.title])
        ws.append([])

        # 写入元数据
        for k, v in report_data.metadata.items():
            ws.append([f"{k}: {v}"])
        ws.append([])

        # 写入表头
        ws.append(report_data.headers)

        # 写入数据
        for row in report_data.rows:
            ws.append(row)

        wb.save(self.output_path)
