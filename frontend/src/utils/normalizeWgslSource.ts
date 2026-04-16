/**
 * 规范化 WGSL 源码供 WebGPU 解析（须与后端 `normalize_wgsl_source` 行为一致）。
 * - 去除开头的 BOM (U+FEFF)
 * - CRLF → LF
 * - NBSP 等「类空格」Unicode → ASCII 空格 (U+0020)
 */
export function normalizeWgslSource(source: string): string {
  let s = source
  if (s.length > 0 && s.charCodeAt(0) === 0xfeff) {
    s = s.slice(1)
  }
  s = s.replace(/\r\n/g, '\n')
  // NBSP、窄不换行、数字空格、U+2000–U+200A、U+3000 等（与 Python 一致）
  s = s.replace(/[\u00A0\u1680\u2000-\u200A\u202F\u205F\u3000]/g, ' ')
  return s
}
