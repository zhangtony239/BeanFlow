"""Business process base class for BeanFlow.

Abstract base class for all business process implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date as date_type
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bf.core.transaction import TransactionEntry
    from bf.core.account import Account
    from bf.project import Project


@dataclass
class BusinessContext:
    """业务流程上下文

    包含执行业务流程所需的所有信息
    """
    project_name: str
    project_path: str
    currency: str = "CNY"
    tax_rate: Decimal = Decimal("0.13")
    narration: str = ""
    date: date_type | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class BusinessProcess(ABC):
    """业务流程抽象基类

    所有业务流程都需要继承此类并实现_build_postings方法
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        narration: str,
        date: date_type | None = None,
    ):
        """初始化业务流程

        Args:
            context: 业务流程上下文
            amount: 交易金额
            narration: 交易描述
            date: 交易日期（可选，默认今天）
        """
        self.context = context
        self.amount = Decimal(str(amount))
        self.narration = narration
        if date:
            self.date = date
        elif context.date:
            self.date = context.date
        else:
            self.date = date_type.today()
        self._postings: list[dict[str, Any]] = []
        self._transaction: TransactionEntry | None = None

    @abstractmethod
    def _build_postings(self) -> list[dict[str, Any]]:
        """构建分录列表

        子类必须实现此方法

        Returns:
            分录字典列表
        """
        pass

    def execute(self) -> TransactionEntry:
        """执行业务流程，生成交易条目

        Returns:
            交易条目
        """
        self._postings = self._build_postings()

        from bf.core.transaction import TransactionEntry, PostingEntry

        tx = TransactionEntry(
            date=self.date,
            narration=self.narration,
            flag="*",
        )

        for posting_data in self._postings:
            tx.add_posting(
                account=posting_data["account"],
                amount=Decimal(str(posting_data["amount"])),
                currency=posting_data.get("currency", self.context.currency),
                flag=posting_data.get("flag", "*"),
            )

        tx.ensure_balance()
        self._transaction = tx
        return tx

    def validate(self) -> tuple[bool, list[str]]:
        """验证业务流程

        Returns:
            (是否有效, 错误信息列表)
        """
        errors = []

        if self.amount <= 0:
            errors.append("Amount must be positive")

        if not self.narration:
            errors.append("Narration is required")

        if not self._postings:
            self._postings = self._build_postings()

        from bf.core.transaction import PostingEntry

        postings = [
            PostingEntry(
                account=p["account"],
                amount=Decimal(str(p["amount"])),
                currency=p.get("currency", self.context.currency),
            )
            for p in self._postings
        ]

        total = sum(posting.amount for posting in postings)
        if abs(total) >= Decimal("0.01"):
            errors.append(f"Postings are not balanced: {total}")

        return len(errors) == 0, errors

    def get_transaction(self) -> TransactionEntry | None:
        """获取生成的交易条目

        Returns:
            交易条目（如未执行则返回None）
        """
        return self._transaction

    def _get_account(self, base: str, sub: str | None = None) -> str:
        """获取带项目名的账户路径

        Args:
            base: 基础账户
            sub: 子账户（可选）

        Returns:
            完整账户路径
        """
        if sub:
            return f"{base}:{sub}:{self.context.project_name}"
        return f"{base}:{self.context.project_name}"

    def _calculate_tax(self, amount: Decimal) -> tuple[Decimal, Decimal]:
        """计算税额

        Args:
            amount: 金额

        Returns:
            (税额, 价税合计)
        """
        tax = (amount * self.context.tax_rate).quantize(Decimal("0.01"))
        total = amount + tax
        return tax, total

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"amount={self.amount}, "
            f"narration='{self.narration}', "
            f"date={self.date})"
        )


class QuickTransfer(BusinessProcess):
    """快速转账业务

    简单的两方转账操作
    """

    def __init__(
        self,
        context: BusinessContext,
        from_account: str,
        to_account: str,
        amount: Decimal | int | float | str,
        narration: str,
        date: date | None = None,
    ):
        """初始化快速转账

        Args:
            context: 业务流程上下文
            from_account: 转出账户
            to_account: 转入账户
            amount: 金额
            narration: 描述
            date: 日期
        """
        self.from_account = from_account
        self.to_account = to_account
        super().__init__(context, amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        return [
            {"account": self.from_account, "amount": -self.amount},
            {"account": self.to_account, "amount": self.amount},
        ]
