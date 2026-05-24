"""Bean file generator for BeanFlow.

Generates Beancount ledger files from transaction entries.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TextIO
import uuid


class BeanGenerator:
    """Bean文件生成器

    负责生成完整的Beancount账本文件
    """

    def __init__(
        self,
        project_name: str,
        currencies: list[str] | None = None,
        default_currency: str = "CNY",
    ):
        """初始化生成器

        Args:
            project_name: 项目名称
            currencies: 支持的货币列表
            default_currency: 默认货币
        """
        self.project_name = project_name
        self.currencies = currencies or ["CNY", "USD"]
        self.default_currency = default_currency
        self.accounts: set[str] = set()
        self.transactions: list[str] = []
        self.metadata: dict[str, str] = {}
        self._document_directives: list[str] = []

    def add_account(self, account: str, currencies: list[str] | None = None) -> None:
        """添加账户声明

        Args:
            account: 账户名称
            currencies: 账户支持的货币
        """
        currencies = currencies or [self.default_currency]
        currencies_str = " ".join(currencies)
        self.accounts.add(f"open {account} {currencies_str}")

    def add_transaction(self, tx_string: str) -> None:
        """添加交易条目

        Args:
            tx_string: 交易字符串（已格式化的）
        """
        self.transactions.append(tx_string)

    def add_metadata(self, key: str, value: str) -> None:
        """添加账本级元数据

        Args:
            key: 元数据键
            value: 元数据值
        """
        self.metadata[key] = value

    def add_document_directive(self, path: str, date_str: str | None = None) -> None:
        """添加文档指令

        Args:
            path: 文档路径
            date_str: 日期字符串（可选）
        """
        if date_str:
            self._document_directives.append(f'{date_str} document "{path}"')
        else:
            today = date.today().strftime("%Y-%m-%d")
            self._document_directives.append(f'{today} document "{path}"')

    def add_commodity(self, commodity: str, date_str: str | None = None) -> None:
        """添加商品/货币指令

        Args:
            commodity: 商品/货币代码
            date_str: 日期字符串
        """
        date_str = date_str or date.today().strftime("%Y-%m-%d")
        self._document_directives.append(f"{date_str} commodity {commodity}")

    def add_event(self, event_type: str, description: str, date_str: str | None = None) -> None:
        """添加事件指令

        Args:
            event_type: 事件类型
            description: 事件描述
            date_str: 日期字符串
        """
        date_str = date_str or date.today().strftime("%Y-%m-%d")
        self._document_directives.append(f'{date_str} event "{event_type}" "{description}"')

    def add_note(self, account: str, note: str, date_str: str | None = None) -> None:
        """添加账户备注

        Args:
            account: 账户名称
            note: 备注内容
            date_str: 日期字符串
        """
        date_str = date_str or date.today().strftime("%Y-%m-%d")
        self._document_directives.append(f'{date_str} note {account} "{note}"')

    def add_balance(self, account: str, amount: Decimal, date_str: str | None = None) -> None:
        """添加账户余额

        Args:
            account: 账户名称
            amount: 余额
            date_str: 日期字符串
        """
        date_str = date_str or date.today().strftime("%Y-%m-%d")
        self._document_directives.append(
            f"{date_str} balance {account} {amount:,.2f} {self.default_currency}"
        )

    def generate_header(self) -> str:
        """生成账本头信息"""
        lines = [
            f"; {self.project_name} - BeanFlow Project",
            f"; Generated: {date.today().strftime('%Y-%m-%d')}",
            f"; UID: {uuid.uuid4().hex[:8]}",
            "",
        ]

        for key, value in self.metadata.items():
            lines.append(f'option "{key}" "{value}"')

        for currency in self.currencies:
            lines.append(f"commodity {currency}")
            lines.append(f"  name: \"{currency}\"")

        lines.append("")
        return "\n".join(lines)

    def generate_accounts_section(self) -> str:
        """生成账户声明部分"""
        if not self.accounts:
            return ""

        lines = ["; 账户声明", ""]
        for account in sorted(self.accounts):
            parts = account.split(" ", 1)
            if len(parts) == 2:
                _, rest = parts
                lines.append(f"2010-01-01 {rest}")
            else:
                lines.append(f"2010-01-01 {account}")

        lines.append("")
        return "\n".join(lines)

    def generate_transactions_section(self) -> str:
        """生成交易记录部分"""
        if not self.transactions:
            return ""

        lines = ["; 交易记录", ""]
        lines.extend(self.transactions)
        lines.append("")
        return "\n".join(lines)

    def generate_footer(self) -> str:
        """生成账本尾部"""
        return "; End of Ledger"

    def generate(self) -> str:
        """生成完整的Bean文件内容"""
        parts = [
            self.generate_header(),
            self.generate_accounts_section(),
            self.generate_transactions_section(),
            self.generate_footer(),
        ]
        return "\n".join(parts)

    def write(self, file_path: str | Path) -> None:
        """写入Bean文件

        Args:
            file_path: 文件路径
        """
        content = self.generate()
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    def write_stream(self, f: TextIO) -> None:
        """流式写入Bean文件

        Args:
            f: 文件对象
        """
        f.write(self.generate())


class ProjectBeanGenerator(BeanGenerator):
    """项目专用的Bean生成器

    提供针对项目场景的便捷方法
    """

    def __init__(
        self,
        project_name: str,
        project_path: str | Path,
        currencies: list[str] | None = None,
        default_currency: str = "CNY",
    ):
        """初始化项目Bean生成器

        Args:
            project_name: 项目名称
            project_path: 项目路径
            currencies: 支持的货币列表
            default_currency: 默认货币
        """
        super().__init__(project_name, currencies, default_currency)
        self.project_path = Path(project_path)

    def setup_standard_accounts(self, include_inventory: bool = True) -> None:
        """设置标准账户

        Args:
            include_inventory: 是否包含存货账户
        """
        accounts = [
            f"Assets:Bank:{self.project_name}",
            f"Assets:Cash:{self.project_name}",
            f"Assets:Receivable:{self.project_name}",
            f"Liabilities:Payable:{self.project_name}",
            f"Liabilities:Loans:{self.project_name}",
            f"Liabilities:Tax-Payable:{self.project_name}",
            f"Equity:Capital:{self.project_name}",
            f"Equity:Retained-Earnings:{self.project_name}",
            f"Income:Sales:{self.project_name}",
            f"Income:Service:{self.project_name}",
            f"Expenses:Cost:{self.project_name}",
            f"Expenses:Tax:{self.project_name}",
            f"Expenses:Office:{self.project_name}",
            f"Expenses:Salary:{self.project_name}",
        ]

        if include_inventory:
            accounts.insert(3, f"Assets:Inventory:{self.project_name}")

        for account in accounts:
            self.add_account(account)

    def get_account(self, category: str, subcategory: str | None = None) -> str:
        """获取项目账户路径

        Args:
            category: 账户类别
            subcategory: 子类别

        Returns:
            完整账户路径
        """
        if subcategory:
            return f"{category}:{subcategory}:{self.project_name}"
        return f"{category}:{self.project_name}"

    def write_main_bean(self) -> Path:
        """写入主Bean文件

        Returns:
            生成的文件路径
        """
        main_bean = self.project_path / "main.bean"
        self.write(main_bean)
        return main_bean
