# 来源与修改说明

本项目由 SarinV 于 2026-09-06 建立，筛选和转换公开上游规则，按 GPL-3.0-only 发布。
后续每次同步的源代码版本、文件最后修改时间和 SHA-256 记录在 `data/status.json`，修改历史见 Git 提交。
本项目并非游戏官方规则或上游作者背书的列表。

## fmz200 / wool_scripts

- 项目：https://github.com/fmz200/wool_scripts
- 文件：`Loon/rule/HonorOfKings.list`
- 原始作者标注：奶思（完整注释保留在 `upstream/fmz200-hok.txt`）。
- 上游许可证：GPL-3.0，完整副本见 `licenses/fmz200-hok.txt`。
- 修改：清理空白、域名小写化、去重排序、转换为 Clash classical YAML 和通用 list；排除 IP-CIDR、关键字与不适合自动接管的宽泛域名。

## v2fly / domain-list-community

- 项目：https://github.com/v2fly/domain-list-community
- 文件：`data/tencent-games`
- Copyright (c) 2018-2019 V2Ray
- 上游许可证：MIT，完整声明及免责条款见 `licenses/v2fly-tencent-games.txt`。
- 修改：从共享腾讯游戏列表中仅选取 `policy.json` 明确列出的域名，转换格式，仅加入可选扩展版。
- 这份列表没有为 HOK 单独分类；本项目没有把这些共享服务宣称为已经抓包验证的 HOK 专属依赖。

所有上游均只读取规则数据，不执行上游脚本。原始规则快照、许可证和逐条筛选结果随仓库分发。
