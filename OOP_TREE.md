# **项目架构类图结构**

## **1\. 账户类 (Account)**

* **BasicAccount**  
  * **LeftAccount**  
    * **AssetsAccount**  
    * **FeeAccount**  
  * **RightAccount**  
    * **DebtAccount**  
    * **EquityAccount**

## **2\. 项目类 (Project)**

* **Project**  
  * **AutoProject**  
    * **FundraisingProject**  
    * **ProcurementProject**  
    * **ProductionProject**  
    * **SalesProject**  
    * **ProfitProject**  
* **ProjectManager(cli和Project之间的有状态daemon，听从yaml中DAEMON_KEEPALIVE内存待命时间。)**

## **3\. 其他功能模块与工具 (Utilities & Others)**

* **cli.py** (命令行接口)  
* **(二阶段) ToDoHandler** (待办事项处理器)