# WebGPU Uniform Contract (MVP)

本文件定义 SimpleTavern 的 WebGPU 背景 MVP 运行契约，用于主界面与预设编辑的一致性。

## 安全上下文与访问方式（页面 API 与 chrome://gpu 可能不一致）

- **`chrome://gpu` / Graphics Feature Status** 反映的是浏览器进程级 GPU 能力；**页面内**是否可用 `navigator.gpu` 还受**安全上下文**约束。
- 请使用 **`https`**，或 **`http://localhost` / `http://127.0.0.1`** 访问前端（开发时 Vite 同理）。
- 若使用 **`http://<局域网IP>:端口`**（非 localhost），通常属于**非安全上下文**，`navigator.gpu` 可能为 `undefined`，与「WebGPU: Hardware accelerated」的进程级报告无关。
- 若页面内提示与上述不符，可在同一页面的开发者工具控制台检查 `window.isSecureContext` 与 `navigator.gpu`。

## 运行行为约定

- WebGPU 不可用时：仅提示并回退到图片背景（若有）或主题底色，不自动修改 `webgpuBackgroundEnabled` 持久化值。
- 点击“运行（仅本次）”：仅写入运行态覆盖（session 内存态），不触发 `/api/settings` 持久化。
- 仅“保存设置”会持久化 `webgpuBackgroundEnabled`、`webgpuBackgroundPresets`、`webgpuBackgroundActivePresetId`。
- 标签页不可见（`document.hidden === true`）时采用降频绘制策略（约 1fps），并继续更新时间参数。
- 预览草稿只用内存 / `sessionStorage`，不写磁盘临时目录。

## Uniform 结构体（WGSL）

MVP 官方模板字段如下（按顺序）：

```wgsl
struct Uniforms {
  time: f32;
  immersive: f32;
  dpr: f32;
  deltaTime: f32;
  resolutionCss: vec2<f32>;
  resolutionPhysical: vec2<f32>;
  frameCounter: f32;
  // uniform 地址空间中 vec2 需 8 字节对齐：frameCounter 后补 4 字节再跟 mouseNorm
  _padMouseAlign: f32;
  mouseNorm: vec2<f32>;
  immersiveBlend: f32;
};
```

绑定位置固定：

```wgsl
@group(0) @binding(0) var<uniform> u: Uniforms;
```

## 字段语义

- `time`: `performance.now() * 0.001`，单位秒。
- `immersive`: 当且仅当聊天页 `headerMorphPhase === "full"` 时为 `1.0`，否则 `0.0`。
- `dpr`: `devicePixelRatio`（最小按 `1` 处理）。
- `deltaTime`: 相邻两次实际绘制的时间间隔（秒）。
- `resolutionCss`: `vec2(cssWidth, cssHeight)`，对应 `canvas.clientWidth/clientHeight`。
- `resolutionPhysical`: `vec2(canvas.width, canvas.height)`，对应 backing store 物理像素。
- `frameCounter`: 自本次 WebGPU 背景循环启动以来已提交的绘制帧计数（从 1 递增）。
- `_padMouseAlign`: 对齐填充，运行时恒为 `0`，着色器中勿作语义依赖。
- `mouseNorm`: 相对画布 **CSS 盒**（`getBoundingClientRect()`）的归一化指针坐标，分量约在 `[0,1]`（`x` 左→右，`y` 上→下，与 DOM 一致）；指针在画布外时按分量钳制到 `[0,1]`。从未收到 `pointermove` 前默认为画布中心 `(0.5, 0.5)`。
- `immersiveBlend`: 向 `immersive`（0 或 1）指数平滑后的值，范围约 `[0,1]`，用于摄像机动画、渐变等需**连续时间**的效果；`immersive` 本身仍为阶跃。

## 演进规则

- 新字段仅允许追加到 `Uniforms` 尾部。
- JS `Float32Array` 写入时，未使用的尾部槽位统一填 `0`，保证旧模板在结构扩展后仍可运行。
- 不强制 `uniformVersion`；当编译通过时允许运行。

## 模板要求

用户 WGSL 至少应实现：

- `@vertex fn vs_main(...)`
- `@fragment fn fs_main(...) -> @location(0) vec4<f32>`

并保持 `@group(0) @binding(0)` 的 `Uniforms` 绑定声明与字段布局契约一致。

调试时若将片元改为纯色且不再读取 `u`，编译器可能剔除未使用的 `var<uniform> u`，导致 `layout: 'auto'` 下 bind group 布局为空，与运行时仍写入的 `binding(0)` 冲突。默认模板在顶点阶段读取 `u.time`（亚像素偏移）以避免该问题。
