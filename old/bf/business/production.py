"""生产业务流程模块

支持成本归集、完工入库等生产业务场景。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from bf.business.base import BusinessContext, BusinessProcess


@dataclass
class CostItem:
    """成本项目"""
    account: str
    amount: Decimal
    description: str = ""


@dataclass
class ProductionCostCollection(BusinessProcess):
    """生产成本归集

    将直接材料、直接人工、制造费用等归集到生产成本

    分录:
        借: Expenses:Cost:WIP
        贷: Assets:Inventory (原材料)
        贷: Expenses:Salary (人工)
        贷: Expenses:Overhead (制造费用)
    """

    def __init__(
        self,
        context: BusinessContext,
        product_name: str,
        cost_items: list[CostItem | dict[str, Any]],
        narration: str | None = None,
        date: date | None = None,
    ):
        self.product_name = product_name
        self.cost_items = self._normalize_cost_items(cost_items)
        total = sum(item.amount for item in self.cost_items)
        narration = narration or f"生产成本归集 - {product_name}"
        super().__init__(context, total, narration, date)

    def _normalize_cost_items(self, items: list[CostItem | dict[str, Any]]) -> list[CostItem]:
        normalized = []
        for item in items:
            if isinstance(item, CostItem):
                normalized.append(item)
            elif isinstance(item, dict):
                normalized.append(CostItem(
                    account=item["account"],
                    amount=Decimal(str(item["amount"])),
                    description=item.get("description", ""),
                ))
        return normalized

    def _build_postings(self) -> list[dict[str, Any]]:
        postings = []

        postings.append({
            "account": self._get_account("Expenses", f"WIP-{self.product_name}"),
            "amount": self.amount,
            "currency": self.context.currency,
        })

        for item in self.cost_items:
            postings.append({
                "account": item.account,
                "amount": -item.amount,
                "currency": self.context.currency,
            })

        return postings


@dataclass
class ProductCompletion(BusinessProcess):
    """产品完工入库

    将完工产品从生产成本转入库存商品

    分录:
        借: Assets:Inventory
        贷: Expenses:Cost:WIP
    """

    def __init__(
        self,
        context: BusinessContext,
        product_name: str,
        quantity: int | Decimal,
        unit_cost: Decimal | int | float | str,
        narration: str | None = None,
        date: date | None = None,
    ):
        self.product_name = product_name
        self.quantity = int(quantity) if isinstance(quantity, Decimal) else quantity
        self.unit_cost = Decimal(str(unit_cost))
        total_cost = self.unit_cost * self.quantity

        narration = narration or f"产品完工入库 - {product_name} x {self.quantity}"
        super().__init__(context, total_cost, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        return [
            {
                "account": self._get_account("Assets", f"Inventory-{self.product_name}"),
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Expenses", f"WIP-{self.product_name}"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]


@dataclass
class DirectMaterialAllocation(BusinessProcess):
    """直接材料分配

    将材料费用分配到生产成本

    分录:
        借: Expenses:Cost:WIP
        贷: Assets:Inventory
    """

    def __init__(
        self,
        context: BusinessContext,
        product_name: str,
        material_account: str,
        amount: Decimal | int | float | str,
        narration: str | None = None,
        date: date | None = None,
    ):
        self.product_name = product_name
        self.material_account = material_account
        narration = narration or f"直接材料分配 - {product_name}"
        super().__init__(context, amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        return [
            {
                "account": self._get_account("Expenses", f"WIP-{self.product_name}"),
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self.material_account,
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]


@dataclass
class DirectLaborAllocation(BusinessProcess):
    """直接人工分配

    将人工费用分配到生产成本

    分录:
        借: Expenses:Cost:WIP
        贷: Expenses:Salary
    """

    def __init__(
        self,
        context: BusinessContext,
        product_name: str,
        amount: Decimal | int | float | str,
        narration: str | None = None,
        date: date | None = None,
    ):
        self.product_name = product_name
        narration = narration or f"直接人工分配 - {product_name}"
        super().__init__(context, amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        return [
            {
                "account": self._get_account("Expenses", f"WIP-{self.product_name}"),
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Expenses", "Salary"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]


@dataclass
class ManufacturingOverhead(BusinessProcess):
    """制造费用分配

    将制造费用分配到生产成本

    分录:
        借: Expenses:Cost:WIP
        贷: Expenses:Overhead
    """

    def __init__(
        self,
        context: BusinessContext,
        product_name: str,
        overhead_type: str,
        amount: Decimal | int | float | str,
        narration: str | None = None,
        date: date | None = None,
    ):
        self.product_name = product_name
        self.overhead_type = overhead_type
        narration = narration or f"制造费用分配 - {overhead_type}"
        super().__init__(context, amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        return [
            {
                "account": self._get_account("Expenses", f"WIP-{self.product_name}"),
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Expenses", "Overhead"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]


@dataclass
class InventoryTransfer(BusinessProcess):
    """库存调拨

    在不同库存之间调拨

    分录:
        借: Assets:Inventory:Target
        贷: Assets:Inventory:Source
    """

    def __init__(
        self,
        context: BusinessContext,
        source_product: str,
        target_product: str,
        amount: Decimal | int | float | str,
        narration: str | None = None,
        date: date | None = None,
    ):
        self.source_product = source_product
        self.target_product = target_product
        narration = narration or f"库存调拨 - {source_product} -> {target_product}"
        super().__init__(context, amount, narration, date)

    def _build_postings(self) -> list[dict[str, Any]]:
        return [
            {
                "account": self._get_account("Assets", f"Inventory-{self.target_product}"),
                "amount": self.amount,
                "currency": self.context.currency,
            },
            {
                "account": self._get_account("Assets", f"Inventory-{self.source_product}"),
                "amount": -self.amount,
                "currency": self.context.currency,
            },
        ]
