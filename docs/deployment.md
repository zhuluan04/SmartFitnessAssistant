# 智能健身食谱 Agent — 上线部署记录

> 部署时间：2026-10-30 ｜ 状态：后端已上线运行，等待 ICP 备案通过后开启 HTTPS
> 域名：`qingjianshen.cn` ｜ 服务器：阿里云 ECS（2C2G，Ubuntu 22.04 LTS，8.137.178.145）

---

## 一、部署架构

```
微信小程序（miniprogram/）
        │ HTTPS（备案通过后生效）
        ▼
Caddy 反向代理（自动签发/续期 Let's Encrypt 证书）
        │ 容器内网 app:8000
        ▼
FastAPI 后端（fitness-app 容器）
        │ OpenAI 兼容协议
        ▼
DashScope（Qwen3.5-Plus + Qwen-VL-Plus） / Tavily 搜索
```

- **编排**：Docker Compose 双服务（`app` + `caddy`）
- **安全设计**：后端只 `expose` 8000 端口不映射宿主机，外部流量必须经 Caddy 单入口进入
- **自愈**：`restart: unless-stopped` + 健康检查（每 30s 探测 `/api/health`）
- **密钥**：`.env` 挂载进容器，不进 Git 仓库，服务器上 `chmod 600`

## 二、上线时间线

| 步骤 | 内容 | 结果 |
|---|---|---|
| 1 | 本地创建 `docker-compose.yml`、`Caddyfile`、`deploy.sh` 并推送 | commit `9cde8fd` |
| 2 | 修复 Caddyfile 换行符（CRLF→LF），`.gitattributes` 补充规则 | commit `320a99c` |
| 3 | 修复 deploy.sh 在仓库目录内运行的定位 bug | commit `7b110d6` |
| 4 | 服务器 SSH → 一键脚本安装 Docker 29.9.2 | ✅ |
| 5 | 服务器克隆仓库、编辑 `.env` 填入密钥 | ✅ |
| 6 | 配置 Docker 镜像加速器 → 构建镜像 | ✅ 22.5s（依赖走清华源） |
| 7 | 启动容器，健康检查通过 | ✅ `Up (healthy)` |
| 8 | 容器内验证接口返回 `{"status":"ok"}` | ✅ |
| 9 | ICP 备案审核中（80/443 端口暂被屏蔽） | 等待中 ⏳ |

## 三、主要问题与解决方案

### 问题 1：服务器上 `deploy.sh: No such file or directory`

**现象**：服务器执行 `bash deploy.sh` 报文件不存在，`ls -la` 显示仓库里连 Dockerfile、README 都没有。

**原因**：服务器克隆的是旧版本仓库，部署文件尚未推送。

**解决**：重置 remote 到官方仓库后 `git fetch + merge --ff-only` 强制同步。

### 问题 2：`git pull` 显示 "Already up to date" 但文件仍然缺失

**现象**：pull 后文件依旧不存在。

**原因**：克隆时使用的镜像源缓存了旧内容，remote-tracking 停在旧提交。

**解决**：`git remote set-url origin` 重置为 GitHub 官方地址，重新 fetch。

### 问题 3：Docker 构建拉取 `python:3.13-slim` 超时

**现象**：`i/o timeout`，访问 `registry-1.docker.io:443` 失败。

**原因**：国内服务器访问 Docker Hub 被墙。

**解决**：配置阿里云专属镜像加速器（ACR 控制台 → 镜像加速器 → 专属地址）。

### 问题 4：阿里云个人加速器返回 `not found`

**现象**：配置专属加速器后超时消失，但构建报 `docker.io/library/python:3.13-slim: not found`。

**原因**：阿里云免费个人加速器只缓存部分镜像，官方 `library/python` 镜像不在缓存且不允许实时回源。

**解决**：改用多公共镜像源兜底，Docker 按顺序自动尝试：

```json
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me",
    "https://docker.1panel.live",
    "https://hub.rat.dev"
  ]
}
```

配置后 `docker pull python:3.13-slim` 成功，构建顺利复用。

### 问题 5：宿主机 `curl localhost:8000` 连接被拒

**现象**：容器日志显示服务正常、健康检查 200 OK，但宿主机 curl 8000 端口 Connection refused。

**原因**：**不是故障**。compose 中 app 端口只 `expose`（容器内网可见）不映射宿主机，这是安全设计——外部流量必须经 Caddy 反代。

**验证方式**：

```bash
docker exec fitness-app python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/health').read().decode())"
# 输出：{"status":"ok","model":"qwen3.5-plus + qwen-vl-plus"}
```

### 问题 6：本地 git push 失败（代理问题）

**现象**：`Failed to connect to github.com port 443 via 127.0.0.1`。

**原因**：git 全局配置了 Clash 代理（127.0.0.1:7897），但代理软件未运行。

**解决**：不修改全局配置，临时绕行直连：`git -c http.proxy= -c https.proxy= push`。

## 四、部署文件说明

| 文件 | 作用 |
|---|---|
| `deploy.sh` | 一键部署：装 Docker → 定位仓库 → 检查密钥 → 构建 → 启动 |
| `docker-compose.yml` | 编排 app + caddy 双服务，含健康检查、数据卷 |
| `Caddyfile` | 域名自动 HTTPS + gzip + 反代后端 |

## 五、备案通过后待办

1. **启动 HTTPS**：服务器执行 `cd ~/SmartFitnessAssistant && docker compose up -d`（Caddy 自动签证书）
2. **DNS**：`qingjianshen.cn` A 记录 → `8.137.178.145`
3. **密钥轮换**：DashScope / Tavily 控制台重新生成 Key → 更新 `.env` → `docker compose up -d app`
4. **小程序**：微信公众平台配置 request 合法域名 `https://qingjianshen.cn` → 改 `miniprogram/app.js` 的 `apiBaseUrl` → 上传代码提交审核

## 六、常用运维命令

```bash
cd ~/SmartFitnessAssistant
docker compose ps                 # 查看服务状态
docker compose logs -f app        # 跟踪后端日志（含工具调用轨迹）
docker compose up -d              # 更新部署（先 git pull）
docker compose restart app        # 重启后端
```

## 七、关键经验沉淀

1. 国内部署必须预设 Docker 镜像加速器（多源兜底，单一加速器会因缓存缺失失败）；
2. 容器端口 `expose` 与 `ports` 的语义差异：前者仅供编排网络内部访问，后者才映射宿主机；
3. 跨平台协作项目必须用 `.gitattributes` 强制 LF（Dockerfile、Caddyfile、脚本类文件）；
4. 部署脚本要兼容"从任意目录运行"与"在仓库目录内运行"两种场景；
5. 备案期间 80/443 端口被屏蔽属正常现象，Caddy 证书签发须等备案通过后进行。
