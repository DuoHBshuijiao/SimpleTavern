from __future__ import annotations

import base64
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.storage import avatar_path, avatars_dir, delete_avatar, save_avatar

router = APIRouter(tags=["avatars"])


class UploadAvatarRequest(BaseModel):
    """头像上传请求，接受base64编码的图片数据"""
    imageData: str  # base64编码的图片数据（可包含或不包含data:image/...;base64,前缀）
    filename: str | None = None  # 可选，指定文件名


class UploadAvatarResponse(BaseModel):
    filename: str


@router.post("/avatars", response_model=UploadAvatarResponse)
def upload_avatar(req: UploadAvatarRequest) -> UploadAvatarResponse:
    """上传头像（接受裁剪后的base64图片数据）"""
    try:
        # 处理base64数据
        image_data = req.imageData
        
        # 移除可能存在的data URL前缀
        if "," in image_data:
            header, image_data = image_data.split(",", 1)
            # 从header中提取扩展名
            if "png" in header.lower():
                ext = "png"
            elif "gif" in header.lower():
                ext = "gif"
            elif "webp" in header.lower():
                ext = "webp"
            else:
                ext = "jpg"
        else:
            ext = "png"  # 默认png
        
        # 解码base64
        try:
            data = base64.b64decode(image_data)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 image data")
        
        # 生成文件名
        if req.filename:
            filename = req.filename
        else:
            filename = f"{uuid4().hex}.{ext}"
        
        # 保存文件
        save_avatar(filename, data)
        
        return UploadAvatarResponse(filename=filename)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/avatars/{filename}")
def get_avatar(filename: str) -> FileResponse:
    """获取头像文件"""
    p = avatar_path(filename)
    if not p.exists():
        raise HTTPException(status_code=404, detail="avatar not found")
    
    # 根据扩展名设置媒体类型
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
    """删除头像文件"""
    delete_avatar(filename)
    return {"ok": True}

