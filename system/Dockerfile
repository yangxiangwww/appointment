FROM python:3.10-slim

WORKDIR /app

# 安装环境依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制全部应用文件
COPY . .

# Hugging Face Spaces 默认监听 7860 端口
EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
