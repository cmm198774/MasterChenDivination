# 基础镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（ffmpeg 用于语音处理）
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 拷贝依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝项目代码
COPY . .

# 创建必要的目录
RUN mkdir -p /app/local_qdrant /app/redis_cache /app/logs

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "server.py"]
