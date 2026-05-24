"""销售业务流程模块

支持商品销售、服务销售、销售折扣等业务场景。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from bf.business.base import BusinessContext, BusinessProcess


class SalesType(Enum):
    """销售类型枚举"""
    GOODS = "goods"
    SERVICES = "services"
    PRODUCT = "product"


@dataclass
class Sales(BusinessProcess):
    """销售业务

    销售商品或提供服务

    分录（商品销售含税）:
        借: Assets:Bank / Assets:Receivable
        借: Expenses:Cost
        贷: Income:Sales
        贷: Liabilities:Tax-Output

    分录（服务销售含税）:
        借: Assets:Bank / Assets:Receivable
        贷: Income:Service
        贷: Liabilities:Tax-Output
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        counterparty: str,
        sales_type: SalesType = SalesType.GOODS,
        cost_of_goods: Decimal | int | float | str | None = None,
        receivable_account: str | None = None,
        include_tax: bool = True,
        narration: str | None = None,
        date: date | None = None,
    ):
        self.counterparty = counterparty
        self.sales_type = sales_type
        self.cost_of_goods = Decimal(str(cost_of_goods)) if cost_of_goods else None
        self.receivable_account = receivable_account
        self.include_tax = include_tax

        type_str = "商品销售" if sales_type == SalesType.GOODS else "服务销售"
        narration = narration or f"{type_str} - {counterparty}"

        super().__init__(context, amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        tax, total = self._calculate_tax(self.amount) if self.include_tax else (Decimal("0"), self.amount)

        income_account = self._get_income_account()
        cash_account = self.receivable_account or self._get_account("Assets", "Bank")

        postings = [
            {
                "account": cash_account,
                "amount": total,
                "currency": self.context.currency,
            },
            {
                "account": income_account,
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]

        if self.include_tax and tax > 0:
            postings.append({
                "account": self._get_account("Liabilities", "Tax-Output"),
                "amount": -tax,
                "currency": self.context.currency,
            })

        return postings

    def _get_income_account(self) -> str:
        if self.sales_type == SalesType.GOODS:
            return self._get_account("Income", "Sales")
        elif self.sales_type == SalesType.SERVICES:
            return self._get_account("Income", "Service")
        else:
            return self._get_account("Income", "Sales")


@dataclass
class SalesOnCredit(BusinessProcess):
    """赊销

    信用销售，产生应收账款

    分录:
        借: Assets:Receivable
        贷: Income:Sales
        贷: Liabilities:Tax-Output
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        counterparty: str,
        include_tax: bool = True,
        due_date: date | None = None,
        narration: str | None = None,
        date: date | None = None,
    ):
        self.counterparty = counterparty
        self.include_tax = include_tax
        self.due_date = due_date

        narration = narration or f"赊销 - {counterparty}"
        if due_date:
            narration += f" (到期日: {due_date})"

        super().__init__(context, amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        tax, total = self._calculate_tax(self.amount) if self.include_tax else (Decimal("0"), self.amount)

        postings = [
            {
                "account": self._get_account("Assets", "Receivable"),
                "amount": total,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Income", "Sales"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]

        if self.include_tax and tax > 0:
            postings.append({
                "account": self._get_account("Liabilities", "Tax-Output"),
                "amount": -tax,
                "currency": self.context.currency,
            })

        return postings


@dataclass
class Collection(BusinessProcess):
    """收款

    收回应收账款

    分录:
        借: Assets:Bank
        贷: Assets:Receivable
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        counterparty: str,
        narration: str | None = None,
        date: date | None = None,
    ):
        narration = narration or f"收款 - {counterparty}"
        super().__init__(context, amount, narration, date)
        self.counterparty = counterparty

    def _build_postings(self) -> list[dict[str, Any]]:
        return [
            {
                "account": self._get_account("Assets", "Bank"),
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Assets", "Receivable"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]


@dataclass
class SalesDiscount(BusinessProcess):
    """销售折扣

    提供销售折扣

    分录:
        借: Income:Sales (折扣部分)
        贷: Assets:Bank (如已收款退款)
        或
        贷: Assets:Receivable (如未收款冲减)
    """

    def __init__(
        self,
        context: BusinessContext,
        original_amount: Decimal | int | float | str,
        discount_amount: Decimal | int | float | str,
        counterparty: str,
        is_refund: bool = False,
        narration: str | None = None,
        date: date | None = None,
    ):
        self.original_amount = Decimal(str(original_amount))
        self.discount_amount = Decimal(str(discount_amount))
        self.counterparty = counterparty
        self.is_refund = is_refund

        narration = narration or f"销售折扣 - {counterparty} ({discount_amount})"
        super().__init__(context, discount_amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        postings = []

        postings.append({
            "account": self._get_account("Income", "Sales"),
            "amount": self.discount_amount,
            "currency": self.context.currency,
        })

        if self.is_refund:
            postings.append({
                "account": self._get_account("Assets", "Bank"),
                "amount": -self.discount_amount,
                "currency": self.context.currency,
            })
        else:
            postings.append({
                "account": self._get_account("Assets", "Receivable"),
                "amount": -self.discount_amount,
                "currency": self.context.currency,
            })

        return postings


@dataclass
class ReturnFromCustomer(BusinessProcess):
    """销售退货

    客户退货处理

    分录:
        借: Income:Sales (红字)
        借: Assets:Bank (退款)
        贷: Assets:Receivable
        贷: Expenses:Cost (成本转出)
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        counterparty: str,
        cost_of_goods: Decimal | int | float | str | None = None,
        narration: str | None = None,
        date: date | None = None,
    ):
        self.counterparty = counterparty
        self.cost_of_goods = Decimal(str(cost_of_goods)) if cost_of_goods else None

        narration = narration or f"销售退货 - {counterparty}"
        super().__init__(context, amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        tax = self._calculate_tax(self.amount)[0] if self.include_tax else Decimal("0")

        postings = []

        postings.extend([
            {
                "account": self._get_account("Income", "Sales"),
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Assets", "Bank"),
                "amount": -(self.amount + tax),
                "currency": self.context.currency,
            },
        ])

        if self.cost_of_goods and self.cost_of_goods > 0:
            postings.append({
                "account": self._get_account("Assets", "Inventory"),
                "amount": self.cost_of_goods,
                "currency": self.context.currency,
            })
            postings.append({
                "account": self._get_account("Expenses", "COGS"),
                "amount": -self.cost_of_goods,
                "currency": self.context.currency,
            })

        return postings
