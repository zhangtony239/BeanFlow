"""
ProjectManager 单元测试。

验证:
    1. 创建非 root 项目时，强制校验 root 项目的存在性。
    2. 创建非 root 项目时，强制将 parent 设为 "root"。
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from bf.project_manager import ProjectManager


def test_create_project_requires_root(tmp_path):
    """测试创建非 root 项目时，强制校验 root 项目的存在性。"""
    workspace = tmp_path
    mgr = ProjectManager(workspace)
    mgr.start()

    # 1. 尝试直接创建非 root 项目，应该抛出 ValueError
    with pytest.raises(ValueError, match="必须先创建并初始化 'root' 项目"):
        mgr.create_project("my_project")

    # 2. 创建 root 项目
    root_proj = mgr.create_project("root")
    assert root_proj.name == "root"
    assert root_proj.parent is None

    # 3. 再次创建 non-root 项目，应该成功
    sub_proj = mgr.create_project("my_project")
    assert sub_proj.name == "my_project"
    assert sub_proj.parent == "root"

    mgr.stop()
