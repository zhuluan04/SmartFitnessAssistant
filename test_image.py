"""测试图片路径处理和编码"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from app.langchain import encode_image_to_base64

# 测试1：引号处理
test_cases = [
    '"D:\\photos\\food.jpg"',       # Windows 拖拽带双引号
    "'D:\\photos\\food.jpg'",       # 单引号
    'D:\\photos\\food.jpg',         # 无引号
    'D:\\photos\\my food.png',      # 空格路径
]

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

print("=== 测试1：引号处理 ===")
for raw in test_cases:
    cleaned = raw.strip('"').strip("'")
    _, ext = os.path.splitext(cleaned)
    is_image = ext.lower() in IMAGE_EXTENSIONS
    print(f"  输入: {raw:40s} -> 清理: {cleaned:30s} -> 扩展名: {ext:6s} -> 图片: {is_image}")

# 测试2：用用户的实际图片测试编码
user_image = r"D:\25038\Pictures\Saved Pictures\微信图片_20260703112547_300_13.jpg"
print(f"\n=== 测试2：实际图片编码 ===")
print(f"  路径: {user_image}")
print(f"  存在: {os.path.exists(user_image)}")

if os.path.exists(user_image):
    mime, data = encode_image_to_base64(user_image)
    print(f"  MIME: {mime}")
    print(f"  大小: {len(data)//1024} KB")
    print(f"  前50字符: {data[:50]}...")
    
    # 测试3：通过 LangChain 模型发送图片
    print(f"\n=== 测试3：通过模型发送图片 ===")
    from dotenv import load_dotenv
    load_dotenv(override=True)
    from langchain.chat_models import init_chat_model
    model = init_chat_model(
        model="qwen-vl-plus",
        model_provider="openai",
        base_url=os.getenv("DASHSCOPE_BASE_URL"),
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        temperature=0.3,
    )
    from langchain_core.messages import HumanMessage
    msg = HumanMessage(content=[
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}},
        {"type": "text", "text": "用一句话描述这张图片中看到的食物"}
    ])
    try:
        resp = model.invoke([msg])
        print(f"  模型响应: {resp.content[:200]}")
    except Exception as e:
        print(f"  错误: {e}")
else:
    print("  文件不存在，跳过编码测试")
