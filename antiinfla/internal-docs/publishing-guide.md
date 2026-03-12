# 发布流程说明

## 概述

本项目有两个关键目录：

- `antiinfla/` — 内容开发目录，所有食物页面、指南、资源在这里编写和维护
- `docs/` — GitHub Pages 发布目录，网站从这里部署到 `www.antiinflammatorydiets.com`

## GitHub Pages 配置

- 仓库：`xiaobaiworld/antiinfla`
- 部署分支：`main`
- 发布目录：`/docs`
- 自定义域名：`www.antiinflammatorydiets.com`
- CNAME 文件位于 `docs/CNAME`
- `.nojekyll` 文件位于 `docs/.nojekyll`

## 发布步骤

每次在 `antiinfla/` 中完成内容更新后，需要手动同步到 `docs/` 才能上线。

### 1. 同步食物页面

```bash
cp -r antiinfla/foods/ docs/foods/
```

### 2. 同步图片资源

```bash
cp -r antiinfla/assets/ docs/assets/
```

### 3. 同步指南页面

```bash
# 同步所有指南（覆盖已有 + 新增）
cp -r antiinfla/guides/* docs/guides/
```

### 4. 同步 SEO 文件

```bash
cp antiinfla/sitemap.xml docs/sitemap.xml
cp antiinfla/robots.txt docs/robots.txt
```

### 5. 注意事项

- `docs/index.html` 和 `docs/styles.css` 是独立维护的发布版本，不要直接用 antiinfla 的版本覆盖
- 如果 antiinfla 中新增了食物页面 CSS 样式，需要手动追加到 `docs/styles.css` 末尾的 `/* Food page styles */` 区块
- `docs/` 中有 `google-config.js`、`google-tag.js`、`zh-cn/` 等发布专用文件，不在 antiinfla 中维护
- CNAME 和 .nojekyll 只需要在 `docs/` 中存在

### 6. 提交并推送

```bash
git add docs/
git commit -m "Sync content to docs for publishing"
git push origin main
```

推送后 GitHub Pages 会自动重新部署，通常 1-2 分钟内生效。

## 验证

推送后访问以下地址确认：

- 首页：https://www.antiinflammatorydiets.com/
- 食物页面示例：https://www.antiinflammatorydiets.com/foods/blueberries/
- 指南示例：https://www.antiinflammatorydiets.com/guides/best-anti-inflammatory-foods/

## QA

发布前可运行验证脚本：

```bash
python3 antiinfla/scripts/validate_public_site.py
```

## 双账号注意

本机有两个 GitHub 账号。antiinfla 仓库使用 `xiaobaiworld` 账号，git remote 配置为 `git@github-2:xiaobaiworld/antiinfla.git`。

确认当前活跃账号：

```bash
gh auth status
```

如需切换：

```bash
gh auth switch --user xiaobaiworld
```
