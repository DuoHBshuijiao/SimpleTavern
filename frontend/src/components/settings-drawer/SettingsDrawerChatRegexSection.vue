<script setup lang="ts">
import { inject } from 'vue'
import { SETTINGS_DRAWER_CHAT_KEY } from '../../composables/settingsDrawerChatKey'
import ThemedCheckbox from '../ThemedCheckbox.vue'

const chat = inject(SETTINGS_DRAWER_CHAT_KEY)!
</script>

<template>
<div class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay overflow-hidden">
  <button
    type="button"
    class="w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium text-[var(--color-text-secondary)] hover:bg-surface-muted transition-colors"
    @click="chat.chatRegexAccordionOpen = !chat.chatRegexAccordionOpen"
  >
    <span>正文正则后处理（规则全局可见，会话独立启用）</span>
    <span class="text-[var(--color-text-muted)]">{{ chat.chatRegexAccordionOpen ? '收起' : '展开' }}</span>
  </button>
  <div v-show="chat.chatRegexAccordionOpen" class="space-y-3 border-t border-[var(--color-border-subtle)] p-3">
    <div class="text-xs text-[var(--color-text-muted)]">规则定义全局共享；本会话仅保存启用状态。assistant 与 user 正文均参与扫描。</div>
    <div class="grid grid-cols-2 gap-3">
      <div class="space-y-1.5">
        <label class="block text-xs font-medium text-[var(--color-text-secondary)]">默认扫描深度（最近 assistant 条数）</label>
        <input
          v-model.number="chat.chatDraft.contentRegexScanDepthDefault"
          type="number"
          min="1"
          max="50"
          class="input w-full"
        />
      </div>
      <div class="flex items-end justify-end gap-2">
        <button type="button" class="btn btn-xs btn-secondary" @click="chat.toggleAllRegexRules(true)">全部启用</button>
        <button type="button" class="btn btn-xs btn-secondary" @click="chat.toggleAllRegexRules(false)">全部禁用</button>
      </div>
    </div>
    <div class="flex items-center justify-between gap-2">
      <div class="text-xs text-[var(--color-text-muted)]">共 {{ chat.contentRegexRulesSorted.length }} 条</div>
      <button type="button" class="btn btn-sm btn-primary" @click="chat.openRegexRuleEditor(null)">新建规则</button>
    </div>
    <div v-if="chat.contentRegexRulesSorted.length === 0" class="rounded-lg border border-dashed border-[var(--color-border-subtle)] bg-surface-muted p-3 text-xs text-[var(--color-text-muted)]">
      当前会话暂无正文正则规则。点击「新建规则」开始配置。
    </div>
    <div v-else class="space-y-2">
      <div
        v-for="(rule, idx) in chat.contentRegexRulesSorted"
        :key="rule.id"
        class="rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted p-2 interactive-surface"
        :class="chat.isRegexRuleEnabled(rule) ? 'surface-selected border-brand-a40' : 'opacity-70'"
        draggable="true"
        @dragstart="chat.handleRegexRuleDragStart(idx)"
        @dragover="chat.handleRegexRuleDragOver($event, idx)"
        @dragend="chat.handleRegexRuleDragEnd"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0 flex-1 cursor-grab active:cursor-grabbing">
            <div class="text-xs font-medium text-[var(--color-text)] break-all">
              {{ rule.name || rule.pattern.slice(0, 50) }}
              <span v-if="rule._origin === 'character'" class="inline-block text-2xs px-1 py-px rounded-full bg-[var(--color-brand-a15)] text-[var(--color-brand)] align-middle ml-1">角色自带</span>
            </div>
            <div class="mt-1 text-2xs text-[var(--color-text-muted)] break-all">{{ rule.pattern }}</div>
            <div class="mt-1 text-2xs text-[var(--color-text-muted)]">
              {{ chat.regexActionLabel(rule.action) }} / {{ chat.regexMatchModeLabel(rule.matchMode) }} / 深度 {{ rule.scanDepthOverride ?? chat.chatDraft.contentRegexScanDepthDefault ?? 50 }}
            </div>
            <div v-if="rule.action === 'extract' || rule.action === 'extract_and_replace'" class="mt-1 text-2xs text-[var(--color-text-muted)]">
              提取来源：{{ chat.regexExtractSourceLabel(rule.extractSource) }}
            </div>
            <div v-if="rule.action === 'replace' || rule.action === 'extract_and_replace'" class="mt-1 text-2xs text-[var(--color-text-muted)] break-all">
              {{ (rule.replacement || '').slice(0, 80) }}
            </div>
          </div>
          <div class="flex items-center gap-1 shrink-0">
            <ThemedCheckbox
              :checked="chat.isRegexRuleEnabled(rule)"
              @update:checked="(checked) => chat.setRegexRuleEnabled(idx, checked)"
            />
            <button type="button" class="btn btn-xs btn-secondary" @click="chat.openRegexRuleEditor(idx)">编辑</button>
            <button type="button" class="btn btn-xs btn-secondary" @click="chat.moveRegexRule(idx, -1)">上移</button>
            <button type="button" class="btn btn-xs btn-secondary" @click="chat.moveRegexRule(idx, 1)">下移</button>
            <button type="button" class="btn btn-xs btn-secondary" @click="chat.removeRegexRule(idx)">删除</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
</template>
