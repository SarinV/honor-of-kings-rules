# 王者荣耀国际服代理规则 · Honor of Kings Global

[![Update HOK rules](https://github.com/SarinV/honor-of-kings-rules/actions/workflows/update.yml/badge.svg)](https://github.com/SarinV/honor-of-kings-rules/actions/workflows/update.yml)
[![Validate](https://github.com/SarinV/honor-of-kings-rules/actions/workflows/validate.yml/badge.svg)](https://github.com/SarinV/honor-of-kings-rules/actions/workflows/validate.yml)

面向 **Clash / Mihomo / FlClash** 的国际服分流规则。每日检查可信 GitHub 上游，筛选、校验并自动提交；客户端通过固定链接更新。

这是**规则集**，需要配合你已有的代理节点和配置使用。范围为 Honor of Kings Global，不是国服王者荣耀或 Arena of Valor / 传说对决。

## 直接使用

| 版本 | Clash / Mihomo / FlClash | 通用 list（Surge / Loon 等） |
| --- | --- | --- |
| 主列表 | [HonorOfKings.yaml](https://raw.githubusercontent.com/SarinV/honor-of-kings-rules/main/rules/HonorOfKings.yaml) | [HonorOfKings.list](https://raw.githubusercontent.com/SarinV/honor-of-kings-rules/main/rules/HonorOfKings.list) |
| 可选扩展版 | [HonorOfKings-Extended.yaml](https://raw.githubusercontent.com/SarinV/honor-of-kings-rules/main/rules/HonorOfKings-Extended.yaml) | [HonorOfKings-Extended.list](https://raw.githubusercontent.com/SarinV/honor-of-kings-rules/main/rules/HonorOfKings-Extended.list) |

先使用主列表。它目前覆盖 `sgameglobal.com`、`intlgame.com` 及其全部子域名；后者是国际游戏共享平台，也可能影响其他使用它的游戏。

扩展版包含主列表，并加入有限的腾讯共享服务：`gcloudcs.com`、`gcloudsdk.com`、`gcloudsvcs.com`、`midasbuy.com`、`proximabeta.com`。仅在登录、语音、充值等连接日志提示需要时选用；它会扩大影响范围，这些域名不是 HOK 专属，也未逐一做实战验证。

规则数量少不等于只覆盖两个服务器：`DOMAIN-SUFFIX` 会匹配整个域名及其子域名。当前数量和检查时间以 [status.json](data/status.json) 为准。

## Clash / Mihomo / FlClash 接入

把下面内容合并到已有配置的相应字段，将 `HOK` 换成已有的游戏策略组或节点名称。将这条 `RULE-SET` 放在 `GEOIP,CN,DIRECT`、其他宽泛直连规则和 `MATCH` 之前。不要覆盖已有的其他规则。

```yaml
rule-providers:
  HonorOfKings:
    type: http
    behavior: classical
    format: yaml
    path: ./ruleset/HonorOfKings.yaml
    url: https://raw.githubusercontent.com/SarinV/honor-of-kings-rules/main/rules/HonorOfKings.yaml
    interval: 86400

rules:
  - RULE-SET,HonorOfKings,HOK
```

完整片段见 [examples/clash-mihomo.yaml](examples/clash-mihomo.yaml)。扩展版同时替换 URL 与 `path` 中的文件名。订阅管理器更新配置可能覆盖直接编辑的内容；应将片段放入所用客户端支持的持久覆写配置。

游戏流量还取决于客户端能否接管 UDP、节点是否支持 UDP 以及节点到目标游戏区服的线路。仅打开系统 HTTP 代理不能据此保证游戏流量已被接管；按客户端支持情况使用 TUN 或 VPN 模式，并在连接日志中确认命中规则和策略组。本仓库不修改你的客户端。

## 上游选择与边界

初次核对时间：2026-09-06。选择依据是仓库的持续提交、明确许可证、可追溯原始文件及规则范围；星标数量仅作背景参考。

| 上游 | 初次核对时的仓库活动 | 规则文件最后修改 | 用途 |
| --- | --- | --- | --- |
| [fmz200/wool_scripts](https://github.com/fmz200/wool_scripts)（约 5.6k stars） | 2026-09-04；近期有连续人工维护 | 2026-04-21 | [国际版专用文件](https://github.com/fmz200/wool_scripts/blob/main/Loon/rule/HonorOfKings.list)，主列表来源 |
| [v2fly/domain-list-community](https://github.com/v2fly/domain-list-community)（约 9.4k stars） | 2026-09-06；持续社区 PR 合并 | 2025-12-07 | [腾讯游戏服务文件](https://github.com/v2fly/domain-list-community/blob/master/data/tencent-games)，只取扩展版的明确选项 |

**每日检查不表示上游每天新增 HOK 规则，也不等于每日抓包验证。** 活跃仓库中的稳定文件可能很久没有修改。最近的上游提交、源文件修改时间、检查时间分别记录，避免混淆。

没有把其他仓库的 Tencent / Game / China 大列表整体合并，也没有把国服规则改名成国际服。初次检索发现部分小仓库的 HOK 文件混入其他游戏域名，未选为自动上游。

主列表中的域名来自专用上游，允许后续新增的有效域名自动进入；共享服务源只允许 [policy.json](policy.json) 中明确选定的后缀进入扩展版。以下项目不会自动发布：

- 上游现有的 `183.192.65.101/16`、`43.132.55.55/16`：含主机位且范围很大，不擅自扩大为整个 `/16`，也不擅自改成 `/32`。
- `DOMAIN-KEYWORD`、正则、include、通用归因 `appsflyersdk.com` 和整片公有云主域。
- 与此任务无关的国内腾讯游戏域名。

完整排除原因与每条已发布规则的来源行号见 [provenance.json](data/provenance.json)，原始文件见 [upstream/](upstream/)。纯 IP / UDP 连接可能不命中域名规则，因此**这是一份可维护的域名分流列表，不能宣称已覆盖所有区服、登录方式和对战服务器**。新增 IP 规则需要有效连接日志支撑，不能仅从某次 DNS 解析推断永久网段。

## 每日更新与失败处理

[Update HOK rules](.github/workflows/update.yml) 每日 **22:23 UTC（北京时间次日 06:23）** 运行，也可在 [Actions](https://github.com/SarinV/honor-of-kings-rules/actions/workflows/update.yml) 手动 Run workflow。GitHub 的定时任务可能排队延迟或被跳过，不能视为严格准点服务。[GitHub 官方说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

每次更新会：

1. 核对上游未归档、许可证与已审阅副本一致、仓库近 180 天有活动。
2. 将分支解析为确定的 commit，再按同一 commit 下载规则，保存原始快照与 SHA-256。
3. 执行解析、筛选、去重、必需规则和异常删减检查。网络暂时故障最多尝试三次。
4. 运行回归测试及离线复现检查，通过后由 GitHub Actions 自动提交规则、来源和状态。

任何上游缺失、解析失败、许可证变化或异常删减均令任务失败，**不发布半份规则或空列表**；原有 Raw 链接继续提供上一版。失败可在 Actions 状态徽章和日志查看，邮件通知取决于你的 GitHub 通知设置。

成功检查会更新 `data/status.json` 并产生提交，即使规则没有变化也留下实际检查记录；规则文件本身保持确定性，无内容变化不改写时间戳。持续正常提交也用于避免公开仓库长期无活动导致计划任务被禁用。若更新长期失败或 workflow 被停用，需要在 Actions 中处理并重新启用。

只使用自动提供的 `GITHUB_TOKEN`，不需要额外密钥。更新任务的权限为本仓库 `contents: write`；PR 验证任务只读。第三方 action 固定到 commit，Dependabot 每月检查 action 更新。

## 本地维护

需要 Python 3.12 或更新版本，无第三方 Python 依赖。

```sh
python -m unittest discover -s tests -v
python scripts/update.py               # 从上游更新，需联网
python scripts/update.py --check       # 从已提交快照离线校验，无写入
```

上游 API 默认使用公开额度；本地若遇限流，可自行设置 `GITHUB_TOKEN`。许可证有变化时先检查上游变更，再更新 `licenses/`；不要让自动任务静默接受改变的许可。新增共享域名应同时修改 `policy.json` 并说明来源与范围。

## 许可证

本仓库按 **GPL-3.0-only** 发布，见 [LICENSE](LICENSE)。上游作者、许可和修改方式见 [NOTICE.md](NOTICE.md)，原始 MIT 声明与 GPL 文本保存在 [licenses/](licenses/)。
