BeanFlow Repository & Schema Architecture

本文档定义了 BeanFlow 系统的物理存储拓扑、核心配置文件的 Schema 规范，以及底层系统的核心逻辑映射模型。BeanFlow 基于 Git 版本控制系统构建“时间线区块链”，以 Unix 哲学思想管理企业财务记账的生命周期。

1. 物理目录拓扑结构 (Directory Topology)

BeanFlow 采用嵌套与平级相结合的文件系统结构，每一个项目节点（无论是手动初始化的 Project 还是系统自动托管的 AutoProject）都是一个自治的 Git 仓库（或逻辑分支节点）。

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


2. 核心配置文件 Schema (Configuration Schemas)

2.1 mapping_dictionary.yaml (会计科目翻译字典)

用于 CLI 输入别名到标准 Beancount 科目的映射，配合 Embedding 模型实现模糊识别。

# mapping_dictionary.yaml
accounts:
  - id: "assets:current:alipay"      # 标准 Beancount 科目 ID
    type: "AssetsAccount"            # 对应的 OOP 派生类 (决定借贷正负号)
    temp: false                      # 是否为阶段临时科目 (用于结项校验)
    names:                           # CLI 别名集合
      - "Alipay"
      - "支付宝"
      - "ali"
      
  - id: "equity:pending_property_loss"
    type: "EquityAccount"
    temp: false
    names: ["待处理财产损溢", "force_loss"]

  - id: "liabilities:short_term_loan"
    type: "DebtAccount"
    temp: true                       # 标记为临时: 筹资阶段结束时必须清零，否则阻断
    names: ["短期借款", "loan"]


2.2 audit.yaml (去中心化 SSH 审计配置)

控制 /bf todo --checkoff 以及阶段结项等敏感操作的权限。

# audit.yaml
audit:
  mode: standard                     # 模式: solo (不阻断) | standard (严格基于 SSH 公钥)
  allow_force_merge: true            # 是否允许使用 --force 触发“待处理财产损溢”强行平账
  
  roles:
    cashier: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5..."     # 出纳的 SSH 公钥
    accountant: "ssh-ed25519 AAAAC3NzaC1lZDI1..."      # 会计的 SSH 公钥
    cfo: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AA..."       # 财务总监的 SSH 公钥

  permissions:
    phase_liquidation: ["cfo", "accountant"]           # 阶段结项 (git merge) 权限
    todo_checkoff: ["cashier", "accountant", "cfo"]    # 待办核销权限


2.3 env.yaml (项目级环境覆盖)

子项目目录下的配置，覆盖全局行为。

# 某子项目的 env.yaml
project:
  name: "Project_A"
  parent: "root"
  current_phase: "procurement"       # 当前处于采购阶段
  
overrides:                           # 仅在当前项目生效的重载
  allow_force_merge: false           # 覆盖全局，本项目严禁强行平账


2.4 .bf_todo.yaml (工作流阻塞缓存)

当系统检测到 temp: true 科目未平或对账异常时生成。若列表不为空，禁止向后流转。

# .bf_todo.yaml
todos:
  - id: "td_9f8a2"
    timestamp: 1716508800
    type: "temp_balance_not_zero"
    message: "筹资阶段结项校验失败：科目 liabilities:short_term_loan 余额为 -5000，预期为 0"
    resolved: false


3. OOP 核心对象模型 (Object-Oriented Core)

3.1 账户基类与符号转换 (Account & Signage)

BeanFlow 彻底封装了 Beancount 的正负号规则，对外统一暴露正数输入。

LeftAccount (借方账户基类)：资产(Assets)、费用(Expenses)

资金转入 (To) / 增加 ➡️ 对应 Beancount 数值: +Count

资金转出 (From) / 减少 ➡️ 对应 Beancount 数值: -Count

RightAccount (贷方账户基类)：负债(Liabilities)、权益(Equity)、收入(Income)

资金转入 (To) / 增加 ➡️ 对应 Beancount 数值: -Count

资金转出 (From) / 减少 ➡️ 对应 Beancount 数值: +Count

3.2 项目拓扑模型 (Project Lifecycle)

class Project:
    """手动初始化的全局或实体项目节点"""
    name: str
    parent_id: str
    git_repo: GitEngine
    
class AutoProject(Project):
    """由 BeanFlow 接管的阶段性子账本，具有自动清算能力"""
    phase_enum: Enum["Fundraising", "Procurement", "Production", "Sales", "Profit"]
    is_liquidated: bool


4. 核心工作流规范 (Core Workflows)

4.1 记账工作流 (/bf pay 等)

接收 CLI 输入的源/目标别名及金额。

检索 mapping_dictionary.yaml (精确匹配 -> 向量模糊匹配)。

获取目标科目对应的 OOP 对象。

应用 LeftAccount/RightAccount 符号计算规则。

追加标准 Beancount 分录并自动执行 git commit。

4.2 结项清算工作流 (Phase Liquidation)

扫描当前 AutoProject 中所有 temp: true 的科目。

Happy Path: 若全部为 0，生成结项 commit，触发 git merge 合并入父级。

Sad Path: 若存在不为 0 的科目，拦截操作，生成 .bf_todo.yaml 记录。

Force Path (--force): 校验 SSH 公钥与 audit.allow_force_merge。自动生成冲抵分录转入“待处理财产损溢”，强行将临时科目平账后提交 Merge。

4.3 对账分析工作流 (/bf diff)

利用 Git History 与外部导入的 .bean 进行“滑动时间窗口算法”对比：

周期边缘 (±Δt 容差内) 不匹配 ➡️ 归类为 未达账项 (In-Transit)。

周期内部孤立不匹配 ➡️ 归类为 错漏账项 (Error/Omission)，阻断并强制抛出 Todo。