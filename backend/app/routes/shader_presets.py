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

from app.schemas import ShaderPresetMutationResponse
from app.storage import delete_shader_preset, load_shader_preset, save_shader_preset, shader_preset_path


router = APIRouter(tags=["shader-presets"])

SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]+$")

DEFAULT_SHADER_TEMPLATE = """// 使用 AI 写着色器代码时，请将该完整模板发给 AI，以便 AI 了解 Uniform 约定与结构布局。
//
// ── Uniform 字段（与 JS 写入顺序一致）──────────────────────────────────────
//  u.time               f32   秒 = performance.now()×0.001，范围 [0, +∞)
//  u.immersive          f32   阶跃：聊天标题栏完全展开（headerMorphPhase===full）时为 1.0，否则 0.0
//  u.dpr                f32   devicePixelRatio（最小按 1），常见约 [1.0, 3.0]
//  u.deltaTime          f32   相邻两次实际绘制的时间间隔（秒），常见约 [0.008, 0.033]（120–30fps）
//  u.resolutionCss      vec2  画布 CSS 像素尺寸 (width, height)，来自 clientWidth/Height
//  u.resolutionPhysical vec2  画布物理像素 (canvas.width, canvas.height)
//  u.frameCounter       f32   本次 WebGPU 背景循环启动后已提交的帧计数，从 1 递增
//  u._padMouseAlign     f32   结构对齐填充，运行时恒为 0；着色器勿作语义依赖
//  u.mouseNorm          vec2  相对画布 CSS 盒的归一化指针坐标，分量约在 [0,1]（x 左→右，y 上→下）
//                             未收到 pointermove 前默认为画布中心 (0.5, 0.5)；画布外按分量钳制到 [0,1]
//  u.immersiveBlend     f32   向 immersive 指数平滑的 [0,1]，用于摄像机动画与连续渐变（非阶跃）
//
// ── 运行行为约定 ─────────────────────────────────────────────────────────────
//  · 标签页不可见（document.hidden）时降频绘制约 1 fps；time 仍连续累加（可用于动画）
//  · 本模板用 immersiveBlend 做「右下偏移 → 中心」等效摄像机缓动；片元内勿用阶跃 u.immersive 驱动线宽/粒子（会跳变）
//  · 其余约定见项目根目录 WEBGPU_UNIFORM_CONTRACT.md

struct Uniforms {
  time: f32,
  immersive: f32,
  dpr: f32,
  deltaTime: f32,
  resolutionCss: vec2<f32>,
  resolutionPhysical: vec2<f32>,
  frameCounter: f32,
  _padMouseAlign: f32,
  mouseNorm: vec2<f32>,
  immersiveBlend: f32,
};

@group(0) @binding(0) var<uniform> u: Uniforms;

struct VsOut {
  @builtin(position) position: vec4<f32>,
  @location(0) uv: vec2<f32>,
};

// φ=(1+√5)/2，顶点在单位球面上；a=1/√(1+φ²)，b=φ/√(1+φ²)
const IC_A: f32 = 0.5257311121191336;
const IC_B: f32 = 0.8506508083520399;

const VERTS: array<vec3<f32>, 12> = array<vec3<f32>, 12>(
  vec3<f32>(0.0, IC_A, IC_B),
  vec3<f32>(0.0, -IC_A, IC_B),
  vec3<f32>(0.0, IC_A, -IC_B),
  vec3<f32>(0.0, -IC_A, -IC_B),
  vec3<f32>(IC_A, IC_B, 0.0),
  vec3<f32>(-IC_A, IC_B, 0.0),
  vec3<f32>(IC_A, -IC_B, 0.0),
  vec3<f32>(-IC_A, -IC_B, 0.0),
  vec3<f32>(IC_B, 0.0, IC_A),
  vec3<f32>(-IC_B, 0.0, IC_A),
  vec3<f32>(IC_B, 0.0, -IC_A),
  vec3<f32>(-IC_B, 0.0, -IC_A)
);

const EDGES: array<vec2<u32>, 30> = array<vec2<u32>, 30>(
  vec2<u32>(0u, 1u), vec2<u32>(0u, 4u), vec2<u32>(0u, 5u), vec2<u32>(0u, 8u), vec2<u32>(0u, 9u),
  vec2<u32>(1u, 6u), vec2<u32>(1u, 7u), vec2<u32>(1u, 8u), vec2<u32>(1u, 9u),
  vec2<u32>(2u, 3u), vec2<u32>(2u, 4u), vec2<u32>(2u, 5u), vec2<u32>(2u, 10u), vec2<u32>(2u, 11u),
  vec2<u32>(3u, 6u), vec2<u32>(3u, 7u), vec2<u32>(3u, 10u), vec2<u32>(3u, 11u),
  vec2<u32>(4u, 5u), vec2<u32>(4u, 8u), vec2<u32>(4u, 10u),
  vec2<u32>(5u, 9u), vec2<u32>(5u, 11u),
  vec2<u32>(6u, 7u), vec2<u32>(6u, 8u), vec2<u32>(6u, 10u),
  vec2<u32>(7u, 9u), vec2<u32>(7u, 11u),
  vec2<u32>(8u, 10u), vec2<u32>(9u, 11u)
);

fn hash11(p: vec2<f32>) -> f32 {
  return fract(sin(dot(p, vec2<f32>(127.1, 311.7))) * 43758.5453);
}

fn seg_dist(p: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> f32 {
  let pa = p - a;
  let ba = b - a;
  let len2 = max(dot(ba, ba), 1e-8);
  let h = clamp(dot(pa, ba) / len2, 0.0, 1.0);
  return length(pa - ba * h);
}

fn rot_y(a: f32) -> mat3x3<f32> {
  let c = cos(a);
  let s = sin(a);
  return mat3x3<f32>(
    vec3<f32>(c, 0.0, -s),
    vec3<f32>(0.0, 1.0, 0.0),
    vec3<f32>(s, 0.0, c)
  );
}

fn rot_x(a: f32) -> mat3x3<f32> {
  let c = cos(a);
  let s = sin(a);
  return mat3x3<f32>(
    vec3<f32>(1.0, 0.0, 0.0),
    vec3<f32>(0.0, c, s),
    vec3<f32>(0.0, -s, c)
  );
}

fn hue_rgb(h: f32) -> vec3<f32> {
  let t = fract(h) * 6.28318;
  return vec3<f32>(
    0.5 + 0.5 * cos(t),
    0.5 + 0.5 * cos(t + 2.094395),
    0.5 + 0.5 * cos(t + 4.18879)
  );
}

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
  // 必须读取 u：若仅 vs 不引用 u、且 fs 调试成常量色，WGSL 可能剔除整段 uniform，layout 变为 []，与 JS 的 binding(0) 冲突
  let pad = sin(u.time) * 1e-20;
  out.uv = p * 0.5 + vec2<f32>(0.5, 0.5) + vec2<f32>(pad, pad);
  return out;
}

@fragment
fn fs_main(in: VsOut) -> @location(0) vec4<f32> {
  let uv = in.uv;
  let aspect = u.resolutionCss.x / max(u.resolutionCss.y, 1.0);
  let p_ndc = vec2<f32>((uv.x - 0.5) * aspect, 0.5 - uv.y);

  let blend01 = clamp(u.immersiveBlend, 0.0, 1.0);
  // smoothstep：进/出两端导数连续，避免 ease_out 在 t→0 时过陡与阶跃 immersive 叠加产生「跳入」感
  let t_cam = blend01 * blend01 * (3.0 - 2.0 * blend01);
  let cam_offset_rest = vec2<f32>(0.10, -0.08);
  let p_cam = p_ndc - mix(cam_offset_rest, vec2<f32>(0.0, 0.0), t_cam);

  let mx = (u.mouseNorm.x - 0.5) * 0.65;
  let my = (u.mouseNorm.y - 0.5) * 0.65;
  let rot_speed = 0.18;
  let ry = my + u.time * rot_speed;
  let rx = mx + u.time * rot_speed * 0.4;
  let rot = rot_x(rx) * rot_y(ry);

  let scale = 0.55;
  // 线宽/粒子仅随 immersiveBlend 变化，勿混用阶跃 u.immersive，否则进入沉浸瞬间会跳变
  let line_w = (0.00175 / max(u.dpr, 1.0)) * (1.0 + 0.8 * blend01);
  let px = 1.0 / max(u.resolutionPhysical.y, 1.0);
  let eps = max(px * 0.5, 1e-5);

  var edge_acc = 0.0;
  var z_acc = 0.0;
  var col_edge = vec3<f32>(0.0, 0.0, 0.0);
  let hue_base = fract(u.time * 0.03);

  for (var ei = 0u; ei < 30u; ei = ei + 1u) {
    let e = EDGES[ei];
    let va = rot * (VERTS[e.x] * scale);
    let vb = rot * (VERTS[e.y] * scale);
    let a2 = vec2<f32>(va.x, va.y);
    let b2 = vec2<f32>(vb.x, vb.y);
    let d = seg_dist(p_cam, a2, b2);
    let mid_z = 0.5 * (va.z + vb.z);
    let contrib = line_w / max(d, eps);
    edge_acc += contrib;
    z_acc += mid_z * contrib;
    let ec = hue_rgb(hue_base + f32(ei) / 30.0);
    let e_local = 1.0 - exp(-contrib * 0.42);
    col_edge += ec * e_local;
  }

  let edge_intensity = 1.0 - exp(-edge_acc * 0.38);
  let z_acc_denom = max(edge_acc, 1e-4);
  let z_norm = z_acc / z_acc_denom;
  let cool = clamp(0.5 - z_norm * 0.35, 0.0, 1.0);
  let warm = clamp(0.5 + z_norm * 0.35, 0.0, 1.0);

  // 粒子：每条棱用该棱色相 ec；初速 0，仅重力下落；竖直速度有上限；每棱 6 个 → 总 180
  // cycle_speed 必须与 tau 绑定：age 在 [0,1) 走完一整周期 = PARTICLE_LIFE_SEC 秒，否则 tau 与 d(age)/dt 错配会像「速度累积」
  let PARTICLE_LIFE_SEC = 2.4;
  let GRAVITY_NDC = 0.95;
  let PARTICLE_V_MAX = 0.42;
  let cycle_speed = 1.0 / PARTICLE_LIFE_SEC;
  var p_glow = 0.0;
  var p_col = vec3<f32>(0.0, 0.0, 0.0);
  let part_kernel = max(eps * 1.1, px * 1.4);
  let t_cap = PARTICLE_V_MAX / max(GRAVITY_NDC, 1e-5);

  for (var ei = 0u; ei < 30u; ei = ei + 1u) {
    let e = EDGES[ei];
    let va = rot * (VERTS[e.x] * scale);
    let vb = rot * (VERTS[e.y] * scale);
    let va2 = vec2<f32>(va.x, va.y);
    let vb2 = vec2<f32>(vb.x, vb.y);
    let ec = hue_rgb(hue_base + f32(ei) / 30.0);

    for (var pj = 0u; pj < 6u; pj = pj + 1u) {
      let pid = vec2<f32>(f32(ei), f32(pj));
      let spawn_t = hash11(pid * 1.731 + vec2<f32>(23.1, 17.9));
      let ph = hash11(pid + vec2<f32>(4.2, 0.0));
      let age = fract(u.time * cycle_speed + ph * 17.0);
      let tau = age / max(cycle_speed, 1e-5);
      let fall = select(
        0.5 * GRAVITY_NDC * tau * tau,
        0.5 * GRAVITY_NDC * t_cap * t_cap + PARTICLE_V_MAX * (tau - t_cap),
        tau > t_cap
      );
      // 与棱顶点同一 2D 空间：此处 y 增大朝向屏幕下方（与 p_ndc 的「上正」相反），故下落为 +fall
      let dy = fall;
      let base = mix(va2, vb2, spawn_t);
      let ppos = base + vec2<f32>(0.0, dy);
      let pd = length(p_cam - ppos);
      let fade = pow(1.0 - age, 1.35);
      let pk = 0.48 + 0.32 * blend01;
      let contrib = fade * pk / max(pd, part_kernel);
      p_glow += contrib;
      p_col += ec * contrib;
    }
  }

  let p_w = min(p_glow * 1.15, 1.0);
  let p_mix = p_col / max(p_glow, 1e-4);
  var col = col_edge * (0.24 + 0.22 * warm);
  col += vec3<f32>(0.65, 0.78, 1.0) * cool * edge_intensity * 0.32;
  col += vec3<f32>(1.0, 0.55, 0.25) * warm * edge_intensity * 0.18;
  col += vec3<f32>(1.0, 0.98, 0.92) * (edge_intensity * edge_intensity) * 0.14;
  col += p_mix * p_w * 1.22;

  let boot = smoothstep(0.0, 1.0, min(u.frameCounter / 50.0, 1.0));
  col *= boot;

  return vec4<f32>(clamp(col, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0);
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


@router.post("/shader-presets", response_model=ShaderPresetMutationResponse)
def create_shader_preset() -> ShaderPresetMutationResponse:
    """
    创建一个默认 WGSL 预设文件，并返回生成后的文件名。
    """
    filename = f"{uuid4().hex}.wgsl"
    save_shader_preset(filename, DEFAULT_SHADER_TEMPLATE)
    return ShaderPresetMutationResponse(filename=filename, normalized=True, diagnostics=[])


@router.put("/shader-presets/{filename}", response_model=ShaderPresetMutationResponse)
def update_shader_preset(filename: str, body: ShaderPresetUpdateRequest) -> ShaderPresetMutationResponse:
    """
    覆盖保存指定 WGSL 预设源码。
    """
    path = _validated_shader_preset_name(filename)
    full = shader_preset_path(path.name)
    if not full.exists():
        raise HTTPException(status_code=404, detail="shader preset not found")
    save_shader_preset(path.name, body.source)
    return ShaderPresetMutationResponse(filename=path.name, normalized=True, diagnostics=[])


@router.delete("/shader-presets/{filename}", status_code=204)
def remove_shader_preset(filename: str) -> Response:
    """
    删除指定 WGSL 预设文件。文件已不存在时仍返回 204（幂等）。
    """
    path = _validated_shader_preset_name(filename)
    full = shader_preset_path(path.name)
    if full.exists():
        delete_shader_preset(path.name)
    return Response(status_code=204)
