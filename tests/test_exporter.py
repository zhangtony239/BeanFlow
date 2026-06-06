"""
Exporter 单元测试。

验证:
    1. Provider-Exporter 模式正常工作。
    2. 科目名称友好翻译正常工作。
"""

import pytest
from pathlib import Path
import tempfile

from bf.project import Project
from bf.core.config import MappingDictionary, MappingEntry, AccountTypeEnum
from bf.core.exporter import (
    ReportData,
    EnterpriseReportProvider,
    CashFlowReportProvider,
    TaxReportProvider,
    PDFExporter,
    ExcelExporter,
)


class MockProject:
    """Mock 项目对象，用于测试 Provider。"""
    def __init__(self, name: str, bean_content: str, mapping: MappingDictionary) -> None:
        self.name = name
        self.bean_content = bean_content
        self.mapping = mapping
        
        # 模拟 env
        from bf.core.config import EnvConfig, ProjectMeta
        self.env = EnvConfig(project=ProjectMeta(name=name, tax_rate=0.13))

    def read_bean(self) -> str:
        return self.bean_content


def test_friendly_name_translation():
    """测试科目名称友好翻译。"""
    mapping = MappingDictionary(
        reserved_embedding_model=None,
        entries=[
            MappingEntry(id="Assets:Bank", type=AccountTypeEnum.ASSETS, temp=False, names=["bank", "银行存款"]),
            MappingEntry(id="Liabilities:Loans", type=AccountTypeEnum.DEBT, temp=False, names=["loans", "短期借款"]),
        ]
    )
    
    bean_content = """
2026-06-06 * "初始投资"
    Assets:Bank  10000.00 CNY
    Equity:Capital  -10000.00 CNY
    """
    
    proj = MockProject("test_proj", bean_content, mapping)
    provider = EnterpriseReportProvider(proj)  # type: ignore
    
    # 1. 测试 _get_friendly_name
    assert provider._get_friendly_name("Assets:Bank") == "银行存款"
    assert provider._get_friendly_name("Liabilities:Loans") == "短期借款"
    assert provider._get_friendly_name("Equity:Capital") == "Equity:Capital"  # 未在字典中，回退到原始 ID


def test_enterprise_report_provider():
    """测试 EnterpriseReportProvider 生成数据。"""
    mapping = MappingDictionary(
        reserved_embedding_model=None,
        entries=[
            MappingEntry(id="Assets:Bank", type=AccountTypeEnum.ASSETS, temp=False, names=["bank", "银行存款"]),
            MappingEntry(id="Expenses:Rent", type=AccountTypeEnum.FEE, temp=False, names=["rent", "租金费用"]),
            MappingEntry(id="Income:Sales", type=AccountTypeEnum.EQUITY, temp=False, names=["sales", "销售收入"]),
        ]
    )
    
    bean_content = """
2026-06-06 * "销售商品"
    Assets:Bank  10000.00 CNY
    Income:Sales  -10000.00 CNY

2026-06-07 * "支付房租"
    Expenses:Rent  2000.00 CNY
    Assets:Bank  -2000.00 CNY
    """
    
    proj = MockProject("test_proj", bean_content, mapping)
    provider = EnterpriseReportProvider(proj)  # type: ignore
    
    # 1. 测试资产负债表数据
    bs_data = provider.get_balance_sheet_data()
    assert bs_data.title == "资产负债表 - test_proj"
    assert bs_data.headers == ["科目", "金额"]
    # 银行存款余额 = 10000 - 2000 = 8000
    assert ["银行存款", "8000.00"] in bs_data.rows
    assert ["资产总计", "8000.00"] in bs_data.rows

    # 2. 测试利润表数据
    is_data = provider.get_income_statement_data()
    assert is_data.title == "利润表 - test_proj"
    assert ["销售收入", "10000.00"] in is_data.rows
    assert ["租金费用", "2000.00"] in is_data.rows
    assert ["净利润", "8000.00"] in is_data.rows


def test_exporters(tmp_path):
    """测试 PDF 和 Excel 导出器。"""
    report_data = ReportData(
        title="测试报表",
        headers=["日期", "摘要", "金额"],
        rows=[
            ["2026-06-06", "测试交易 1", "1000.00"],
            ["2026-06-07", "测试交易 2", "-500.00"],
        ],
        metadata={"project": "test_proj", "type": "test"}
    )

    # 1. 测试 PDF 导出
    pdf_path = tmp_path / "test_report.pdf"
    pdf_exporter = PDFExporter(pdf_path)
    pdf_exporter.export_report(report_data)
    assert pdf_path.exists()

    # 2. 测试 Excel 导出
    pytest.importorskip("openpyxl")
    excel_path = tmp_path / "test_report.xlsx"
    excel_exporter = ExcelExporter(excel_path)
    excel_exporter.export_report(report_data)
    assert excel_path.exists()
