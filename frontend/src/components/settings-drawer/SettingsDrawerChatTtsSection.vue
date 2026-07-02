<script setup lang="ts">
import { computed, inject } from 'vue'
import type { AutoReadScope } from '../../types/models'
import { SETTINGS_DRAWER_CHAT_KEY } from '../../composables/settingsDrawerChatKey'
import ModernSelect from '../ModernSelect.vue'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import TtsVoiceInput from '../TtsVoiceInput.vue'

const chat = inject(SETTINGS_DRAWER_CHAT_KEY)!

const autoReadSlideIndex = computed(() => {
  const scope = (chat.chatDraft?.tts?.autoReadScope ?? 'off') as AutoReadScope
  const options = chat.TTS_AUTO_READ_OPTIONS as Array<{ value: AutoReadScope; label: string }>
  return Math.max(0, options.findIndex((option) => option.value === scope))
})
</script>

<template>
<div class="space-y-3 rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-settings-control-bg)] p-4">
  <div class="flex items-center justify-between gap-3">
    <div>
      <div class="text-sm font-medium text-[var(--color-text-secondary)]">文字转语音</div>
      <p class="mt-1 text-xs text-[var(--color-text-muted)]">
        会话级 TTS 设置挂在世界书之后保存；自动朗读范围使用“角色 / 用户 / 全部”语义。
      </p>
    </div>
    <span
      class="shrink-0 whitespace-nowrap rounded-full px-2 py-1 text-[11px] font-medium"
      :class="chat.globalDraft.ttsEnabled ? 'bg-brand-a20 text-brand' : 'bg-surface-overlay text-[var(--color-text-muted)]'"
    >
      {{ chat.globalDraft.ttsEnabled ? '启用' : '禁用' }}
    </span>
  </div>

  <div
    class="space-y-3"
    :class="chat.globalDraft.ttsEnabled ? '' : 'opacity-55 pointer-events-none select-none'"
  >
    <div v-if="!chat.globalDraft.ttsEnabled" class="rounded-lg border border-dashed border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-2 text-xs text-[var(--color-text-muted)]">
      请先在“全局设置 → 文字转语音（TTS）”里开启 TTS，当前会话配置才会生效。
    </div>

    <div class="space-y-1.5">
      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">TTS 模型</label>
      <ModernSelect
        v-model="chat.chatDraft.tts!.model"
        :selected-preset-id="chat.chatDraft.tts?.presetId ?? null"
        :options="chat.ttsSessionModelOptions"
        searchable
        allow-create
        placeholder="选择 TTS 模型..."
        :disabled="!chat.globalDraft.ttsEnabled || chat.ttsSessionModelOptions.length === 0"
        @select="chat.updateChatTtsModel"
      />
      <p class="text-xs text-[var(--color-text-muted)]">
        先选模型，预设会自动关联到对应的 TTS 服务。
        <span v-if="chat.selectedChatTtsPreset" class="text-brand">当前预设：{{ chat.selectedChatTtsPreset.name }} · {{ chat.formatTtsProviderLabel(chat.selectedChatTtsProvider) }}</span>
      </p>
      <p v-if="chat.ttsSessionModelOptions.length === 0" class="text-xs text-[var(--color-text-muted)]">
        还没有可用的 TTS 模型。请先在 API 预设中把目标预设标记为 TTS 服务并获取模型列表。
      </p>
    </div>

    <div class="space-y-2">
      <div class="text-sm font-medium text-[var(--color-text-secondary)]">自动朗读范围</div>
      <div class="relative inline-flex w-full gap-1 rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted p-1">
        <div
          class="pointer-events-none absolute left-1 top-1 bottom-1 rounded-md bg-brand shadow-sm transition-transform duration-[var(--motion-duration-moderate)] ease-out"
          :style="{
            width: 'calc((100% - 1.25rem) / 4)',
            transform: `translateX(calc(${autoReadSlideIndex} * (100% + 0.25rem)))`,
          }"
        />
        <button
          v-for="option in chat.TTS_AUTO_READ_OPTIONS"
          :key="option.value"
          type="button"
          class="relative z-10 min-h-[2.25rem] flex-1 rounded-md px-2 py-1 text-xs font-medium transition-colors duration-[var(--motion-duration-moderate)] ease-out"
          :class="(chat.chatDraft.tts?.autoReadScope ?? 'off') === option.value ? 'text-[var(--color-on-brand)]' : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'"
          @click="chat.updateChatTtsAutoReadScope(option.value as AutoReadScope)"
        >
          {{ option.label }}
        </button>
      </div>
    </div>

    <div class="space-y-1.5">
      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">朗读间隔（秒）</label>
      <input
        type="number"
        min="0"
        step="0.1"
        class="input w-full"
        :value="chat.chatDraft.tts?.readGapSeconds ?? 0"
        @input="chat.updateChatTtsReadGapSeconds(($event.target as HTMLInputElement).value)"
      />
    </div>

    <div class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3">
      <div class="text-sm font-medium text-[var(--color-text-secondary)]">文本后处理</div>
      <div class="flex flex-wrap gap-4 text-xs text-[var(--color-text-secondary)]">
        <button type="button" class="inline-flex items-center gap-2 transition-colors hover:text-[var(--color-text)]" @click="chat.updateChatTtsPreprocessEnabled(!(chat.chatDraft.tts?.preprocessEnabled === true))">
          <ThemedCheckbox :checked="chat.chatDraft.tts?.preprocessEnabled === true" />
          <span>启用文本后处理</span>
        </button>
        <button type="button" class="inline-flex items-center gap-2 transition-colors hover:text-[var(--color-text)]" :disabled="!(chat.chatDraft.tts?.preprocessEnabled === true)" @click="chat.updateChatTtsInjectEmotionTags(!(chat.chatDraft.tts?.injectEmotionTags === true))">
          <ThemedCheckbox :checked="chat.chatDraft.tts?.injectEmotionTags === true" :disabled="!(chat.chatDraft.tts?.preprocessEnabled === true)" />
          <span>注入英文情绪标签</span>
        </button>
      </div>
      <div v-if="chat.chatDraft.tts?.preprocessEnabled" class="space-y-1.5">
        <label class="block text-xs font-medium text-[var(--color-text-secondary)]">后处理目标语言</label>
        <input
          type="text"
          class="input w-full"
          :value="chat.chatDraft.tts?.preprocessTargetLanguage ?? ''"
          placeholder="例如 简体中文、English（留空则不按语言翻译）"
          @input="chat.updateChatTtsPreprocessTargetLanguage(($event.target as HTMLInputElement).value)"
        />
      </div>
      <ModernSelect
        v-if="chat.chatDraft.tts?.preprocessEnabled"
        v-model="chat.chatDraft.tts!.preprocessModel"
        :selected-preset-id="chat.chatDraft.tts?.preprocessPresetId ?? null"
        :options="chat.ttsPreprocessModelOptions"
        searchable
        allow-create
        placeholder="选择文本后处理模型..."
        :disabled="chat.ttsPreprocessModelOptions.length === 0"
        @select="chat.updateChatTtsPreprocessModel"
      />
      <p class="text-xs text-[var(--color-text-muted)]">
        后处理请求会以 JSON 发送 language、raw_text、inject_emotion_tags；目标语言同时写入提示词占位符。留空则不翻译。模型从普通文本预设里选。若开启「注入语气相关标签」，请确认当前 TTS 模型文档是否支持，否则可能产生异常或怪音。
      </p>
    </div>

    <div class="space-y-2">
      <div class="text-sm font-medium text-[var(--color-text-secondary)]">角色音色</div>
      <div v-if="chat.currentChatCharacterVoiceRows.length" class="space-y-2">
        <div
          v-for="row in chat.currentChatCharacterVoiceRows"
          :key="row.id"
          class="grid items-center gap-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-2 md:grid-cols-[minmax(0,11rem)_1fr]"
        >
          <div class="flex min-h-8 items-center text-xs text-[var(--color-text-secondary)]">{{ row.name }}</div>
          <TtsVoiceInput
            :model-value="chat.getCharacterVoiceValue(row.id)"
            :voices="chat.availableTtsVoices"
            placeholder="输入或下拉选择 voice_id"
            @update:model-value="chat.updateCharacterVoiceValue(row.id, $event)"
          />
        </div>
      </div>
      <div v-else class="text-xs text-[var(--color-text-muted)]">当前会话没有可配置的角色。</div>
    </div>

    <div class="space-y-2">
      <div class="text-sm font-medium text-[var(--color-text-secondary)]">用户音色</div>
      <div v-if="chat.currentChatPersonaVoiceRows.length" class="space-y-2">
        <div
          v-for="row in chat.currentChatPersonaVoiceRows"
          :key="row.id"
          class="grid items-center gap-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-2 md:grid-cols-[minmax(0,11rem)_1fr]"
        >
          <div class="flex min-h-8 items-center text-xs text-[var(--color-text-secondary)]">{{ row.name }}</div>
          <TtsVoiceInput
            :model-value="chat.getPersonaVoiceValue(row.id)"
            :voices="chat.availableTtsVoices"
            placeholder="输入或下拉选择 voice_id"
            @update:model-value="chat.updatePersonaVoiceValue(row.id, $event)"
          />
        </div>
      </div>
      <div
        v-else-if="chat.chat && !chat.chat?.userPersonaId"
        class="text-xs text-[var(--color-text-muted)]"
      >
        当前会话未绑定用户身份，请先在侧栏选择用户身份后再配置音色。
      </div>
      <div v-else class="text-xs text-[var(--color-text-muted)]">当前没有可用的用户身份音色入口。</div>
      <p v-if="chat.availableTtsVoices.length === 0" class="text-xs text-[var(--color-text-muted)]">
        当前预设还没有已拉取的音色列表。你可以回到 API 预设里点击「从 API 获取并筛选」勾选音色，也可以直接手输 voice_id。
      </p>
    </div>
  </div>
</div>
</template>
