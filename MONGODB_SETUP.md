# MongoDB 配置指南

## 概述

为了解决程序重启后历史任务数据丢失的问题，我们已将历史任务存储迁移到 MongoDB 数据库。这确保了数据的持久化和可靠性。

## MongoDB 安装

### Windows

1. **下载 MongoDB Community Server**
   - 访问：https://www.mongodb.com/try/download/community
   - 选择 Windows 版本并下载

2. **安装 MongoDB**
   - 运行下载的 `.msi` 文件
   - 选择 "Complete" 安装类型
   - 勾选 "Install MongoDB as a Service"
   - 勾选 "Install MongoDB Compass"（可选的图形管理工具）

3. **启动 MongoDB 服务**
   ```cmd
   # 方法1：通过Windows服务管理器启动
   services.msc -> 找到MongoDB Server -> 启动
   
   # 方法2：通过命令行启动
   net start MongoDB
   ```

### macOS

```bash
# 使用 Homebrew 安装
brew tap mongodb/brew
brew install mongodb-community

# 启动 MongoDB 服务
brew services start mongodb/brew/mongodb-community
```

### Linux (Ubuntu/Debian)

```bash
# 导入公钥
wget -qO - https://www.mongodb.org/static/pgp/server-6.0.asc | sudo apt-key add -

# 添加仓库
echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/6.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list

# 安装 MongoDB
sudo apt-get update
sudo apt-get install -y mongodb-org

# 启动服务
sudo systemctl start mongod
sudo systemctl enable mongod
```

## 环境变量配置

在项目启动前，您可以通过环境变量自定义 MongoDB 连接设置：

```bash
# MongoDB 连接URL（默认：mongodb://localhost:27017）
set MONGODB_URL=mongodb://localhost:27017

# 数据库名称（默认：stylize_video）
set MONGODB_DATABASE=stylize_video
```

### 高级配置示例

```bash
# 连接到远程 MongoDB 实例
set MONGODB_URL=mongodb://username:password@remote-host:27017/dbname

# 连接到 MongoDB Atlas（云服务）
set MONGODB_URL=mongodb+srv://username:password@cluster.mongodb.net/dbname

# 连接到 MongoDB 副本集
set MONGODB_URL=mongodb://host1:27017,host2:27017,host3:27017/dbname?replicaSet=myReplicaSet
```

## 验证安装

1. **检查 MongoDB 服务状态**
   ```bash
   # Windows
   sc query MongoDB
   
   # macOS
   brew services list | grep mongodb
   
   # Linux
   sudo systemctl status mongod
   ```

2. **测试数据库连接**
   - 启动项目后访问：http://localhost:5000/api/database/status
   - 应该返回数据库连接状态信息

## 数据库结构

系统会自动创建以下集合：

### history_tasks
存储历史任务信息：
```json
{
  "task_id": "uuid-string",
  "status": "completed",
  "created_at": "2024-01-01T12:00:00",
  "completed_at": "2024-01-01T12:05:00",
  "config": {
    "slide_count": 3,
    "fps": 30,
    "width": 720,
    "height": 1280
  },
  "images": [
    {
      "file_id": "image-uuid",
      "style": "赛博朋克",
      "url": "/api/files/image-uuid"
    }
  ],
  "original_image_id": "original-uuid",
  "saved_at": "2024-01-01T12:05:30"
}
```

### file_metadata
存储文件元数据信息：
```json
{
  "file_id": "uuid-string",
  "filename": "original.jpg",
  "file_type": "image",
  "size": 1024000,
  "created_at": "2024-01-01T12:00:00"
}
```

## 故障排除

### 常见问题

1. **MongoDB 连接失败**
   - 检查 MongoDB 服务是否正在运行
   - 验证连接URL和端口（默认27017）
   - 检查防火墙设置

2. **权限问题**
   - 确保 MongoDB 数据目录有适当的读写权限
   - Windows: 通常在 `C:\Program Files\MongoDB\Server\6.0\data`
   - Linux/macOS: 通常在 `/var/lib/mongodb`

3. **端口冲突**
   - 默认端口 27017 可能被其他应用占用
   - 修改 MongoDB 配置文件中的端口设置

### 日志查看

```bash
# Windows - 查看 MongoDB 日志
type "C:\Program Files\MongoDB\Server\6.0\log\mongod.log"

# Linux/macOS - 查看 MongoDB 日志
sudo tail -f /var/log/mongodb/mongod.log
```

## 数据备份与恢复

### 备份数据
```bash
# 备份整个数据库
mongodump --db stylize_video --out /path/to/backup/

# 备份特定集合
mongodump --db stylize_video --collection history_tasks --out /path/to/backup/
```

### 恢复数据
```bash
# 恢复整个数据库
mongorestore --db stylize_video /path/to/backup/stylize_video/

# 恢复特定集合
mongorestore --db stylize_video --collection history_tasks /path/to/backup/stylize_video/history_tasks.bson
```

## 性能优化

1. **索引优化**
   - 系统自动创建必要的索引
   - 对于大量数据，考虑添加复合索引

2. **连接池设置**
   ```python
   # 在需要时可以调整连接池参数
   MONGODB_URL = "mongodb://localhost:27017/?maxPoolSize=50&minPoolSize=5"
   ```

3. **数据清理**
   - 系统提供自动清理超过30天的旧任务功能
   - 可通过API手动触发清理

## MongoDB Compass（可选）

MongoDB Compass 是官方提供的图形化管理工具：

1. 打开 MongoDB Compass
2. 连接到 `mongodb://localhost:27017`
3. 选择 `stylize_video` 数据库
4. 查看和管理 `history_tasks` 集合

通过 Compass 您可以：
- 查看历史任务数据
- 执行查询和聚合
- 监控数据库性能
- 导入/导出数据

## 注意事项

1. **兼容性处理**
   - 如果 MongoDB 不可用，系统会自动降级，但历史任务功能将无法使用
   - 系统启动时会显示 MongoDB 连接状态

2. **数据迁移**
   - 从内存存储迁移到 MongoDB 是自动的
   - 旧的内存数据在程序重启后会丢失，但新产生的任务会保存到 MongoDB

3. **安全建议**
   - 生产环境中建议启用 MongoDB 身份验证
   - 配置适当的网络安全规则
   - 定期备份重要数据