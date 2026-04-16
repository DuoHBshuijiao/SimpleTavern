/**
 * WebGPU WGSL 编译诊断：与浏览器 getCompilationInfo() 对齐的结构化表示。
 */

export type WgslSeverity = 'error' | 'warning' | 'info'

/** 与浏览器 GPUCompilationMessage 字段对齐（自声明，避免部分 TS 工程缺少 lib.dom 全局） */
export interface WgslCompilationMessageLike {
  readonly message: string
  readonly type: string
  lineNum?: number
  linePos?: number
  length?: number
  offset?: number
}

export interface WgslDiagnostic {
  severity: WgslSeverity
  /** 完整原始消息（含 Tint 附带的行列与上下文） */
  message: string
  /** 1-based 行号；未知时为 0 */
  line: number
  column: number
  length: number
  raw: string
}

function gpuCompilationMessageTypeToSeverity(t: string): WgslSeverity {
  if (t === 'error') return 'error'
  if (t === 'warning') return 'warning'
  return 'info'
}

/** 将单条 GPUCompilationMessage 转为结构化诊断（保留完整 message 文本） */
export function gpuMessageToDiagnostic(msg: WgslCompilationMessageLike): WgslDiagnostic {
  const line =
    typeof msg.lineNum === 'number' && msg.lineNum > 0 ? Math.floor(msg.lineNum) : 0
  const column = typeof msg.linePos === 'number' ? Math.floor(msg.linePos) : 0
  const length = typeof msg.length === 'number' ? Math.floor(msg.length) : 0
  return {
    severity: gpuCompilationMessageTypeToSeverity(msg.type),
    message: msg.message,
    line,
    column,
    length,
    raw: msg.message,
  }
}

export function compilationMessagesToDiagnostics(
  messages: Iterable<WgslCompilationMessageLike>,
): WgslDiagnostic[] {
  return Array.from(messages, gpuMessageToDiagnostic)
}

/** 多条错误完整展示（段落之间空行分隔） */
export function formatDiagnosticsAsText(diagnostics: WgslDiagnostic[]): string {
  return diagnostics.map((d) => d.raw).join('\n\n')
}

export function filterDiagnosticsBySeverity(
  diagnostics: WgslDiagnostic[],
  severity: WgslSeverity,
): WgslDiagnostic[] {
  return diagnostics.filter((d) => d.severity === severity)
}

/** 从诊断列表得到需要高亮的逻辑行号（1-based，去重） */
export function errorLineNumbersFromDiagnostics(
  diagnostics: WgslDiagnostic[],
): number[] {
  const set = new Set<number>()
  for (const d of diagnostics) {
    if (d.severity === 'error' && d.line > 0) set.add(d.line)
  }
  return Array.from(set).sort((a, b) => a - b)
}
