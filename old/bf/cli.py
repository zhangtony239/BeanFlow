"""BeanFlow CLI - Command Line Interface

Typer-based CLI for BeanFlow operations.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from bf import __version__
from bf.core.config import get_config
from bf.project import Project, ProjectManager
from bf.business.base import BusinessContext, QuickTransfer
from bf.business.fundraising import (
    LoanFundraising,
    EquityFundraising,
    LoanRepayment,
)
from bf.business.procurement import Procurement, ProcurementType
from bf.business.sales import Sales, SalesType, Collection
from bf.business.profit import TaxAccrual, TaxType, DividendDeclaration, DividendPayment

app = typer.Typer(
    name="bf",
    help="BeanFlow - Beancount上游封装库",
    add_completion=False,
    no_args_is_help=True,
)

fundraising_app = typer.Typer(help="资金筹集命令")
procurement_app = typer.Typer(help="采购命令")
sales_app = typer.Typer(help="销售命令")
profit_app = typer.Typer(help="利润分配命令")

app.add_typer(fundraising_app, name="fundraising")
app.add_typer(procurement_app, name="procurement")
app.add_typer(sales_app, name="sales")
app.add_typer(profit_app, name="profit")


def parse_decimal(value: str) -> Decimal:
    """解析字符串为Decimal"""
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise typer.BadParameter(f"无效的金额: {value}")


def _get_project(name: Optional[str] = None) -> Project | None:
    """获取项目实例"""
    manager = ProjectManager()
    if name:
        return manager.load_project(name)
    projects = manager.list_projects()
    if len(projects) == 1:
        return manager.load_project(projects[0])
    return None


def _get_or_create_project(name: str, create: bool = False) -> Project:
    """获取或创建项目"""
    manager = ProjectManager()
    project = manager.load_project(name)
    if project:
        return project
    if create:
        return manager.create_project(name)
    raise typer.BadParameter(f"项目 '{name}' 不存在，请先创建项目或使用 --create 参数")


@app.command()
def init(
    name: str = typer.Argument(..., help="项目名称"),
    currency: str = typer.Option("CNY", "--currency", "-c", help="项目货币"),
    tax_rate: float = typer.Option(0.13, "--tax-rate", "-t", help="税率"),
) -> None:
    """初始化新项目"""
    manager = ProjectManager()
    if manager.load_project(name):
        typer.echo(f"项目 '{name}' 已存在", err=True)
        raise typer.Exit(1)

    project = manager.create_project(name, currency, tax_rate)
    typer.echo(f"✓ 项目 '{name}' 创建成功")
    typer.echo(f"  路径: {project.path}")
    typer.echo(f"  货币: {currency}")
    typer.echo(f"  税率: {tax_rate * 100}%")


@app.command()
def pay(
    from_account: str = typer.Argument(..., help="转出账户"),
    to_account: str = typer.Argument(..., help="转入账户"),
    amount: str = typer.Argument(..., help="金额", callback=parse_decimal),
    reason: str = typer.Argument(..., help="交易描述"),
    project_name: Annotated[str | None, typer.Option("--project", "-p")] = None,
    date_str: Annotated[str | None, typer.Option("--date", "-d")] = None,
) -> None:
    """快速转账"""
    project = _get_or_create_project(project_name or "sample", create=True)
    amount_dec = Decimal(str(amount))

    tx_date = None
    if date_str:
        try:
            tx_date = date.fromisoformat(date_str)
        except ValueError:
            raise typer.BadParameter(f"无效的日期格式: {date_str}")

    context = project.get_business_context(reason, tx_date)

    transfer = QuickTransfer(
        context=context,
        from_account=from_account,
        to_account=to_account,
        amount=amount_dec,
        narration=reason,
        date=tx_date,
    )

    tx = transfer.execute()
    project.add_transaction(tx)

    typer.echo(f"✓ 转账记录已添加")
    typer.echo(f"  日期: {tx.date}")
    typer.echo(f"  描述: {reason}")
    typer.echo(f"  金额: {amount_dec} {project.currency}")
    typer.echo(f"")
    typer.echo(tx.to_string())

    project.save()
    typer.echo(f"")
    typer.echo(f"✓ 已保存到 {project.path / 'main.bean'}")


@fundraising_app.command("borrow")
def fundraising_borrow(
    amount: str = typer.Argument(..., help="借款金额", callback=parse_decimal),
    counterparty: str = typer.Argument(..., help="借款方"),
    project_name: Annotated[str | None, typer.Option("--project", "-p")] = None,
    term: Annotated[int | None, typer.Option("--term", "-t")] = None,
    rate: Annotated[float | None, typer.Option("--rate", "-r")] = None,
    date_str: Annotated[str | None, typer.Option("--date", "-d")] = None,
) -> None:
    """借款融资"""
    project = _get_or_create_project(project_name or "sample", create=True)
    amount_dec = Decimal(str(amount))

    tx_date = None
    if date_str:
        tx_date = date.fromisoformat(date_str)

    context = project.get_business_context(f"借款融资 - {counterparty}", tx_date)

    loan = LoanFundraising(
        context=context,
        amount=amount_dec,
        counterparty=counterparty,
        loan_term=term,
        interest_rate=Decimal(str(rate)) if rate else None,
        date=tx_date,
    )

    tx = project.add_business_process(loan)

    typer.echo(f"✓ 借款融资记录已添加")
    typer.echo(f"  日期: {tx.date}")
    typer.echo(f"  金额: {amount_dec} {project.currency}")
    typer.echo(f"  对方: {counterparty}")
    typer.echo(f"")
    typer.echo(tx.to_string())

    project.save()


@fundraising_app.command("equity")
def fundraising_equity(
    amount: str = typer.Argument(..., help="融资金额", callback=parse_decimal),
    counterparty: str = typer.Argument(..., help="投资方"),
    project_name: Annotated[str | None, typer.Option("--project", "-p")] = None,
    ratio: Annotated[float | None, typer.Option("--ratio")] = None,
    date_str: Annotated[str | None, typer.Option("--date", "-d")] = None,
) -> None:
    """股权融资"""
    project = _get_or_create_project(project_name or "sample", create=True)
    amount_dec = Decimal(str(amount))

    tx_date = None
    if date_str:
        tx_date = date.fromisoformat(date_str)

    context = project.get_business_context(f"股权融资 - {counterparty}", tx_date)

    equity = EquityFundraising(
        context=context,
        amount=amount_dec,
        counterparty=counterparty,
        share_ratio=Decimal(str(ratio)) if ratio else None,
        date=tx_date,
    )

    tx = project.add_business_process(equity)

    typer.echo(f"✓ 股权融资记录已添加")
    typer.echo(f"  日期: {tx.date}")
    typer.echo(f"  金额: {amount_dec} {project.currency}")
    typer.echo(f"  投资方: {counterparty}")
    typer.echo(f"")
    typer.echo(tx.to_string())

    project.save()


@fundraising_app.command("repay")
def fundraising_repay(
    amount: str = typer.Argument(..., help="还款金额", callback=parse_decimal),
    counterparty: str = typer.Argument(..., help="贷款方"),
    project_name: Annotated[str | None, typer.Option("--project", "-p")] = None,
    interest: Annotated[str | None, typer.Option("--interest")] = None,
    date_str: Annotated[str | None, typer.Option("--date", "-d")] = None,
) -> None:
    """偿还借款"""
    project = _get_or_create_project(project_name or "sample", create=True)
    amount_dec = Decimal(str(amount))

    tx_date = None
    if date_str:
        tx_date = date.fromisoformat(date_str)

    context = project.get_business_context(f"偿还借款 - {counterparty}", tx_date)

    interest_dec = Decimal(str(interest)) if interest else None

    repay = LoanRepayment(
        context=context,
        amount=amount_dec,
        counterparty=counterparty,
        interest=interest_dec,
        date=tx_date,
    )

    tx = project.add_business_process(repay)

    typer.echo(f"✓ 还款记录已添加")
    typer.echo(f"  日期: {tx.date}")
    typer.echo(f"  本金: {amount_dec} {project.currency}")
    if interest_dec:
        typer.echo(f"  利息: {interest_dec} {project.currency}")
    typer.echo(f"")
    typer.echo(tx.to_string())

    project.save()


@procurement_app.command("buy")
def procurement_buy(
    amount: str = typer.Argument(..., help="采购金额", callback=parse_decimal),
    counterparty: str = typer.Argument(..., help="供应商"),
    project_name: Annotated[str | None, typer.Option("--project", "-p")] = None,
    proc_type: ProcurementType = typer.Option(
        ProcurementType.RAW_MATERIALS,
        "--type",
        "-t",
        help="采购类型 (raw/office/equipment/services)",
    ),
    with_tax: bool = typer.Option(True, "--with-tax/--no-tax", help="是否含税"),
    date_str: Annotated[str | None, typer.Option("--date", "-d")] = None,
) -> None:
    """采购"""
    project = _get_or_create_project(project_name or "sample", create=True)
    amount_dec = Decimal(str(amount))

    tx_date = None
    if date_str:
        tx_date = date.fromisoformat(date_str)

    context = project.get_business_context(f"采购 - {counterparty}", tx_date)

    proc = Procurement(
        context=context,
        amount=amount_dec,
        counterparty=counterparty,
        procurement_type=proc_type,
        include_tax=with_tax,
        date=tx_date,
    )

    tx = project.add_business_process(proc)

    typer.echo(f"✓ 采购记录已添加")
    typer.echo(f"  日期: {tx.date}")
    typer.echo(f"  金额: {amount_dec} {project.currency} ({'含税' if with_tax else '不含税'})")
    typer.echo(f"  供应商: {counterparty}")
    typer.echo(f"")
    typer.echo(tx.to_string())

    project.save()


@sales_app.command("sell")
def sales_sell(
    amount: str = typer.Argument(..., help="销售金额", callback=parse_decimal),
    counterparty: str = typer.Argument(..., help="客户"),
    project_name: Annotated[str | None, typer.Option("--project", "-p")] = None,
    sales_type: SalesType = typer.Option(SalesType.GOODS, "--type", "-t", help="销售类型 (goods/services)"),
    cost: Annotated[str | None, typer.Option("--cost", "-c")] = None,
    with_tax: bool = typer.Option(True, "--with-tax/--no-tax", help="是否含税"),
    date_str: Annotated[str | None, typer.Option("--date", "-d")] = None,
) -> None:
    """销售"""
    project = _get_or_create_project(project_name or "sample", create=True)
    amount_dec = Decimal(str(amount))

    tx_date = None
    if date_str:
        tx_date = date.fromisoformat(date_str)

    context = project.get_business_context(f"销售 - {counterparty}", tx_date)

    cost_dec = Decimal(str(cost)) if cost else None

    sale = Sales(
        context=context,
        amount=amount_dec,
        counterparty=counterparty,
        sales_type=sales_type,
        cost_of_goods=cost_dec,
        include_tax=with_tax,
        date=tx_date,
    )

    tx = project.add_business_process(sale)

    typer.echo(f"✓ 销售记录已添加")
    typer.echo(f"  日期: {tx.date}")
    typer.echo(f"  金额: {amount_dec} {project.currency} ({'含税' if with_tax else '不含税'})")
    typer.echo(f"  客户: {counterparty}")
    typer.echo(f"")
    typer.echo(tx.to_string())

    project.save()


@sales_app.command("collect")
def sales_collect(
    amount: str = typer.Argument(..., help="收款金额", callback=parse_decimal),
    counterparty: str = typer.Argument(..., help="客户"),
    project_name: Annotated[str | None, typer.Option("--project", "-p")] = None,
    date_str: Annotated[str | None, typer.Option("--date", "-d")] = None,
) -> None:
    """收款"""
    project = _get_or_create_project(project_name or "sample", create=True)
    amount_dec = Decimal(str(amount))

    tx_date = None
    if date_str:
        tx_date = date.fromisoformat(date_str)

    context = project.get_business_context(f"收款 - {counterparty}", tx_date)

    collection = Collection(
        context=context,
        amount=amount_dec,
        counterparty=counterparty,
        date=tx_date,
    )

    tx = project.add_business_process(collection)

    typer.echo(f"✓ 收款记录已添加")
    typer.echo(f"  日期: {tx.date}")
    typer.echo(f"  金额: {amount_dec} {project.currency}")
    typer.echo(f"  客户: {counterparty}")
    typer.echo(f"")
    typer.echo(tx.to_string())

    project.save()


@profit_app.command("accrue-tax")
def profit_accrue_tax(
    amount: str = typer.Argument(..., help="税额", callback=parse_decimal),
    project_name: Annotated[str | None, typer.Option("--project", "-p")] = None,
    tax_type: TaxType = typer.Option(TaxType.INCOME_TAX, "--type", "-t", help="税费类型"),
    date_str: Annotated[str | None, typer.Option("--date", "-d")] = None,
) -> None:
    """计提税费"""
    project = _get_or_create_project(project_name or "sample", create=True)
    amount_dec = Decimal(str(amount))

    tx_date = None
    if date_str:
        tx_date = date.fromisoformat(date_str)

    context = project.get_business_context(f"计提税费 - {tax_type.value}", tx_date)

    tax = TaxAccrual(
        context=context,
        amount=amount_dec,
        tax_type=tax_type,
        date=tx_date,
    )

    tx = project.add_business_process(tax)

    typer.echo(f"✓ 税费计提记录已添加")
    typer.echo(f"  日期: {tx.date}")
    typer.echo(f"  税额: {amount_dec} {project.currency}")
    typer.echo(f"  类型: {tax_type.value}")
    typer.echo(f"")
    typer.echo(tx.to_string())

    project.save()


@profit_app.command("dividend")
def profit_dividend(
    amount: str = typer.Argument(..., help="分红金额", callback=parse_decimal),
    shareholder: str = typer.Argument(..., help="股东"),
    project_name: Annotated[str | None, typer.Option("--project", "-p")] = None,
    action: str = typer.Option("declare", "--action", "-a", help="操作: declare/pay"),
    date_str: Annotated[str | None, typer.Option("--date", "-d")] = None,
) -> None:
    """分红"""
    project = _get_or_create_project(project_name or "sample", create=True)
    amount_dec = Decimal(str(amount))

    tx_date = None
    if date_str:
        tx_date = date.fromisoformat(date_str)

    context = project.get_business_context(f"分红 - {shareholder}", tx_date)

    if action == "declare":
        div = DividendDeclaration(
            context=context,
            amount=amount_dec,
            shareholder=shareholder,
            date=tx_date,
        )
    else:
        div = DividendPayment(
            context=context,
            amount=amount_dec,
            shareholder=shareholder,
            date=tx_date,
        )

    tx = project.add_business_process(div)

    typer.echo(f"✓ 分红{'宣告' if action == 'declare' else '支付'}记录已添加")
    typer.echo(f"  日期: {tx.date}")
    typer.echo(f"  金额: {amount_dec} {project.currency}")
    typer.echo(f"  股东: {shareholder}")
    typer.echo(f"  操作: {'宣告' if action == 'declare' else '支付'}")
    typer.echo(f"")
    typer.echo(tx.to_string())

    project.save()


@app.command()
def list_projects(
    manager_path: Annotated[str | None, typer.Option("--manager", "-m")] = None,
) -> None:
    """列出所有项目"""
    mgr = ProjectManager(manager_path)
    projects = mgr.list_projects()

    if not projects:
        typer.echo("暂无项目，使用 'bf init <name>' 创建新项目")
        return

    typer.echo(f"项目列表 ({len(projects)} 个):")
    for name in projects:
        project = mgr.load_project(name)
        if project:
            typer.echo(f"  • {name}")
            typer.echo(f"    货币: {project.currency}")
            typer.echo(f"    税率: {project.tax_rate * 100}%")
            typer.echo(f"    路径: {project.path}")


@app.command()
def version_cmd(
    detailed: bool = typer.Option(False, "--detailed", help="显示详细信息"),
) -> None:
    """显示版本信息"""
    typer.echo(f"BeanFlow v{__version__}")
    if detailed:
        config = get_config()
        typer.echo(f"全局配置: {config._global_config.version if config._global_config else 'N/A'}")
        typer.echo(f"支持货币: {', '.join(config.get_operating_currencies())}")


@app.callback()
def main_callback() -> None:
    """BeanFlow - Beancount上游封装库"""
    pass


if __name__ == "__main__":
    app()
