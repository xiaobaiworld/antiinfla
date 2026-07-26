# 应用型 CLI 优先池（50）

定位：优先收录“像 Obsidian CLI、飞书 CLI”这类应用与协作工具。  
说明：
- `现成CLI` = 社区/官方通常已有可用命令行入口（仍需你上线前逐条验收）
- `封装CLI` = 建议你基于 API/MCP 做统一命令封装（这是你站点最有价值的部分）

| # | 工具名 | 建议命令 | 类型 |
|---|---|---|---|
| 1 | Obsidian CLI | `obsidian` | 现成CLI |
| 2 | Feishu CLI | `feishu` | 封装CLI |
| 3 | GitHub CLI | `gh` | 现成CLI |
| 4 | GitLab CLI | `glab` | 现成CLI |
| 5 | Jira CLI | `jira` | 封装CLI |
| 6 | Confluence CLI | `confluence` | 封装CLI |
| 7 | Notion CLI | `notion` | 封装CLI |
| 8 | Slack CLI | `slack` | 封装CLI |
| 9 | Discord CLI | `discord` | 封装CLI |
| 10 | Telegram CLI | `telegram` | 封装CLI |
| 11 | WeCom CLI (企业微信) | `wecom` | 封装CLI |
| 12 | DingTalk CLI | `dingtalk` | 封装CLI |
| 13 | Airtable CLI | `airtable` | 封装CLI |
| 14 | Trello CLI | `trello` | 封装CLI |
| 15 | Asana CLI | `asana` | 封装CLI |
| 16 | ClickUp CLI | `clickup` | 封装CLI |
| 17 | Linear CLI | `linear` | 封装CLI |
| 18 | Monday CLI | `monday` | 封装CLI |
| 19 | Zoom CLI | `zoom` | 封装CLI |
| 20 | Google Drive CLI | `gdrive` | 封装CLI |
| 21 | Google Calendar CLI | `gcal` | 封装CLI |
| 22 | Gmail CLI | `gmail` | 封装CLI |
| 23 | Google Docs CLI | `gdocs` | 封装CLI |
| 24 | Google Sheets CLI | `gsheets` | 封装CLI |
| 25 | Dropbox CLI | `dropbox` | 封装CLI |
| 26 | OneDrive CLI | `onedrive` | 封装CLI |
| 27 | Box CLI | `box` | 封装CLI |
| 28 | Evernote CLI | `evernote` | 封装CLI |
| 29 | Yuque CLI (语雀) | `yuque` | 封装CLI |
| 30 | Xmind CLI | `xmind` | 封装CLI |
| 31 | Figma CLI | `figma` | 封装CLI |
| 32 | Miro CLI | `miro` | 封装CLI |
| 33 | Canva CLI | `canva` | 封装CLI |
| 34 | Salesforce CLI | `sf` | 现成CLI |
| 35 | HubSpot CLI | `hubspot` | 封装CLI |
| 36 | Zendesk CLI | `zendesk` | 封装CLI |
| 37 | Intercom CLI | `intercom` | 封装CLI |
| 38 | Shopify CLI | `shopify` | 现成CLI |
| 39 | Stripe CLI | `stripe` | 现成CLI |
| 40 | Twilio CLI | `twilio` | 现成CLI |
| 41 | Supabase CLI | `supabase` | 现成CLI |
| 42 | Firebase CLI | `firebase` | 现成CLI |
| 43 | Vercel CLI | `vercel` | 现成CLI |
| 44 | Netlify CLI | `netlify` | 现成CLI |
| 45 | Cloudflare Wrangler | `wrangler` | 现成CLI |
| 46 | AWS CLI | `aws` | 现成CLI |
| 47 | Google Cloud CLI | `gcloud` | 现成CLI |
| 48 | Azure CLI | `az` | 现成CLI |
| 49 | MCP Filesystem Server | `mcp-server-filesystem` | 现成CLI |
| 50 | MCP GitHub Server | `mcp-server-github` | 现成CLI |

---

## 你这个方向更有价值的原因（简版）

1. 你不是在做“工具大全”，而是在做“应用能力 CLI 化入口”。
2. 飞书/Obsidian 这类应用本身粘性高，用户会长期复访。
3. 你可以沉淀统一命令规范：
   - `app get ...`
   - `app search ...`
   - `app create ...`
   - `app sync ...`

这会形成你自己的“命令标准层”，壁垒比普通目录站高得多。
