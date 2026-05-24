"""采购业务流程模块

支持原材料采购、费用采购、预付款等业务场景。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from bf.business.base import BusinessContext, BusinessProcess


class ProcurementType(Enum):
    """采购类型枚举"""
    RAW_MATERIALS = "raw"
    OFFICE_SUPPLIES = "office"
    EQUIPMENT = "equipment"
    SERVICES = "services"
    OTHER = "other"


@dataclass
class Procurement(BusinessProcess):
    """采购业务

    采购原材料、商品或服务

    分录（不含税）:
        借: Expenses:Cost / Expenses:Office
        贷: Assets:Bank

    分录（含税）:
        借: Expenses:Cost
        借: Assets:Tax-Input:VAT
        贷: Assets:Bank
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        counterparty: str,
        procurement_type: ProcurementType = ProcurementType.RAW_MATERIALS,
        include_tax: bool = True,
        narration: str | None = None,
        date: date | None = None,
    ):
        super().__init__(context, amount, narration or f"采购 - {counterparty}", date)
        self.counterparty = counterparty
        self.procurement_type = procurement_type
        self.include_tax = include_tax

    def _build_postings(self) -> list[dict[str, Any]]:
        tax, total = self._calculate_tax(self.amount) if self.include_tax else (Decimal("0"), self.amount)

        expense_account = self._get_expense_account()

        postings = []

        if self.include_tax and tax > 0:
            postings.extend([
                {
                    "account": expense_account,
                    "amount": self.amount,
                    "currency": self.context.currency,
                },
                {
                    "account": self._get_account("Assets", "Tax-Input"),
                    "amount": tax,
                    "currency": self.context.currency,
                },
                {
                    "account": self._get_account("Assets", "Bank"),
                    "amount": -(self.amount + tax),
                    "currency": self.context.currency,
                },
            ])
        else:
            postings.extend([
                {
                    "account": expense_account,
                    "amount": self.amount,
                    "currency": self.context.currency,
                },
                {
                    "account": self._get_account("Assets", "Bank"),
                    "amount": -self.amount,
                    "currency": self.context.currency,
                },
            ])

        return postings

    def _get_expense_account(self) -> str:
        type_map = {
            ProcurementType.RAW_MATERIALS: ("Expenses", "Cost"),
            ProcurementType.OFFICE_SUPPLIES: ("Expenses", "Office"),
            ProcurementType.EQUIPMENT: ("Assets", "Equipment"),
            ProcurementType.SERVICES: ("Expenses", "Services"),
            ProcurementType.OTHER: ("Expenses", "Other"),
        }
        category, sub = type_map.get(self.procurement_type, ("Expenses", "Other"))
        return self._get_account(category, sub)


@dataclass
class AdvancePayment(BusinessProcess):
    """预付款

    向供应商预付货款

    分录:
        借: Assets:Advance-Payment
        贷: Assets:Bank
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        counterparty: str,
        payment_ratio: Decimal | float = Decimal("100"),
        narration: str | None = None,
        date: date | None = None,
    ):
        narration = narration or f"预付款 - {counterparty}"
        super().__init__(context, amount, narration, date)
        self.counterparty = counterparty
        self.payment_ratio = Decimal(str(payment_ratio))

    def _build_postings(self) -> list[dict[str, Any]]:
        return [
            {
                "account": self._get_account("Assets", "Advance-Payment"),
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Assets", "Bank"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]


@dataclass
class ProcurementSettlement(BusinessProcess):
    """采购结算

    采购完成后的实际结算（用于预付款场景）

    分录:
        借: Expenses:Cost
        贷: Assets:Advance-Payment
        贷: Assets:Bank (如需补款)
        借: Assets:Bank (如需退款)
    """

    def __init__(
        self,
        context: BusinessContext,
        original_advance: Decimal | int | float | str,
        actual_amount: Decimal | int | float | str,
        counterparty: str,
        include_tax: bool = True,
        narration: str | None = None,
        date: date | None = None,
    ):
        self.original_advance = Decimal(str(original_advance))
        self.actual_amount = Decimal(str(actual_amount))
        self.counterparty = counterparty
        self.include_tax = include_tax

        diff = self.actual_amount - self.original_advance
        narration = narration or f"采购结算 - {counterparty} (差额: {diff})"

        super().__init__(context, actual_amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        tax, total = self._calculate_tax(self.actual_amount) if self.include_tax else (Decimal("0"), self.actual_amount)
        advance_used = min(self.original_advance, self.actual_amount)

        postings = []

        if self.include_tax and tax > 0:
            postings.extend([
                {
                    "account": self._get_account("Expenses", "Cost"),
                    "amount": self.actual_amount - tax,
                    "currency": self.context.currency,
                },
                {
                    "account": self._get_account("Assets", "Tax-Input"),
                    "amount": tax,
                    "currency": self.context.currency,
                },
                {
                    "account": self._get_account("Assets", "Advance-Payment"),
                    "amount": -advance_used,
                    "currency": self.context.currency,
                },
            ])
        else:
            postings.extend([
                {
                    "account": self._get_account("Expenses", "Cost"),
                    "amount": self.actual_amount,
                    "currency": self.context.currency,
                },
                {
                    "account": self._get_account("Assets", "Advance-Payment"),
                    "amount": -advance_used,
                    "currency": self.context.currency,
                },
            ])

        diff = self.actual_amount - self.original_advance
        if diff > 0:
            postings.extend([
                {
                    "account": self._get_account("Assets", "Bank"),
                    "amount": -diff,
                    "currency": self.context.currency,
                },
            ])
        elif diff < 0:
            postings.extend([
                {
                    "account": self._get_account("Assets", "Bank"),
                    "amount": abs(diff),
                    "currency": self.context.currency,
                },
            ])

        return postings


@dataclass
class RefundFromSupplier(BusinessProcess):
    """供应商退款

    收到供应商退款

    分录:
        借: Assets:Bank
        贷: Assets:Advance-Payment
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        counterparty: str,
        narration: str | None = None,
        date: date | None = None,
    ):
        narration = narration or f"供应商退款 - {counterparty}"
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
                "account": self._get_account("Assets", "Advance-Payment"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]
