"""
账户类体系单元测试。

验证:
    1. 继承关系正确
    2. 符号转换规则正确（红线测试）
    3. 工厂函数正确
"""

import pytest
from decimal import Decimal

from bf.core.account import (
    AssetsAccount,
    BasicAccount,
    DebtAccount,
    EquityAccount,
    FeeAccount,
    LeftAccount,
    RightAccount,
    classify_account,
    create_account,
)


class TestAccountInheritance:
    """测试账户类继承关系。"""

    def test_left_account_is_basic_account(self):
        assert issubclass(LeftAccount, BasicAccount)

    def test_right_account_is_basic_account(self):
        assert issubclass(RightAccount, BasicAccount)

    def test_assets_account_is_left_account(self):
        assert issubclass(AssetsAccount, LeftAccount)

    def test_fee_account_is_left_account(self):
        assert issubclass(FeeAccount, LeftAccount)

    def test_debt_account_is_right_account(self):
        assert issubclass(DebtAccount, RightAccount)

    def test_equity_account_is_right_account(self):
        assert issubclass(EquityAccount, RightAccount)


class TestSignConversion:
    """测试符号转换规则（红线测试）。"""

    def test_left_account_increase_is_positive(self):
        """LeftAccount: 资金转入/增加 → +Count"""
        acc = AssetsAccount("Assets:Bank")
        result = acc.to_beancount_amount(Decimal("1000"), is_increase=True)
        assert result == Decimal("1000")

    def test_left_account_decrease_is_negative(self):
        """LeftAccount: 资金转出/减少 → -Count"""
        acc = AssetsAccount("Assets:Bank")
        result = acc.to_beancount_amount(Decimal("1000"), is_increase=False)
        assert result == Decimal("-1000")

    def test_right_account_increase_is_negative(self):
        """RightAccount: 资金转入/增加 → -Count"""
        acc = EquityAccount("Equity:Capital")
        result = acc.to_beancount_amount(Decimal("1000"), is_increase=True)
        assert result == Decimal("-1000")

    def test_right_account_decrease_is_positive(self):
        """RightAccount: 资金转出/减少 → +Count"""
        acc = EquityAccount("Equity:Capital")
        result = acc.to_beancount_amount(Decimal("1000"), is_increase=False)
        assert result == Decimal("1000")

    def test_fee_account_follows_left_rule(self):
        """FeeAccount 遵循 LeftAccount 规则。"""
        acc = FeeAccount("Expenses:Cost")
        assert acc.to_beancount_amount(Decimal("500"), is_increase=True) == Decimal("500")
        assert acc.to_beancount_amount(Decimal("500"), is_increase=False) == Decimal("-500")

    def test_debt_account_follows_right_rule(self):
        """DebtAccount 遵循 RightAccount 规则。"""
        acc = DebtAccount("Liabilities:Loans")
        assert acc.to_beancount_amount(Decimal("500"), is_increase=True) == Decimal("-500")
        assert acc.to_beancount_amount(Decimal("500"), is_increase=False) == Decimal("500")

    def test_reject_negative_amount(self):
        """对外接口拒绝负数金额。"""
        acc = AssetsAccount("Assets:Bank")
        with pytest.raises(ValueError, match="正数金额"):
            acc.to_beancount_amount(Decimal("-100"), is_increase=True)

    def test_is_debit_positive(self):
        """测试 is_debit_positive 方法。"""
        assert LeftAccount("Assets:Bank").is_debit_positive() is True
        assert RightAccount("Equity:Capital").is_debit_positive() is False
        assert AssetsAccount("Assets:Bank").is_debit_positive() is True
        assert FeeAccount("Expenses:Cost").is_debit_positive() is True
        assert DebtAccount("Liabilities:Loans").is_debit_positive() is False
        assert EquityAccount("Equity:Capital").is_debit_positive() is False


class TestAccountFactory:
    """测试账户工厂函数。"""

    def test_create_assets_account(self):
        acc = create_account("Assets:Bank", "assets")
        assert isinstance(acc, AssetsAccount)
        assert acc.account_path == "Assets:Bank"

    def test_create_fee_account(self):
        acc = create_account("Expenses:Cost", "fee")
        assert isinstance(acc, FeeAccount)

    def test_create_debt_account(self):
        acc = create_account("Liabilities:Loans", "debt")
        assert isinstance(acc, DebtAccount)

    def test_create_equity_account(self):
        acc = create_account("Equity:Capital", "equity")
        assert isinstance(acc, EquityAccount)

    def test_create_account_with_alias(self):
        """测试别名支持。"""
        acc = create_account("Assets:Bank", "asset")
        assert isinstance(acc, AssetsAccount)

        acc = create_account("Expenses:Cost", "expenses")
        assert isinstance(acc, FeeAccount)

        acc = create_account("Liabilities:Loans", "liability")
        assert isinstance(acc, DebtAccount)

        acc = create_account("Equity:Capital", "income")
        assert isinstance(acc, EquityAccount)

    def test_create_account_unknown_type(self):
        """测试未知类型抛出异常。"""
        with pytest.raises(ValueError, match="未知账户类型"):
            create_account("Assets:Bank", "unknown")

    def test_classify_account(self):
        """测试账户分类。"""
        assert classify_account("Assets:Bank") == "assets"
        assert classify_account("Liabilities:Loans") == "debt"
        assert classify_account("Equity:Capital") == "equity"
        assert classify_account("Income:Sales") == "equity"
        assert classify_account("Expenses:Cost") == "fee"


class TestAccountEquality:
    """测试账户相等性。"""

    def test_same_type_same_path_equal(self):
        acc1 = AssetsAccount("Assets:Bank")
        acc2 = AssetsAccount("Assets:Bank")
        assert acc1 == acc2

    def test_different_type_not_equal(self):
        acc1 = AssetsAccount("Assets:Bank")
        acc2 = EquityAccount("Assets:Bank")
        assert acc1 != acc2

    def test_different_path_not_equal(self):
        acc1 = AssetsAccount("Assets:Bank")
        acc2 = AssetsAccount("Assets:Cash")
        assert acc1 != acc2

    def test_hash_consistency(self):
        acc1 = AssetsAccount("Assets:Bank")
        acc2 = AssetsAccount("Assets:Bank")
        assert hash(acc1) == hash(acc2)