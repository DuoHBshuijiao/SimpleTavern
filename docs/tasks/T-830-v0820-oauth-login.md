# T-830 v0.820 GitHub Copilot / OpenAI Codex OAuth 登录

- status: **done**（真机 Copilot/Codex 登录需账号点选）
- area: `backend/app/llm/oauth/`、`backend/app/routes/oauth.py`、`preset_resolve.py`、`auth_headers_for_style`、`frontend` 预设登录弹窗
- priority: P0
- depends_on: T-820-A1/A2（目录 `oauth_device` / `oauth_pkce` 桩）

## 目标

把 v0.810 目录里的 Copilot / Codex 从「允许空 Key」变成可登录、可刷新、可发请求。信源对齐 [pi GitHub Copilot OAuth](https://github.com/earendil-works/pi/blob/main/packages/ai/src/auth/oauth/github-copilot.ts) 与 [OpenAI Codex OAuth](https://github.com/earendil-works/pi/blob/main/packages/ai/src/auth/oauth/openai-codex.ts)。

## 契约

- Token 存 `data/oauth_tokens.json`（按 preset id），**不进** `settings.json`。
- `GET /api/llm/oauth/status` 只返回 `loggedIn / expiresAt / accountId / provider`。
- Copilot：GitHub device-code（`read:user`）→ `copilot_internal/v2/token` 换 access；过期前 5 分钟 refresh。
- Codex：默认 device-code；PKCE 仅「打开授权页 + 粘贴回调 URL」。不做 `localhost:1455` 监听。
- `oauth_device` / `oauth_pkce` 在已有 access token 时发 `Authorization: Bearer`。
- 未登录就选该预设 → `MISSING_OAUTH_LOGIN`（401）。
- Copilot 额外头：`Copilot-Integration-Id` / `Editor-Version` / `User-Agent`；主机不加 `/v1`。
- Codex 额外头：`chatgpt-account-id`、`originator: simpletavern`、`OpenAI-Beta: responses=experimental`。

## 不做

- 本机 HTTP 回调服务器。
- Copilot Enterprise 模型 policy 批量 enable（登录成功即可；列模型走上游 `/models`）。
- 把 refresh token 回传到前端。
