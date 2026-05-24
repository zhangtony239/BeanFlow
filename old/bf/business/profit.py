"""利润分配业务流程模块

支持税费计提、利润结转、股东分红等业务场景。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from bf.business.base import BusinessContext, BusinessProcess


class TaxType(Enum):
    """税费类型枚举"""
    INCOME_TAX = "income"
    VAT = "vat"
    SURCHARGE = "surcharge"
    OTHER = "other"


@dataclass
class TaxAccrual(BusinessProcess):
    """税费计提

    计提各项税费

    分录:
        借: Expenses:Tax
        贷: Liabilities:Tax-Payable
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        tax_type: TaxType = TaxType.INCOME_TAX,
        narration: str | None = None,
        date: date | None = None,
    ):
        self.tax_type = tax_type
        narration = narration or f"计提税费 - {tax_type.value}"
        super().__init__(context, amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        expense_account = self._get_expense_account()
        liability_account = self._get_liability_account()

        return [
            {
                "account": expense_account,
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": liability_account,
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]

    def _get_expense_account(self) -> str:
        type_map = {
            TaxType.INCOME_TAX: ("Expenses", "Income-Tax"),
            TaxType.VAT: ("Expenses", "VAT"),
            TaxType.SURCHARGE: ("Expenses", "Surcharge"),
            TaxType.OTHER: ("Expenses", "Other-Tax"),
        }
        category, sub = type_map.get(self.tax_type, ("Expenses", "Tax"))
        return self._get_account(category, sub)

    def _get_liability_account(self) -> str:
        type_map = {
            TaxType.INCOME_TAX: ("Liabilities", "Income-Tax-Payable"),
            TaxType.VAT: ("Liabilities", "VAT-Payable"),
            TaxType.SURCHARGE: ("Liabilities", "Surcharge-Payable"),
            TaxType.OTHER: ("Liabilities", "Other-Tax-Payable"),
        }
        category, sub = type_map.get(self.tax_type, ("Liabilities", "Tax-Payable"))
        return self._get_account(category, sub)


@dataclass
class TaxPayment(BusinessProcess):
    """税费支付

    缴纳税费

    分录:
        借: Liabilities:Tax-Payable
        贷: Assets:Bank
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        tax_type: TaxType = TaxType.INCOME_TAX,
        narration: str | None = None,
        date: date | None = None,
    ):
        self.tax_type = tax_type
        narration = narration or f"缴纳税费 - {tax_type.value}"
        super().__init__(context, amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        liability_account = self._get_liability_account()

        return [
            {
                "account": liability_account,
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Assets", "Bank"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]

    def _get_liability_account(self) -> str:
        type_map = {
            TaxType.INCOME_TAX: ("Liabilities", "Income-Tax-Payable"),
            TaxType.VAT: ("Liabilities", "VAT-Payable"),
            TaxType.SURCHARGE: ("Liabilities", "Surcharge-Payable"),
            TaxType.OTHER: ("Liabilities", "Other-Tax-Payable"),
        }
        category, sub = type_map.get(self.tax_type, ("Liabilities", "Tax-Payable"))
        return self._get_account(category, sub)


@dataclass
class ProfitTransfer(BusinessProcess):
    """利润结转

    将收入和费用结转到本年利润

    分录:
        借: Income:All
        贷: Equity:Current-Year-Profit

        借: Equity:Current-Year-Profit
        贷: Expenses:All
    """

    def __init__(
        self,
        context: BusinessContext,
        income_accounts: list[str],
        income_amounts: list[Decimal | int | float | str],
        expense_accounts: list[str],
        expense_amounts: list[Decimal | int | float | str],
        narration: str | None = None,
        date: date | None = None,
    ):
        self.income_accounts = income_accounts
        self.income_amounts = [Decimal(str(a)) for a in income_amounts]
        self.expense_accounts = expense_accounts
        self.expense_amounts = [Decimal(str(a)) for a in expense_amounts]

        total_income = sum(self.income_amounts)
        total_expense = sum(self.expense_amounts)
        net_profit = total_income - total_expense

        self.total_income = total_income
        self.total_expense = total_expense
        self.net_profit = net_profit

        narration = narration or f"利润结转 - 本期净利润: {net_profit}"
        super().__init__(context, net_profit, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        postings = []

        for account, amount in zip(self.income_accounts, self.income_amounts):
            postings.append({
                "account": account,
                "amount": amount,
                "currency": self.context.currency,
            })

        postings.append({
            "account": self._get_account("Equity", "Current-Year-Profit"),
            "amount": -self.total_income,
            "currency": self.context.currency,
        })

        postings.append({
            "account": self._get_account("Equity", "Current-Year-Profit"),
            "amount": self.total_expense,
            "currency": self.context.currency,
        })

        for account, amount in zip(self.expense_accounts, self.expense_amounts):
            postings.append({
                "account": account,
                "amount": -amount,
                "currency": self.context.currency,
            })

        return postings


@dataclass
class RetainedEarningsTransfer(BusinessProcess):
    """未分配利润转入

    将本年利润转入未分配利润

    分录:
        借: Equity:Current-Year-Profit
        贷: Equity:Retained-Earnings
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        narration: str | None = None,
        date: date | None = None,
    ):
        narration = narration or f"利润转入未分配利润"
        super().__init__(context, amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        return [
            {
                "account": self._get_account("Equity", "Current-Year-Profit"),
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Equity", "Retained-Earnings"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]


@dataclass
class DividendDeclaration(BusinessProcess):
    """宣告分红

    宣告向股东分红

    分录:
        借: Equity:Retained-Earnings
        贷: Liabilities:Dividend-Payable
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        shareholder: str,
        narration: str | None = None,
        date: date | None = None,
    ):
        self.shareholder = shareholder
        narration = narration or f"宣告分红 - {shareholder}"
        super().__init__(context, amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        return [
            {
                "account": self._get_account("Equity", "Retained-Earnings"),
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Liabilities", "Dividend-Payable"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]


@dataclass
class DividendPayment(BusinessProcess):
    """分红支付

    实际支付股东分红

    分录:
        借: Liabilities:Dividend-Payable
        贷: Assets:Bank
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        shareholder: str,
        narration: str | None = None,
        date: date | None = None,
    ):
        self.shareholder = shareholder
        narration = narration or f"支付分红 - {shareholder}"
        super().__init__(context, amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        return [
            {
                "account": self._get_account("Liabilities", "Dividend-Payable"),
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
class WithholdingTax(BusinessProcess):
    """代扣代缴个人所得税

    代扣代缴股东分红的个人所得税

    分录:
        借: Liabilities:Dividend-Payable
        贷: Assets:Bank
        贷: Liabilities:Tax-Payable (代扣个人所得税)
    """

    def __init__(
        self,
        context: BusinessContext,
        tax_amount: Decimal | int | float | str,
        shareholder: str,
        narration: str | None = None,
        date: date | None = None,
    ):
        self.shareholder = shareholder
        narration = narration or f"代扣代缴个税 - {shareholder}"
        super().__init__(context, tax_amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        return [
            {
                "account": self._get_account("Liabilities", "Dividend-Payable"),
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Assets", "Bank"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Liabilities", "Tax-Payable"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]
