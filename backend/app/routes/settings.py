"""
设置管理路由模块

提供全局设置的读取和更新API端点。

主要功能：
    - GET /settings: 获取全局设置
    - PUT /settings: 更新全局设置

主要函数：
    - get_settings: 获取全局设置
    - put_settings: 更新全局设置

文件关系：
    - 被导入：被main.py导入router
    - 导入：导入schemas.py的Settings和storage.py的存储函数
    - 依赖：依赖schemas.py和storage.py
    - 位置：路由层，处理设置相关的HTTP请求
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas import Settings
from app.storage import load_settings, save_settings


router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=Settings)
def get_settings() -> Settings:
    """
    获取全局设置
    
    Returns:
        Settings: 全局设置对象
    """
    return load_settings()


@router.put("/settings", response_model=Settings)
def put_settings(settings: Settings) -> Settings:
    """
    更新全局设置
    
    直接保存到本地文件系统（单用户本地应用）。
    
    Args:
        settings: 新的设置对象
    
    Returns:
        Settings: 保存后的设置对象
    """
    return save_settings(settings)
