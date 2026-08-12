# 梦幻工具箱

面向 Windows 桌面端的梦幻西游个人工具，基于 Python 及 Flet 0.86.2。

## 功能

- 账号管理：保存、搜索、复制以及加密导入导出账号信息。
- 收益记账：记录活动产出，查看明细、趋势图和分类汇总。
- 养成规划：维护角色当前属性、目标属性、成长进度和装备备注。
- 抓鬼辅助：OCR 识别大小鬼任务，预测坐标范围，采集并标定游戏小地图。

## Windows 环境

```powershell
conda env create -f environment.yml
conda activate menghuanTools
python main.py
```

更新已有环境：

```powershell
conda env update -n menghuanTools -f environment.yml --prune
```

## 数据目录

开发运行时数据位于项目目录；打包运行时位于程序旁的 `data` 目录，包括：

- `accounts.json`：账号数据。
- `accounting.db`：收益记录。
- `growth.db`：养成规划。
- `ghost_hunter_learning.json`：抓鬼反馈样本。
- `captured_maps/`：用户采集地图、审核状态及标定参数。
- `logs/`：滚动运行日志，单文件最多 2 MB，保留 3 份备份。

内置地图位于 `assets/maps`，审核通过的采集地图优先使用，异常时自动回退到内置地图。

## 开发标准

开发约定见 `codeConfig.yaml`：

- 开发日志写入 `codeLogs`。
- 已解决问题写入 `codeProblems`。
- 设计文档写入 `codeMds`。
