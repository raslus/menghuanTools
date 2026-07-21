# 账号管理系统

基于 Python Flet 框架（v0.80+）开发的跨平台账号管理应用。

> 适配 Flet 0.80+ 新版本 API，使用异步编程模式。

## 功能特性

- **账号管理**
  - 添加新账号（用户名、密码、备注）
  - 编辑已有账号信息
  - 删除账号
  - 搜索筛选账号
  - 一键复制用户名/密码到剪贴板

- **统计页面（预留）**
  - 账号数量统计
  - 数据趋势图表（预留）
  - 活动记录（预留）

## 项目结构

```
.
├── main.py              # 应用入口
├── data_manager.py      # 数据管理模块
├── requirements.txt     # 依赖列表
├── pages/
│   ├── __init__.py
│   ├── account_page.py  # 账号管理页面
│   └── stats_page.py    # 统计页面
└── accounts.json        # 数据存储文件（自动创建）
```

## 安装运行

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 运行应用：
```bash
python main.py
```

## 数据存储

账号数据以 JSON 格式存储在 `accounts.json` 文件中，位于程序运行目录下。

## 平台支持

- Windows
- macOS
- Linux
