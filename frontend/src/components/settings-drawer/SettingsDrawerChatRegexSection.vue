<script setup lang="ts">
import { inject } from 'vue'
import { SETTINGS_DRAWER_CHAT_KEY } from '../../composables/settingsDrawerChatKey'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import SettingsField from './SettingsField.vue'
import SettingsHint from './SettingsHint.vue'

const chat = inject(SETTINGS_DRAWER_CHAT_KEY)!
</script>

<template>
<SettingsDrawerGlobalAccordion v-model:open="chat.chatRegexAccordionOpen" title="正文正则后处理">
  <div class="settings-group">
    <SettingsHint more="规则定义全局共享；本会话仅保存启用状态。assistant 与 user 正文均参与扫描。">规则全局共享，启用状态按会话保存。</SettingsHint>
    <div class="grid grid-cols-2 gap-3">
      <SettingsField label="默认扫描深度" more="扫描最近多少条 assistant 消息。">
        <input
          v-model.number="chat.chatDraft.contentRegexScanDepthDefault"
          type="number"
          min="1"
          max="50"
          class="input w-full"
        />
      </SettingsField>
      <div class="flex items-start justify-end gap-2 pt-7">
        <button type="button" class="btn btn-xs btn-secondary" @click="chat.toggleAllRegexRules(true)">全部启用</button>
        <button type="button" class="btn btn-xs btn-secondary" @click="chat.toggleAllRegexRules(false)">全部禁用</button>
      </div>
    </div>
    <div class="flex items-center justify-between gap-2">
      <div class="settings-label">共 {{ chat.contentRegexRulesSorted.length }} 条</div>
      <button type="button" class="btn btn-xs btn-secondary" @click="chat.openRegexRuleEditor(null)">新建规则</button>
    </div>
    <div v-if="chat.contentRegexRulesSorted.length === 0" class="settings-hint">
      当前会话暂无正文正则规则。点击「新建规则」开始配置。
    </div>
    <div v-else class="space-y-2">
      <div
        v-for="(rule, idx) in chat.contentRegexRulesSorted"
        :key="rule.id"
        class="settings-item"
        :class="chat.isRegexRuleEnabled(rule) ? 'settings-item--selected' : 'opacity-70'"
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
            <div class="settings-hint mt-1 break-all">{{ rule.pattern }}</div>
            <div class="settings-hint mt-1">
              {{ chat.regexActionLabel(rule.action) }} / {{ chat.regexMatchModeLabel(rule.matchMode) }} / 深度 {{ rule.scanDepthOverride ?? chat.chatDraft.contentRegexScanDepthDefault ?? 50 }}
            </div>
            <div v-if="rule.action === 'extract' || rule.action === 'extract_and_replace'" class="settings-hint mt-1">
              提取来源：{{ chat.regexExtractSourceLabel(rule.extractSource) }}
            </div>
            <div v-if="rule.action === 'replace' || rule.action === 'extract_and_replace'" class="settings-hint mt-1 break-all">
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
</SettingsDrawerGlobalAccordion>
</template>
