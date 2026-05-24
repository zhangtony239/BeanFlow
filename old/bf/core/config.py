"""Configuration management for BeanFlow.

Supports global config.yaml + project-level env.yaml dual-layer configuration system.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class AccountConfig(BaseModel):
    """账户配置"""
    bank: str = "Assets:Bank"
    cash: str = "Assets:Cash"
    receivable: str = "Assets:Receivable"
    inventory: str = "Assets:Inventory"


class LiabilitiesConfig(BaseModel):
    """负债账户配置"""
    payable: str = "Liabilities:Payable"
    loans: str = "Liabilities:Loans"
    tax_payable: str = "Liabilities:Tax-Payable"


class EquityConfig(BaseModel):
    """权益账户配置"""
    capital: str = "Equity:Capital"
    retained: str = "Equity:Retained-Earnings"
    dividend: str = "Equity:Distributions"


class IncomeConfig(BaseModel):
    """收入账户配置"""
    sales: str = "Income:Sales"
    service: str = "Income:Service"


class ExpensesConfig(BaseModel):
    """费用账户配置"""
    cost: str = "Expenses:Cost"
    tax: str = "Expenses:Tax"
    office: str = "Expenses:Office"
    salary: str = "Expenses:Salary"


class DefaultAccountsConfig(BaseModel):
    """默认账户配置"""
    assets: AccountConfig = Field(default_factory=AccountConfig)
    liabilities: LiabilitiesConfig = Field(default_factory=LiabilitiesConfig)
    equity: EquityConfig = Field(default_factory=EquityConfig)
    income: IncomeConfig = Field(default_factory=IncomeConfig)
    expenses: ExpensesConfig = Field(default_factory=ExpensesConfig)


class BeancountConfig(BaseModel):
    """Beancount配置"""
    operating_currency: list[str] = Field(default_factory=lambda: ["CNY", "USD"])


class GlobalConfigModel(BaseModel):
    """全局配置模型"""
    version: str = "1.0"
    beancount: BeancountConfig = Field(default_factory=BeancountConfig)
    default_accounts: DefaultAccountsConfig = Field(default_factory=DefaultAccountsConfig)


class ProjectConfig(BaseModel):
    """项目配置"""
    name: str = "sample"
    currency: str = "CNY"
    tax_rate: float = 0.13


class ProjectEnv(BaseModel):
    """项目环境配置"""
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    exchange_rates: dict[str, float] = Field(default_factory=dict)


class Config:
    """配置管理器

    支持全局config.yaml + 项目级env.yaml双层配置体系
    """

    _instance: Config | None = None
    _global_config: GlobalConfigModel | None = None

    def __new__(cls) -> Config:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._global_config is None:
            self._load_global_config()

    def _load_global_config(self) -> None:
        """加载全局配置"""
        config_paths = [
            Path.cwd() / "config.yaml",
            Path(__file__).parent.parent.parent / "config.yaml",
            Path.home() / ".beanflow" / "config.yaml",
        ]

        for config_path in config_paths:
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                self._global_config = GlobalConfigModel(**data)
                return

        self._global_config = GlobalConfigModel()

    def load_project_env(self, project_path: str | Path) -> ProjectEnv:
        """加载项目级env.yaml配置

        Args:
            project_path: 项目路径

        Returns:
            项目环境配置
        """
        env_path = Path(project_path) / "env.yaml"
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return ProjectEnv(**data)
        return ProjectEnv()

    def get_global_config(self) -> GlobalConfigModel:
        """获取全局配置"""
        return self._global_config

    def get_default_accounts(self) -> DefaultAccountsConfig:
        """获取默认账户配置"""
        return self._global_config.default_accounts

    def get_operating_currencies(self) -> list[str]:
        """获取运营货币列表"""
        return self._global_config.beancount.operating_currency


def get_config() -> Config:
    """获取配置单例"""
    return Config()
