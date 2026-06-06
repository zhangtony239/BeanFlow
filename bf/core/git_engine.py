"""
Git 版本控制引擎。

封装 GitPython，实现：
    - 自动 init / commit / merge / branch
    - 确保所有操作可追溯
    - 提交信息标准化
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:
    import git
    HAS_GITPYTHON = True
except ImportError:
    HAS_GITPYTHON = False


class GitEngine:
    """Git 操作引擎，确保每次数据变更都生成可追溯的 commit。"""

    def __init__(self, repo_path: Path) -> None:
        self.repo_path = Path(repo_path).resolve()
        self._repo: Optional["git.Repo"] = None

    # ── 仓库生命周期 ─────────────────────────────────

    def init(self, initial_message: str = "init: 初始化项目仓库") -> "GitEngine":
        """初始化 Git 仓库并执行首次 commit。"""
        if not HAS_GITPYTHON:
            raise RuntimeError("需要安装 GitPython: pip install gitpython")
        self.repo_path.mkdir(parents=True, exist_ok=True)
        self._repo = git.Repo.init(self.repo_path)
        # 首次 commit — 空仓库直接提交
        self._first_commit(initial_message)
        return self

    def open(self) -> "GitEngine":
        """打开已有仓库。"""
        if not HAS_GITPYTHON:
            raise RuntimeError("需要安装 GitPython: pip install gitpython")
        self._repo = git.Repo(self.repo_path)
        return self

    @property
    def repo(self) -> "git.Repo":
        if self._repo is None:
            self.open()
        return self._repo

    @property
    def is_initialized(self) -> bool:
        return (self.repo_path / ".git").exists()

    # ── 提交操作 ─────────────────────────────────────

    def _first_commit(self, message: str) -> str:
        """首次提交（空仓库，无 HEAD）。"""
        repo = self.repo
        repo.git.add(A=True)
        commit = repo.index.commit(message, author=git.Actor("BeanFlow", "bf@localhost"))
        return commit.hexsha

    def commit_all(self, message: str, author: Optional[str] = None) -> str:
        """Stage 所有变更并提交。"""
        repo = self.repo
        # 添加所有文件
        repo.git.add(A=True)
        # 检查是否有变更
        try:
            if not repo.index.diff("HEAD"):
                commit = repo.index.commit(message, author=author or git.Actor("BeanFlow", "bf@localhost"))
            else:
                commit = repo.index.commit(message, author=author or git.Actor("BeanFlow", "bf@localhost"))
        except Exception:
            # 空仓库或无效 HEAD，直接提交
            commit = repo.index.commit(message, author=author or git.Actor("BeanFlow", "bf@localhost"))
        return commit.hexsha

    def commit_file(self, file_path: Path, message: str, author: Optional[str] = None) -> str:
        """只提交指定文件。"""
        repo = self.repo
        rel = file_path.relative_to(self.repo_path) if file_path.is_absolute() else file_path
        repo.git.add(str(rel))
        diff = repo.index.diff("HEAD", paths=[str(rel)])
        if not diff:
            # 尝试空提交
            commit = repo.index.commit(message, author=author or git.Actor("BeanFlow", "bf@localhost"),
                                       skip_hooks=True)
        else:
            commit = repo.index.commit(message, author=author or git.Actor("BeanFlow", "bf@localhost"))
        return commit.hexsha

    # ── 合并操作 ─────────────────────────────────────

    def merge(self, source_repo_path: Path, message: str = "merge: 子项目结项归并") -> str:
        """将 source_repo 的内容合并到当前仓库。

        策略：将源仓库文件复制过来后提交。
        （不做真正的 git merge，而是文件级归并以保证可控性）
        """
        import shutil

        repo = self.repo
        src = Path(source_repo_path).resolve()

        # 复制所有非 .git 文件
        for item in src.rglob("*"):
            if ".git" in item.parts:
                continue
            rel = item.relative_to(src)
            dest = self.repo_path / rel
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)

        return self.commit_all(message)

    # ── 分支操作 ─────────────────────────────────────

    def create_branch(self, name: str) -> str:
        """创建并切换到新分支。"""
        repo = self.repo
        current = repo.active_branch
        new_branch = repo.create_head(name)
        new_branch.checkout()
        return name

    def switch_branch(self, name: str) -> str:
        """切换到指定分支。"""
        repo = self.repo
        repo.git.checkout(name)
        return name

    # ── 历史查询 ─────────────────────────────────────

    def log(self, max_count: int = 10) -> list[str]:
        """获取最近 N 次提交信息。"""
        repo = self.repo
        commits = list(repo.iter_commits(max_count=max_count))
        return [f"{c.hexsha[:8]} {c.message.strip()}" for c in commits]

    def last_commit(self) -> Optional[str]:
        """最近一次提交的 hexsha。"""
        try:
            return self.repo.head.commit.hexsha
        except Exception:
            return None