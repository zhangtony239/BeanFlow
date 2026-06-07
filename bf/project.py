"""
项目类体系 —— 层级嵌套项目模型。

继承链:
    Project（手动初始化的根/子项目）
    └── AutoProject（系统自动托管的阶段子项目）
        ├── FundraisingProject
        ├── ProcurementProject
        ├── ProductionProject
        ├── SalesProject
        └── ProfitProject

Project  : 负责加载配置、管理主账本、触发子项目创建
AutoProject: 核心特性是自动清算能力，结项时扫描所有 temp:true 科目
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from .core.config import (
    EnvConfig,
    MappingDictionary,
    ProjectMeta,
    TodoList,
    load_env_config,
    load_mapping_dictionary,
    load_todo_list,
    save_todo_list,
)
from .core.git_engine import GitEngine


# ═══════════════════════════════════════════════════
# Project
# ═══════════════════════════════════════════════════


class Project:
    """手动初始化的根/子项目。负责加载配置、管理主账本、触发子项目创建。"""

    name: str
    parent: Optional[str]
    path: Path
    env: EnvConfig
    mapping: MappingDictionary
    engine: GitEngine
    _bean_file: Path

    def __init__(self, project_path: Path, mapping: Optional[MappingDictionary] = None) -> None:
        self.path = Path(project_path).resolve()
        if not self.path.exists():
            raise FileNotFoundError(f"项目路径不存在: {self.path}")

        # 加载配置
        env_path = self.path / "env.yaml"
        if not env_path.exists():
            raise FileNotFoundError(f"env.yaml 不存在: {env_path}")
        self.env = load_env_config(env_path)
        self.name = self.env.project.name
        self.parent = self.env.project.parent

        # 科目映射（Overlay 覆盖合并模式）
        base_mapping = self._load_overlay_mappings(default_base=mapping)
        
        mapping_path = self.path / "mapping_dictionary.yaml"
        if mapping_path.exists():
            local_mapping = load_mapping_dictionary(mapping_path)
            self.mapping = base_mapping.overlay(local_mapping)
        else:
            self.mapping = base_mapping

        # Git 引擎
        self.engine = GitEngine(self.path)

        # 主账本文件
        self._bean_file = self.path / f"{self.name}_main.bean"
        if not self._bean_file.exists():
            self._bean_file.touch()

    def _load_overlay_mappings(self, default_base: Optional[MappingDictionary] = None) -> MappingDictionary:
        """向上递归收集所有 mapping_dictionary.yaml，并自上而下（从全局到父级）进行 overlay 合并。"""
        mapping_files: List[Path] = []
        current = self.path.parent  # 从父目录开始向上找
        
        while current != current.parent:
            candidate = current / "mapping_dictionary.yaml"
            if candidate.exists():
                mapping_files.append(candidate)
            current = current.parent

        # 自上而下合并（数组反转，从最外层/全局开始合并）
        merged = default_base or MappingDictionary(reserved_embedding_model=None)
        for f in reversed(mapping_files):
            parent_map = load_mapping_dictionary(f)
            merged = merged.overlay(parent_map)
            
        return merged

    def close(self) -> None:
        """关闭项目，释放资源。"""
        self.engine.close()

    # ── 子项目操作 ───────────────────────────────────

    def create_subproject(self, name: str) -> "Project":
        """在本项目下创建子项目。"""
        sub_path = self.path / name
        sub_path.mkdir(parents=True, exist_ok=True)

        # 生成 env.yaml
        env_cfg = EnvConfig(
            project=ProjectMeta(
                name=name,
                parent=self.name,
                currency=self.env.project.currency,
                tax_rate=self.env.project.tax_rate,
            ),
            overrides=self.env.overrides,
            exchange_rates=self.env.exchange_rates,
        )
        import yaml
        with open(sub_path / "env.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(env_cfg.model_dump(), f, allow_unicode=True, default_flow_style=False)

        # 初始化 Git
        sub_engine = GitEngine(sub_path)
        sub_engine.init(f"init: 创建子项目 {name}，父项目: {self.name}")

        return Project(sub_path, mapping=self.mapping)

    def create_autoproject(self, phase_name: str, auto_cls: Type["AutoProject"]) -> "AutoProject":
        """创建阶段 AutoProject。"""
        phase_path = self.path / f"phase_{phase_name}"
        phase_path.mkdir(parents=True, exist_ok=True)

        phase_num = phase_name.split("_")[0]
        phase_label = phase_name.split("_", 1)[1] if "_" in phase_name else phase_name

        # 生成 env.yaml
        env_cfg = EnvConfig(
            project=ProjectMeta(
                name=f"{self.name}_{phase_label}",
                parent=self.name,
                current_phase=phase_label,
                currency=self.env.project.currency,
                tax_rate=self.env.project.tax_rate,
            ),
            overrides=self.env.overrides,
            exchange_rates=self.env.exchange_rates,
        )
        import yaml
        with open(phase_path / "env.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(env_cfg.model_dump(), f, allow_unicode=True, default_flow_style=False)

        # 初始化 Git
        phase_engine = GitEngine(phase_path)
        phase_engine.init(f"init: 创建阶段项目 {phase_label}，父项目: {self.name}")

        # 更新父项目 current_phase
        self.env.project.current_phase = phase_label
        self._save_env()

        return auto_cls(phase_path, mapping=self.mapping)

    def _save_env(self) -> None:
        import yaml
        with open(self.path / "env.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(self.env.model_dump(), f, allow_unicode=True, default_flow_style=False)

    # ── 账本操作 ─────────────────────────────────────

    def append_transaction(self, beancount_entry: str, reason: str = "") -> None:
        """追加一笔 Beancount 分录到主账本并提交 Git。"""
        with open(self._bean_file, "a", encoding="utf-8") as f:
            f.write("\n" + beancount_entry + "\n")
        msg = f"record: {reason}" if reason else "record: 追加交易分录"
        self.engine.commit_all(msg)

    def read_bean(self) -> str:
        """读取完整账本内容。"""
        if self._bean_file.exists():
            return self._bean_file.read_text(encoding="utf-8")
        return ""

    # ── 待办 ────────────────────────────────────────

    def get_todo_list(self) -> TodoList:
        todo_path = self.path / ".bf_todo.yaml"
        if todo_path.exists():
            return load_todo_list(todo_path)
        return TodoList()

    def save_todo_list(self, todo_list: TodoList) -> None:
        save_todo_list(todo_list, self.path / ".bf_todo.yaml")
        self.engine.commit_all("todo: 更新待办列表")

    # ── 子项目列表 ───────────────────────────────────

    def list_phase_projects(self) -> List[Path]:
        """列出所有阶段子项目目录。"""
        return sorted([p for p in self.path.iterdir() if p.is_dir() and p.name.startswith("phase_")])


# ═══════════════════════════════════════════════════
# AutoProject
# ═══════════════════════════════════════════════════


class AutoProject(Project):
    """系统自动托管的阶段子项目。核心特性：自动清算能力。"""

    phase_name: str

    def __init__(self, project_path: Path, mapping: Optional[MappingDictionary] = None) -> None:
        super().__init__(project_path, mapping=mapping)
        self.phase_name = self.env.project.current_phase or ""

    def get_temp_accounts(self) -> List[str]:
        """获取本阶段涉及的临时科目列表。"""
        return [e.id for e in self.mapping.entries if e.temp]

    def get_temp_balances(self, bean_content: str) -> List[tuple[str, str]]:
        """扫描账本中临时科目的余额。返回 [(科目路径, 余额), ...]。"""
        from decimal import Decimal
        from collections import defaultdict

        balances: dict[str, Decimal] = defaultdict(Decimal)
        temp_ids = set(self.get_temp_accounts())

        for line in bean_content.splitlines():
            line = line.strip()
            if not line or line.startswith((";", "*", "!", "#")):
                continue
            for temp_id in temp_ids:
                if temp_id in line:
                    # 尝试解析金额
                    parts = line.split()
                    for i, p in enumerate(parts):
                        if p.replace(".", "").replace("-", "").isdigit():
                            try:
                                val = Decimal(p)
                                balances[temp_id] += val
                            except Exception:
                                pass
                            break
                        elif p.startswith("-") and p[1:].replace(".", "").isdigit():
                            try:
                                val = Decimal(p)
                                balances[temp_id] += val
                            except Exception:
                                pass
                            break
        return [(k, str(v)) for k, v in balances.items() if v != 0]

    def settle(self, force: bool = False) -> tuple[bool, str]:
        """结项清算。

        Happy Path: 所有临时科目已清零，直接 merge 到父项目
        Sad Path:  临时科目未清零，生成 Todo 阻断
        Force Path: 有权限时，自动生成待处理财产损溢冲抵分录并 merge

        Returns:
            (success, message)
        """
        from .core.checker import Checker, CheckReport

        bean_content = self.read_bean()
        temp_balances = self.get_temp_balances(bean_content)
        checker = Checker(self.mapping)

        # 检查临时科目
        account_balances = [(b[0], __import__("decimal").Decimal(b[1])) for b in temp_balances]
        report, todos = checker.check_temp_cleared(account_balances)

        if report.all_passed:
            # Happy Path: 所有临时科目已清零
            return self._happy_settle()
        elif force:
            # Force Path: 强行平账
            return self._force_settle(todos)
        else:
            # Sad Path: 生成待办阻塞
            return self._sad_settle(todos)

    def _happy_settle(self) -> tuple[bool, str]:
        """Happy Path: 结项并 merge 到父项目。"""
        # 合并账本到父项目
        parent_path = self.path.parent
        parent_bean = parent_path / f"{self.env.project.parent}_main.bean"
        if parent_bean.exists():
            content = self.read_bean()
            with open(parent_bean, "a", encoding="utf-8") as f:
                f.write(f"\n; === 阶段 {self.phase_name} 结项归并 ===\n")
                f.write(content)
            # 提交父项目
            parent_engine = GitEngine(parent_path)
            parent_engine.commit_all(f"settle: {self.phase_name} 阶段结项归并 (Happy Path)")
        return True, f"阶段 {self.phase_name} 结项成功 (Happy Path)"

    def _sad_settle(self, todos: list) -> tuple[bool, str]:
        """Sad Path: 生成待办阻塞。"""
        from .core.config import TodoEntry

        todo_list = self.get_todo_list()
        for t in todos:
            if isinstance(t, TodoEntry):
                todo_list.todos.append(t)
        self.save_todo_list(todo_list)
        unresolved = [t.message for t in todo_list.get_unresolved()]
        return False, f"阶段 {self.phase_name} 结项阻塞: 存在未清零临时科目\n" + "\n".join(f"  - {m}" for m in unresolved)

    def _force_settle(self, todos: list) -> tuple[bool, str]:
        """Force Path: 自动生成待处理财产损溢冲抵分录。"""
        from decimal import Decimal
        from datetime import date

        bean_content = self.read_bean()
        temp_balances = self.get_temp_balances(bean_content)

        # 生成冲抵分录
        postings = []
        for acc_path, balance_str in temp_balances:
            balance = Decimal(balance_str)
            if balance == 0:
                continue
            # 冲抵到 待处理财产损溢
            postings.append(f"    {acc_path}  {-balance} CNY")
            postings.append(f"    Equity:Unsettled-PnL  {balance} CNY")

        if postings:
            today = date.today().isoformat()
            entry = f'{today} * "Force Settle: 待处理财产损溢冲抵 - {self.phase_name}"'
            entry += "\n" + "\n".join(postings)
            self.append_transaction(entry, reason=f"Force Settle: {self.phase_name}")

        # 清除待办
        todo_list = self.get_todo_list()
        for t in todo_list.todos:
            t.resolved = True
        self.save_todo_list(todo_list)

        return self._happy_settle()


# ═══════════════════════════════════════════════════
# 五个阶段派生类
# ═══════════════════════════════════════════════════


class FundraisingProject(AutoProject):
    """筹资阶段 AutoProject。"""
    pass


class ProcurementProject(AutoProject):
    """采购阶段 AutoProject。"""
    pass


class ProductionProject(AutoProject):
    """生产阶段 AutoProject。"""
    pass


class SalesProject(AutoProject):
    """销售阶段 AutoProject。"""
    pass


class ProfitProject(AutoProject):
    """利润分配阶段 AutoProject。"""
    pass


# ── 工厂 ────────────────────────────────────────────


PHASE_CLASS_MAP: Dict[str, Type[AutoProject]] = {
    "fundraising": FundraisingProject,
    "procurement": ProcurementProject,
    "production": ProductionProject,
    "sales": SalesProject,
    "profit": ProfitProject,
}


def create_project(path: Path, mapping: Optional[MappingDictionary] = None) -> Project:
    """工厂函数：根据路径创建 Project 或 AutoProject 实例。"""
    env_path = path / "env.yaml"
    if not env_path.exists():
        raise FileNotFoundError(f"env.yaml 不存在: {env_path}")
    env = load_env_config(env_path)
    phase = env.project.current_phase
    if phase and phase in PHASE_CLASS_MAP:
        return PHASE_CLASS_MAP[phase](path, mapping=mapping)
    return Project(path, mapping=mapping)
