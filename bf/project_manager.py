"""
ProjectManager 有状态守护进程。

听从 DAEMON_KEEPALIVE 配置保持内存待命，减少 CLI 启动开销。
统一调度所有项目操作，对接 CLI 与底层对象。
"""

from __future__ import annotations

import os
import time
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from .core.config import AuditConfig, MappingDictionary, load_audit_config, load_mapping_dictionary
from .project import Project, create_project


class ProjectManager:
    """有状态守护进程，统一调度所有项目操作。

    用法:
        mgr = ProjectManager(workspace_root=Path("."))
        mgr.start()
        proj = mgr.get_project("my_project")
        mgr.stop()
    """

    DAEMON_KEEPALIVE_DEFAULT = 300  # 默认 5 分钟超时

    def __init__(
        self,
        workspace_root: Path,
        daemon_keepalive: Optional[int] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.daemon_keepalive = daemon_keepalive or self.DAEMON_KEEPALIVE_DEFAULT

        # 全局配置
        self.mapping = self._load_global_mapping()
        self.audit = self._load_global_audit()

        # 项目缓存
        self._projects: Dict[str, Project] = {}
        self._lock = threading.Lock()
        self._last_activity = time.time()
        self._running = False
        self._watchdog_thread: Optional[threading.Thread] = None

    # ── 全局配置加载 ─────────────────────────────────

    def _load_global_mapping(self) -> MappingDictionary:
        mp = self.workspace_root / "mapping_dictionary.yaml"
        if mp.exists():
            return load_mapping_dictionary(mp)
        return MappingDictionary(reserved_embedding_model=None)

    def _load_global_audit(self) -> AuditConfig:
        ap = self.workspace_root / "audit.yaml"
        if ap.exists():
            return load_audit_config(ap)
        return AuditConfig()

    # ── 守护进程生命周期 ─────────────────────────────

    def start(self) -> None:
        """启动守护进程。"""
        self._running = True
        self._last_activity = time.time()
        self._watchdog_thread = threading.Thread(target=self._watchdog, daemon=True)
        self._watchdog_thread.start()

    def stop(self) -> None:
        """停止守护进程。"""
        self._running = False
        if self._watchdog_thread:
            self._watchdog_thread.join(timeout=2)
        self._projects.clear()

    def _watchdog(self) -> None:
        """看门狗线程：超时自动退出。"""
        while self._running:
            elapsed = time.time() - self._last_activity
            if elapsed > self.daemon_keepalive:
                self._running = False
                break
            time.sleep(5)

    def _touch(self) -> None:
        """更新最后活动时间。"""
        self._last_activity = time.time()

    # ── 项目操作 ────────────────────────────────────

    def get_project(self, name: str, base_path: Optional[Path] = None) -> Project:
        """获取或加载项目。

        Args:
            name: 项目名称
            base_path: 基础路径（默认为 workspace_root）
        """
        self._touch()
        with self._lock:
            if name in self._projects:
                return self._projects[name]
            base = base_path or self.workspace_root
            proj_path = base / name
            if not proj_path.exists():
                raise FileNotFoundError(f"项目不存在: {proj_path}")
            proj = create_project(proj_path, mapping=self.mapping)
            self._projects[name] = proj
            return proj

    def create_project(self, name: str, parent: Optional[str] = None, base_path: Optional[Path] = None) -> Project:
        """创建新项目。

        Args:
            name: 项目名称
            parent: 父项目名称
            base_path: 基础路径（默认为 workspace_root）
        """
        self._touch()
        base = base_path or self.workspace_root

        # 1. 强制校验 root 项目的存在性
        if name != "root":
            root_path = base / "root"
            if not root_path.exists():
                raise ValueError("创建任何业务项目前，必须先创建并初始化 'root' 项目（总会计主体）！")
            # 强制将 parent 设为 "root"
            parent = "root"

        proj_path = base / name
        if proj_path.exists():
            raise FileExistsError(f"项目已存在: {proj_path}")

        # 创建目录
        proj_path.mkdir(parents=True, exist_ok=True)

        # 生成 env.yaml
        from .core.config import EnvConfig, ProjectMeta
        import yaml

        env_cfg = EnvConfig(
            project=ProjectMeta(name=name, parent=parent),
        )
        with open(proj_path / "env.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(env_cfg.model_dump(), f, allow_unicode=True, default_flow_style=False)

        # 初始化 Git
        from .core.git_engine import GitEngine
        engine = GitEngine(proj_path)
        engine.init(f"init: 创建项目 {name}")

        # 复制 mapping_dictionary（如果是根项目）
        if parent is None:
            mp_src = self.workspace_root / "mapping_dictionary.yaml"
            if mp_src.exists():
                import shutil
                shutil.copy2(mp_src, proj_path / "mapping_dictionary.yaml")

        # 创建主账本
        (proj_path / f"{name}_main.bean").touch()

        proj = Project(proj_path, mapping=self.mapping)
        with self._lock:
            self._projects[name] = proj
        return proj

    def list_projects(self) -> list[str]:
        """列出所有项目。"""
        self._touch()
        projects = []
        for item in self.workspace_root.iterdir():
            if item.is_dir() and (item / "env.yaml").exists():
                # 跳过阶段子项目
                if not item.name.startswith("phase_"):
                    projects.append(item.name)
        return sorted(projects)

    def delete_project(self, name: str) -> bool:
        """删除项目。"""
        self._touch()
        proj_path = self.workspace_root / name
        if not proj_path.exists():
            return False
        import shutil
        import stat

        def remove_readonly(func, path, excinfo):
            os.chmod(path, stat.S_IWRITE)
            func(path)

        shutil.rmtree(proj_path, onerror=remove_readonly)
        with self._lock:
            self._projects.pop(name, None)
        return True

    def invalidate_cache(self, name: Optional[str] = None) -> None:
        """清除缓存。"""
        with self._lock:
            if name:
                self._projects.pop(name, None)
            else:
                self._projects.clear()
