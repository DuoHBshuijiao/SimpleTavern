# SimpleTavern（本地单用户 AI 角色扮演）

前端：Vue 3（Vite + TS）  
后端：FastAPI（SSE 流式）  
存储：本地 `data/` 下按文件拆分的 JSON（无数据库）

## 目录
- `frontend/`：Vue3 前端
- `backend/`：FastAPI 后端
- `data/`：本地 JSON 数据（settings/characters/chats）

## 启动（Windows PowerShell）

### 1) 后端

```powershell
cd E:\SimpleTavern\backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

后端默认会在首次启动时创建/补齐 `data/settings.json`。

### 2) 前端

```powershell
cd E:\SimpleTavern\frontend
npm install
npm run dev
```

打开 Vite 输出的本地地址（通常是 `http://localhost:5173`）。

## 配置模型（OpenAI 兼容）

在应用内“设置”里配置：\n- Base URL：例如 `https://api.openai.com` 或你的兼容网关地址\n- API Key：明文存储到 `data/settings.json`\n- Model：例如 `gpt-4o-mini`（取决于你的服务端支持）


