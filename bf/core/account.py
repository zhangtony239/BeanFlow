"""
账户类体系 —— 严格借贷符号转换规则。

继承链:
    BasicAccount
    ├── LeftAccount（借方账户：资产、费用）
    │   ├── AssetsAccount
    │   └── FeeAccount
    └── RightAccount（贷方账户：负债、权益、收入）
        ├── DebtAccount
        └── EquityAccount

符号转换红线:
    LeftAccount :  资金转入/增加 → Beancount 数值 +Count
                   资金转出/减少 → Beancount 数值 -Count
    RightAccount:  资金转入/增加 → Beancount 数值 -Count
                   资金转出/减少 → Beancount 数值 +Count

对外接口统一接收正数金额，内部自动转换为 Beancount 符号。
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional


class BasicAccount(ABC):
    """账户基类，定义统一接口。"""

    account_path: str  # Beancount 完整账户路径，如 "Assets:Bank:ICBC"

    def __init__(self, account_path: str) -> None:
        if not account_path:
            raise ValueError("account_path 不能为空")
        self.account_path = account_path

    @abstractmethod
    def is_debit_positive(self) -> bool:
        """借方为正？LeftAccount=True, RightAccount=False"""
        ...

    def to_beancount_amount(self, amount: Decimal, is_increase: bool) -> Decimal:
        """将业务语义（正数金额 + 增减方向）转换为 Beancount 带符号数值。

        Args:
            amount: 正数金额（业务视角）
            is_increase: True=资金转入/增加, False=资金转出/减少

        Returns:
            带 Beancount 借贷方向的 Decimal
        """
        if amount < 0:
            raise ValueError(f"对外接口只接受正数金额，收到: {amount}")
        if self.is_debit_positive():
            # LeftAccount: 增加+ 减少-
            return amount if is_increase else -amount
        else:
            # RightAccount: 增加- 减少+
            return -amount if is_increase else amount

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.account_path!r})"

    def __hash__(self) -> int:
        return hash((self.__class__.__name__, self.account_path))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BasicAccount):
            return NotImplemented
        return self.__class__ == other.__class__ and self.account_path == other.account_path


# ── 借方账户 ──────────────────────────────────────────────


class LeftAccount(BasicAccount):
    """借方账户：资产、费用。资金转入→+Count，资金转出→-Count。"""

    def is_debit_positive(self) -> bool:
        return True


class AssetsAccount(LeftAccount):
    """资产类账户。"""
    pass


class FeeAccount(LeftAccount):
    """费用类账户。"""
    pass


# ── 贷方账户 ──────────────────────────────────────────────


class RightAccount(BasicAccount):
    """贷方账户：负债、权益、收入。资金转入→-Count，资金转出→+Count。"""

    def is_debit_positive(self) -> bool:
        return False


class DebtAccount(RightAccount):
    """负债类账户。"""
    pass


class EquityAccount(RightAccount):
    """权益类账户（含收入）。"""
    pass


# ── 工厂函数 ──────────────────────────────────────────────


def create_account(account_path: str, account_type: str) -> BasicAccount:
    """根据账户路径和类型字符串创建对应的账户实例。

    Args:
        account_path: Beancount 账户路径
        account_type: 类型标识，如 "Assets"/"Fee"/"Debt"/"Equity"
    """
    _type_map = {
        "assets": AssetsAccount,
        "asset": AssetsAccount,
        "fee": FeeAccount,
        "expenses": FeeAccount,
        "expense": FeeAccount,
        "debt": DebtAccount,
        "liability": DebtAccount,
        "liabilities": DebtAccount,
        "equity": EquityAccount,
        "income": EquityAccount,
        "revenue": EquityAccount,
    }
    t = account_type.lower()
    cls = _type_map.get(t)
    if cls is None:
        raise ValueError(f"未知账户类型: {account_type!r}，支持的: {list(_type_map.keys())}")
    return cls(account_path)


def classify_account(account_path: str) -> str:
    """根据 Beancount 路径自动推断账户大类。

    Beancount 五类:
        Assets → LeftAccount/AssetsAccount
        Liabilities → RightAccount/DebtAccount
        Equity → RightAccount/EquityAccount
        Income → RightAccount/EquityAccount
        Expenses → LeftAccount/FeeAccount
    """
    parts = account_path.split(":")
    root = parts[0] if parts else ""
    _map = {
        "assets": "assets",
        "liabilities": "debt",
        "equity": "equity",
        "income": "equity",
        "expenses": "fee",
    }
    return _map.get(root.lower(), "assets")