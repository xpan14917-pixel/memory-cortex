# 安全与隐私

## 数据只存在本地

- 所有聊天记录、记忆、日记、画像都存在本机 `data/bot.db`（SQLite）。
- 只有**发给模型的上下文**会离开本机（默认 DeepSeek API）；如果换成本地模型（Ollama / llama.cpp），则完全不出网。
- 项目不包含任何遥测、埋点、统计上报。

## 不要提交到仓库的文件

`.gitignore` 已经排除：`data/`、`logs/`、`backups/`、`.runtime/`、`config.json`、`persona.json`、`*.db`、`panel/js/data.real.js`。

其中最容易误提交、且泄露最严重的是：

| 文件 | 里面有什么 |
|---|---|
| `data/bot.db` | 全部对话原文、记忆、日记 |
| `config.json` | LLM API Key、OneBot token、你的 QQ 号 |
| `logs/bot.log` | 完整聊天日志 |
| `panel/js/data.real.js` | 记忆原文（用于面板） |
| `.runtime/qqhome/` | NapCat/QQ 登录态 |

**快速自检**：

```bash
git status --short
git ls-files | grep -E "bot\.db|config\.json|\.log$|data\.real\.js" && echo "!! 有敏感文件被跟踪"
```

## 密钥泄露怎么办

1. 立刻去 DeepSeek 控制台吊销该 key，重新生成；
2. 替换 `config.json` 里的 `llm.api_key`；
3. 如果已经 push：`git filter-repo` 或 BFG 清理历史，然后强制推送；
4. 同步换掉 NapCat 的 OneBot token。

## 模型侧的边界

- 人格是风格，不是欺骗：被认真问起时，它应承认自己是程序；
- 不要把 API Key 写进 prompt；
- 面板是只读可视化，不参与生成，也不对外提供写接口（除非你自己加）。
