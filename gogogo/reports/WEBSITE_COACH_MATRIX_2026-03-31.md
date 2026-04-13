# 两网站评测与三教练矩阵（2026-03-31）

## 0. 使用说明

这是当前唯一审查总览页。  
目标：在一个文件里看到两网站的现状评分、改进方向、下一步动作、三位“教练”建议。

适用网站：

- `guthuealthfoods`（`/Users/bai/code/guthuealthfoods`）
- `antiinfla`（`/Users/bai/code/antiinfla`）

评分标准：
[WEBSITE_REVIEW_SCORECARD.md](/Users/bai/code/gogogo/templates/WEBSITE_REVIEW_SCORECARD.md)

---

## 1. 总分对比（/30）

| 网站 | 需求定位 | 流量基础(SEO/内容) | 转化路径 | 数据验证 | 技术体验 | 复盘闭环 | 总分 | 评级 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| guthuealthfoods | 3 | 4 | 1 | 1 | 4 | 3 | 16 | C |
| antiinfla | 4 | 4 | 2 | 3 | 4 | 4 | 21 | B |

---

## 2. 证据快照

### guthuealthfoods

- 内容规模（双语）：
  - foods: `48(en) + 48(zh)`
  - guides: `4(en) + 4(zh)`
  - categories: `8(en) + 8(zh)`
- SEO 基础：
  - 存在 `sitemap.ts`、`robots.ts`、语言 alternates 逻辑、JSON-LD 组件
- 工程检查：
  - `npm run lint` 通过（0 error，1 warning）
- 当前缺口：
  - 暂未看到已接入的 GA4/核心事件实现
  - 首页 CTA 以内容浏览为主，缺少业务转化动作

### antiinfla

- 内容规模（静态站）：
  - foods: `38`
  - guides: `7`
  - categories: `8`
- SEO 基础：
  - `canonical + sitemap.xml + robots.txt` 完整
  - 验证脚本 `scripts/validate_public_site.py` 输出 `status=ok`
- 数据基础：
  - `docs/google-tag.js` + `docs/google-config.js` 已配置 GA ID（`G-QZHTKEW60L`）
  - conversion labels 为空，转化事件尚未落地
- 当前缺口：
  - 首页主 CTA 仍是内容浏览，商业动作弱

---

## 3. 三教练矩阵建议

## guthuealthfoods

### 教练 A：gstack（事实与体验）

1. 先实测 3 条用户路径：`首页 -> 食品页 -> 指南页`，输出移动端/桌面端证据截图。
2. 检查首屏是否 5 秒说清核心价值（当前更偏“资料站介绍”，转化导向不足）。
3. 对首页按钮做 A/B 候选：`Explore foods` vs `Start 7-day plan`，观察点击率差异。

### 教练 B：dbskill（商业与增长）

1. 先收敛一个主用户场景，不要“泛健康资料站”，建议优先“肠道问题人群入门方案”。
2. 把“内容资产”变“可转化产品”：邮件清单、7天计划、可下载清单三选一先做一个。
3. 每周只追 1 条增长主线：`自然流量 -> 邮件留资 -> 回访`，先跑通闭环再扩展。

### 教练 C：superpower（流程与验证）

1. 每次改动前先写验收标准，改完后必须有命令级验证证据。
2. 每周固定 1 次评审：评分卡打分 + 返工点 + 下一周 Top3。
3. 没有指标证据的结论一律降级为“假设”，不进入最终行动清单。

## antiinfla

### 教练 A：gstack（事实与体验）

1. 全站抽检 10 个页面的关键信息密度与可读性，避免“长文但关键动作弱”。
2. 首页到“实用动作页”的路径需要缩短（如餐单、购物清单、可打印清单）。
3. 对现有搜索体验做可用性实测：搜索命中率、空结果提示、移动端输入体验。

### 教练 B：dbskill（商业与增长）

1. 目前是高质量内容站，下一步应明确“商业动作是什么”（订阅、咨询、产品导流）。
2. 把转化事件定义成最小 3 个：`primary_cta_click / guide_click / contact_click`。
3. 先做“低风险可复用漏斗”：内容页 -> 指南页 -> 轻量行动（订阅或下载）。

### 教练 C：superpower（流程与验证）

1. 既然 SEO 校验脚本已稳定，继续扩展为“内容质量 + 转化事件”双校验脚本。
2. 每次内容新增后，要求同步检查：canonical、sitemap 覆盖、内部链接完整性。
3. 每周输出“本周新增内容是否带来行为变化”的证据对照表。

---

## 4. 接下来 14 天动作（可执行版）

## 第 1 周（先打底）

1. `guthuealthfoods`：定义 1 个业务 CTA（建议：7-day gut health starter）。
2. `guthuealthfoods`：接入最小事件追踪（至少 pageview + primary CTA click）。
3. `antiinfla`：补全 conversion labels 并绑定 2 个真实按钮事件。
4. 两站都执行一次评分卡并记录到会话日志。

## 第 2 周（做验证）

1. `guthuealthfoods`：上线首个“可转化资产”（邮件或下载页），观察 7 天数据。
2. `antiinfla`：把首页 CTA 改成“内容浏览 + 行动入口”双 CTA 结构。
3. 两站都跑一次“三教练审查”，比较本周分数变化和关键指标变化。

---

## 5. 本轮结论

1. `antiinfla` 当前更成熟，基础质量和闭环强于 `guthuealthfoods`。
2. 两站共同短板是“转化动作与可衡量业务指标不足”。
3. 下一阶段的重点不再是堆内容，而是把内容转为可验证增长闭环。

