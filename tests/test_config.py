"""
配置文件 Pydantic 解析器单元测试。

验证:
    1. mapping_dictionary.yaml 解析正确
    2. audit.yaml 解析正确
    3. env.yaml 解析正确
    4. .bf_todo.yaml 解析正确
    5. 字段校验正确
"""

import pytest
from pathlib import Path
import tempfile

from bf.core.config import (
    AccountTypeEnum,
    AuditConfig,
    AuditMode,
    EnvConfig,
    MappingDictionary,
    MappingEntry,
    ProjectMeta,
    Role,
    TodoEntry,
    TodoList,
    load_audit_config,
    load_env_config,
    load_mapping_dictionary,
    load_todo_list,
    save_todo_list,
)


class TestMappingDictionary:
    """测试会计科目映射字典。"""

    def test_mapping_entry_validation(self):
        """测试 MappingEntry 字段校验。"""
        entry = MappingEntry(
            id="Assets:Bank",
            type=AccountTypeEnum.ASSETS,
            temp=False,
            names=["bank", "银行"],
        )
        assert entry.id == "Assets:Bank"
        assert entry.type == AccountTypeEnum.ASSETS
        assert entry.temp is False
        assert entry.names == ["bank", "银行"]

    def test_mapping_entry_id_must_contain_colon(self):
        """测试 id 必须包含冒号。"""
        with pytest.raises(Exception):
            MappingEntry(id="InvalidPath", type=AccountTypeEnum.ASSETS)

    def test_mapping_dictionary_resolve_alias(self):
        """测试别名解析。"""
        mapping = MappingDictionary(
            entries=[
                MappingEntry(id="Assets:Bank", type=AccountTypeEnum.ASSETS, names=["bank"]),
                MappingEntry(id="Equity:Capital", type=AccountTypeEnum.EQUITY, names=["capital"]),
            ]
        )
        entry = mapping.resolve_alias("bank")
        assert entry.id == "Assets:Bank"

        entry = mapping.resolve_alias("Assets:Bank")
        assert entry.id == "Assets:Bank"

    def test_mapping_dictionary_resolve_alias_not_found(self):
        """测试别名解析失败。"""
        mapping = MappingDictionary(entries=[])
        with pytest.raises(KeyError, match="无法解析别名"):
            mapping.resolve_alias("unknown")

    def test_mapping_dictionary_get_by_id(self):
        """测试按 ID 获取。"""
        mapping = MappingDictionary(
            entries=[
                MappingEntry(id="Assets:Bank", type=AccountTypeEnum.ASSETS),
            ]
        )
        entry = mapping.get_by_id("Assets:Bank")
        assert entry is not None
        assert entry.id == "Assets:Bank"

        entry = mapping.get_by_id("Unknown")
        assert entry is None

    def test_mapping_dictionary_overlay(self):
        """测试 MappingDictionary 的 overlay 覆盖合并。"""
        parent = MappingDictionary(
            reserved_embedding_model=None,
            entries=[
                MappingEntry(id="Assets:Bank", type=AccountTypeEnum.ASSETS, temp=False, names=["bank"]),
                MappingEntry(id="Liabilities:Loans", type=AccountTypeEnum.DEBT, temp=False, names=["loans"]),
            ]
        )
        child = MappingDictionary(
            reserved_embedding_model=None,
            entries=[
                # 覆盖已有科目
                MappingEntry(id="Assets:Bank", type=AccountTypeEnum.ASSETS, temp=True, names=["bank", "ali"]),
                # 追加新科目
                MappingEntry(id="Expenses:WIP", type=AccountTypeEnum.FEE, temp=True, names=["wip"]),
            ]
        )
        
        merged = parent.overlay(child)
        
        # 1. 检查覆盖的科目
        bank_entry = merged.get_by_id("Assets:Bank")
        assert bank_entry is not None
        assert bank_entry.temp is True  # 覆盖成功
        assert bank_entry.names == ["bank", "ali"]  # 覆盖成功
        
        # 2. 检查未被覆盖的父级科目
        loans_entry = merged.get_by_id("Liabilities:Loans")
        assert loans_entry is not None
        assert loans_entry.temp is False
        
        # 3. 检查追加的新科目
        wip_entry = merged.get_by_id("Expenses:WIP")
        assert wip_entry is not None
        assert wip_entry.temp is True
        assert wip_entry.type == AccountTypeEnum.FEE


class TestAuditConfig:
    """测试审计权限配置。"""

    def test_audit_config_defaults(self):
        """测试默认值。"""
        config = AuditConfig()
        assert config.mode == AuditMode.SOLO
        assert config.allow_force_merge is False
        assert config.roles == []

    def test_solo_mode_allows_all(self):
        """测试 solo 模式允许所有操作。"""
        config = AuditConfig(mode=AuditMode.SOLO)
        assert config.has_permission("any_key", "any_permission") is True

    def test_standard_mode_checks_permission(self):
        """测试 standard 模式校验权限。"""
        config = AuditConfig(
            mode=AuditMode.STANDARD,
            roles=[
                Role(
                    name="admin",
                    ssh_public_keys=["ssh-rsa AAAA... admin@example.com"],
                    permissions=["checkoff_todo", "force_settle"],
                )
            ],
        )
        assert config.has_permission("ssh-rsa AAAA... admin@example.com", "checkoff_todo") is True
        assert config.has_permission("ssh-rsa AAAA... admin@example.com", "delete_project") is False
        assert config.has_permission("unknown_key", "checkoff_todo") is False


class TestEnvConfig:
    """测试项目环境配置。"""

    def test_env_config_creation(self):
        """测试创建配置。"""
        config = EnvConfig(
            project=ProjectMeta(name="test", currency="CNY", tax_rate=0.13),
        )
        assert config.project.name == "test"
        assert config.project.currency == "CNY"
        assert config.project.tax_rate == 0.13

    def test_env_config_name_required(self):
        """测试项目名称必填。"""
        with pytest.raises(Exception):
            EnvConfig(project=ProjectMeta(name=""))

    def test_env_config_get_effective(self):
        """测试配置覆盖。"""
        config = EnvConfig(
            project=ProjectMeta(name="test"),
            overrides={"allow_force_merge": False},
        )
        assert config.get_effective("allow_force_merge") is False
        assert config.get_effective("unknown", "default") == "default"


class TestTodoList:
    """测试待办列表。"""

    def test_todo_entry_creation(self):
        """测试创建待办条目。"""
        entry = TodoEntry(
            id="test_001",
            type="temp_account_uncleared",
            message="临时科目未清零",
        )
        assert entry.id == "test_001"
        assert entry.resolved is False

    def test_todo_list_has_unresolved(self):
        """测试是否有未核销待办。"""
        todo_list = TodoList(
            todos=[
                TodoEntry(id="1", type="test", message="test", resolved=False),
                TodoEntry(id="2", type="test", message="test", resolved=True),
            ]
        )
        assert todo_list.has_unresolved is True

    def test_todo_list_all_resolved(self):
        """测试全部已核销。"""
        todo_list = TodoList(
            todos=[
                TodoEntry(id="1", type="test", message="test", resolved=True),
            ]
        )
        assert todo_list.has_unresolved is False

    def test_todo_list_resolve(self):
        """测试核销待办。"""
        todo_list = TodoList(
            todos=[
                TodoEntry(id="1", type="test", message="test", resolved=False),
            ]
        )
        assert todo_list.resolve("1") is True
        assert todo_list.todos[0].resolved is True

    def test_todo_list_resolve_not_found(self):
        """测试核销不存在的待办。"""
        todo_list = TodoList(todos=[])
        assert todo_list.resolve("unknown") is False

    def test_todo_list_get_unresolved(self):
        """测试获取未核销待办。"""
        todo_list = TodoList(
            todos=[
                TodoEntry(id="1", type="test", message="test", resolved=False),
                TodoEntry(id="2", type="test", message="test", resolved=True),
            ]
        )
        unresolved = todo_list.get_unresolved()
        assert len(unresolved) == 1
        assert unresolved[0].id == "1"


class TestConfigFileIO:
    """测试配置文件 I/O。"""

    def test_load_save_todo_list(self, tmp_path):
        """测试待办列表保存和加载。"""
        todo_list = TodoList(
            todos=[
                TodoEntry(id="1", type="test", message="test message"),
            ]
        )
        todo_path = tmp_path / ".bf_todo.yaml"
        save_todo_list(todo_list, todo_path)

        loaded = load_todo_list(todo_path)
        assert len(loaded.todos) == 1
        assert loaded.todos[0].id == "1"
        assert loaded.todos[0].message == "test message"

    def test_load_mapping_dictionary(self, tmp_path):
        """测试加载科目映射字典。"""
        import yaml
        data = {
            "version": "1.0",
            "entries": [
                {"id": "Assets:Bank", "type": "assets", "temp": False, "names": ["bank"]},
            ],
        }
        config_path = tmp_path / "mapping_dictionary.yaml"
        with open(config_path, "w") as f:
            yaml.safe_dump(data, f)

        mapping = load_mapping_dictionary(config_path)
        assert len(mapping.entries) == 1
        assert mapping.entries[0].id == "Assets:Bank"

    def test_load_audit_config(self, tmp_path):
        """测试加载审计配置。"""
        import yaml
        data = {
            "version": "1.0",
            "mode": "standard",
            "allow_force_merge": False,
            "roles": [],
        }
        config_path = tmp_path / "audit.yaml"
        with open(config_path, "w") as f:
            yaml.safe_dump(data, f)

        audit = load_audit_config(config_path)
        assert audit.mode == AuditMode.STANDARD

    def test_load_env_config(self, tmp_path):
        """测试加载项目配置。"""
        import yaml
        data = {
            "project": {
                "name": "test_project",
                "currency": "CNY",
                "tax_rate": 0.13,
            },
            "overrides": {},
            "exchange_rates": {},
        }
        config_path = tmp_path / "env.yaml"
        with open(config_path, "w") as f:
            yaml.safe_dump(data, f)

        env = load_env_config(config_path)
        assert env.project.name == "test_project"
        assert env.project.currency == "CNY"

    def test_load_nonexistent_file(self):
        """测试加载不存在的文件。"""
        with pytest.raises(FileNotFoundError):
            load_mapping_dictionary(Path("/nonexistent/path.yaml"))