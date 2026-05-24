"""资金筹集业务流程模块

支持借款融资和股权融资两种主要资金筹集方式。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from bf.business.base import BusinessContext, BusinessProcess


class FundraisingProcess(BusinessProcess):
    """资金筹集业务流程基类"""

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        counterparty: str,
        narration: str | None = None,
        date: date | None = None,
    ):
        narration = narration or f"资金筹集 - {counterparty}"
        super().__init__(context, amount, narration, date)
        self.counterparty = counterparty


class LoanFundraising(FundraisingProcess):
    """借款融资

    从银行或其他金融机构借款

    分录:
        借: Assets:Bank
        贷: Liabilities:Loans
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        counterparty: str,
        loan_term: int | None = None,
        interest_rate: Decimal | None = None,
        narration: str | None = None,
        date: date | None = None,
    ):
        super().__init__(context, amount, counterparty, narration, date)
        self.loan_term = loan_term
        self.interest_rate = interest_rate
        if narration is None:
            self.narration = f"借款融资 - {counterparty}"
            if loan_term:
                self.narration += f" (期限{loan_term}个月)"

    def _build_postings(self) -> list[dict[str, Any]]:
        return [
            {
                "account": self._get_account("Assets", "Bank"),
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Liabilities", "Loans"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]


class EquityFundraising(FundraisingProcess):
    """股权融资

    吸收投资者股权投资

    分录:
        借: Assets:Bank
        贷: Equity:Capital
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        counterparty: str,
        share_ratio: Decimal | None = None,
        narration: str | None = None,
        date: date | None = None,
    ):
        super().__init__(context, amount, counterparty, narration, date)
        self.share_ratio = share_ratio
        if narration is None:
            self.narration = f"股权融资 - {counterparty}"
            if share_ratio:
                self.narration += f" (股权比例{share_ratio}%)"

    def _build_postings(self) -> list[dict[str, Any]]:
        return [
            {
                "account": self._get_account("Assets", "Bank"),
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Equity", "Capital"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]


class LoanRepayment(FundraisingProcess):
    """偿还借款

    偿还银行贷款本金

    分录:
        借: Liabilities:Loans
        贷: Assets:Bank
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        counterparty: str,
        interest: Decimal | int | float | str | None = None,
        narration: str | None = None,
        date: date | None = None,
    ):
        super().__init__(context, amount, counterparty, narration, date)
        self.interest = Decimal(str(interest)) if interest else Decimal("0")
        if narration is None:
            self.narration = f"偿还借款 - {counterparty}"

    def _build_postings(self) -> list[dict[str, Any]]:
        postings = [
            {
                "account": self._get_account("Liabilities", "Loans"),
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Assets", "Bank"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]

        if self.interest > 0:
            postings.extend([
                {
                    "account": self._get_account("Expenses", "Interest"),
                    "amount": self.interest,
                    "currency": self.context.currency,
                },
                {
                    "account": self._get_account("Assets", "Bank"),
                    "amount": -self.interest,
                    "currency": self.context.currency,
                },
            ])

        return postings


class DividendDistribution(FundraisingProcess):
    """分红派息

    向股东分配利润

    分录:
        借: Equity:Distributions:Dividend
        贷: Liabilities:Dividend-Payable
    """

    def __init__(
        self,
        context: BusinessContext,
        amount: Decimal | int | float | str,
        shareholder: str,
        action: str = "declare",
        narration: str | None = None,
        date: date | None = None,
    ):
        narration = narration or f"分红派息 - {shareholder}"
        super().__init__(context, amount, shareholder, narration, date)
        self.shareholder = shareholder
        self.action = action

    def _build_postings(self) -> list[dict[str, Any]]:
        return [
            {
                "account": self._get_account("Equity", "Dividend"),
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Liabilities", "Dividend-Payable"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]
