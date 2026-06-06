"""
全局校验器 (def Checker)。

职责:
    1. 科目存在性校验 — 确认科目在 mapping_dictionary 中注册
    2. 借贷平衡校验 — 确认分录借贷相等
    3. 结项临时科目校验 — 结项时确认所有 temp:true 科目已清零
    4. 权限校验 — 对接 audit.yaml 校验操作权限
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Set, Tuple

from .account import BasicAccount
from .config import AuditConfig, MappingDictionary, TodoEntry


@dataclass
class CheckResult:
    """单条校验结果。"""
    passed: bool
    message: str
    level: str = "error"  # error / warning / info


@dataclass
class CheckReport:
    """校验报告。"""
    results: List[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results if r.level == "error")

    def add(self, result: CheckResult) -> None:
        self.results.append(result)

    def errors(self) -> List[CheckResult]:
        return [r for r in self.results if not r.passed and r.level == "error"]


# ── def Checker ──────────────────────────────────────


class Checker:
    """全局校验器。

    用法:
        checker = Checker(mapping=mapping_dict, audit=audit_cfg)
        report = checker.check_account_exists(["Assets:Bank:ICBC"])
        report = checker.check_balance(postings)
        report = checker.check_temp_cleared(...)
    """

    def __init__(
        self,
        mapping: MappingDictionary,
        audit: Optional[AuditConfig] = None,
    ) -> None:
        self.mapping = mapping
        self.audit = audit or AuditConfig()

    # ── 1. 科目存在性校验 ──────────────────────────

    def check_account_exists(self, account_paths: List[str]) -> CheckReport:
        """校验所有科目是否在 mapping_dictionary 中注册。"""
        report = CheckReport()
        registered: Set[str] = {e.id for e in self.mapping.entries}
        for path in account_paths:
            if path not in registered:
                # 也尝试模糊匹配（检查是否为已注册科目的子路径）
                matched = any(path.startswith(r) for r in registered)
                if not matched:
                    report.add(CheckResult(
                        passed=False,
                        message=f"科目 {path!r} 未在 mapping_dictionary.yaml 中注册",
                        level="error",
                    ))
                else:
                    report.add(CheckResult(
                        passed=True,
                        message=f"科目 {path!r} 匹配到已注册父级科目",
                        level="info",
                    ))
            else:
                report.add(CheckResult(
                    passed=True,
                    message=f"科目 {path!r} 已注册",
                    level="info",
                ))
        return report

    # ── 2. 借贷平衡校验 ─────────────────────────────

    def check_balance(self, amounts: List[Decimal]) -> CheckReport:
        """校验 Beancount 分录借贷平衡（所有带符号金额之和应为 0）。"""
        report = CheckReport()
        total = sum(amounts, Decimal("0"))
        tolerance = Decimal("0.0001")
        if abs(total) <= tolerance:
            report.add(CheckResult(
                passed=True,
                message=f"借贷平衡，合计: {total}",
                level="info",
            ))
        else:
            report.add(CheckResult(
                passed=False,
                message=f"借贷不平衡! 合计: {total}，差额: {abs(total)}",
                level="error",
            ))
        return report

    # ── 3. 结项临时科目校验 ──────────────────────────

    def check_temp_cleared(
        self,
        account_balances: List[Tuple[str, Decimal]],
    ) -> Tuple[CheckReport, List[TodoEntry]]:
        """校验所有 temp:true 科目是否已清零。

        Args:
            account_balances: [(科目路径, 当前余额), ...]

        Returns:
            (CheckReport, 未清零待办列表)
        """
        report = CheckReport()
        todos: List[TodoEntry] = []
        temp_entries = [e for e in self.mapping.entries if e.temp]

        for entry in temp_entries:
            balance = Decimal("0")
            for path, bal in account_balances:
                if path == entry.id or path.startswith(entry.id + ":"):
                    balance += bal
            if abs(balance) > Decimal("0.0001"):
                msg = f"临时科目 {entry.id!r} 未清零，余额: {balance}"
                report.add(CheckResult(passed=False, message=msg, level="error"))
                todos.append(TodoEntry(
                    id=f"temp_uncleared_{entry.id.replace(':', '_')}",
                    type="temp_account_uncleared",
                    message=msg,
                ))
            else:
                report.add(CheckResult(
                    passed=True,
                    message=f"临时科目 {entry.id!r} 已清零",
                    level="info",
                ))
        return report, todos

    # ── 4. 权限校验 ─────────────────────────────────

    def check_permission(
        self, ssh_key: str, permission: str, operation: str = ""
    ) -> CheckReport:
        """校验当前用户是否有指定操作权限。

        Args:
            ssh_key: 用户 SSH 公钥
            permission: 所需权限标识
            operation: 操作名称（用于报告）
        """
        report = CheckReport()
        desc = operation or permission
        if self.audit.has_permission(ssh_key, permission):
            report.add(CheckResult(
                passed=True,
                message=f"操作 {desc!r}: 权限校验通过",
                level="info",
            ))
        else:
            report.add(CheckResult(
                passed=False,
                message=f"操作 {desc!r}: 权限不足，需要权限 {permission!r}",
                level="error",
            ))
        return report