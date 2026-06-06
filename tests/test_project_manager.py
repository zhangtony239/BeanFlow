"""
ProjectManager 单元测试。

验证:
    1. 创建非 bf_root 项目时，强制校验 bf_root 项目的存在性。
    2. 创建非 bf_root 项目时，强制将 parent 设为 "bf_root"。
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from bf.project_manager import ProjectManager


def test_create_project_requires_root(tmp_path):
    """测试创建非 bf_root 项目时，强制校验 bf_root 项目的存在性。"""
    workspace = tmp_path
    mgr = ProjectManager(workspace)
    mgr.start()

    # 1. 尝试直接创建非 bf_root 项目，应该抛出 ValueError
    with pytest.raises(ValueError, match="必须先创建并初始化 'bf_root' 项目"):
        mgr.create_project("my_project")

    # 2. 创建 bf_root 项目
    root_proj = mgr.create_project("bf_root")
    assert root_proj.name == "bf_root"
    assert root_proj.parent is None

    # 3. 再次创建 non-root 项目，应该成功
    sub_proj = mgr.create_project("my_project")
    assert sub_proj.name == "my_project"
    assert sub_proj.parent == "bf_root"

    mgr.stop()


def test_delete_project_with_readonly_files(tmp_path):
    """测试删除包含只读文件的项目，验证不会因权限问题报错。"""
    import os
    import stat

    workspace = tmp_path
    mgr = ProjectManager(workspace)
    mgr.start()

    # 创建 bf_root 项目
    mgr.create_project("bf_root")
    # 创建子项目
    proj = mgr.create_project("my_project")

    # 在项目目录下创建一个只读文件
    readonly_file = Path(proj.path) / "readonly.txt"
    readonly_file.write_text("test", encoding="utf-8")
    # 设置为只读属性
    os.chmod(readonly_file, stat.S_IREAD)

    # 验证删除项目成功
    assert mgr.delete_project("my_project") is True
    assert not readonly_file.exists()
    assert not Path(proj.path).exists()

    mgr.stop()
