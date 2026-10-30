#!/bin/bash
set -e
echo "===== 智能健身食谱 Agent 一键部署 ====="

echo "[1/5] 安装 Docker..."
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
    systemctl enable --now docker
fi
docker -v

echo "[2/5] 拉取代码..."
if [ ! -d SmartFitnessAssistant ]; then
    git clone https://github.com/zhuluan04/SmartFitnessAssistant.git
fi
cd SmartFitnessAssistant
git pull --ff-only

echo "[3/5] 配置密钥..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo ">>> 请编辑 .env 填入真实密钥后重新执行本脚本："
    echo ">>>   cd ~/SmartFitnessAssistant && nano .env"
    exit 0
fi

echo "[4/5] 构建镜像（首次约 3-5 分钟，走清华源）..."
docker compose build

echo "[5/5] 启动后端（备案通过前仅内网验证）..."
docker compose up -d app
sleep 5
docker compose ps

echo ""
echo "===== 验证：执行下面这行，看到 status=ok 即成功 ====="
echo "curl http://localhost:8000/api/health"
echo ""
echo "备案通过后执行: cd ~/SmartFitnessAssistant && docker compose up -d"
echo "（自动启动 Caddy + HTTPS）"
