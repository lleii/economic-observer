# 经济观察 · Economic Observatory

[正式网站](https://lleii.github.io/economic-observer/) · [源码仓库](https://github.com/lleii/economic-observer)

以数字经济、数据要素、人工智能、技术进步、企业发展和新质生产力为主线，观察国家经济政策与产业变化。

## 采集与编辑

- GitHub Actions 按 UTC 23:00（北京时间次日 07:00）调度采集。候选材料及运行情况写入 `data/candidates.json` 与 `data/candidate_run.json`。
- 自 2026-11-22 起，每日07:00期号使用前一天新文章：例如11月22日期号收录11月21日材料。新期设置 `previous_day_only: true`，构建时拒绝其他日期文章；日报日期与原文日期分别显示。
- 完整日报的自动编辑发布由本地 Codex 每日任务执行，依赖本机任务运行环境与 GitHub 授权；GitHub Actions 的定时采集本身不会生成 AI 研判。发布成功以线上首页和当期独立页面为准。
- 编辑审阅最近 7–30 天材料，必要时引用更早的正式文件。依次判断主题相关性、政策和经济研究价值、信息增量与研究启发。重大正式政策走独立候选通道；80 分用于编辑参考。
- 首页精读优先选正文有明确判断的理论文章及国家政策。正式文件、专家观点、报道与综合判断分别标示。地方材料只在有研究价值且有明确边界时用于精选或佐证。
- 要核对原文、作者、发布日期、证据与结论。候选池由规则筛出，定时任务当前无需 AI API。完整日报由编辑审阅后发布，首页一直显示最新一期。

## 构建与归档

运行 `python brief-preview/build.py --issues editions --output public`，打开 `public/index.html`。Pages 工作流部署已审阅的日报与不可覆盖的日期快照。历史采集数据保存在 `data/items.json`。具体步骤见 [部署指南](DEPLOY_GUIDE.md)。
