"""
CLI 命令层 —— 所有用户交互入口。

命令列表:
    /bf init          — 创建项目（支持层级嵌套）
    /bf pay           — 通用转账记账
    /bf fundraising   — 创建筹资阶段 AutoProject
    /bf procurement   — 创建采购阶段 AutoProject
    /bf production    — 创建生产阶段 AutoProject
    /bf sales         — 创建销售阶段 AutoProject
    /bf profit        — 创建利润分配阶段 AutoProject
    /bf settle        — 阶段结项清算
    /bf todo          — 待办查看/核销
    /bf diff          — 滑动时间窗口对账
    /bf export        — 导出 PDF 会计账簿
    /bf delete        — 清算并终结项目
    /bf list          — 列出所有项目
"""

from __future__ import annotations

import locale
import os
import sys
from datetime import date

# Windows 终端 UTF-8 编码强制设置
if sys.platform == "win32":
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    try:
        locale.setlocale(locale.LC_ALL, "zh_CN.UTF-8")
    except locale.Error:
        pass
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from .core.account import create_account, classify_account
from .core.checker import Checker
from .core.config import MappingEntry, TodoEntry
from .core.exporter import PDFExporter
from .core.todo import ToDoHandler
from .project import (
    Project,
    FundraisingProject,
    ProcurementProject,
    ProductionProject,
    SalesProject,
    ProfitProject,
    PHASE_CLASS_MAP,
)
from .project_manager import ProjectManager
from .utils.reconciler import SlidingWindowReconciler, ReconciliationItem, ReconciliationResult

app = typer.Typer(
    name="bf",
    help="BeanFlow - Beancount 业务流管理系统",
    no_args_is_help=True,
)

# ── 全局状态 ────────────────────────────────────────

_workspace = Path.cwd()
_manager: Optional[ProjectManager] = None


def _get_manager() -> ProjectManager:
    global _manager
    if _manager is None:
        _manager = ProjectManager(_workspace)
        _manager.start()
    return _manager


def _echo_success(msg: str) -> None:
    typer.echo(f"[OK] {msg}")


def _echo_error(msg: str) -> None:
    typer.echo(f"[ERROR] {msg}")


def _echo_warning(msg: str) -> None:
    typer.echo(f"[WARN] {msg}")


# ═══════════════════════════════════════════════════
# /bf init
# ═══════════════════════════════════════════════════


@app.command()
def init(
    proj_name: Annotated[str, typer.Argument(help="项目名称")],
    under: Annotated[Optional[str], typer.Option("--under", help="父项目名称列表，逗号分隔")] = None,
) -> None:
    """创建项目，支持指定父项目实现层级嵌套。

    示例:
        bf init root                          # 创建根项目
        bf init my_project --under root       # 在 root 下创建子项目
    """
    mgr = _get_manager()

    # 如果有父项目，先校验父项目存在
    parent_names = []
    if under:
        parent_names = [n.strip() for n in under.split(",") if n.strip()]

    if parent_names:
        for pname in parent_names:
            proj_path = _workspace / pname
            if not proj_path.exists() or not (proj_path / "env.yaml").exists():
                _echo_error(f"父项目 {pname!r} 不存在")
                raise typer.Exit(1)

    # 确定项目路径
    if parent_names:
        # 子项目创建在父项目目录下
        parent_path = _workspace / parent_names[0]
        proj_path = parent_path / proj_name
    else:
        proj_path = _workspace / proj_name

    if proj_path.exists():
        _echo_error(f"项目 {proj_name!r} 已存在")
        raise typer.Exit(1)

    # 创建项目
    base_path = _workspace / parent_names[0] if parent_names else _workspace
    proj = mgr.create_project(proj_name, parent=parent_names[0] if parent_names else None, base_path=base_path)
    _echo_success(f"项目 {proj_name!r} 创建成功")
    typer.echo(f"  路径：{proj.path}")
    if parent_names:
        typer.echo(f"  父项目：{parent_names[0]}")


# ═══════════════════════════════════════════════════
# /bf pay
# ═══════════════════════════════════════════════════


@app.command()
def pay(
    from_account: Annotated[str, typer.Argument(help="付款方账户（资金转出方）")],
    to_account: Annotated[str, typer.Argument(help="收款方账户（资金转入方）")],
    count: Annotated[float, typer.Argument(help="金额")],
    reason: Annotated[str, typer.Option("--reason", "-r", help="交易原因")],
    proj: Annotated[str, typer.Option("--proj", "-p", help="目标项目名称")] = "root",
) -> None:
    """通用转账记账，从 from 账户转入 to 账户。

    语义：from_account 减少，to_account 增加（符合资金流转逻辑）

    示例:
        bf pay Assets:Bank Equity:Capital 1000000 --reason "股东初始投资" --proj root
        bf pay Assets:Bank Assets:Inventory 50000 --reason "采购原材料" --proj root
    """
    mgr = _get_manager()
    proj_obj = mgr.get_project(proj)

    # 解析别名
    mapping = proj_obj.mapping
    from_id = _resolve_account(mapping, from_account)
    to_id = _resolve_account(mapping, to_account)

    # 获取账户类型
    from_type = classify_account(from_id)
    to_type = classify_account(to_id)

    from_acc = create_account(from_id, from_type)
    to_acc = create_account(to_id, to_type)

    # 符号转换：from 账户减少，to 账户增加
    amount = Decimal(str(count))
    from_beancount = from_acc.to_beancount_amount(amount, is_increase=False)  # 转出/减少
    to_beancount = to_acc.to_beancount_amount(amount, is_increase=True)  # 转入/增加

    # 校验借贷平衡
    checker = Checker(mapping)
    balance_report = checker.check_balance([from_beancount, to_beancount])
    if not balance_report.all_passed:
        for r in balance_report.errors():
            _echo_error(r.message)
        raise typer.Exit(1)

    # 生成 Beancount 分录
    today = date.today().isoformat()
    narration = reason or f"转账：{from_account} → {to_account}"
    entry = f'{today} * "{narration}"'
    entry += f"\n    {from_id}  {from_beancount} CNY"
    entry += f"\n    {to_id}  {to_beancount} CNY"

    proj_obj.append_transaction(entry, reason=narration)
    _echo_success(f"记账成功：{from_account} → {to_account} {count} CNY")
    typer.echo(f"  项目：{proj_obj}")
    typer.echo(f"  摘要：{narration}")


def _resolve_account(mapping, alias: str) -> str:
    """解析账户别名。"""
    if ":" in alias:
        # 已经是完整路径
        return alias
    try:
        entry = mapping.resolve_alias(alias)
        return entry.id
    except KeyError:
        # 可能是简单别名，尝试直接使用
        return alias


# ═══════════════════════════════════════════════════
# /bf fundraising / procurement / production / sales / profit
# ═══════════════════════════════════════════════════


def _create_phase_command(phase_name: str, phase_label: str):
    """工厂函数：创建阶段命令。"""

    @app.command(name=phase_name)
    def phase_cmd(
        proj: Annotated[str, typer.Option("--proj", "-p", help="父项目名称")] = "root",
    ) -> None:
        """创建{phase_label}阶段 AutoProject。"""
        mgr = _get_manager()
        parent = mgr.get_project(proj)

        phase_num = {"fundraising": "1", "procurement": "2", "production": "3", "sales": "4", "profit": "5"}.get(phase_name, "0")
        auto_cls = PHASE_CLASS_MAP.get(phase_name)
        if auto_cls is None:
            _echo_error(f"未知的阶段类型: {phase_name}")
            raise typer.Exit(1)

        auto = parent.create_autoproject(f"{phase_num}_{phase_name}", auto_cls)
        _echo_success(f"{phase_label}阶段项目创建成功")
        typer.echo(f"  父项目：{proj}")
        typer.echo(f"  阶段路径：{auto.path}")

    if phase_cmd.__doc__:
        phase_cmd.__doc__ = phase_cmd.__doc__.format(phase_label=phase_label)
    return phase_cmd


for name, label in [
    ("fundraising", "筹资"),
    ("procurement", "采购"),
    ("production", "生产"),
    ("sales", "销售"),
    ("profit", "利润分配"),
]:
    _create_phase_command(name, label)


# ═══════════════════════════════════════════════════
# /bf settle
# ═══════════════════════════════════════════════════


@app.command()
def settle(
    proj: Annotated[str, typer.Option("--proj", "-p", help="阶段项目名称")] = "",
    force: Annotated[bool, typer.Option("--force", "-f", help="强行平账")] = False,
) -> None:
    """阶段结项清算。

    Happy Path: 所有临时科目已清零，自动 merge 到父项目
    Sad Path:  临时科目未清零，生成 Todo 阻塞
    Force Path: 有权限时强行平账

    示例:
        bf settle --proj phase_1_fundraising
        bf settle --proj phase_1_fundraising --force
    """
    if not proj:
        _echo_error("请指定阶段项目名称：--proj <name>")
        raise typer.Exit(1)

    mgr = _get_manager()

    # 搜索阶段项目路径
    proj_path = _workspace / proj
    if not proj_path.exists():
        # 在所有项目中搜索
        found = False
        for pname in mgr.list_projects():
            candidate = _workspace / pname / proj
            if candidate.exists():
                proj_path = candidate
                found = True
                break
        if not found:
            _echo_error(f"阶段项目 {proj!r} 不存在")
            raise typer.Exit(1)

    proj_obj = mgr.get_project(proj, base_path=proj_path.parent)

    from .project import AutoProject
    if not isinstance(proj_obj, AutoProject):
        _echo_error(f"项目 {proj!r} 不是 AutoProject，无法结项")
        raise typer.Exit(1)

    if force:
        _echo_warning("强制平账模式：将自动生成待处理财产损溢冲抵分录")

    success, message = proj_obj.settle(force=force)

    if success:
        _echo_success(message)
    else:
        _echo_error(message)


# ═══════════════════════════════════════════════════
# /bf todo
# ═══════════════════════════════════════════════════


@app.command()
def todo(
    proj_name: Annotated[str, typer.Argument(help="项目名称")] = "",
    checkoff: Annotated[Optional[str], typer.Option("--checkoff", "-c", help="核销待办 ID")] = None,
    list_all: Annotated[bool, typer.Option("--all", "-a", help="显示所有待办（含已核销）")] = False,
) -> None:
    """查看或核销待办事项。

    示例:
        bf todo my_project                    # 查看未核销待办
        bf todo my_project --all             # 查看所有待办
        bf todo my_project --checkoff abc123 # 核销指定待办
    """
    if not proj_name:
        _echo_error("请指定项目名称")
        raise typer.Exit(1)

    mgr = _get_manager()
    proj = mgr.get_project(proj_name)
    handler = ToDoHandler(proj.path, audit=mgr.audit, engine=proj.engine)

    if checkoff:
        # 核销
        try:
            success = handler.checkoff(checkoff)
            if success:
                _echo_success(f"待办 {checkoff!r} 已核销")
            else:
                _echo_error(f"待办 {checkoff!r} 不存在或已核销")
        except PermissionError as e:
            _echo_error(str(e))
            raise typer.Exit(1)
    else:
        # 查看
        todo_list = handler.list_all()
        entries = todo_list.todos if list_all else todo_list.get_unresolved()

        if not entries:
            typer.echo("没有待办事项")
            return

        typer.echo(typer.style("待办列表:", fg=typer.colors.BRIGHT_BLUE, bold=True))
        for entry in entries:
            status = "[x]" if entry.resolved else "[ ]"
            color = typer.colors.GREEN if entry.resolved else typer.colors.RED
            typer.echo(typer.style(f"  [{status}] {entry.id}", fg=color))
            typer.echo(f"    类型：{entry.type}")
            typer.echo(f"    描述：{entry.message}")
            typer.echo(f"    时间：{entry.timestamp}")
            typer.echo()


# ═══════════════════════════════════════════════════
# /bf diff
# ═══════════════════════════════════════════════════


@app.command()
def diff(
    source: Annotated[str, typer.Argument(help="外部账单文件路径")],
    proj_list: Annotated[Optional[str], typer.Argument(help="项目名称列表，逗号分隔")] = None,
    tolerance: Annotated[int, typer.Option("--tolerance", "-t", help="时间窗口容差天数")] = 3,
) -> None:
    """扫描外部账单与系统实际状态，生成调节表。

    核心算法：滑动时间窗口对比
    - 周期边缘 ±Δt 容差内不匹配 → 未达账项（仅记录，不阻塞）
    - 周期内部孤立不匹配 → 错漏账项（生成 Todo，阻塞流程）

    示例:
        bf diff bank_statement.csv my_project
        bf diff external.bean proj1,proj2 --tolerance 5
    """
    source_path = Path(source)
    if not source_path.exists():
        _echo_error(f"外部账单文件不存在：{source}")
        raise typer.Exit(1)

    # 读取外部账单
    external_content = source_path.read_text(encoding="utf-8")
    external_items = SlidingWindowReconciler.parse_beancount_transactions(external_content)

    projects = []
    if proj_list:
        for name in proj_list.split(","):
            name = name.strip()
            if name:
                projects.append(name)
    else:
        mgr = _get_manager()
        projects = mgr.list_projects()

    mgr = _get_manager()
    reconciler = SlidingWindowReconciler(tolerance_days=tolerance)

    all_errors = []

    for pname in projects:
        try:
            proj = mgr.get_project(pname)
            bean_content = proj.read_bean()
            system_items = SlidingWindowReconciler.parse_beancount_transactions(bean_content)

            result = reconciler.reconcile(external_items, system_items)

            typer.echo(typer.style(f"\n项目：{pname}", fg=typer.colors.BRIGHT_BLUE, bold=True))
            typer.echo(f"  匹配：{len(result.matched)} 笔")
            typer.echo(f"  未达账项：{len(result.outstanding)} 笔")
            typer.echo(f"  错漏账项：{len(result.errors)} 笔")

            # 未达账项
            for item in result.outstanding:
                typer.echo(f"    [WARN] [未达] {item.date} {item.amount} {item.description}")

            # 错漏账项 → 生成 Todo
            if result.errors:
                handler = ToDoHandler(proj.path, audit=mgr.audit, engine=proj.engine)
                for item in result.errors:
                    typer.echo(f"    [ERROR] [错漏] {item.date} {item.amount} {item.description}")
                    handler.generate(
                        "reconciliation_error",
                        f"对账错漏：{item.date} {item.amount} {item.description} (来源：{item.source})",
                    )
                all_errors.extend(result.errors)

        except FileNotFoundError as e:
            _echo_warning(f"项目 {pname!r}: {e}")

    if all_errors:
        _echo_warning(f"\n共发现 {len(all_errors)} 笔错漏账项，已生成待办阻塞后续流程")
        typer.echo("  使用 bf todo <project> 查看待办")


# ═══════════════════════════════════════════════════
# /bf export
# ═══════════════════════════════════════════════════


@app.command()
def export(
    proj_name: Annotated[str, typer.Argument(help="项目名称")],
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="输出路径")] = None,
    type: Annotated[str, typer.Option("--type", "-t", help="报表类型: enterprise | cashflow | tax")] = "enterprise",
    format: Annotated[str, typer.Option("--format", "-f", help="导出格式: pdf | excel")] = "pdf",
) -> None:
    """导出项目当前账务状态为 PDF 或 Excel 会计账簿。

    示例:
        bf export my_project
        bf export my_project --type cashflow --format excel
    """
    mgr = _get_manager()
    proj = mgr.get_project(proj_name)

    # 1. 选择 Provider
    from .core.exporter import EnterpriseReportProvider, CashFlowReportProvider, TaxReportProvider
    if type == "enterprise":
        provider = EnterpriseReportProvider(proj)
    elif type == "cashflow":
        provider = CashFlowReportProvider(proj)
    elif type == "tax":
        provider = TaxReportProvider(proj)
    else:
        _echo_error(f"不支持的报表类型: {type}")
        raise typer.Exit(1)

    # 2. 获取数据
    if type == "enterprise":
        report_data = provider.get_detail_ledger_data()
    elif type == "cashflow":
        report_data = provider.get_detail_ledger_data()
    elif type == "tax":
        report_data = provider.get_detail_ledger_data()
    else:
        _echo_error(f"不支持的报表类型: {type}")
        raise typer.Exit(1)

    # 3. 选择 Exporter
    from .core.exporter import PDFExporter, ExcelExporter
    ext = "pdf" if format == "pdf" else "xlsx"
    out_path = Path(output) if output else Path(f"{proj_name}_{type}_report.{ext}")

    if format == "pdf":
        exporter = PDFExporter(out_path)
    elif format == "excel":
        exporter = ExcelExporter(out_path)
    else:
        _echo_error(f"不支持的导出格式: {format}")
        raise typer.Exit(1)

    # 4. 导出
    try:
        exporter.export_report(report_data)
        _echo_success(f"报表已导出：{out_path}")
    except Exception as e:
        _echo_error(f"导出失败: {e}")
        raise typer.Exit(1)


# ═══════════════════════════════════════════════════
# /bf delete
# ═══════════════════════════════════════════════════


@app.command()
def delete(
    proj_name: Annotated[str, typer.Argument(help="项目名称")],
    force: Annotated[bool, typer.Option("--force", "-f", help="强制删除")] = False,
) -> None:
    """清算并终结项目。

    必须先完成所有阶段结项，清零所有临时科目，否则禁止执行。

    示例:
        bf delete my_project
        bf delete my_project --force
    """
    mgr = _get_manager()
    proj = mgr.get_project(proj_name)

    # 检查是否有未结项阶段
    phase_projects = proj.list_phase_projects()
    if phase_projects and not force:
        _echo_error(f"项目 {proj_name!r} 存在未结项阶段项目:")
        for pp in phase_projects:
            typer.echo(f"  - {pp.name}")
        typer.echo("  请先结项所有阶段项目，或使用 --force 强制删除")
        raise typer.Exit(1)

    # 检查待办
    todo_list = proj.get_todo_list()
    if todo_list.has_unresolved and not force:
        _echo_error(f"项目 {proj_name!r} 存在未核销待办:")
        for t in todo_list.get_unresolved():
            typer.echo(f"  - {t.id}: {t.message}")
        typer.echo("  请先核销所有待办，或使用 --force 强制删除")
        raise typer.Exit(1)

    # 删除
    success = mgr.delete_project(proj_name)
    if success:
        _echo_success(f"项目 {proj_name!r} 已删除")
    else:
        _echo_error(f"删除项目 {proj_name!r} 失败")


# ═══════════════════════════════════════════════════
# /bf list
# ═══════════════════════════════════════════════════


@app.command(name="list")
def list_projects() -> None:
    """列出所有项目。"""
    mgr = _get_manager()
    projects = mgr.list_projects()
    if not projects:
        typer.echo("没有项目")
        return
    typer.echo(typer.style("项目列表:", fg=typer.colors.BRIGHT_BLUE, bold=True))
    for name in projects:
        try:
            proj = mgr.get_project(name)
            phase = proj.env.project.current_phase or "—"
            typer.echo(f"  {name}")
            typer.echo(f"    当前阶段：{phase}")
            typer.echo(f"    路径：{proj.path}")
        except Exception:
            typer.echo(f"  {name}")


# ═══════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════


def main() -> None:
    app()


if __name__ == "__main__":
    main()
