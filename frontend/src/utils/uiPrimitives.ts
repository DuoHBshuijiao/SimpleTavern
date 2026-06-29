export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success'
export type ButtonSize = 'xs' | 'sm' | 'md' | 'lg'
export type SurfaceTone = 'card' | 'panel' | 'inset' | 'muted'

export interface ButtonClassOptions {
  variant?: ButtonVariant
  size?: ButtonSize
  iconOnly?: boolean
  loading?: boolean
}

export interface SurfaceClassOptions {
  tone?: SurfaceTone
  interactive?: boolean
  selected?: boolean
}

const BUTTON_VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: 'btn-primary',
  secondary: 'btn-secondary',
  ghost: 'btn-ghost',
  danger: 'btn-danger',
  success: 'btn-success',
}

const BUTTON_SIZE_CLASS: Record<ButtonSize, string> = {
  xs: 'btn-xs',
  sm: 'btn-sm',
  md: '',
  lg: 'btn-lg',
}

const SURFACE_TONE_CLASS: Record<SurfaceTone, string> = {
  card: 'surface-card',
  panel: 'surface-panel',
  inset: 'surface-inset',
  muted: 'surface-muted',
}

export function buttonClass(options: ButtonClassOptions = {}): string {
  const variant = options.variant ?? 'secondary'
  const size = options.size ?? 'md'
  return [
    'btn',
    BUTTON_VARIANT_CLASS[variant],
    BUTTON_SIZE_CLASS[size],
    options.iconOnly ? 'btn-icon' : '',
    options.loading ? 'btn-loading' : '',
  ]
    .filter(Boolean)
    .join(' ')
}

export function surfaceClass(options: SurfaceClassOptions = {}): string {
  const tone = options.tone ?? 'card'
  return [
    SURFACE_TONE_CLASS[tone],
    options.interactive ? 'interactive-surface' : '',
    options.selected ? 'surface-selected' : '',
  ]
    .filter(Boolean)
    .join(' ')
}

export function dialogAria(titleId: string, describedBy?: string) {
  return {
    role: 'dialog',
    'aria-modal': 'true',
    'aria-labelledby': titleId,
    ...(describedBy ? { 'aria-describedby': describedBy } : {}),
  } as const
}
