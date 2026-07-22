# Docker 完全隔离迁移设计

**目标：** 完全隔离的 Docker 部署，本地开发环境不受影响

**架构：**
- 3 个容器：app（Python 应用）、redis、qdrant
- 容器间通过 Docker 内部网络通信（`redis://redis:6379`、`http://qdrant:6333`）
- 只有 app 的 8000 端口映射到宿主机

**配置管理：**
- 环境变量：使用 `env_file: .env` 读取，不映射文件进容器
- config.py 自动检测 Docker 环境（`os.path.exists("/.dockerenv")`），选择正确的主机名
  - Docker：REDIS_HOST=`redis`，QDRANT_HOST=`qdrant`
  - 本地：REDIS_HOST=`localhost`，QDRANT_HOST=`localhost`

**数据持久化：**
- Redis：使用 named volume `redis_data`
- Qdrant：使用 named volume `qdrant_data`
- 本地目录不映射，完全隔离

**日志：**
- 改用标准输出（print/sys.stdout），使用 `docker logs master-chen-app` 查看

**端口映射：**
- app: 8000→8000（飞书 WebSocket 出站，不需要入站）
- redis: 不映射（容器内访问）
- qdrant: 不映射（容器内访问）

**文件清单：**
- `Dockerfile` - Python 应用镜像
- `docker-compose.yml` - 服务编排
- `config.py` - 自动检测环境选择主机名
- `MyTools.py` - QdrantClient 根据环境选择连接方式
- `.env` - 环境变量（复用，不映射进容器）
