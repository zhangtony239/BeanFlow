"""Transaction and Posting classes for BeanFlow.

Handles transaction entries with double-entry bookkeeping validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
import uuid


@dataclass
class PostingEntry:
    """分录条目

    Attributes:
        account: 账户名称
        amount: 金额（正数为借方，负数为贷方）
        currency: 货币类型
        units: 数量单位（可选）
        cost: 成本（可选）
        price: 价格（可选）
        flag: 标志（如 * 表示已确认， ! 表示待确认）
    """
    account: str
    amount: Decimal
    currency: str = "CNY"
    units: str | None = None
    cost: Decimal | None = None
    price: Decimal | None = None
    flag: str = "*"
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.amount, (int, float, str)):
            self.amount = Decimal(str(self.amount))

    @property
    def is_debit(self) -> bool:
        """是否为借方分录"""
        return self.amount > 0

    @property
    def is_credit(self) -> bool:
        """是否为贷方分录"""
        return self.amount < 0

    @property
    def signed_amount(self) -> Decimal:
        """带符号的金额"""
        return self.amount

    def to_string(self) -> str:
        """转换为Beancount语法字符串"""
        parts = [f"{self.flag} {self.account}"]

        if self.amount >= 0:
            parts.append(f"{self.amount:,.2f} {self.currency}")
        else:
            abs_amount = abs(self.amount)
            parts.append(f"{-abs_amount:,.2f} {self.currency}")

        if self.cost:
            parts.append(f"{{{self.cost}}}")

        if self.price:
            parts.append(f"@ {self.price}")

        return " ".join(parts)

    def copy(self) -> PostingEntry:
        """复制分录"""
        return PostingEntry(
            account=self.account,
            amount=self.amount,
            currency=self.currency,
            units=self.units,
            cost=self.cost,
            price=self.price,
            flag=self.flag,
            meta=self.meta.copy(),
        )


@dataclass
class TransactionEntry:
    """交易条目

    Attributes:
        date: 交易日期
        narration: 交易描述
        postings: 分录列表
        flag: 交易标志
        payee: 交易对方
        links: 关联链接
        meta: 元数据
    """
    date: date
    narration: str
    postings: list[PostingEntry] = field(default_factory=list)
    flag: str = "*"
    payee: str | None = None
    links: set[str] = field(default_factory=set)
    meta: dict[str, Any] = field(default_factory=dict)
    txid: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def add_posting(
        self,
        account: str,
        amount: Decimal | int | float | str,
        currency: str = "CNY",
        flag: str | None = None,
        **kwargs
    ) -> PostingEntry:
        """添加分录

        Args:
            account: 账户名称
            amount: 金额
            currency: 货币类型
            flag: 标志
            **kwargs: 其他参数

        Returns:
            创建的分录
        """
        posting = PostingEntry(
            account=account,
            amount=Decimal(str(amount)),
            currency=currency,
            flag=flag or self.flag,
            **kwargs
        )
        self.postings.append(posting)
        return posting

    def add_link(self, link: str) -> None:
        """添加关联链接"""
        self.links.add(link)

    def validate_balance(self) -> tuple[bool, Decimal]:
        """校验借贷平衡

        Returns:
            (是否平衡, 差额)
        """
        total = sum(p.amount for p in self.postings)
        is_balanced = abs(total) < Decimal("0.01")
        return is_balanced, total

    def ensure_balance(self, tolerance: Decimal = Decimal("0.01")) -> bool:
        """确保借贷平衡，如不平衡则抛出异常

        Args:
            tolerance: 容差

        Returns:
            是否平衡

        Raises:
            ValueError: 借贷不平衡时抛出
        """
        is_balanced, diff = self.validate_balance()
        if not is_balanced and abs(diff) > tolerance:
            raise ValueError(
                f"Transaction is not balanced: difference is {diff}"
            )
        return True

    def total_debits(self) -> Decimal:
        """计算借方总额"""
        return sum(p.amount for p in self.postings if p.is_debit)

    def total_credits(self) -> Decimal:
        """计算贷方总额"""
        return sum(abs(p.amount) for p in self.postings if p.is_credit)

    def to_string(self) -> str:
        """转换为Beancount语法字符串"""
        lines = []

        date_str = self.date.strftime("%Y-%m-%d")
        flag_str = self.flag

        if self.payee:
            lines.append(f'{date_str} {flag_str} "{self.payee}" "{self.narration}"')
        else:
            lines.append(f'{date_str} {flag_str} "{self.narration}"')

        for posting in self.postings:
            amount_str = ""
            if posting.amount >= 0:
                amount_str = f"{posting.amount:,.2f} {posting.currency}"
            else:
                amount_str = f"{-posting.amount:,.2f} {posting.currency}"

            line = f"  {posting.account} {amount_str}"

            if posting.cost:
                line += f" {{{posting.cost}}}"
            if posting.price:
                line += f" @ {posting.price}"

            lines.append(line)

        if self.links:
            links_str = " ".join(f"^{link}" for link in self.links)
            lines.append(f"  {links_str}")

        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_string()


@dataclass
class OpenEntry:
    """账户开启条目

    用于在Bean文件中声明账户
    """
    date: date
    account: str
    currencies: list[str] = field(default_factory=list)
    flag: str = "*"
    meta: dict[str, Any] = field(default_factory=dict)

    def to_string(self) -> str:
        """转换为Beancount语法"""
        currencies_str = " ".join(self.currencies) if self.currencies else "CNY"
        return f"{self.date.strftime('%Y-%m-%d')} open {self.account} {currencies_str}"


@dataclass
class CloseEntry:
    """账户关闭条目"""
    date: date
    account: str

    def to_string(self) -> str:
        return f"{self.date.strftime('%Y-%m-%d')} close {self.account}"


@dataclass
class CommodityEntry:
    """商品/货币条目"""
    date: date
    base: str
    quote: str

    def to_string(self) -> str:
        return f"{self.date.strftime('%Y-%m-%d')} commodity {self.base}"
