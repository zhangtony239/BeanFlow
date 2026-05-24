"""Project class for BeanFlow.

Project is the traceback unit for accountability.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bf.core.config import Config, ProjectEnv, get_config
from bf.core.beangenerator import ProjectBeanGenerator
from bf.core.transaction import TransactionEntry, PostingEntry
from bf.business.base import BusinessContext

if TYPE_CHECKING:
    from bf.business.base import BusinessProcess


class Project:
    """项目类

    项目是追责单元（Traceback范围）
    包含项目配置、Bean文件生成器、交易记录等

    Attributes:
        name: 项目名称
        path: 项目路径
        env: 项目环境配置
        bean_generator: Bean文件生成器
    """

    def __init__(
        self,
        name: str,
        path: str | Path,
        env: ProjectEnv | None = None,
    ):
        """初始化项目

        Args:
            name: 项目名称
            path: 项目路径
            env: 项目环境配置（可选）
        """
        self.name = name
        self.path = Path(path)
        self.env = env or self._load_env()
        self._setup_bean_generator()
        self._transactions: list[TransactionEntry] = []
        self._load_existing_transactions()

    def _load_env(self) -> ProjectEnv:
        """加载项目环境配置"""
        config = get_config()
        return config.load_project_env(self.path)

    def _setup_bean_generator(self) -> None:
        """设置Bean文件生成器"""
        self.bean_generator = ProjectBeanGenerator(
            project_name=self.name,
            project_path=self.path,
            currencies=["CNY", "USD"],
            default_currency=self.env.project.currency,
        )
        self.bean_generator.setup_standard_accounts()

    def _load_existing_transactions(self) -> None:
        """加载已存在的交易记录"""
        import re

        bean_file = self.path / "main.bean"
        if not bean_file.exists():
            return

        with open(bean_file, "r", encoding="utf-8") as f:
            content = f.read()

        tx_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2})\s+\*\s+"([^"]*)"')

        lines = content.split("\n")
        current_tx = None
        tx_date = None
        tx_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith(";") or not stripped:
                continue

            match = tx_pattern.match(stripped)
            if match:
                if current_tx and tx_lines:
                    self._parse_transaction(tx_date, current_tx, tx_lines)
                    tx_lines = []
                current_tx = match.group(2)
                tx_date = match.group(1)
            elif line.startswith("  ") and current_tx:
                tx_lines.append(line)

        if current_tx and tx_lines:
            self._parse_transaction(tx_date, current_tx, tx_lines)

    def _parse_transaction(self, date_str: str | None, narration: str, lines: list[str]) -> None:
        """解析交易行"""
        if not lines or not date_str or not narration:
            return

        try:
            tx_date = date.fromisoformat(date_str)
        except ValueError:
            return

        postings = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            tokens = line.split()
            if len(tokens) >= 3:
                account = tokens[0]
                amount_str = tokens[1].replace(",", "")
                currency = tokens[2] if len(tokens) > 2 else "CNY"

                try:
                    amount = Decimal(amount_str)
                except:
                    amount = Decimal("0")

                postings.append(PostingEntry(
                    account=account,
                    amount=amount,
                    currency=currency,
                ))

        if postings:
            tx = TransactionEntry(
                date=tx_date,
                narration=narration,
            )
            for p in postings:
                tx.add_posting(p.account, p.amount, p.currency)
            self._transactions.append(tx)

    @property
    def currency(self) -> str:
        """获取项目货币"""
        return self.env.project.currency

    @property
    def tax_rate(self) -> Decimal:
        """获取税率"""
        return Decimal(str(self.env.project.tax_rate))

    def get_business_context(self, narration: str = "", date: date | None = None) -> BusinessContext:
        """获取业务流程上下文

        Args:
            narration: 交易描述
            date: 交易日期

        Returns:
            业务流程上下文
        """
        return BusinessContext(
            project_name=self.name,
            project_path=str(self.path),
            currency=self.currency,
            tax_rate=self.tax_rate,
            narration=narration,
            date=date,
        )

    def add_transaction(self, transaction: TransactionEntry) -> None:
        """添加交易条目

        Args:
            transaction: 交易条目
        """
        self._transactions.append(transaction)
        self.bean_generator.add_transaction(transaction.to_string())

    def add_business_process(self, process: BusinessProcess) -> TransactionEntry:
        """执行业务流程并添加交易

        Args:
            process: 业务流程实例

        Returns:
            生成的交易条目
        """
        tx = process.execute()
        self.add_transaction(tx)
        return tx

    def save(self) -> Path:
        """保存项目Bean文件

        Returns:
            生成的文件路径
        """
        self.bean_generator.transactions.clear()

        for tx in self._transactions:
            self.bean_generator.add_transaction(tx.to_string())

        return self.bean_generator.write_main_bean()

    def generate_report(self) -> str:
        """生成项目报告

        Returns:
            报告内容
        """
        lines = [
            f"# {self.name} - 项目报告",
            f"",
            f"## 项目信息",
            f"- 货币: {self.currency}",
            f"- 税率: {self.tax_rate * 100}%",
            f"- 路径: {self.path}",
            f"",
            f"## 交易记录",
            f"",
        ]

        for i, tx in enumerate(self._transactions, 1):
            lines.append(f"### {i}. {tx.date} - {tx.narration}")
            lines.append("```")
            lines.append(tx.to_string())
            lines.append("```")
            lines.append("")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"Project(name='{self.name}', path={self.path}, currency='{self.currency}')"


class ProjectManager:
    """项目管理器

    负责项目的创建、加载和管理
    """

    def __init__(self, base_path: str | Path | None = None):
        """初始化项目管理器

        Args:
            base_path: 项目根目录（默认为当前目录/projects）
        """
        self.base_path = Path(base_path) if base_path else Path.cwd() / "projects"
        self._projects: dict[str, Project] = {}

    def create_project(
        self,
        name: str,
        currency: str = "CNY",
        tax_rate: float = 0.13,
    ) -> Project:
        """创建新项目

        Args:
            name: 项目名称
            currency: 货币类型
            tax_rate: 税率

        Returns:
            创建的项目实例
        """
        project_path = self.base_path / name
        project_path.mkdir(parents=True, exist_ok=True)

        env = ProjectEnv(
            project={"name": name, "currency": currency, "tax_rate": tax_rate},
            exchange_rates={},
        )

        env_path = project_path / "env.yaml"
        self._save_env(env, env_path)

        project = Project(name, project_path, env)
        self._projects[name] = project

        return project

    def load_project(self, name: str) -> Project | None:
        """加载已有项目

        Args:
            name: 项目名称

        Returns:
            项目实例（如不存在则返回None）
        """
        if name in self._projects:
            return self._projects[name]

        project_path = self.base_path / name
        if not project_path.exists():
            return None

        config = get_config()
        env = config.load_project_env(project_path)

        project = Project(name, project_path, env)
        self._projects[name] = project
        return project

    def list_projects(self) -> list[str]:
        """列出所有项目

        Returns:
            项目名称列表
        """
        if not self.base_path.exists():
            return []

        return [
            d.name for d in self.base_path.iterdir()
            if d.is_dir() and (d / "env.yaml").exists()
        ]

    def delete_project(self, name: str) -> bool:
        """删除项目

        Args:
            name: 项目名称

        Returns:
            是否成功删除
        """
        import shutil

        project_path = self.base_path / name
        if project_path.exists():
            shutil.rmtree(project_path)
            if name in self._projects:
                del self._projects[name]
            return True
        return False

    @staticmethod
    def _save_env(env: ProjectEnv, path: Path) -> None:
        """保存环境配置"""
        import yaml

        data = {
            "project": {
                "name": env.project.name,
                "currency": env.project.currency,
                "tax_rate": env.project.tax_rate,
            },
            "exchange_rates": env.exchange_rates,
        }

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
