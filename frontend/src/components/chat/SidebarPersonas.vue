<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from 'vue'
import { ChevronDown, Pencil, Trash2, UserRound } from 'lucide-vue-next'
import type { UserPersona } from '../../types/models'
import { usePreferHoverChrome } from '../../composables/usePreferHoverChrome'
import ModernAvatar from '../ModernAvatar.vue'

const props = defineProps<{
  personas: UserPersona[]
  selectedPersonaId: string | null
  sidebar: HTMLElement | null
  collapsed: boolean
  confirmingDelete: boolean
}>()

const emit = defineEmits<{
  create: []
  select: [id: string]
  edit: [persona: UserPersona]
  remove: [persona: UserPersona, target: HTMLElement]
}>()

const { preferHoverChrome } = usePreferHoverChrome()
const open = ref(false)
const trigger = ref<HTMLButtonElement | null>(null)
const panel = ref<HTMLElement | null>(null)
const panelId = useId()
const position = ref<Record<string, string>>({})
const selected = computed(() => props.personas.find(persona => persona.id === props.selectedPersonaId))

function positionPanel() {
  if (!props.sidebar || !trigger.value) return
  const sidebar = props.sidebar.getBoundingClientRect()
  const card = trigger.value.getBoundingClientRect()
  position.value = {
    left: `${sidebar.left}px`,
    top: `${card.bottom}px`,
    width: `${sidebar.width}px`,
    '--persona-available-height': `${Math.max(0, window.innerHeight - card.bottom - 12)}px`,
    '--persona-origin-scale': String(card.width / sidebar.width),
  }
}

function close(restoreFocus = false) {
  open.value = false
  if (restoreFocus) trigger.value?.focus({ preventScroll: true })
}

async function toggle(event: MouseEvent) {
  if (open.value) {
    close()
    return
  }
  positionPanel()
  open.value = true
  if (event.detail === 0) {
    await nextTick()
    if (open.value) focusFirstChoice()
  }
}

function focusFirstChoice() {
  panel.value?.querySelector<HTMLButtonElement>('.sidebar-persona-choice')?.focus({ preventScroll: true })
}

function enterPanelFromTrigger(event: KeyboardEvent) {
  if (!open.value) return
  if (event.shiftKey) {
    close()
    return
  }
  event.preventDefault()
  focusFirstChoice()
}

function selectPersona(id: string) {
  close(true)
  emit('select', id)
}

function editPersona(persona: UserPersona) {
  close(true)
  emit('edit', persona)
}

watch(() => props.collapsed || !props.personas.length, (unavailable) => {
  if (unavailable) close()
})

watch(open, (isOpen, _, onCleanup) => {
  if (!isOpen) return

  function onOutsidePointer(event: PointerEvent) {
    if (!(event.target instanceof Element)) return
    if (panel.value?.contains(event.target) || trigger.value?.contains(event.target)) return
    if (props.confirmingDelete && event.target.closest('.popconfirm')) return
    close()
  }

  function onEscape(event: KeyboardEvent) {
    if (event.key !== 'Escape' || props.confirmingDelete) return
    event.preventDefault()
    event.stopImmediatePropagation()
    close(true)
  }

  document.addEventListener('pointerdown', onOutsidePointer, true)
  document.addEventListener('keydown', onEscape, true)
  window.addEventListener('resize', positionPanel)
  const observer = new ResizeObserver(positionPanel)
  if (props.sidebar) observer.observe(props.sidebar)
  if (trigger.value) observer.observe(trigger.value)
  onCleanup(() => {
    document.removeEventListener('pointerdown', onOutsidePointer, true)
    document.removeEventListener('keydown', onEscape, true)
    window.removeEventListener('resize', positionPanel)
    observer.disconnect()
  })
})

function onPanelTab(event: KeyboardEvent) {
  const contents = panel.value?.querySelectorAll('button')
  if (!contents?.length || props.confirmingDelete) return
  const edge = event.shiftKey ? contents[0] : contents[contents.length - 1]
  if (event.target === edge) {
    event.preventDefault()
    close(true)
  }
}
</script>

<template>
  <section class="bg-[var(--color-sidebar-sandwich-outer)] border-b border-[var(--color-border-subtle)] shrink-0">
    <div class="flex items-center justify-between mb-3 px-4 pt-4">
      <span class="text-xs text-[var(--color-text-secondary)]">我的身份</span>
      <button type="button" class="btn btn-xs btn-ghost text-brand" aria-label="新建身份" @click="emit('create')">
        + 新建
      </button>
    </div>
    <div class="px-4 pb-4">
      <button
        v-if="personas.length"
        ref="trigger"
        type="button"
        class="sidebar-persona-card settings-item settings-item--selected flex w-full cursor-pointer items-center gap-3 p-2 text-left"
        aria-haspopup="dialog"
        :aria-expanded="open"
        :aria-controls="open ? panelId : undefined"
        :aria-label="selected ? `切换身份，当前为${selected.name}` : '选择身份'"
        @click="toggle"
        @keydown.tab="enterPanelFromTrigger"
      >
        <ModernAvatar v-if="selected" :src="selected.avatar ? `/api/avatars/${selected.avatar}` : null" :display="selected.avatarDisplay" :name="selected.name" :size="36" aspect="1" />
        <UserRound v-else class="m-2 h-5 w-5 shrink-0 text-[var(--color-text-muted)]" aria-hidden="true" />
        <span class="min-w-0 flex-1 truncate text-sm text-brand">{{ selected?.name || '选择身份' }}</span>
        <ChevronDown class="mr-2 h-3.5 w-3.5 shrink-0 text-[var(--color-text-secondary)] transition-transform" :class="{ 'rotate-180': open }" aria-hidden="true" />
      </button>
      <p v-else class="my-2 text-center text-xs text-[var(--color-text-muted)]">点击上方新建创建你的第一个身份</p>
    </div>

    <Teleport to="body">
      <Transition name="sidebar-personas">
        <div v-if="open" :style="position" class="sidebar-persona-layer fixed z-floating">
          <section
            :id="panelId"
            ref="panel"
            class="sidebar-persona-surface sidebar-scroll-region"
            role="dialog"
            aria-label="切换身份"
            @keydown.tab="onPanelTab"
          >
            <ul class="sidebar-persona-list sidebar-scrollbar custom-scrollbar">
              <li
                v-for="persona in personas"
                :key="persona.id"
                class="sidebar-persona-card group settings-item flex items-center gap-1 p-2"
                :class="persona.id === selectedPersonaId ? 'settings-item--selected' : 'hover:bg-surface-hover'"
              >
                <button
                  type="button"
                  class="sidebar-persona-choice flex min-w-0 flex-1 cursor-pointer items-center gap-3 rounded-lg text-left"
                  :aria-current="persona.id === selectedPersonaId ? 'true' : undefined"
                  :title="persona.name"
                  @click="selectPersona(persona.id)"
                >
                  <ModernAvatar :src="persona.avatar ? `/api/avatars/${persona.avatar}` : null" :display="persona.avatarDisplay" :name="persona.name" :size="36" aspect="1" />
                  <span class="truncate text-sm" :class="persona.id === selectedPersonaId ? 'text-brand' : 'text-[var(--color-text-secondary)]'">{{ persona.name }}</span>
                </button>
                <div
                  class="sidebar-persona-capsule flex shrink-0 gap-1 rounded-lg bg-[var(--color-surface-inset)] p-0.5 transition-opacity"
                  :class="preferHoverChrome ? 'opacity-0 group-hover:opacity-100' : 'opacity-100'"
                >
                  <button type="button" class="icon-button p-1" :aria-label="`编辑身份 ${persona.name}`" title="编辑身份" @click="editPersona(persona)">
                    <Pencil class="h-3.5 w-3.5" />
                  </button>
                  <button type="button" class="icon-button p-1 hover:text-error" :aria-label="`删除身份 ${persona.name}`" title="删除身份" @click="emit('remove', persona, $event.currentTarget as HTMLElement)">
                    <Trash2 class="h-3.5 w-3.5" />
                  </button>
                </div>
              </li>
            </ul>
          </section>
        </div>
      </Transition>
    </Teleport>
  </section>
</template>

<style scoped>
.sidebar-persona-card {
  block-size: 3.25rem;
}

.sidebar-persona-layer {
  --persona-row-height: 3.25rem;
  --persona-row-gap: 0.5rem;
  --persona-list-padding: 0.75rem;
  padding-top: 4px;
  clip-path: inset(0 -3rem -3rem);
}

.sidebar-persona-surface {
  padding-block: var(--persona-list-padding);
  background-color: var(--color-surface);
  background-image: linear-gradient(var(--color-popover-surface), var(--color-popover-surface));
  border: 1px solid var(--color-glass-border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-glass-popover);
  transform-origin: top center;
}

.sidebar-persona-list {
  display: flex;
  flex-direction: column;
  gap: var(--persona-row-gap);
  margin: 0;
  padding-inline: calc(1rem - 1px);
  max-block-size: min(
    calc(5 * var(--persona-row-height) + 4 * var(--persona-row-gap)),
    max(0px, var(--persona-available-height) - 6px - 2 * var(--persona-list-padding))
  );
  overflow-y: auto;
  overscroll-behavior: contain;
}

.sidebar-persona-list > li {
  flex: none;
}

:root[data-color-scheme] button.sidebar-persona-card:focus-visible,
:root[data-color-scheme] button.sidebar-persona-choice:focus-visible {
  outline: 2px solid var(--color-focus-ring);
  outline-offset: -2px;
  background-image: none;
}

.sidebar-persona-card:has(:focus-visible) .sidebar-persona-capsule {
  opacity: 1;
}

.sidebar-personas-enter-active {
  transition: clip-path 340ms var(--ease-out-product);
}

.sidebar-personas-enter-active .sidebar-persona-surface {
  transition: transform 340ms var(--ease-out-product);
}

.sidebar-personas-leave-active {
  pointer-events: none;
  transition: clip-path 230ms cubic-bezier(0.4, 0, 0.8, 0.3);
}

.sidebar-personas-leave-active .sidebar-persona-surface {
  transition: transform 230ms cubic-bezier(0.4, 0, 0.8, 0.3);
}

.sidebar-personas-enter-from,
.sidebar-personas-leave-to {
  clip-path: inset(0 -3rem 100%);
}

.sidebar-personas-enter-from .sidebar-persona-surface,
.sidebar-personas-leave-to .sidebar-persona-surface {
  transform: translateY(-0.75rem) scaleX(var(--persona-origin-scale, 0.9));
}

.sidebar-personas-enter-to .sidebar-persona-surface,
.sidebar-personas-leave-from .sidebar-persona-surface {
  transform: translateY(0) scaleX(1);
}

@media (prefers-reduced-motion: reduce) {
  .sidebar-personas-enter-active,
  .sidebar-personas-leave-active,
  .sidebar-personas-enter-active .sidebar-persona-surface,
  .sidebar-personas-leave-active .sidebar-persona-surface {
    transition: none;
  }
}
</style>
