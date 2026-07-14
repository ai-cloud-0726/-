# 学迹智评部署与运维说明书

## 1. MVP 部署目标

首版部署在一台腾讯云 Ubuntu 服务器，使用 Docker Compose 管理前端、后端、PostgreSQL、Redis 和 Nginx。PaddleOCR 可在同机运行；若资源不足则先以异步低并发方式运行。

## 2. 推荐服务器

- Ubuntu 24.04 LTS 或 22.04 LTS
- 最低：2核4GB；建议：4核8GB
- 系统盘：100GB以上
- 公网防火墙仅开放 22、80、443
- PostgreSQL 5432、Redis 6379 不对公网开放

## 3. 容器

```text
nginx          反向代理与静态入口
frontend       React/Vite 构建产物
backend        FastAPI API
postgres       PostgreSQL + pgvector
redis          缓存与队列
ocr-worker     PaddleOCR 异步任务（后续启用）
```

## 4. 环境变量

```dotenv
APP_ENV=development
APP_SECRET_KEY=replace-me
DATABASE_URL=postgresql+psycopg://xueji:password@postgres:5432/xueji
REDIS_URL=redis://redis:6379/0
UPLOAD_DIR=/data/uploads
MAX_UPLOAD_MB=10
AI_PRIMARY_PROVIDER=bailian
AI_FALLBACK_PROVIDER=hunyuan
DASHSCOPE_API_KEY=
HUNYUAN_SECRET_ID=
HUNYUAN_SECRET_KEY=
OCR_PROVIDER=mock
CORS_ORIGINS=http://localhost:5173
```

真实 `.env` 不得提交 Git。

## 5. 本地启动

```bash
cp .env.example .env
docker compose -f deployment/docker-compose.yml up --build
```

## 6. 生产启动

1. 创建非 root 运维用户。
2. 安装 Docker Engine 与 Compose Plugin。
3. 克隆仓库并切换发布标签。
4. 创建 `.env`，使用强密码和生产密钥。
5. 挂载独立数据目录。
6. 执行数据库迁移。
7. 启动容器并检查健康状态。
8. 配置域名和 HTTPS。
9. 设置备份、日志轮转和费用告警。

## 7. Nginx 规则

- `/` 转发前端。
- `/api/` 转发后端。
- `/health` 用于探活。
- 上传大小限制与后端一致。
- 添加 HSTS、X-Content-Type-Options、Referrer-Policy 等安全头。
- 对登录、上传和报告接口设置基础限流。

## 8. 数据目录

```text
/data/xueji/
├── postgres/
├── redis/
├── uploads/
├── reports/
├── backups/
└── logs/
```

## 9. 备份

每日：`pg_dump`，保留7天。

每周：数据库完整备份 + 文件增量备份，保留4周。

备份至少复制到服务器以外位置。每月执行一次恢复演练并记录结果。

## 10. 发布流程

```mermaid
flowchart LR
  DEV[开发分支] --> PR[Pull Request]
  PR --> CI[测试/构建]
  CI --> REVIEW[审核]
  REVIEW --> MAIN[合并 main]
  MAIN --> TAG[发布标签]
  TAG --> DEPLOY[腾讯云部署]
  DEPLOY --> CHECK[健康检查]
```

禁止直接把未经审核的开发分支部署到生产。

## 11. 健康检查

- `GET /health`：进程状态。
- `GET /ready`：数据库和 Redis 可用性。
- 监控 CPU、内存、磁盘、数据库连接、5xx、OCR队列、AI错误率和报告耗时。

## 12. 告警阈值

- 磁盘使用超过75%。
- 内存持续超过85%。
- API 5xx 超过2%。
- OCR任务等待超过10分钟。
- AI报告失败率超过5%。
- 数据库备份失败。
- TLS证书剩余少于15天。

## 13. 安全检查

- 禁止默认密码。
- 禁止在 Git 中保存 `.env`、私钥和生产数据。
- SSH 优先使用密钥，关闭弱密码。
- 数据库仅容器网络访问。
- 定期升级操作系统和基础镜像。
- 生产日志中不输出学生原始资料。

## 14. 初期容量估算

单机 4核8GB目标：数百名内测用户、低并发练习、OCR与报告异步处理。若 OCR、报告和数据库争抢资源，优先将 OCR Worker 限制并发，随后迁移文件存储和数据库。
