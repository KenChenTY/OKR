# OKR 企业工作空间

基于本目录《OKR系统技术设计文档》开发的 Python FastAPI、Vue 3、SQL Server 应用。生产入口采用 Nginx，运行平台为 Windows Server。

当前代码提供目标、KR、对齐、两级审批、进展更新、证据隔离扫描、变更审批、评审行动、报表导出、历史快照、角色权限及审计。数据库只支持 SQL Server，不使用 SQLite 替代事务验证。数据库尚未准备时可以构建前端、运行规则和浏览器契约测试；业务操作需要真实 SQL Server。

## 项目结构

界面右上角提供“中文 / English”切换，登录页同样可切换。语言选择保存在浏览器本地，刷新后保留。文案集中在 `frontend/src/locales/en.json`，通过 `frontend/src/i18n.ts` 读取；日期格式和 Element Plus 组件语言随之更新。用户录入的目标、意见及其他业务内容保持原文，切换语言保留当前表单输入。

```text
backend/app/             API、业务规则、认证、数据模型、后台任务
backend/migrations/      固定版本的 Alembic 迁移
backend/tests/           规则、契约与真实 SQL Server 集成测试
frontend/src/            Vue 3 页面、组件、路由和状态
frontend/tests/          Playwright 浏览器契约测试
deploy/nginx/            Nginx 配置样例
deploy/windows/          本地启动与服务托管样例
deploy/sql/              SQL审阅文件和数据库运行角色
docs/                    开发状态与运维说明
```

## 本地开发准备

当前默认使用账号密码登录（`OKR_AUTH_MODE=password`），账号由管理员授权，数据库密码与网页登录密码彼此独立。已初始化的本机开发账号信息保存在未纳入版本控制的 `var/development-accounts.txt`。

重置或为已有用户开通网页账号，在 backend 目录执行，按提示输入新密码（12–128 字符）：

```powershell
..\.venv\Scripts\python.exe -m app.cli set-password --user-id 1 --username employee
```

用户编号以实际数据库为准。密码仅保存带随机盐的 PBKDF2-SHA256 哈希；重置后旧会话失效。每账号 15 分钟内连续错误五次暂停登录，每来源地址同一窗口最多允许三十次失败。生产仍要求 HTTPS 和可信 SQL Server 证书；切回 Entra 时设置 `OKR_AUTH_MODE=entra` 并配置企业身份参数。

需要 Python 3.12、Node.js 22.12及以上、SQL Server及Microsoft ODBC Driver 18。以下命令在项目根目录的PowerShell运行。`.env`、密钥、数据库内容和附件不应提交版本控制。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock.txt
Copy-Item backend/.env.example backend/.env
cd frontend
npm.cmd ci --cache ../.cache/npm
cd ..
```

开发时编辑 `backend/.env`，填写实际SQL Server连接，并将 `OKR_AUTH_MODE=development` 和 `OKR_ENABLE_DEV_LOGIN=true` 同时打开。该登录方式仅用于本地开发，生产配置会拒绝启用。开发服务只监听127.0.0.1。

ODBC驱动是操作系统组件，安装pyodbc不会自动安装它。数据库证书必须与服务器名称匹配并由客户端信任；示例默认启用加密且不跳过证书校验。

## 数据库准备好后

由DBA先创建空数据库和迁移身份，配置连接串。随后在backend目录运行：

```powershell
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
# 仅限空的开发数据库，创建组织、角色测试账号和本年季度。
..\.venv\Scripts\python.exe -m app.cli seed-development
cd ..
```

迁移由发布身份执行，API启动不自动建表、不自动迁移、不自动创建演示业务数据。`deploy/sql/002-alembic-upgrade.sql` 是可供DBA审阅的完整离线升级脚本；日常以 Alembic 为唯一版本管理入口，不重复执行创建SQL。

在三个PowerShell终端分别运行：

```powershell
# 终端一
.\deploy\windows\start-api.ps1
# 终端二
.\deploy\windows\start-frontend.ps1
# 终端三
.\deploy\windows\start-worker.ps1
```

开发地址为 http://localhost:5173 ，API文档为 http://127.0.0.1:8000/api/docs 。必须保持 `.env` 的 `OKR_PUBLIC_URL` 与浏览器实际使用的地址一致，避免开发登录的Origin检查失败。

无SQL Server时，登录页显示服务未就绪并禁用登录；这不影响 `/health/live`、前端构建及独立测试。

## 开发流程示例

使用 `admin` 账号登录后，侧栏提供“人员管理”。支持按姓名/账号搜索和启用状态筛选、新增账号、编辑姓名/组织/七种角色、停用或启用、重设密码。普通角色无法进入页面，直接调用接口也会被拒绝。停用、角色/组织变更和密码重设会撤销目标用户的旧会话；不允许停用自己或撤销自己的管理员角色。密码为 12–128 字符，仅保存哈希，审计不记录密码。重设自己的密码后需重新登录。

本次无需数据库结构迁移。已使用旧版 `deploy/sql/runtime-role.sql` 的部署需由 DBA 重新应用更新后的权限脚本：允许运行身份在受 Admin 接口控制下新增/修改 users 与 local_credentials，继续禁止删除人员及凭据。当前开发连接本身已有相应权限。

1. 以目标负责人登录，创建当前季度的目标，添加KR，确保权重合计100%。
2. 提交目标，退出后切换经理身份，通过第一级审批；切换事业部负责人完成第二级审批。
3. 切回负责人，点击开始执行，提交当前值、信心、风险及下一步。进度由服务端计算。
4. 上传文件进入隔离区。配置扫描程序并运行Worker后，通过扫描的文件才能被引用和下载。未配置扫描器时保持隔离，不会默认放行。
5. 如需修改已批准的基线或目标值，在“变更与权限”提交变更，经理和事业部重新审批；原版本继续生效直到批准。
6. 负责人发起结项申请，指定经理审批后保存最终快照，后续可以归档。管理角色可创建CSV导出任务，Worker生成文件后下载。
7. 在举措与收益页面登记执行事项及外部项目链接。收益申报关联证据，由独立核验人审核；汇总区分别显示申报与核验结果，并按币种和单位统计。

审批人根据当前组织向祖先组织解析并固定，缺少独立经理或事业部审批人时拒绝提交。开发种子中的八个账号用于角色边界测试，不可用于生产。

## 测试与构建

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check backend
cd frontend
npm.cmd run build
npm.cmd run test:ui
cd ..
```

浏览器测试默认使用本机Chrome。若未安装，可将 `frontend/playwright.config.ts` 的channel改为已安装的受支持浏览器，或安装Playwright Chromium后去掉channel。测试使用独立的HTTP拦截夹具，不代表真实SQL Server集成验收。

如自动启动的前端进程在受限Windows环境中无法清理，可先单独运行前端，再使用：

```powershell
cd frontend
$env:OKR_TEST_EXTERNAL_SERVER='1'
npm.cmd run test:ui
```

真实数据库测试必须使用数据库名以 `_test` 结尾的专用测试库，先执行迁移，再设置 `OKR_TEST_DATABASE_URL` 后运行 `pytest -m sqlserver`。测试会写入隔离测试记录，不删除数据库或生产记录；测试库应由DBA按测试环境策略回收。未配置时明确显示skipped。

## 企业接入

正式身份采用Microsoft Entra OIDC授权码流程。配置tenant、client、client secret和回调URL `<OKR_PUBLIC_URL>/auth/callback`。密钥从受保护环境注入。生产必须HTTPS、关闭开发登录，并完成企业条件访问/MFA实际验收。

组织、周期及身份授权初始化使用独立管理身份执行：

```powershell
cd backend
..\.venv\Scripts\python.exe -m app.cli add-org --name '科技事业部' --type division
..\.venv\Scripts\python.exe -m app.cli add-org --name '运营技术部' --type department --parent-id 1
..\.venv\Scripts\python.exe -m app.cli add-cycle --name '2026 Q4' --start 2026-10-01 --end 2026-12-31
..\.venv\Scripts\python.exe -m app.cli provision-user --subject 'TENANT_ID:OBJECT_ID' --name '姓名' --role Employee --org-id 2
```

编号以命令实际返回为准，不要直接照搬示例。角色名称包括Employee、Manager、Division Head、PMO、HR、System Admin、Audit。带空格的角色使用引号包裹。

Windows生产部署步骤和待验收项见 [部署运行说明](docs/DEPLOYMENT.md)；功能覆盖、当前约束及后续路线见 [开发状态](docs/IMPLEMENTATION.md)。

Ubuntu 上使用 Docker Compose 启动系统与 SQL Server，见 [Ubuntu Docker 部署指南](docs/DEPLOYMENT_UBUNTU.md)。配置位于 `deploy/docker/`，默认用于内网试运行；指南包含数据库迁移、管理员初始化及正式生产需要补齐的配置。
