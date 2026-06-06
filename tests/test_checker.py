"""
全局校验器单元测试。

验证:
    1. 科目存在性校验
    2. 借贷平衡校验
    3. 结项临时科目校验
    4. 权限校验
"""

import pytest
from decimal import Decimal

from bf.core.checker import CheckReport, CheckResult, Checker
from bf.core.config import (
    AccountTypeEnum,
    AuditConfig,
    AuditMode,
    MappingDictionary,
    MappingEntry,
    Role,
)


@pytest.fixture
def sample_mapping():
    """创建示例科目映射。"""
    return MappingDictionary(
        entries=[
            MappingEntry(id="Assets:Bank", type=AccountTypeEnum.ASSETS, temp=False),
            MappingEntry(id="Assets:Cash", type=AccountTypeEnum.ASSETS, temp=False),
            MappingEntry(id="Equity:Capital", type=AccountTypeEnum.EQUITY, temp=False),
            MappingEntry(id="Expenses:WIP", type=AccountTypeEnum.FEE, temp=True),
        ]
    )


@pytest.fixture
def checker(sample_mapping):
    """创建校验器。"""
    return Checker(mapping=sample_mapping)


class TestAccountExistenceCheck:
    """测试科目存在性校验。"""

    def test_registered_account(self, checker):
        """测试已注册科目。"""
        report = checker.check_account_exists(["Assets:Bank"])
        assert report.all_passed is True

    def test_unregistered_account(self, checker):
        """测试未注册科目。"""
        report = checker.check_account_exists(["Unknown:Account"])
        assert report.all_passed is False

    def test_subpath_account(self, checker):
        """测试子路径科目（模糊匹配）。"""
        report = checker.check_account_exists(["Assets:Bank:ICBC"])
        # 子路径应该通过（匹配到父级）
        assert report.all_passed is True


class TestBalanceCheck:
    """测试借贷平衡校验。"""

    def test_balanced_postings(self, checker):
        """测试平衡的分录。"""
        report = checker.check_balance([Decimal("1000"), Decimal("-1000")])
        assert report.all_passed is True

    def test_unbalanced_postings(self, checker):
        """测试不平衡的分录。"""
        report = checker.check_balance([Decimal("1000"), Decimal("-500")])
        assert report.all_passed is False

    def test_zero_postings(self, checker):
        """测试零金额分录。"""
        report = checker.check_balance([Decimal("0"), Decimal("0")])
        assert report.all_passed is True

    def test_tolerance(self, checker):
        """测试容差。"""
        report = checker.check_balance([Decimal("1000.00001"), Decimal("-1000")])
        # 在容差范围内
        assert report.all_passed is True


class TestTempAccountCheck:
    """测试临时科目校验。"""

    def test_cleared_temp_account(self, checker):
        """测试已清零的临时科目。"""
        balances = [("Expenses:WIP", Decimal("0"))]
        report, todos = checker.check_temp_cleared(balances)
        assert report.all_passed is True
        assert len(todos) == 0

    def test_uncleared_temp_account(self, checker):
        """测试未清零的临时科目。"""
        balances = [("Expenses:WIP", Decimal("1000"))]
        report, todos = checker.check_temp_cleared(balances)
        assert report.all_passed is False
        assert len(todos) == 1
        assert "未清零" in todos[0].message

    def test_no_temp_accounts(self, checker):
        """测试没有临时科目的情况。"""
        balances = [("Assets:Bank", Decimal("1000"))]
        report, todos = checker.check_temp_cleared(balances)
        assert report.all_passed is True
        assert len(todos) == 0


class TestPermissionCheck:
    """测试权限校验。"""

    def test_solo_mode_allows_all(self):
        """测试 solo 模式允许所有操作。"""
        audit = AuditConfig(mode=AuditMode.SOLO)
        checker = Checker(mapping=MappingDictionary(), audit=audit)
        report = checker.check_permission("any_key", "any_permission")
        assert report.all_passed is True

    def test_standard_mode_with_permission(self):
        """测试 standard 模式有权限。"""
        audit = AuditConfig(
            mode=AuditMode.STANDARD,
            roles=[
                Role(
                    name="admin",
                    ssh_public_keys=["ssh-rsa AAAA..."],
                    permissions=["checkoff_todo"],
                )
            ],
        )
        checker = Checker(mapping=MappingDictionary(), audit=audit)
        report = checker.check_permission("ssh-rsa AAAA...", "checkoff_todo")
        assert report.all_passed is True

    def test_standard_mode_without_permission(self):
        """测试 standard 模式无权限。"""
        audit = AuditConfig(
            mode=AuditMode.STANDARD,
            roles=[
                Role(
                    name="admin",
                    ssh_public_keys=["ssh-rsa AAAA..."],
                    permissions=["checkoff_todo"],
                )
            ],
        )
        checker = Checker(mapping=MappingDictionary(), audit=audit)
        report = checker.check_permission("unknown_key", "checkoff_todo")
        assert report.all_passed is False


class TestCheckReport:
    """测试校验报告。"""

    def test_empty_report(self):
        """测试空报告。"""
        report = CheckReport()
        assert report.all_passed is True
        assert len(report.errors()) == 0

    def test_report_with_errors(self):
        """测试有错误的报告。"""
        report = CheckReport()
        report.add(CheckResult(passed=False, message="error", level="error"))
        report.add(CheckResult(passed=True, message="info", level="info"))
        assert report.all_passed is False
        assert len(report.errors()) == 1

    def test_report_with_warnings_only(self):
        """测试只有警告的报告。"""
        report = CheckReport()
        report.add(CheckResult(passed=False, message="warning", level="warning"))
        # 警告不影响 all_passed
        assert report.all_passed is True