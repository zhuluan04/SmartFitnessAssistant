"""
智能健身食谱与卡路里总结 Agent — 项目入口

阶段一：命令行交互式测试
阶段三：将替换为 FastAPI 服务入口
"""

import subprocess
import sys


def run_cli():
    """启动命令行交互式 Agent（阶段一）"""
    subprocess.run([sys.executable, "-m", "app.langchain"])


def run_api():
    """启动 FastAPI 服务（阶段三，占位）"""
    import uvicorn
    uvicorn.run("app.api:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="智能健身食谱与卡路里总结 Agent")
    parser.add_argument(
        "mode",
        nargs="?",
        default="cli",
        choices=["cli", "api"],
        help="运行模式：cli（命令行交互，阶段一）/ api（FastAPI 服务，阶段三）",
    )
    args = parser.parse_args()

    if args.mode == "cli":
        run_cli()
    elif args.mode == "api":
        run_api()
