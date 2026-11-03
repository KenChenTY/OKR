# Ubuntu + Docker 部署 OKR 与 SQL Server

本指南对应仓库里的 `deploy/docker/compose.yaml`。所有命令均在 Ubuntu 的 Bash 中执行，不是在 Windows PowerShell 中执行。

## 1. 先确认服务器与部署范围

建议 Ubuntu 24.04 LTS、Intel/AMD x86-64、4 核 CPU、8 GB 内存、至少 30 GB 可用磁盘。这个规格是本项目试运行的建议，不是容量保证；构建和业务文件还会占用空间。SQL Server 官方容器要求 x86-64，不能将 ARM 服务器作为本方案的受支持平台。

```bash
uname -m
free -h
df -h /
```

`uname -m` 应为 `x86_64`。本方案启动四个常驻服务：

| 服务 | 用途 | 对宿主机开放端口 |
| --- | --- | --- |
| web | Nginx + 已构建 Vue 前端 | 默认 8080 |
| api | FastAPI | 无 |
| worker | 提醒、快照、导出、扫描任务 | 无 |
| sqlserver | SQL Server 2022 | 无 |

另有手动执行的 `admin` 容器，用于建库、迁移和管理员初始化。API、Worker 以非 root 用户运行，并使用 `okr_app` 数据库账号和项目既有的 `okr_runtime` 权限角色；只有 SQL Server 和一次性管理容器获得 sa 密码。容器通过服务名 `sqlserver:1433` 连接数据库，不能填写 `localhost`。

**默认配置用于受控内网试运行**：HTTP、SQL Server 自签名证书、`OKR_ENV=development`，但仍使用真实账号密码登录，关闭开发快捷登录。SQL Server 默认 Developer 版仅限开发和测试，不适用于正式生产业务。正式生产转换见第 9 节。

## 2. 安装 Docker Engine 和 Compose

已安装 Docker Engine 与 Compose v2 时，直接验证后跳到下一节。不要在承载其他容器的服务器上盲目卸载已有组件；如存在发行版自带 Docker 与官方软件包冲突，先按照官方安装文档处理。

新 Ubuntu 服务器执行：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl openssl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

后文统一使用 `sudo docker compose`，不要求将当前用户加入 docker 组。

## 3. 上传项目、设置地址和密码

将包含本次新增 Docker 文件的**完整项目**上传到服务器，例如 `/opt/okr`。如果用 Git，应拉取包含这些文件的提交；如果用 SFTP，应包含 `frontend/package-lock.json` 和 `backend/requirements.lock.txt`。无需上传 `.venv`、`node_modules`、`frontend/dist`、本地 `backend/.env`、`var` 和本地账号文件。下面是新库初始化流程，不会自动导入原有数据库和附件。

进入 Docker 配置目录，后面所有 Compose 命令均在这里执行：

```bash
cd /opt/okr/deploy/docker
cp .env.example .env
chmod 600 .env
nano .env
```

先将 `OKR_PUBLIC_URL` 改成浏览器实际使用的地址，例如：

```dotenv
OKR_PUBLIC_URL=http://192.168.1.100:8080
OKR_HTTP_BIND=0.0.0.0
OKR_HTTP_PORT=8080
```

替换为服务器真实 IP，地址不要加末尾 `/`。端口变化时同时改 URL 与 `OKR_HTTP_PORT`。如果通过域名访问，URL 必须使用该域名。Origin 校验要求协议、主机和端口与浏览器完全一致。

在首次初始化前生成两个不同的数据库密码并写入配置，不会将密码打印到终端：

```bash
sed -i "s/^MSSQL_SA_PASSWORD=.*/MSSQL_SA_PASSWORD=Sa9$(openssl rand -hex 24)/" .env
sed -i "s/^OKR_APP_PASSWORD=.*/OKR_APP_PASSWORD=App9$(openssl rand -hex 24)/" .env
```

这两个命令仅在**首次初始化**时执行。密码只含 ASCII 字母和数字，适配本 Compose 的连接串拼接方式，不能自行替换成含 `@`、`:`、`%`、`$` 等符号的明文密码。配置文件应保存在受控备份中。已有持久卷或登录账号时，修改 `.env` 不会修改 SQL Server 内的实际密码；需要显式执行数据库密码轮换。不要用重新生成 `.env` 的方式修复密码错误。

## 4. 用 Docker 启动 SQL Server

```bash
sudo docker compose pull sqlserver
sudo docker compose up -d sqlserver
sudo docker compose ps
sudo docker compose logs --tail=100 sqlserver
```

等待 `sqlserver` 变为 `healthy`。首次启动可能需要几分钟；healthcheck 会执行真实 SQL 查询。数据库保存在命名卷 `okr_sqlserver_data`，容器重建后保留。

需要进入 SQL Server 检查时执行：

```bash
sudo docker compose exec sqlserver bash -lc \
  'SQLCMDPASSWORD="$MSSQL_SA_PASSWORD" /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b'
```

例如输入：

```sql
SELECT @@VERSION;
GO
SELECT name FROM sys.databases;
GO
QUIT
```

`-C` 表示此试运行环境信任数据库自签名证书。SQL Server 未映射宿主机 1433 端口，无需开放云安全组 1433。如果要从电脑上的 SSMS 连接，建议先添加只绑定服务器 `127.0.0.1` 的端口映射，再使用 SSH 隧道，不要直接暴露数据库公网端口。

## 5. 构建系统并初始化数据库

```bash
sudo docker compose build api web
sudo docker compose run --rm admin
```

构建时会安装 Python 依赖、Microsoft ODBC Driver 18，编译 Vue 前端。Ubuntu 宿主机无需额外安装 Python、Node.js 或 ODBC。需要服务器能访问 Docker Hub、Microsoft 镜像/软件源、PyPI 和 npm。

`admin` 命令依次执行：

1. 不存在时创建 `OKR` 数据库。
2. 执行 `alembic upgrade head`，当前迁移版本为 `0006`。
3. 不存在时创建 `okr_app` SQL 登录，并应用 `deploy/sql/runtime-role.sql`。
4. 验证 `okr_app` 可以连接并读取迁移版本。

看到 `OKR database ready at migration 0006` 才继续。该命令可以再次执行以迁移已有数据库，不删除已有记录，也不修改已有登录的密码。升级前仍需备份；当前迁移不支持通用的破坏性降级。

## 6. 创建第一个网页管理员

不要将本机开发账号文件上传到服务器，也不要依赖演示账号。先创建自己的组织和管理员身份：

```bash
sudo docker compose run --rm admin python -m app.cli add-org --name '公司' --type corporate
```

记录输出的 `Created record ID`。下面假设返回 `1`，如不同，修改 `--org-id`：

```bash
sudo docker compose run --rm admin python -m app.cli provision-user \
  --subject 'local:admin' --name '系统管理员' --role 'System Admin' --org-id 1
```

读取刚创建用户的实际编号：

```bash
sudo docker compose run --rm -T admin python -c \
  "from sqlalchemy import select; from app.db import session_factory; from app.models import User; db=session_factory()(); print(db.scalar(select(User.id).where(User.subject=='local:admin'))); db.close()"
```

下面假设编号为 `1`，请按实际输出修改 `--user-id`：

```bash
sudo docker compose run --rm admin python -m app.cli set-password --user-id 1 --username admin
```

按提示输入两遍 12–128 字符的**网页登录密码**。此密码与 sa、okr_app 的数据库密码完全独立。密码输入不回显，不要加 `-T`，该命令需要交互终端。以上组织和用户创建步骤只执行一次；重设密码时仅重新执行 `set-password`。

周期和组织也可以通过管理命令创建，例如：

```bash
sudo docker compose run --rm admin python -m app.cli add-cycle \
  --name '2026 Q4' --start 2026-10-01 --end 2026-12-31
```

周期日期按实际使用时间调整。后续登录网页的“人员管理”添加人员；审批流还需要建立相应部门、经理和事业部负责人，缺少独立审批人时系统会拒绝提交。

## 7. 启动并访问

```bash
sudo docker compose up -d api worker web
sudo docker compose ps
curl -f http://127.0.0.1:8080/health/ready
```

就绪结果应为 `{"status":"ready"}`。浏览器访问 `.env` 中的地址，如 `http://192.168.1.100:8080`，使用 `admin` 和第 6 节设置的网页登录密码登录。

如果修改了默认端口，curl 也要相应调整。云服务器安全组允许指定来源访问 TCP 8080；Docker 发布端口可能绕过 UFW 规则，访问限制应同时在云安全组或 Docker 的转发规则中落实。需要只允许本机访问时，将 `OKR_HTTP_BIND=127.0.0.1`。

API 8000 不映射宿主机端口，仅由内部 Nginx 转发；Uvicorn 在此隔离网络内接收代理头，Nginx 会覆盖客户端转发地址。不要另外将 API 8000 暴露给不受信任的客户端。

API 与 Worker 共用 `okr_okr_files` 命名卷，保存证据、隔离文件和导出。默认未安装病毒扫描器，上传的附件会保持隔离，不能作为已通过扫描的证据下载使用。要使用完整附件流程，需扩展后端镜像安装实际扫描工具，并为 Worker 配置 `OKR_SCANNER_EXECUTABLE`；退出码约定见原部署文档。

## 8. 常用维护与排错

```bash
# 查看状态和最近日志；跟随日志时 Ctrl+C 退出，不会关闭服务
sudo docker compose ps -a
sudo docker compose logs --tail=100 api worker web sqlserver
sudo docker compose logs -f --tail=100 api worker

# 停止 / 恢复服务；持久卷保留
sudo docker compose stop
sudo docker compose start

# 修改 .env 后，重建容器以加载新环境变量
sudo docker compose up -d api worker web
```

修改 `.env` 后仅 `restart` 不会更新容器环境。不要将 `docker compose config` 的完整输出发到聊天或工单中，其中包含数据库密码；仅做语法检查用 `sudo docker compose config --quiet`。

| 现象 | 检查方法 |
| --- | --- |
| SQL Server 不健康 | 检查容器日志、可用内存、x86-64 架构、密码是否与已有数据卷一致 |
| API 显示 unhealthy / 数据库未就绪 | 检查第 5 节初始化是否成功，API 与 SQL Server 日志，以及数据卷可写性 |
| 登录报来源错误 | 核对 `OKR_PUBLIC_URL` 与浏览器地址的协议、IP/域名和端口，然后重新 `up -d` |
| 页面能打开但功能超时 | 检查 API 是否健康、数据库连接及反向代理日志 |
| 任务不运行 | 检查 worker 服务状态和日志；配置扫描器后需处理原有失败扫描任务 |
| 外部无法打开网页 | 核对监听地址、端口占用、服务器 IP、云安全组和 Docker 转发规则 |
| 构建拉取超时 | 核对服务器访问镜像源、Microsoft 软件源、PyPI 与 npm 的网络能力 |

更新项目代码后的顺序：先备份，再执行下面命令。更新期间会短暂停服：

```bash
sudo docker compose build api web
sudo docker compose stop web worker api
sudo docker compose run --rm admin
sudo docker compose up -d api worker web
curl -f http://127.0.0.1:8080/health/ready
```

SQL Server 数据卷不等于备份。数据库需使用 SQL Server 原生 BACKUP，并将备份复制到异机存储；附件卷、配置也要同步备份，定期验证联合恢复。不要直接复制运行中的数据库数据文件作为一致性备份。不要执行 `docker compose down -v` 或删除持久卷，这会删除数据库与附件。`2022-latest` 等标签会随上游发布变化，正式发布时应固定经过验证的镜像版本或 digest。

## 9. 转换为正式生产

这一步需要结合实际域名、证书、数据库授权和扫描服务配置，不能只把 development 改成 production：

1. 使用适用于生产业务的 SQL Server 授权版本；Developer 版不能用于正式生产。
2. 在入口配置 HTTPS，设置真实 `OKR_PUBLIC_URL=https://你的域名`。如在外部网关终结 TLS，将内部 HTTP 入口绑定本机或限制为网关可达。
3. 为 SQL Server 安装证书，证书 SAN 必须匹配应用连接使用的服务器名称，并把颁发 CA 加入后端镜像的系统信任库。API、Worker 和管理连接都启用 `Encrypt=yes&TrustServerCertificate=no`。按名称选择容器网络别名或正确配置 `HostNameInCertificate`。
4. API、Worker 使用 `OKR_ENV=production`、`OKR_AUTH_MODE=password`，或完整配置 Entra；保持 `OKR_ENABLE_DEV_LOGIN=false`。未完成 HTTPS 和 SQL 证书配置时，应用会拒绝生产模式启动。试运行的 `bootstrap.py` 仅允许 development，生产迁移应由独立发布身份直接运行 Alembic，不使用该试运行引导脚本。
5. 将创建组织、周期、用户和迁移交给独立受控管理身份；运行服务继续使用项目的 `okr_runtime` 最小权限角色。生产不要直接复用本试运行的 sa 管理配置。
6. 安装并验证扫描器，完成备份恢复、权限与真实 SQL Server 事务并发验收，按需求配置监控和资源限额。

## 官方资料

- [Docker Engine 的 Ubuntu 安装说明](https://docs.docker.com/engine/install/ubuntu/)
- [Microsoft SQL Server Docker 容器快速入门](https://learn.microsoft.com/en-us/sql/linux/quickstart-install-connect-docker)
- [Microsoft ODBC Driver 18 Linux 安装说明](https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server)
