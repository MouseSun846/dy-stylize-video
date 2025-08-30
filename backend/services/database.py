#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MongoDB数据库服务
用于持久化存储历史任务和文件元数据
"""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
import logging

logger = logging.getLogger(__name__)


class DatabaseService:
    """MongoDB数据库服务类"""
    
    def __init__(self, mongodb_url: str, database_name: str):
        self.mongodb_url = mongodb_url
        self.database_name = database_name
        self.client: Optional[AsyncIOMotorClient] = None
        self.database: Optional[AsyncIOMotorDatabase] = None
        self.history_collection: Optional[AsyncIOMotorCollection] = None
        self.files_collection: Optional[AsyncIOMotorCollection] = None
        self.gallery_groups_collection: Optional[AsyncIOMotorCollection] = None  # 图库分组集合
        self.gallery_images_collection: Optional[AsyncIOMotorCollection] = None  # 图库图片集合
        self._is_connected = False
    
    async def connect(self):
        """连接到MongoDB"""
        try:
            self.client = AsyncIOMotorClient(self.mongodb_url)
            # 测试连接
            await self.client.admin.command('ping')
            self.database = self.client[self.database_name]
            self.history_collection = self.database['history_tasks']
            self.files_collection = self.database['file_metadata']
            self.gallery_groups_collection = self.database['gallery_groups']  # 图库分组集合
            self.gallery_images_collection = self.database['gallery_images']  # 图库图片集合
            
            # 创建索引
            await self._create_indexes()
            
            self._is_connected = True
            logger.info(f"MongoDB连接成功: {self.mongodb_url}")
            return True
            
        except Exception as e:
            logger.error(f"MongoDB连接失败: {str(e)}")
            self._is_connected = False
            return False
    
    async def disconnect(self):
        """断开MongoDB连接"""
        if self.client:
            self.client.close()
            self._is_connected = False
            logger.info("MongoDB连接已关闭")
    
    async def _create_indexes(self):
        """创建数据库索引"""
        try:
            # 为历史任务集合创建索引
            await self.history_collection.create_index("task_id", unique=True)
            await self.history_collection.create_index("created_at")
            await self.history_collection.create_index("status")
            
            # 为文件元数据集合创建索引
            await self.files_collection.create_index("file_id", unique=True)
            await self.files_collection.create_index("created_at")
            
            # 为图库分组集合创建索引
            await self.gallery_groups_collection.create_index("id", unique=True)
            await self.gallery_groups_collection.create_index("name")
            await self.gallery_groups_collection.create_index("created_at")
            
            # 为图库图片集合创建索引
            await self.gallery_images_collection.create_index("id", unique=True)
            await self.gallery_images_collection.create_index("group_id")
            await self.gallery_images_collection.create_index("created_at")
            await self.gallery_images_collection.create_index([("group_id", 1), ("created_at", -1)])
            
            logger.info("数据库索引创建完成")
        except Exception as e:
            logger.error(f"创建数据库索引失败: {str(e)}")
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._is_connected
    
    async def save_history_task(self, task_id: str, task_data: Dict[str, Any]) -> bool:
        """保存历史任务"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，无法保存历史任务")
            return False
        
        try:
            # 添加保存时间戳
            task_data_copy = task_data.copy()
            task_data_copy['task_id'] = task_id
            task_data_copy['saved_at'] = datetime.utcnow()
            
            # 使用upsert操作，如果任务已存在则更新
            result = await self.history_collection.replace_one(
                {"task_id": task_id},
                task_data_copy,
                upsert=True
            )
            
            logger.info(f"历史任务已保存: task_id={task_id}")
            return True
            
        except Exception as e:
            logger.error(f"保存历史任务失败 (task_id: {task_id}): {str(e)}")
            return False
    
    async def get_history_tasks(self, limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
        """获取历史任务列表"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，返回空历史任务列表")
            return []
        
        try:
            cursor = self.history_collection.find(
                {"status": {"$in": ["completed", "images_ready"]}},
                {"_id": 0}  # 排除MongoDB的_id字段
            ).sort("created_at", -1).limit(limit).skip(skip)
            
            tasks = await cursor.to_list(length=limit)
            logger.info(f"获取到 {len(tasks)} 个历史任务")
            return tasks
            
        except Exception as e:
            logger.error(f"获取历史任务列表失败: {str(e)}")
            return []
    
    async def get_history_task_by_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取特定历史任务"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，无法获取历史任务")
            return None
        
        try:
            task = await self.history_collection.find_one(
                {"task_id": task_id},
                {"_id": 0}
            )
            
            if task:
                logger.info(f"获取到历史任务: task_id={task_id}")
            else:
                logger.warning(f"历史任务不存在: task_id={task_id}")
            
            return task
            
        except Exception as e:
            logger.error(f"获取历史任务失败 (task_id: {task_id}): {str(e)}")
            return None
    
    async def delete_history_task(self, task_id: str) -> bool:
        """删除历史任务"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，无法删除历史任务")
            return False
        
        try:
            result = await self.history_collection.delete_one({"task_id": task_id})
            
            if result.deleted_count > 0:
                logger.info(f"历史任务已删除: task_id={task_id}")
                return True
            else:
                logger.warning(f"要删除的历史任务不存在: task_id={task_id}")
                return False
                
        except Exception as e:
            logger.error(f"删除历史任务失败 (task_id: {task_id}): {str(e)}")
            return False
    
    async def remove_image_from_history_tasks(self, image_id: str) -> int:
        """从所有历史任务中移除指定图片"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，无法移除图片引用")
            return 0
        
        try:
            # 使用$pull操作从数组中移除匹配的元素
            result = await self.history_collection.update_many(
                {"images.file_id": image_id},  # 查找条件：包含该图片ID的任务
                {"$pull": {"images": {"file_id": image_id}}}  # 移除操作：从数组中删除匹配的图片
            )
            
            updated_count = result.modified_count
            logger.info(f"已从 {updated_count} 个历史任务中移除图片 {image_id}")
            return updated_count
            
        except Exception as e:
            logger.error(f"从历史任务中移除图片失败 (image_id: {image_id}): {str(e)}")
            return 0
    
    async def cleanup_old_tasks(self, days: int = 30) -> int:
        """清理超过指定天数的旧任务"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，无法清理旧任务")
            return 0
        
        try:
            from datetime import timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            result = await self.history_collection.delete_many({
                "created_at": {"$lt": cutoff_date.isoformat()}
            })
            
            deleted_count = result.deleted_count
            logger.info(f"清理了 {deleted_count} 个超过 {days} 天的旧任务")
            return deleted_count
            
        except Exception as e:
            logger.error(f"清理旧任务失败: {str(e)}")
            return 0
    
    # ==================== 图库功能相关方法 ====================
    
    async def create_gallery_group(self, group_id: str, name: str) -> bool:
        """创建图库分组"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，无法创建图库分组")
            return False
        
        try:
            group_data = {
                "id": group_id,
                "name": name,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            await self.gallery_groups_collection.insert_one(group_data)
            logger.info(f"图库分组创建成功: {group_id} - {name}")
            return True
            
        except Exception as e:
            logger.error(f"创建图库分组失败 (group_id: {group_id}): {str(e)}")
            return False
    
    async def get_gallery_groups(self) -> List[Dict[str, Any]]:
        """获取所有图库分组"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，返回空图库分组列表")
            return []
        
        try:
            # 获取分组列表并计算每个分组的图片数量
            pipeline = [
                {
                    "$lookup": {
                        "from": "gallery_images",
                        "localField": "id",
                        "foreignField": "group_id",
                        "as": "images"
                    }
                },
                {
                    "$addFields": {
                        "image_count": {"$size": "$images"}
                    }
                },
                {
                    "$project": {
                        "images": 0,  # 不返回图片详情
                        "_id": 0
                    }
                },
                {
                    "$sort": {"created_at": -1}
                }
            ]
            
            groups = await self.gallery_groups_collection.aggregate(pipeline).to_list(None)
            logger.info(f"获取到 {len(groups)} 个图库分组")
            return groups
            
        except Exception as e:
            logger.error(f"获取图库分组列表失败: {str(e)}")
            return []
    
    async def get_gallery_group_by_id(self, group_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取图库分组"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，无法获取图库分组")
            return None
        
        try:
            group = await self.gallery_groups_collection.find_one(
                {"id": group_id},
                {"_id": 0}
            )
            
            if group:
                logger.info(f"获取到图库分组: group_id={group_id}")
            else:
                logger.warning(f"图库分组不存在: group_id={group_id}")
            
            return group
            
        except Exception as e:
            logger.error(f"获取图库分组失败 (group_id: {group_id}): {str(e)}")
            return None
    
    async def update_gallery_group(self, group_id: str, name: str) -> bool:
        """更新图库分组名称"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，无法更新图库分组")
            return False
        
        try:
            result = await self.gallery_groups_collection.update_one(
                {"id": group_id},
                {
                    "$set": {
                        "name": name,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"图库分组更新成功: group_id={group_id}")
                return True
            else:
                logger.warning(f"图库分组不存在或未更新: group_id={group_id}")
                return False
                
        except Exception as e:
            logger.error(f"更新图库分组失败 (group_id: {group_id}): {str(e)}")
            return False
    
    async def delete_gallery_group(self, group_id: str) -> bool:
        """删除图库分组及其所有图片"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，无法删除图库分组")
            return False
        
        try:
            # 先删除分组中的所有图片
            deleted_images = await self.gallery_images_collection.delete_many({"group_id": group_id})
            logger.info(f"已删除分组 {group_id} 中的 {deleted_images.deleted_count} 张图片")
            
            # 再删除分组本身
            result = await self.gallery_groups_collection.delete_one({"id": group_id})
            
            if result.deleted_count > 0:
                logger.info(f"图库分组删除成功: group_id={group_id}")
                return True
            else:
                logger.warning(f"图库分组不存在: group_id={group_id}")
                return False
                
        except Exception as e:
            logger.error(f"删除图库分组失败 (group_id: {group_id}): {str(e)}")
            return False
    
    async def add_image_to_gallery_group(self, image_id: str, group_id: str, name: str, metadata: Dict[str, Any]) -> bool:
        """添加图片到图库分组"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，无法添加图片到图库分组")
            return False
        
        try:
            image_data = {
                "id": image_id,
                "group_id": group_id,
                "name": name,
                "metadata": metadata,
                "created_at": datetime.utcnow()
            }
            
            await self.gallery_images_collection.insert_one(image_data)
            logger.info(f"图片添加到图库分组成功: image_id={image_id}, group_id={group_id}")
            return True
            
        except Exception as e:
            logger.error(f"添加图片到图库分组失败 (image_id: {image_id}, group_id: {group_id}): {str(e)}")
            return False
    
    async def get_images_in_gallery_group(self, group_id: str) -> List[Dict[str, Any]]:
        """获取图库分组中的所有图片"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，返回空图片列表")
            return []
        
        try:
            images = await self.gallery_images_collection.find(
                {"group_id": group_id},
                {"_id": 0}
            ).sort("created_at", -1).to_list(None)
            
            logger.info(f"从分组 {group_id} 获取到 {len(images)} 张图片")
            return images
            
        except Exception as e:
            logger.error(f"获取图库分组图片失败 (group_id: {group_id}): {str(e)}")
            return []
    
    async def delete_gallery_image(self, image_id: str) -> bool:
        """删除图库图片"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，无法删除图库图片")
            return False
        
        try:
            result = await self.gallery_images_collection.delete_one({"id": image_id})
            
            if result.deleted_count > 0:
                logger.info(f"图库图片删除成功: image_id={image_id}")
                return True
            else:
                logger.warning(f"图库图片不存在: image_id={image_id}")
                return False
                
        except Exception as e:
            logger.error(f"删除图库图片失败 (image_id: {image_id}): {str(e)}")
            return False
    
    async def delete_gallery_images_batch(self, image_ids: List[str]) -> int:
        """批量删除图库图片"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，无法批量删除图库图片")
            return 0
        
        try:
            result = await self.gallery_images_collection.delete_many({"id": {"$in": image_ids}})
            deleted_count = result.deleted_count
            logger.info(f"批量删除图库图片成功: {deleted_count} 张")
            return deleted_count
            
        except Exception as e:
            logger.error(f"批量删除图库图片失败: {str(e)}")
            return 0
    
    async def save_file_metadata(self, file_id: str, metadata: Dict[str, Any]) -> bool:
        """保存文件元数据"""
        if not self.is_connected():
            logger.warning("MongoDB未连接，无法保存文件元数据")
            return False
        
        try:
            metadata_copy = metadata.copy()
            metadata_copy['file_id'] = file_id
            metadata_copy['created_at'] = datetime.utcnow()
            
            result = await self.files_collection.replace_one(
                {"file_id": file_id},
                metadata_copy,
                upsert=True
            )
            
            logger.info(f"文件元数据已保存: file_id={file_id}")
            return True
            
        except Exception as e:
            logger.error(f"保存文件元数据失败 (file_id: {file_id}): {str(e)}")
            return False
    
    async def get_file_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """获取文件元数据"""
        if not self.is_connected():
            return None
        
        try:
            metadata = await self.files_collection.find_one(
                {"file_id": file_id},
                {"_id": 0}
            )
            return metadata
            
        except Exception as e:
            logger.error(f"获取文件元数据失败 (file_id: {file_id}): {str(e)}")
            return None
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        if not self.is_connected():
            return {"connected": False}
        
        try:
            history_count = await self.history_collection.count_documents({})
            files_count = await self.files_collection.count_documents({})
            groups_count = await self.gallery_groups_collection.count_documents({})
            images_count = await self.gallery_images_collection.count_documents({})
            
            # 获取最近的任务
            recent_task = await self.history_collection.find_one(
                {},
                {"_id": 0, "task_id": 1, "created_at": 1},
                sort=[("created_at", -1)]
            )
            
            return {
                "connected": True,
                "database": self.database_name,
                "history_tasks_count": history_count,
                "files_count": files_count,
                "gallery_groups_count": groups_count,
                "gallery_images_count": images_count,
                "most_recent_task": recent_task
            }
            
        except Exception as e:
            logger.error(f"获取数据库统计信息失败: {str(e)}")
            return {"connected": True, "error": str(e)}


# 全局数据库服务实例
db_service: Optional[DatabaseService] = None


async def get_database_service() -> Optional[DatabaseService]:
    """获取数据库服务实例"""
    global db_service
    return db_service


async def init_database_service(config) -> DatabaseService:
    """初始化数据库服务"""
    global db_service
    db_service = DatabaseService(config.MONGODB_URL, config.MONGODB_DATABASE)
    await db_service.connect()
    return db_service


async def close_database_service():
    """关闭数据库服务"""
    global db_service
    if db_service:
        await db_service.disconnect()
        db_service = None
