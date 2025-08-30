# Stylize Video - AI视频风格转换工具

一个本地运行的AI视频风格转换工具，通过输入图片和音乐，生成具有不同艺术风格的视频内容。

## ✨ 主要特性

- 🎨 **多种艺术风格**: 支持30+种艺术风格，包括赛博朋克、浮世绘、哥特暗黑等
- 🔒 **本地运行**: 完全本地处理，保护用户隐私
- 📱 **两步式工作流**: 先生成风格图片，用户选择后再合成视频
- 🎵 **背景音乐**: 支持添加自定义背景音乐
- 📋 **历史任务**: 自动保存任务历史，支持重新生成视频
- 🗑️ **图片管理**: 支持删除不满意的风格图片
- ⚡ **快速重新生成**: 复用已生成的图片，快速调整视频参数

## 🛠️ 技术栈

- **后端**: FastAPI + Python
- **前端**: HTML + JavaScript (原生)
- **视频处理**: FFmpeg
- **AI服务**: OpenRouter API
- **数据库**: MongoDB (历史任务持久化)
- **图像处理**: Pillow

## 🚀 快速开始

### 环境要求

- Python 3.8+
- FFmpeg
- MongoDB (可选，用于历史任务持久化)
- OpenRouter API Key

### 安装步骤

1. **克隆项目**
   ```bash
   git clone https://github.com/your-username/stylize-video.git
   cd stylize-video
   ```

2. **设置MongoDB (推荐)**
   ```bash
   # 参考 MONGODB_SETUP.md 安装和配置MongoDB
   # MongoDB用于持久化历史任务，如不安装则历史功能不可用
   ```

3. **启动项目**
   
   **Windows:**
   ```cmd
   start.bat
   ```
   
   **Linux/macOS:**
   ```bash
   ./start.sh
   ```

4. **访问应用**
   - 前端界面: http://localhost:5000
   - API文档: http://localhost:5000/docs
   - 数据库状态: http://localhost:5000/api/database/status

## 📋 使用指南

### 基本工作流程

1. **获取OpenRouter API Key**
   - 访问 [OpenRouter](https://openrouter.ai/)
   - 注册账号并获取API Key

2. **选择生成模式**
   - **新任务**: 完整的图片生成+视频合成流程
   - **仅生成图片**: 只生成风格图片，稍后选择合成
   - **历史任务**: 复用之前的图片重新生成视频

3. **上传原图和配置**
   - 上传要进行风格转换的原图
   - 选择风格图数量、视频参数等
   - 可选：添加背景音乐

4. **生成和管理**
   - 等待AI生成风格化图片
   - 预览并删除不满意的图片
   - 选择转场效果和视频参数
   - 合成最终视频

### 高级配置

- **转场效果**: 支持50+种转场效果，包括滑动、淡化、特效等
- **视频分辨率**: 支持多种分辨率，包括抖音竖屏(720x1280)
- **帧率控制**: 15-60 FPS可调
- **并发控制**: 可调整AI请求并发数量

## 🔧 配置说明

### 环境变量

```bash
# 服务器配置
HOST=127.0.0.1
PORT=5000
DEBUG=True

# MongoDB配置 (可选)
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=stylize_video

# FFmpeg路径 (Windows需要)
FFMPEG_PATH=C:\path\to\ffmpeg.exe
```

### 目录结构

```
stylize-video/
├── backend/
│   ├── app.py              # FastAPI主应用
│   ├── services/           # 业务服务
│   │   ├── image_generator.py
│   │   ├── video_composer.py
│   │   ├── file_manager.py
│   │   └── database.py     # MongoDB服务
│   ├── utils/              # 工具类
│   └── storage/            # 文件存储
│       ├── uploads/        # 上传文件
│       ├── generated/      # 生成的图片
│       ├── videos/         # 生成的视频
│       └── temp/           # 临时文件
├── frontend/
│   └── index.html          # 前端界面
├── MONGODB_SETUP.md        # MongoDB配置指南
└── README.md
```

## 📊 功能特性

### 🎨 支持的艺术风格

- 东方风格：浮世绘、水墨画、新海诚、吉卜力
- 现代风格：赛博朋克、蒸汽波、霓虹灯效果
- 经典艺术：哥特暗黑、Art Nouveau、包豪斯
- 动漫风格：美式漫画、赛璐璐动画、JOJO风格
- 特效风格：双重曝光、迷幻艺术、荧光色

### 🔄 转场效果

- 滑动系列：左滑、右滑、上滑、下滑、平滑移动
- 淡化系列：黑色淡入、白色淡入、溶解、快速/慢速淡化
- 特效系列：像素化、圆形裁切、径向、风效果
- 擦除系列：各方向擦除、对角擦除

### 💾 数据持久化

- **历史任务**: 所有完成的任务自动保存到MongoDB
- **文件管理**: 支持文件元数据存储和管理
- **自动清理**: 支持定期清理过期数据
- **数据备份**: 提供数据备份和恢复工具

## 🐛 故障排除

### 常见问题

1. **FFmpeg 未找到**
   ```bash
   # Windows: 下载FFmpeg并设置环境变量
   # Linux: sudo apt install ffmpeg
   # macOS: brew install ffmpeg
   ```

2. **MongoDB 连接失败**
   ```bash
   # 检查MongoDB服务状态
   # Windows: net start MongoDB
   # Linux: sudo systemctl start mongod
   ```

3. **API调用失败**
   - 检查OpenRouter API Key是否有效
   - 确认账户余额充足
   - 检查网络连接

4. **图片生成失败**
   - 确认图片格式支持(jpg, png, webp)
   - 检查图片大小(<10MB)
   - 尝试降低并发请求数

### 日志查看

```bash
# 查看应用日志
tail -f backend/storage/logs/app.log

# 查看MongoDB日志 (如果安装)
# 参考 MONGODB_SETUP.md
```

## 📈 性能优化

- **并发控制**: 根据API限制调整并发请求数
- **缓存机制**: 复用历史任务的图片资源
- **增量生成**: 支持实时预览生成的图片
- **资源管理**: 自动清理临时文件和过期数据

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- [OpenRouter](https://openrouter.ai/) - 提供AI模型API服务
- [FFmpeg](https://ffmpeg.org/) - 强大的多媒体处理框架
- [FastAPI](https://fastapi.tiangolo.com/) - 现代高性能的Web框架
- [MongoDB](https://www.mongodb.com/) - 文档数据库

## 📞 支持

如有问题或建议，请通过以下方式联系：

- 创建 [Issue](https://github.com/your-username/stylize-video/issues)
- 发送邮件到: your-email@example.com

---

**免责声明**: 本工具仅供学习和研究使用，请遵守相关法律法规和服务商的使用条款。