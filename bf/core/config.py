"""
核心配置文件 Pydantic v2 解析器。

四个 Schema:
    1. mapping_dictionary.yaml  — 会计科目映射字典
    2. audit.yaml               — 去中心化审计权限
    3. env.yaml                 — 项目级覆盖配置
    4. .bf_todo.yaml            — 工作流待办阻塞缓存

所有配置禁止硬编码默认值，严格通过 Pydantic 校验。
"""

from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


# ═══════════════════════════════════════════════════
# 1. mapping_dictionary.yaml
# ═══════════════════════════════════════════════════


class AccountTypeEnum(str, Enum):
    """会计科目 OOP 派生类型。"""
    ASSETS = "assets"
    FEE = "fee"
    DEBT = "debt"
    EQUITY = "equity"


class MappingEntry(BaseModel):
    """单个科目映射条目。"""
    id: str = Field(..., description="标准 Beancount 科目路径")
    type: AccountTypeEnum = Field(..., description="OOP 派生类类型")
    temp: bool = Field(False, description="是否为临时科目")
    names: List[str] = Field(default_factory=list, description="CLI 别名列表")

    @field_validator("id")
    @classmethod
    def id_must_be_valid_path(cls, v: str) -> str:
        if not v or ":" not in v:
            raise ValueError(f"id 必须是有效的 Beancount 科目路径(含':'), 收到: {v!r}")
        return v


class MappingDictionary(BaseModel):
    """会计科目映射字典（全局）。"""
    version: str = "1.0"
    entries: List[MappingEntry] = Field(default_factory=list, description="科目映射条目列表")
    reserved_embedding_model: Optional[str] = Field(
        None, description="预留：向量模糊匹配模型名"
    )

    def resolve_alias(self, alias: str) -> MappingEntry:
        """精确匹配别名 → MappingEntry，暂不实现向量模糊匹配。"""
        for entry in self.entries:
            if alias == entry.id or alias in entry.names:
                return entry
        raise KeyError(f"无法解析别名 {alias!r}，请检查 mapping_dictionary.yaml")

    def get_by_id(self, account_id: str) -> Optional[MappingEntry]:
        for entry in self.entries:
            if entry.id == account_id:
                return entry
        return None


# ═══════════════════════════════════════════════════
# 2. audit.yaml
# ═══════════════════════════════════════════════════


class AuditMode(str, Enum):
    SOLO = "solo"
    STANDARD = "standard"


class Role(BaseModel):
    """角色定义。"""
    name: str
    ssh_public_keys: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)


class AuditConfig(BaseModel):
    """审计权限配置。"""
    version: str = "1.0"
    mode: AuditMode = AuditMode.SOLO
    allow_force_merge: bool = False
    roles: List[Role] = Field(default_factory=list)

    def get_role_by_key(self, ssh_key: str) -> Optional[Role]:
        for role in self.roles:
            for k in role.ssh_public_keys:
                if k.strip() == ssh_key.strip():
                    return role
        return None

    def has_permission(self, ssh_key: str, permission: str) -> bool:
        if self.mode == AuditMode.SOLO:
            return True
        role = self.get_role_by_key(ssh_key)
        if role is None:
            return False
        return permission in role.permissions


# ═══════════════════════════════════════════════════
# 3. env.yaml
# ═══════════════════════════════════════════════════


class ProjectMeta(BaseModel):
    """项目元信息。"""
    name: str = Field(..., min_length=1)
    parent: Optional[str] = None
    current_phase: Optional[str] = None
    currency: str = "CNY"
    tax_rate: float = 0.0


class EnvConfig(BaseModel):
    """项目环境配置。"""
    project: ProjectMeta
    overrides: Dict[str, Any] = Field(default_factory=dict, description="覆盖全局配置的键值对")
    exchange_rates: Dict[str, float] = Field(default_factory=dict)

    @field_validator("project")
    @classmethod
    def check_project(cls, v: ProjectMeta) -> ProjectMeta:
        if not v.name or not v.name.strip():
            raise ValueError("project.name 不能为空")
        return v

    def get_effective(self, key: str, default: Any = None) -> Any:
        """获取生效配置：子项目 overrides > 全局默认。"""
        return self.overrides.get(key, default)


# ═══════════════════════════════════════════════════
# 4. .bf_todo.yaml
# ═══════════════════════════════════════════════════


class TodoEntry(BaseModel):
    """单条待办事项。"""
    id: str = Field(..., description="唯一待办 ID")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    type: str = Field(..., description="待办类型, e.g. 'temp_account_uncleared'")
    message: str = Field(..., description="待办描述")
    resolved: bool = Field(False, description="是否已核销")


class TodoList(BaseModel):
    """待办列表。"""
    version: str = "1.0"
    todos: List[TodoEntry] = Field(default_factory=list)

    @property
    def has_unresolved(self) -> bool:
        return any(not t.resolved for t in self.todos)

    def get_unresolved(self) -> List[TodoEntry]:
        return [t for t in self.todos if not t.resolved]

    def resolve(self, todo_id: str) -> bool:
        for t in self.todos:
            if t.id == todo_id and not t.resolved:
                t.resolved = True
                return True
        return False


# ═══════════════════════════════════════════════════
# 文件 I/O 工具
# ═══════════════════════════════════════════════════


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def load_mapping_dictionary(path: Path) -> MappingDictionary:
    return MappingDictionary(**_read_yaml(path))


def load_audit_config(path: Path) -> AuditConfig:
    return AuditConfig(**_read_yaml(path))


def load_env_config(path: Path) -> EnvConfig:
    return EnvConfig(**_read_yaml(path))


def load_todo_list(path: Path) -> TodoList:
    data = _read_yaml(path)
    todos_data = data.get("todos", [])
    if isinstance(todos_data, list):
        return TodoList(version=data.get("version", "1.0"), todos=[TodoEntry(**t) for t in todos_data])
    return TodoList(**data)


def save_todo_list(todo_list: TodoList, path: Path) -> None:
    _write_yaml(path, todo_list.model_dump())