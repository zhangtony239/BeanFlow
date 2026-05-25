# Roo's BeanFlow 工作台笔记 (ROO_NOTE.md)

本文档是 Roo 的专属工作台笔记。在每次开始任务前，必须阅读此文档以理清当前架构思路；在任务完成或架构发生演进时，必须实时回写并更新此文件。

---

## 1. 项目概述与核心定位

BeanFlow 是一个基于 Beancount 的上游封装库，旨在通过 Git 版本控制系统构建“时间线区块链”，以 Unix 哲学思想管理企业财务记账的生命周期。它彻底封装了 Beancount 复杂的正负号规则，对外统一暴露正数输入，并引入了去中心化审计、多阶段生命周期托管（AutoProject）以及智能对账分析等企业级特性。

---

## 2. 物理目录拓扑结构 (Directory Topology)

根据 [`REPO_INIT.md`](REPO_INIT.md)，BeanFlow 采用嵌套与平级相结合的自治 Git 仓库结构：

```text
/ (Workspace Root)
├── Project_root/                        # 企业全局环境 (Root Project)
│   ├── .git/                            # 全局归档总账流水历史
│   ├── config.yaml                      # 全局主配置文件
│   ├── audit.yaml                       # 审计与权限控制配置
│   ├── mapping_dictionary.yaml          # 全局会计科目与别名映射字典
│   └── .bean_cache/                     # Hash缓存与性能索引
│
└── 📁 Project_A/                        # 具体业务实体 (独立项目, 通过 bf init --under root 创建)
    ├── .git/                            # 项目 A 的独立凭证历史
    ├── env.yaml                         # 继承并覆盖 Root 的配置
    ├── Project_A_main.bean              # 主账本文件 (持久化账户)
    ├── .bf_todo.yaml                    # 待办/异常阻断缓存
    │
    │   # === AutoProject (系统自动托管的生命周期状态子项目) ===
    ├── 📁 phase_1_fundraising/          # 筹资阶段
    │   ├── env.yaml
    │   ├── temp_fundraising.bean        # 该阶段产生的临时分录
    │   └── .bf_todo.yaml                # 阶段内待办
    │
    └── 📁 phase_2_procurement/          # 采购阶段 (筹资阶段结项并 merge 后自动生成)
        └── ...
```

---

## 3. 核心配置文件 Schema 规范

### 3.1 会计科目翻译字典 (`mapping_dictionary.yaml`)
用于 CLI 输入别名到标准 Beancount 科目的映射，配合 Embedding 模型实现模糊识别。
- **`id`**: 标准 Beancount 科目 ID（如 `Assets:Current:Alipay`）。
- **`type`**: 对应的 OOP 派生类（决定借贷正负号，如 `AssetsAccount`）。
- **`temp`**: 是否为阶段临时科目（用于结项校验，如 `Liabilities:Short_Term_Loan` 在筹资阶段结束时必须清零）。
- **`names`**: CLI 别名集合（如 `["Alipay", "支付宝", "ali"]`）。

### 3.2 去中心化 SSH 审计配置 (`audit.yaml`)
控制待办核销（`bf todo --checkoff`）以及阶段结项等敏感操作的权限。
- **`mode`**: `solo`（不阻断）或 `standard`（严格基于 SSH 公钥）。
- **`allow_force_merge`**: 是否允许使用 `--force` 触发“待处理财产损溢”强行平账。
- **`roles`**: 角色与 SSH 公钥映射（如 `cashier`, `accountant`, `cfo`）。
- **`permissions`**: 敏感操作权限分配（如 `phase_liquidation` 仅限 `["cfo", "accountant"]`）。

### 3.3 项目级环境覆盖 (`env.yaml`)
子项目目录下的配置，继承并覆盖全局行为。
- **`project`**: 包含 `name`, `parent`, `current_phase` 等。
- **`overrides`**: 仅在当前项目生效的重载（如 `allow_force_merge: false`）。

### 3.4 工作流阻塞缓存 (`.bf_todo.yaml`)
当系统检测到 `temp: true` 科目未平或对账异常时生成。若列表不为空，禁止向后流转。
- **`todos`**: 待办列表，包含 `id`, `timestamp`, `type`, `message`, `resolved`。

---

## 4. OOP 核心对象模型 (Object-Oriented Core)

根据 [`OOP_TREE.md`](OOP_TREE.md) 与 [`REPO_INIT.md`](REPO_INIT.md)，BeanFlow 的核心类图结构如下：

### 4.1 账户类层次结构 (Account Hierarchy)
BeanFlow 彻底封装了 Beancount 的正负号规则，对外统一暴露正数输入。

```text
BasicAccount (账户基类)
├── LeftAccount (借方账户基类)
│   ├── AssetsAccount (资产账户)
│   └── FeeAccount (费用账户)
└── RightAccount (贷方账户基类)
    ├── DebtAccount (负债账户)
    └── EquityAccount (权益账户)
```

#### 符号转换规则 (Signage Rules)
- **`LeftAccount` (借方)**：
  - 资金转入 (To) / 增加 ➡️ 对应 Beancount 数值: `+Count`
  - 资金转出 (From) / 减少 ➡️ 对应 Beancount 数值: `-Count`
- **`RightAccount` (贷方)**：
  - 资金转入 (To) / 增加 ➡️ 对应 Beancount 数值: `-Count`
  - 资金转出 (From) / 减少 ➡️ 对应 Beancount 数值: `+Count`

### 4.2 项目类层次结构 (Project Hierarchy)
项目是追责单元（Traceback 范围），支持多阶段生命周期托管。

```text
Project (手动初始化的全局或实体项目节点)
└── AutoProject (由 BeanFlow 接管的阶段性子账本，具有自动清算能力)
    ├── FundraisingProject (筹资阶段项目)
    ├── ProcurementProject (采购阶段项目)
    ├── ProductionProject (生产阶段项目)
    ├── SalesProject (销售阶段项目)
    └── ProfitProject (利润分配阶段项目)
```

- **`ProjectManager`**: 作为 `cli` 和 `Project` 之间的**有状态守护进程 (Daemon)**，听从 YAML 配置中的 `DAEMON_KEEPALIVE` 内存待命时间，负责项目的生命周期管理、缓存和状态保持。

### 4.3 其他功能模块与工具 (Utilities & Others)
- **`cli.py`**: 命令行接口，负责解析用户输入并与 `ProjectManager` 守护进程通信。
- **`ToDoHandler` (二阶段)**: 待办事项处理器，负责解析、生成、核销 `.bf_todo.yaml` 阻塞缓存，并与 `audit.yaml` 审计模块联动。

---

## 5. 核心工作流规范 (Core Workflows)

### 5.1 记账工作流 (`/bf pay` 等)
1. 接收 CLI 输入的源/目标别名及金额。
2. 检索 `mapping_dictionary.yaml`（精确匹配 -> 向量模糊匹配）。
3. 获取目标科目对应的 OOP 对象。
4. 应用 `LeftAccount`/`RightAccount` 符号计算规则。
5. 追加标准 Beancount 分录并自动执行 `git commit`。

### 5.2 结项清算工作流 (Phase Liquidation)
1. 扫描当前 `AutoProject` 中所有 `temp: true` 的科目。
2. **Happy Path**: 若全部为 0，生成结项 commit，触发 `git merge` 合并入父级。
3. **Sad Path**: 若存在不为 0 的科目，拦截操作，生成 `.bf_todo.yaml` 记录。
4. **Force Path (`--force`)**: 校验 SSH 公钥与 `audit.allow_force_merge`。自动生成冲抵分录转入“待处理财产损溢”（`equity:pending_property_loss`），强行将临时科目平账后提交 Merge。

### 5.3 对账分析工作流 (`/bf diff`)
利用 Git History 与外部导入的 `.bean` 进行“滑动时间窗口算法”对比：
- 周期边缘（`±Δt` 容差内）不匹配 ➡️ 归类为 **未达账项 (In-Transit)**。
- 周期内部孤立不匹配 ➡️ 归类为 **错漏账项 (Error/Omission)**，阻断并强制抛出 Todo。

### 5.4 报表导出工作流 (`/bf export`)
- 支持将项目账目、资产负债表等财务报表导出为 PDF 格式。
- 底层 PDF 渲染库统一采用 **ReportLab**，确保排版精确与跨平台一致性。

---

## 6. 上一个大版本遗产 (`old/`) 深度剖析

旧版本代码（位于 `old/` 目录）实现了一个基础的 Beancount 封装和业务流程生成器，但与 [`REPO_INIT.md`](REPO_INIT.md) 及 [`OOP_TREE.md`](OOP_TREE.md) 定义的全新架构存在显著差异。

### 6.1 遗产模块清单与核心逻辑
- **[`old/bf/core/account.py`](old/bf/core/account.py)**:
  - 定义了 [`AccountType`](old/bf/core/account.py:13) 枚举（`ASSETS`, `LIABILITIES`, `EQUITY`, `INCOME`, `EXPENSES`）。
  - 实现了 [`AccountType.is_debit_positive()`](old/bf/core/account.py:41) 方法，用于判断是否为借方增加类型。
  - 提供了 [`Account`](old/bf/core/account.py:51) 数据类，支持账户组件拼接（`with_suffix`, `append_component`）和解析（`parse`）。
  - 提供了 [`PostingAccount`](old/bf/core/account.py:158) 用于分录账户。
- **[`old/bf/core/transaction.py`](old/bf/core/transaction.py)**:
  - 定义了 [`PostingEntry`](old/bf/core/transaction.py:16)，包含账户、金额、货币等，并实现了 [`PostingEntry.to_string()`](old/bf/core/transaction.py:56) 转换为 Beancount 语法。
  - 定义了 [`TransactionEntry`](old/bf/core/transaction.py:89)，支持添加分录、校验借贷平衡（[`TransactionEntry.validate_balance()`](old/bf/core/transaction.py:144)）以及转换为 Beancount 语法。
  - 提供了 [`OpenEntry`](old/bf/core/transaction.py:220)、[`CloseEntry`](old/bf/core/transaction.py:238) 和 [`CommodityEntry`](old/bf/core/transaction.py:248) 指令类。
- **[`old/bf/core/beangenerator.py`](old/bf/core/beangenerator.py)**:
  - 实现了 [`BeanGenerator`](old/bf/core/beangenerator.py:15)，负责生成完整的 Beancount 账本文件（包括 Header、Accounts、Transactions、Footer）。
  - 派生了 [`ProjectBeanGenerator`](old/bf/core/beangenerator.py:207)，提供针对项目场景的便捷方法（如 [`ProjectBeanGenerator.setup_standard_accounts()`](old/bf/core/beangenerator.py:231) 自动生成标准账户）。
- **[`old/bf/core/config.py`](old/bf/core/config.py)**:
  - 使用 Pydantic 定义了配置模型（`AccountConfig`, `LiabilitiesConfig`, `EquityConfig`, `IncomeConfig`, `ExpensesConfig`, `DefaultAccountsConfig`, `BeancountConfig`, `GlobalConfigModel`, `ProjectConfig`, `ProjectEnv`）。
  - 实现了 [`Config`](old/bf/core/config.py:86) 单例管理器，支持加载全局 `config.yaml` 和项目级 `env.yaml`。
- **[`old/bf/project.py`](old/bf/project.py)**:
  - 实现了 [`Project`](old/bf/project.py:22) 类，负责加载环境配置、通过正则表达式解析已存在的 `main.bean` 交易记录（[`Project._load_existing_transactions()`](old/bf/project.py:70)）、添加交易、保存账本以及生成项目报告。
  - 实现了 [`ProjectManager`](old/bf/project.py:243) 类，负责在 `projects/` 目录下创建、加载、列出和删除项目。
- **[`old/bf/business/`](old/bf/business/)**:
  - [`base.py`](old/bf/business/base.py): 定义了 [`BusinessContext`](old/bf/business/base.py:21) 和 [`BusinessProcess`](old/bf/business/base.py:35) 抽象基类，以及 [`QuickTransfer`](old/bf/business/base.py:185) 快速转账流程。
  - [`fundraising.py`](old/bf/business/fundraising.py): 实现了 [`LoanFundraising`](old/bf/business/fundraising.py:32)（借款融资）、[`EquityFundraising`](old/bf/business/fundraising.py:75)（股权融资）、[`LoanRepayment`](old/bf/business/fundraising.py:116)（偿还借款）和 [`DividendDistribution`](old/bf/business/fundraising.py:171)（分红派息）。
  - 其他业务模块（`procurement.py`, `production.py`, `sales.py`, `profit.py`）实现了采购、生产、销售和利润分配的具体分录构建逻辑。
- **[`old/bf/cli.py`](old/bf/cli.py)**:
  - 基于 Typer 构建的命令行工具，提供了 `init`, `pay`, `fundraising borrow/equity/repay`, `procurement buy`, `sales sell/collect`, `profit accrue-tax/dividend`, `list-projects`, `version` 等命令。

### 6.2 遗产与新架构的差异与重构痛点

| 维度 | 旧版本遗产 (`old/`) | 新版本规范 (`REPO_INIT.md` & `OOP_TREE.md`) | 重构与实现要点 |
| :--- | :--- | :--- | :--- |
| **目录拓扑** | 扁平的 `projects/` 目录，无层级关系。 | 树状层级：Root Project -> Sub-Project -> AutoProject (阶段子项目)。 | 需要重构 `ProjectManager`，支持 `--under root` 初始化子项目，并支持嵌套的 Git 仓库管理。 |
| **账户模型** | 统一的 `Account` 类，通过 `AccountType.is_debit_positive()` 辅助判断借贷。 | 显式的 OOP 层次结构：`BasicAccount` -> `LeftAccount` (`AssetsAccount`, `FeeAccount`) / `RightAccount` (`DebtAccount`, `EquityAccount`)。 | 必须重构 `Account` 体系，实现完整的 OOP 派生类，并在其中封装符号转换逻辑。 |
| **项目模型** | 扁平的 `Project` 类，无阶段派生。 | 显式的 OOP 层次结构：`Project` -> `AutoProject` -> `FundraisingProject`, `ProcurementProject`, `ProductionProject`, `SalesProject`, `ProfitProject`。 | 必须重构 `Project` 体系，实现各阶段子项目的特化逻辑与自动清算能力。 |
| **守护进程** | 无守护进程，每次 CLI 调用都是无状态的。 | `ProjectManager` 作为有状态守护进程，听从 `DAEMON_KEEPALIVE` 内存待命时间。 | 需要实现 `ProjectManager` 守护进程，在内存中保持项目状态，减少 CLI 启动和加载开销。 |
| **科目映射** | 依赖硬编码或简单的配置路径拼接。 | 引入 `mapping_dictionary.yaml`，支持精确匹配与向量模糊匹配。 | 需要实现别名映射解析器，并预留 Embedding 模糊匹配接口。 |
| **工作流控制** | 仅支持直接追加分录并保存，无状态流转。 | 引入 AutoProject 阶段流转、结项清算（Happy/Sad/Force Path）及 `.bf_todo.yaml` 阻塞。 | 必须实现 `AutoProject` 生命周期管理器，在结项时扫描 `temp: true` 科目，并生成/核销 `.bf_todo.yaml`。 |
| **审计与权限** | 无审计和权限控制。 | 引入 `audit.yaml`，基于 SSH 公钥进行去中心化权限校验。 | 需要实现 SSH 签名/公钥校验模块，在执行敏感操作（结项、Todo核销）时进行权限拦截。 |
| **对账分析** | 无对账功能。 | 引入 `/bf diff`，采用“滑动时间窗口算法”识别未达账项与错漏账项。 | 需要实现滑动时间窗口对比算法，并能自动抛出 Todo 阻塞。 |
| **Git 联动** | 无 Git 联动，仅写入本地文件。 | 每次记账、结项、冲抵等操作均自动执行 `git commit` 或 `git merge`。 | 需要集成 GitPython 或通过 CLI 调用 Git，确保操作的事务性与可追溯性。 |

---

## 7. Roo 后续任务执行指南

在接下来的开发中，我们将严格按照以下步骤逐步构建全新的 BeanFlow 系统：

1. **基础架构奠基**:
   - 实现 `BasicAccount`、`LeftAccount`、`RightAccount` 及其派生类（`AssetsAccount`, `FeeAccount`, `DebtAccount`, `EquityAccount`），确保符号转换逻辑 100% 正确。
   - 实现 `mapping_dictionary.yaml`、`audit.yaml`、`env.yaml` 和 `.bf_todo.yaml` 的 Pydantic 解析器。
2. **目录拓扑与 Git 引擎**:
   - 重构 `Project` 和 `ProjectManager`，支持 Root Project 与 Sub-Project 的层级关系。
   - 实现 Git 引擎，封装 commit、merge、branch 等操作，确保每次记账自动 commit。
3. **生命周期与 AutoProject**:
   - 实现 `AutoProject` 及其阶段派生类（`FundraisingProject`, `ProcurementProject`, `ProductionProject`, `SalesProject`, `ProfitProject`）。
   - 实现结项清算工作流（Happy Path, Sad Path, Force Path），支持 `temp: true` 科目校验与 `.bf_todo.yaml` 阻塞。
4. **守护进程与有状态管理**:
   - 实现 `ProjectManager` 守护进程，支持 `DAEMON_KEEPALIVE` 内存待命时间。
5. **去中心化审计**:
   - 实现基于 SSH 公钥的权限校验模块，对接 `audit.yaml`。
6. **智能对账与分析**:
   - 实现 `/bf diff` 滑动时间窗口算法，自动识别未达账项与错漏账项。
7. **报表导出功能**:
   - 实现 `/bf export` 命令，使用 **ReportLab** 库渲染并输出 PDF 格式的财务报表。
8. **CLI 接口重构**:
   - 重构 Typer CLI，全面对接新工作流。
