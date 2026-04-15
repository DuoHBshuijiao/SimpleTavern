"""
WebGPU 着色器预设路由模块

提供预设 WGSL 文件的创建、读取、更新与删除 API。源码文件保存在 data/shader_presets，
设置侧仅保存元数据（id/name/wgslFile）。
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.storage import delete_shader_preset, load_shader_preset, save_shader_preset, shader_preset_path


router = APIRouter(tags=["shader-presets"])

SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]+$")

DEFAULT_SHADER_TEMPLATE = """struct Uniforms {
  time: f32,
  immersive: f32,
  dpr: f32,
  _pad0: f32,
  resolutionCss: vec2<f32>,
  resolutionPhysical: vec2<f32>,
};

@group(0) @binding(0) var<uniform> u: Uniforms;

struct VsOut {
  @builtin(position) position: vec4<f32>,
  @location(0) uv: vec2<f32>,
};

@vertex
fn vs_main(@builtin(vertex_index) vertexIndex: u32) -> VsOut {
  var pos = array<vec2<f32>, 3>(
    vec2<f32>(-1.0, -3.0),
    vec2<f32>(-1.0, 1.0),
    vec2<f32>(3.0, 1.0)
  );
  var out: VsOut;
  let p = pos[vertexIndex];
  out.position = vec4<f32>(p, 0.0, 1.0);
  out.uv = p * 0.5 + vec2<f32>(0.5, 0.5);
  return out;
}

@fragment
fn fs_main(in: VsOut) -> @location(0) vec4<f32> {
  let uv = in.uv;
  let t = u.time * 0.2;
  let pulse = 0.5 + 0.5 * sin(t * 6.28318);
  let base = vec3<f32>(uv.x, uv.y, 0.22 + 0.35 * pulse);
  let immersiveBoost = mix(0.0, 0.18, clamp(u.immersive, 0.0, 1.0));
  return vec4<f32>(base + vec3<f32>(immersiveBoost), 1.0);
}
"""


class ShaderPresetUpdateRequest(BaseModel):
    source: str


def _validated_shader_preset_name(filename: str) -> Path:
    path = Path(filename)
    if not filename or path.name != filename:
        raise HTTPException(status_code=400, detail="invalid shader preset filename")
    if path.suffix.lower() != ".wgsl" or not SAFE_FILENAME_RE.match(path.name):
        raise HTTPException(status_code=400, detail="invalid shader preset filename")
    return path


@router.get("/shader-presets/{filename}", response_class=PlainTextResponse)
def get_shader_preset(filename: str) -> PlainTextResponse:
    """
    返回 WebGPU 着色器预设源码（WGSL）。
    """
    path = _validated_shader_preset_name(filename)
    full = shader_preset_path(path.name)
    if not full.exists():
        raise HTTPException(status_code=404, detail="shader preset not found")
    source = load_shader_preset(path.name)
    return PlainTextResponse(content=source)


@router.post("/shader-presets")
def create_shader_preset() -> dict[str, str]:
    """
    创建一个默认 WGSL 预设文件，并返回生成后的文件名。
    """
    filename = f"{uuid4().hex}.wgsl"
    save_shader_preset(filename, DEFAULT_SHADER_TEMPLATE)
    return {"filename": filename}


@router.put("/shader-presets/{filename}", status_code=204)
def update_shader_preset(filename: str, body: ShaderPresetUpdateRequest) -> Response:
    """
    覆盖保存指定 WGSL 预设源码。
    """
    path = _validated_shader_preset_name(filename)
    full = shader_preset_path(path.name)
    if not full.exists():
        raise HTTPException(status_code=404, detail="shader preset not found")
    save_shader_preset(path.name, body.source)
    return Response(status_code=204)


@router.delete("/shader-presets/{filename}", status_code=204)
def remove_shader_preset(filename: str) -> Response:
    """
    删除指定 WGSL 预设文件。
    """
    path = _validated_shader_preset_name(filename)
    full = shader_preset_path(path.name)
    if not full.exists():
        raise HTTPException(status_code=404, detail="shader preset not found")
    delete_shader_preset(path.name)
    return Response(status_code=204)
