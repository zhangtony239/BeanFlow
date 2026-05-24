"""Account class for BeanFlow.

Represents Beancount account types with full path support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class AccountType(Enum):
    """Beancount账户类型枚举"""
    ASSETS = "Assets"
    LIABILITIES = "Liabilities"
    EQUITY = "Equity"
    INCOME = "Income"
    EXPENSES = "Expenses"

    @classmethod
    def from_string(cls, type_str: str) -> AccountType:
        """从字符串解析账户类型"""
        type_map = {
            "assets": cls.ASSETS,
            "liabilities": cls.LIABILITIES,
            "equity": cls.EQUITY,
            "income": cls.INCOME,
            "expenses": cls.EXPENSES,
            "a": cls.ASSETS,
            "l": cls.LIABILITIES,
            "e": cls.EQUITY,
            "i": cls.INCOME,
            "x": cls.EXPENSES,
        }
        normalized = type_str.lower()
        if normalized not in type_map:
            raise ValueError(f"Unknown account type: {type_str}")
        return type_map[normalized]

    def is_debit_positive(self) -> bool:
        """判断是否为借方增加类型

        Assets和Expenses为借方增加，贷方减少
        Liabilities、Equity、Income为贷方增加，借方减少
        """
        return self in (AccountType.ASSETS, AccountType.EXPENSES)


@dataclass
class Account:
    """Beancount账户类

    Attributes:
        account_type: 账户类型
        components: 账户组件列表
        full_name: 完整账户名
    """
    account_type: AccountType
    components: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.components and self.account_type:
            self.components = [self.account_type.value]
        elif self.components and self.components[0].lower() != self.account_type.value.lower():
            self.components.insert(0, self.account_type.value)

    @property
    def full_name(self) -> str:
        """获取完整账户名"""
        return ":".join(self.components)

    def with_suffix(self, *suffixes: str) -> Account:
        """添加账户后缀

        Args:
            *suffixes: 后缀组件

        Returns:
            添加后缀后的新账户
        """
        new_components = list(self.components) + list(suffixes)
        return Account(self.account_type, new_components)

    def append_component(self, component: str) -> Account:
        """追加账户组件

        Args:
            component: 要添加的组件

        Returns:
            添加组件后的新账户
        """
        new_components = list(self.components) + [component]
        return Account(self.account_type, new_components)

    @classmethod
    def parse(cls, account_string: str) -> Account:
        """从字符串解析Account

        Args:
            account_string: 账户字符串，如 "Assets:Bank:ProjectA"

        Returns:
            Account实例
        """
        if not account_string:
            raise ValueError("Account string cannot be empty")

        parts = account_string.split(":")
        if len(parts) < 1:
            raise ValueError(f"Invalid account string: {account_string}")

        type_str = parts[0]
        components = [c for c in parts if c]

        try:
            account_type = AccountType.from_string(type_str)
        except ValueError:
            account_type = AccountType.ASSETS

        return cls(account_type, components)

    @classmethod
    def from_type(cls, account_type: AccountType, *components: str) -> Account:
        """从类型创建Account

        Args:
            account_type: 账户类型
            *components: 账户组件

        Returns:
            Account实例
        """
        return cls(account_type, list(components))

    def __str__(self) -> str:
        return self.full_name

    def __repr__(self) -> str:
        return f"Account({self.account_type.value}, {self.components})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Account):
            return False
        return self.full_name == other.full_name

    def __hash__(self) -> int:
        return hash(self.full_name)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Account):
            return NotImplemented
        return self.full_name < other.full_name


@dataclass
class PostingAccount:
    """分录账户，用于Transaction中的分录

    支持简写形式自动补全
    """
    raw_string: str
    resolved_account: Account | None = None

    def __post_init__(self):
        self.resolved_account = Account.parse(self.raw_string)

    @property
    def full_name(self) -> str:
        return self.resolved_account.full_name if self.resolved_account else self.raw_string

    def __str__(self) -> str:
        return self.full_name


def create_accounts_from_config(
    account_type: AccountType,
    base_path: str,
    *components: str
) -> Account:
    """从配置创建账户

    Args:
        account_type: 账户类型
        base_path: 基础路径
        *components: 额外组件

    Returns:
        Account实例
    """
    parts = base_path.split(":") + list(components)
    return Account(account_type, parts)


def build_account_path(
    account_type: AccountType,
    project_name: str,
    *segments: str
) -> str:
    """构建账户完整路径

    Args:
        account_type: 账户类型
        project_name: 项目名称
        *segments: 额外路径段

    Returns:
        完整账户路径字符串
    """
    segments = (account_type.value, project_name) + segments
    return ":".join(segments)
