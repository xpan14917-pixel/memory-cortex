# 发布到 GitHub

仓库已经**初始化并提交**（分支 `main`）。
本地 git 已配置好提交信息。

**不含任何真实对话 / 密钥 / 运行时**。发布包：`dist/memory-cortex.zip`。

---

## 只需要三步（仓库已就绪）

先在 GitHub 网页建一个**空仓库**（名字 `memory-cortex`，不要勾 README / .gitignore / license），然后：

```powershell
cd C:\path\to\qq-soul
git remote add origin https://github.com/<你的用户名>/memory-cortex.git
git push -u origin main
```

第一次 push 会弹浏览器要求登录 GitHub（或让你填 Personal Access Token）。

## 推送前自检

```powershell
git status --short          # 应该是 clean
git ls-files | findstr /i "bot.db config.json persona.json .log data.real runtime dist"
# 应该没有任何输出
```

## 不想用 Git（网页上传）

1. 解压 `dist/memory-cortex.zip`；
2. GitHub 新建空仓库；
3. 点 **uploading an existing file**，把解压出来的内容整体拖进去；
4. 提交。

网页上传单次限制 100 个文件 / 25 MB，这个包是 69 个文件 / 1.76 MB，没问题。

## 推送后建议

- 仓库 **About**：`给 LLM 聊天机器人一个会遗忘的记忆 | forgetting curve + semantic regions + 3D brain map`
- Topics：`llm` `memory` `forgetting-curve` `spaced-repetition` `chatbot` `sqlite` `webgl` `visualization` `qq`
- 在 Releases 里附上 `panel/小小记忆脑图.html`（单文件版，下载就能看）

## 发布检查清单

- [x] `data/`、`logs/`、`backups/`、`.runtime/`、`dist/` 都没被跟踪
- [x] 仓库里没有 `config.json` / `persona.json`（只有 `.example.json`）
- [x] `panel/js/data.real.js` 没被跟踪（里面是真实记忆）
- [x] `tools/pack_release.py` 输出「未发现 API Key / QQ 号 / token」
- [x] `python -m unittest discover -s tests` 全绿（45 个用例）
- [ ] 全新目录 clone 后跑通 `tools/make_demo_db.py` + 打开 `panel/index.html`

## 如果哪天误推了密钥

1. 立刻吊销 DeepSeek key，换新的；
2. 用 `git filter-repo` / BFG 清历史，或直接删仓库重建；
3. 参考 `SECURITY.md`。
