"""
滑动时间窗口对账算法。

核心逻辑:
    1. 周期边缘 ±Δt 容差内不匹配 → 未达账项（仅记录，不阻塞）
    2. 周期内部孤立不匹配 → 错漏账项（生成 Todo，阻塞流程）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple


@dataclass
class ReconciliationItem:
    """对账条目。"""
    date: date
    amount: Decimal
    description: str
    source: str  # "external" or "system"
    matched: bool = False


@dataclass
class ReconciliationResult:
    """对账结果。"""
    matched: List[Tuple[ReconciliationItem, ReconciliationItem]] = field(default_factory=list)
    outstanding: List[ReconciliationItem] = field(default_factory=list)  # 未达账项
    errors: List[ReconciliationItem] = field(default_factory=list)  # 错漏账项

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def is_clean(self) -> bool:
        return len(self.outstanding) == 0 and len(self.errors) == 0


class SlidingWindowReconciler:
    """滑动时间窗口对账器。

    用法:
        reconciler = SlidingWindowReconciler(tolerance_days=3)
        result = reconciler.reconcile(external_items, system_items)
    """

    def __init__(self, tolerance_days: int = 3) -> None:
        self.tolerance_days = tolerance_days
        self.tolerance = Decimal("0.01")

    def reconcile(
        self,
        external_items: List[ReconciliationItem],
        system_items: List[ReconciliationItem],
    ) -> ReconciliationResult:
        """执行对账。

        Args:
            external_items: 外部账单条目
            system_items: 系统实际记录

        Returns:
            ReconciliationResult
        """
        result = ReconciliationResult()
        ext_remaining = list(external_items)
        sys_remaining = list(system_items)

        # 第一轮：精确匹配（日期相同 + 金额相同）
        for ext in list(ext_remaining):
            for sys in list(sys_remaining):
                if ext.date == sys.date and abs(ext.amount - sys.amount) <= self.tolerance:
                    ext.matched = True
                    sys.matched = True
                    result.matched.append((ext, sys))
                    ext_remaining.remove(ext)
                    sys_remaining.remove(sys)
                    break

        # 第二轮：时间窗口内匹配（未达账项识别）
        for ext in list(ext_remaining):
            for sys in list(sys_remaining):
                date_diff = abs((ext.date - sys.date).days)
                if date_diff <= self.tolerance_days and abs(ext.amount - sys.amount) <= self.tolerance:
                    # 周期边缘容差内 → 未达账项
                    result.outstanding.append(ext)
                    result.outstanding.append(sys)
                    ext_remaining.remove(ext)
                    sys_remaining.remove(sys)
                    break

        # 第三轮：剩余全部为错漏账项
        result.errors.extend(ext_remaining)
        result.errors.extend(sys_remaining)

        return result

    @staticmethod
    def parse_beancount_transactions(bean_content: str) -> List[ReconciliationItem]:
        """从 Beancount 内容解析交易列表。"""
        import re
        items = []
        pattern = re.compile(
            r'(\d{4}-\d{2}-\d{2})\s+\*\s+"([^"]*)"',
            re.MULTILINE,
        )
        amount_pattern = re.compile(r'([-+]?\d+(?:\.\d+)?)\s+(\w+)')

        for match in pattern.finditer(bean_content):
            d = date.fromisoformat(match.group(1))
            narration = match.group(2)
            # 找第一个金额
            amount_match = amount_pattern.search(bean_content, match.end())
            if amount_match:
                amount = Decimal(amount_match.group(1))
                items.append(ReconciliationItem(
                    date=d,
                    amount=amount,
                    description=narration,
                    source="system",
                ))
        return items