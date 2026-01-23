"""
头像管理路由模块

提供头像文件的上传、获取和删除API端点。

主要功能：
    - POST /avatars: 上传头像（接受base64编码的图片数据）
    - GET /avatars/{filename}: 获取头像文件
    - DELETE /avatars/{filename}: 删除头像文件

主要函数：
    - upload_avatar: 上传头像
    - get_avatar: 获取头像文件
    - remove_avatar: 删除头像文件

文件关系：
    - 被导入：被main.py导入router
    - 导入：导入storage.py的头像管理函数
    - 依赖：依赖storage.py
    - 位置：路由层，处理头像相关的HTTP请求
"""

from __future__ import annotations

import base64
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.storage import avatar_path, avatars_dir, delete_avatar, save_avatar

router = APIRouter(tags=["avatars"])


class UploadAvatarRequest(BaseModel):
    """
    头像上传请求模型
    
    接受base64编码的图片数据，支持data URL格式。
    
    主要属性：
        imageData: base64编码的图片数据，可包含或不包含data:image/...;base64,前缀
        filename: 可选的文件名，如果不提供则自动生成UUID
    """
    imageData: str
    filename: str | None = None


class UploadAvatarResponse(BaseModel):
    """
    头像上传响应模型
    
    主要属性：
        filename: 保存后的文件名
    """
    filename: str


@router.post("/avatars", response_model=UploadAvatarResponse)
def upload_avatar(req: UploadAvatarRequest) -> UploadAvatarResponse:
    """
    上传头像
    
    接受base64编码的图片数据，支持data URL格式。
    自动识别图片格式（png/jpg/gif/webp），如果未指定文件名则生成UUID文件名。
    
    Args:
        req: 上传请求，包含base64图片数据和可选文件名
    
    Returns:
        UploadAvatarResponse: 包含保存后的文件名
    
    Raises:
        HTTPException: base64解码失败或保存失败时抛出400或500错误
    """
    try:
        image_data = req.imageData
        
        if "," in image_data:
            header, image_data = image_data.split(",", 1)
            if "png" in header.lower():
                ext = "png"
            elif "gif" in header.lower():
                ext = "gif"
            elif "webp" in header.lower():
                ext = "webp"
            else:
                ext = "jpg"
        else:
            ext = "png"
        
        try:
            data = base64.b64decode(image_data)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 image data")
        
        if req.filename:
            filename = req.filename
        else:
            filename = f"{uuid4().hex}.{ext}"
        
        save_avatar(filename, data)
        
        return UploadAvatarResponse(filename=filename)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/avatars/{filename}")
def get_avatar(filename: str) -> FileResponse:
    """
    获取头像文件
    
    根据文件扩展名设置正确的媒体类型。
    
    Args:
        filename: 头像文件名
    
    Returns:
        FileResponse: 头像文件响应
    
    Raises:
        HTTPException: 文件不存在时抛出404错误
    """
    p = avatar_path(filename)
    if not p.exists():
        raise HTTPException(status_code=404, detail="avatar not found")
    
    ext = p.suffix.lower()
    media_type_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_type_map.get(ext, "application/octet-stream")
    
    return FileResponse(p, media_type=media_type)


@router.delete("/avatars/{filename}")
def remove_avatar(filename: str) -> dict:
    """
    删除头像文件
    
    Args:
        filename: 头像文件名
    
    Returns:
        dict: 成功响应 {"ok": True}
    """
    delete_avatar(filename)
    return {"ok": True}
