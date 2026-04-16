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

// ── 基础数学与旋转 ──────────────────────────────────────────────────────────
fn rot_x(a: f32) -> mat3x3<f32> {
  let c = cos(a);
  let s = sin(a);
  return mat3x3<f32>(
    vec3<f32>(1.0, 0.0, 0.0),
    vec3<f32>(0.0, c, s),
    vec3<f32>(0.0, -s, c)
  );
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

// ── 3D 噪声函数 (用于吸积盘流体细节) ───────────────────────────────────────
fn hash31(p3_in: vec3<f32>) -> f32 {
  var p3 = fract(p3_in * 0.1031);
  p3 += dot(p3, p3.zyx + 31.32);
  return fract((p3.x + p3.y) * p3.z);
}

fn noise3(x: vec3<f32>) -> f32 {
  let p = floor(x);
  let f = fract(x);
  let f_m = f * f * (3.0 - 2.0 * f);

  let n000 = hash31(p + vec3<f32>(0.0, 0.0, 0.0));
  let n100 = hash31(p + vec3<f32>(1.0, 0.0, 0.0));
  let n010 = hash31(p + vec3<f32>(0.0, 1.0, 0.0));
  let n110 = hash31(p + vec3<f32>(1.0, 1.0, 0.0));
  let n001 = hash31(p + vec3<f32>(0.0, 0.0, 1.0));
  let n101 = hash31(p + vec3<f32>(1.0, 0.0, 1.0));
  let n011 = hash31(p + vec3<f32>(0.0, 1.0, 1.0));
  let n111 = hash31(p + vec3<f32>(1.0, 1.0, 1.0));

  let nx00 = mix(n000, n100, f_m.x);
  let nx10 = mix(n010, n110, f_m.x);
  let nx01 = mix(n001, n101, f_m.x);
  let nx11 = mix(n011, n111, f_m.x);

  let nxy0 = mix(nx00, nx10, f_m.y);
  let nxy1 = mix(nx01, nx11, f_m.y);

  return mix(nxy0, nxy1, f_m.z);
}

fn fbm(p_in: vec3<f32>) -> f32 {
  var f = 0.0;
  var amp = 0.5;
  var p = p_in;
  for(var i = 0u; i < 4u; i = i + 1u) {
    f += amp * noise3(p);
    p = p * 2.03;
    amp *= 0.5;
  }
  return f;
}

// ── ACES 电影级色调映射 ──────────────────────────────────────────────────────
fn aces_tonemap(color: vec3<f32>) -> vec3<f32> {
  let a = 2.51;
  let b = 0.03;
  let c = 2.43;
  let d = 0.59;
  let e = 0.14;
  return clamp((color * (a * color + b)) / (color * (c * color + d) + e), vec3<f32>(0.0), vec3<f32>(1.0));
}

// ── 宇宙背景 (受引力透镜扭曲) ───────────────────────────────────────────────
fn stars_field(rd: vec3<f32>) -> vec3<f32> {
  var col = vec3<f32>(0.0);

  // 两层不同密度的星场
  for (var layer = 0u; layer < 2u; layer = layer + 1u) {
    let scale = select(80.0, 200.0, layer == 1u);
    let brightness = select(6.0, 3.0, layer == 1u);
    let threshold = select(0.96, 0.98, layer == 1u);

    // 将方向向量投影到球面网格
    let p = rd * scale;
    let cell = floor(p);
    let f = fract(p);

    var min_dist = 1.0;
    var star_rand = 0.0;

    // 检查周围 3x3x3 邻域（确保跨单元边界连续）
    for (var dz = -1; dz <= 1; dz = dz + 1) {
      for (var dy = -1; dy <= 1; dy = dy + 1) {
        for (var dx = -1; dx <= 1; dx = dx + 1) {
          let offset = vec3<f32>(f32(dx), f32(dy), f32(dz));
          let neighbor = cell + offset;

          // 该单元格内星的随机位置
          let h = fract(sin(dot(neighbor, vec3<f32>(127.1, 311.7, 74.7))) * 43758.5453);
          let h2 = fract(sin(dot(neighbor, vec3<f32>(269.5, 183.3, 246.1))) * 43758.5453);
          let h3 = fract(sin(dot(neighbor, vec3<f32>(113.5, 271.9, 124.6))) * 43758.5453);

          let star_pos = offset + vec3<f32>(h, h2, h3) - f;
          let d = length(star_pos);

          if (d < min_dist) {
            min_dist = d;
            star_rand = h;
          }
        }
      }
    }

    // 只有少数单元格实际产生可见星
    if (star_rand > threshold) {
      let star_bright = pow(1.0 - min_dist, 12.0) * brightness;
      let temp = fract(star_rand * 17.3);
      let star_col = mix(
        vec3<f32>(0.7, 0.8, 1.0),  // 蓝白
        vec3<f32>(1.0, 0.85, 0.6), // 暖黄
        temp
      );
      col += star_col * star_bright;
    }
  }

  return col;
}

fn get_background(rd: vec3<f32>) -> vec3<f32> {
  let band = pow(max(1.0 - abs(rd.y) * 2.5, 0.0), 4.0);
  let noise_bg = fbm(rd * 12.0);
  let milky = vec3<f32>(0.05, 0.1, 0.2) * band * noise_bg;

  return milky + stars_field(rd);
}

// ── 顶点着色器 ─────────────────────────────────────────────────────────────
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

// ── 片元着色器 (核心光追逻辑) ──────────────────────────────────────────────
@fragment
fn fs_main(in: VsOut) -> @location(0) vec4<f32> {
  let uv = in.uv;
  let aspect = u.resolutionCss.x / max(u.resolutionCss.y, 1.0);
  let p_ndc = vec2<f32>((uv.x - 0.5) * aspect, 0.5 - uv.y);

  // 1. 相机控制与沉浸式过渡
  let blend01 = clamp(u.immersiveBlend, 0.0, 1.0);
  let cam_dist = mix(9.0, 4.5, smoothstep(0.0, 1.0, blend01)); // 沉浸模式推进镜头

  var ro = vec3<f32>(0.0, 0.8, cam_dist);
  var rd = normalize(vec3<f32>(p_ndc, -1.0));

  // 鼠标与自动旋转
  let mx = (u.mouseNorm.x - 0.5) * 1.256;
  let my = (u.mouseNorm.y - 0.5) * 2.0;
  let rx = rot_x(my - 0.25);
  let ry = rot_y(mx + u.time * 0.08); // 缓慢自转

  ro = ry * rx * ro;
  rd = ry * rx * rd;

  // 2. 物理光线追踪 (Raymarching) 初始化
  var col = vec3<f32>(0.0);
  var transmittance = 1.0;
  let max_steps = 350u;
  var hit_bh = false;

  let rs = 1.0; // 黑洞史瓦西半径
  let disk_inner = 1.35 * rs;
  let disk_outer = 7.0 * rs;

  for(var i = 0u; i < max_steps; i = i + 1u) {
    let r = length(ro);

    // 跌入事件视界
    if (r < rs * 0.98) {
      hit_bh = true;
      break;
    }
    // 飞出感兴趣区域，终止计算
    if (r > 20.0) {
      break;
    }

    // 自适应步长：靠近黑洞时步长极小，以精确模拟引力透镜
    let dt = min(0.04, r * 0.025);

    // 引力透镜效应：光线向质量中心弯曲 (近似广义相对论光子轨道)
    let r3 = r * r * r;
    let force = 1.5 * rs / max(r3, 0.01);
    rd = normalize(rd - ro * force * dt);

    // 3. 吸积盘体积渲染
    let dist_to_plane = abs(ro.y);
    if (dist_to_plane < 1.2 && r > disk_inner && r < disk_outer) {

      // 吸积盘密度分布 (径向和垂直衰减)
      let rad_falloff = smoothstep(disk_inner, disk_inner + 0.8, r) * smoothstep(disk_outer, disk_outer - 3.0, r);
      let height_falloff = exp(-dist_to_plane * (12.0 - r * 0.5));
      let base_density = rad_falloff * height_falloff;

      if (base_density > 0.005) {
        // 开普勒运动：内圈转速极快，外圈慢
        let vel_mag = 2.5 / max(pow(r, 1.5), 0.1);
        let angle = atan2(ro.z, ro.x) - u.time * vel_mag;
        let r_xz = length(ro.xz);
        let pos_rot = vec3<f32>(cos(angle)*r_xz, ro.y, sin(angle)*r_xz);

        // 使用 FBM 注入流体细节
        let n = fbm(pos_rot * 3.5 + vec3<f32>(0.0, u.time * 0.4, u.time * 0.2));
        let density = base_density * smoothstep(0.1, 0.9, n) * 2.5;

        if (density > 0.0) {
          // 相对论多普勒效应 (Relativistic Beaming)
          // 盘体围绕 Y 轴逆时针旋转，计算该点速度方向
          let flow_dir = normalize(vec3<f32>(-ro.z, 0.0, ro.x));
          let doppler = dot(rd, flow_dir);
          let shift = max(1.0 + doppler * 0.75, 0.1); // >1为接近(蓝移变亮), <1为远离(红移变暗)

          // 温度映射：内圈极高温(偏白蓝/紫)，外圈降温(橙红)
          let temp_norm = smoothstep(disk_outer, disk_inner, r);
          var heat_col = mix(vec3<f32>(0.8, 0.15, 0.02), vec3<f32>(0.6, 0.85, 1.0), temp_norm);

          // 应用多普勒频移：极大地增强亮度对比并发生色彩偏移
          let shifted_col = heat_col * vec3<f32>(pow(shift, 0.5), shift, pow(shift, 1.8));
          let emission = shifted_col * density * dt * 15.0 * pow(shift, 2.5);

          // 光线吸收与累加
          let alpha = 1.0 - exp(-density * dt * 4.0);
          col += transmittance * emission;
          transmittance *= (1.0 - alpha);
        }
      }
    }

    // 如果光线已被完全遮挡，提早退出
    if (transmittance < 0.01) {
      break;
    }

    ro += rd * dt;
  }

  // 4. 背景与光环混合
  if (!hit_bh && transmittance > 0.01) {
    // 逃逸的光线最终打在宇宙背景上
    let bg = get_background(rd);
    col += transmittance * bg;
  }

  // 5. 辉光与后处理 (电影级调色)
  col = aces_tonemap(col * 1.2); // 曝光提升后进行ACES压限

  // 边缘暗角 (Vignette)
  let vignette = clamp(1.0 - length(p_ndc) * 0.6, 0.0, 1.0);
  col *= pow(vignette, 0.4);

  // 启动淡入动画
  let boot = smoothstep(0.0, 1.0, min(u.frameCounter / 80.0, 1.0));
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
