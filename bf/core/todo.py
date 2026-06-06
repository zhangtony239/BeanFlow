"""
ToDoHandler（二阶段待办处理）。

职责:
    1. 生成待办 — 当校验失败时自动创建 .bf_todo.yaml 条目
    2. 解析待办 — 读取并展示当前项目的待办列表
    3. 核销待办 — 标记 resolved: true，与审计模块联动校验核销权限

solo 模式下自动核销所有待办，不阻塞流程。
standard 模式下校验核销权限后才能标记为 resolved。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .config import (
    AuditConfig,
    AuditMode,
    TodoEntry,
    TodoList,
    load_todo_list,
    save_todo_list,
)
from .git_engine import GitEngine


class ToDoHandler:
    """二阶段待办处理器。

    用法:
        handler = ToDoHandler(project_path, audit_config)
        handler.generate("temp_account_uncleared", "临时科目未清零: ...")
        todos = handler.list_all()
        handler.checkoff("todo_id", ssh_key="...")
    """

    def __init__(
        self,
        project_path: Path,
        audit: Optional[AuditConfig] = None,
        engine: Optional[GitEngine] = None,
    ) -> None:
        self.project_path = Path(project_path).resolve()
        self.todo_path = self.project_path / ".bf_todo.yaml"
        self.audit = audit or AuditConfig()
        self.engine = engine or GitEngine(self.project_path)

    # ── 生成待办 ─────────────────────────────────────

    def generate(self, todo_type: str, message: str, commit: bool = True) -> TodoEntry:
        """生成一条待办并持久化。

        solo 模式下自动标记为 resolved。
        """
        import uuid
        from datetime import datetime

        entry = TodoEntry(
            id=f"{todo_type}_{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now().isoformat(),
            type=todo_type,
            message=message,
            resolved=(self.audit.mode == AuditMode.SOLO),
        )

        todo_list = self._load()
        todo_list.todos.append(entry)
        self._save(todo_list, commit=commit)
        return entry

    def generate_batch(self, entries: list[tuple[str, str]], commit: bool = True) -> list[TodoEntry]:
        """批量生成待办。"""
        results = []
        for todo_type, message in entries:
            results.append(self.generate(todo_type, message, commit=False))
        if commit and results:
            self._save(self._load(), commit=True)
        return results

    # ── 解析/展示 ────────────────────────────────────

    def list_all(self) -> TodoList:
        """获取所有待办。"""
        return self._load()

    def list_unresolved(self) -> list[TodoEntry]:
        """获取未核销待办。"""
        return self._load().get_unresolved()

    def has_unresolved(self) -> bool:
        """是否有未核销待办。"""
        return self._load().has_unresolved

    # ── 核销 ────────────────────────────────────────

    def checkoff(self, todo_id: str, ssh_key: Optional[str] = None) -> bool:
        """核销指定待办。

        solo 模式：直接核销
        standard 模式：校验核销权限
        """
        todo_list = self._load()

        # 权限校验
        if self.audit.mode == AuditMode.STANDARD:
            if not ssh_key:
                raise PermissionError("standard 模式下核销待办需要提供 SSH 公钥")
            if not self.audit.has_permission(ssh_key, "checkoff_todo"):
                raise PermissionError(f"SSH 公钥 {ssh_key[:20]}... 无核销待办权限")

        success = todo_list.resolve(todo_id)
        if success:
            self._save(todo_list, commit=True)
        return success

    def checkoff_all(self, ssh_key: Optional[str] = None) -> int:
        """核销所有待办。返回核销数量。"""
        if self.audit.mode == AuditMode.STANDARD:
            if not ssh_key:
                raise PermissionError("standard 模式下核销待办需要提供 SSH 公钥")
            if not self.audit.has_permission(ssh_key, "checkoff_todo"):
                raise PermissionError("无核销待办权限")

        todo_list = self._load()
        count = 0
        for t in todo_list.todos:
            if not t.resolved:
                t.resolved = True
                count += 1
        if count:
            self._save(todo_list, commit=True)
        return count

    # ── 内部 ────────────────────────────────────────

    def _load(self) -> TodoList:
        if self.todo_path.exists():
            return load_todo_list(self.todo_path)
        return TodoList()

    def _save(self, todo_list: TodoList, commit: bool = True) -> None:
        save_todo_list(todo_list, self.todo_path)
        if commit:
            self.engine.commit_all("todo: 更新待办列表")