<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import type { AutoReadScope } from '../../types/models'
import { SETTINGS_DRAWER_CHAT_KEY } from '../../composables/settingsDrawerChatKey'
import ModernSelect from '../ModernSelect.vue'
import ThemedRadioTags from '../ThemedRadioTags.vue'
import TtsVoiceInput from '../TtsVoiceInput.vue'
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import SettingsField from './SettingsField.vue'
import SettingsHint from './SettingsHint.vue'
import SettingsSwitch from './SettingsSwitch.vue'

const chat = inject(SETTINGS_DRAWER_CHAT_KEY)!
const open = ref(false)
const isDeepSeek = computed(() => chat.selectedChatTtsProvider === 'deepseek')
const voiceOptions = computed(() => [
  { value: '', label: '选择音色' },
  ...chat.availableTtsVoices.map((voice: { voiceId: string; name: string }) => ({ value: voice.voiceId, label: voice.name })),
])

function voiceSelection(value: string) {
  return voiceOptions.value.some(option => option.value === value) ? value : ''
}

</script>

<template>
<SettingsDrawerGlobalAccordion v-model:open="open" title="文字转语音">
  <div class="settings-group">
    <SettingsHint v-if="!chat.globalDraft.ttsEnabled">请先在“全局设置 → 文字转语音（TTS）”里开启 TTS，当前会话配置才会生效。</SettingsHint>
  <div
    class="flex flex-col gap-4"
    :class="chat.globalDraft.ttsEnabled ? '' : 'opacity-55'"
    :inert="!chat.globalDraft.ttsEnabled"
  >
    <SettingsField label="TTS 预设">
      <ModernSelect
        aria-label="TTS 预设"
        :model-value="chat.selectedChatTtsPreset?.id ?? ''"
        :options="chat.ttsPresetOptions"
        :placeholder="chat.ttsPresetOptions.length ? '选择 TTS 预设...' : '请先添加 TTS 预设'"
        :disabled="chat.ttsPresetOptions.length === 0"
        @update:model-value="chat.updateChatTtsPreset"
      />
    </SettingsField>

    <SettingsField v-if="!isDeepSeek" label="TTS 模型">
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
      <p v-if="chat.selectedChatTtsPreset" class="settings-hint">
        <span>当前预设：{{ chat.selectedChatTtsPreset.name }} · {{ chat.formatTtsProviderLabel(chat.selectedChatTtsProvider) }}</span>
      </p>
      <p v-if="chat.ttsSessionModelOptions.length === 0" class="settings-hint">
        还没有可用的 TTS 模型。请先在 API 预设中把目标预设标记为 TTS 服务并获取模型列表。
      </p>
    </SettingsField>

    <SettingsField label="自动朗读范围">
      <ThemedRadioTags
        :model-value="(chat.chatDraft.tts?.autoReadScope ?? 'off') as AutoReadScope"
        :options="chat.TTS_AUTO_READ_OPTIONS"
        aria-label="自动朗读范围"
        stretch
        @update:model-value="chat.updateChatTtsAutoReadScope"
      />
    </SettingsField>

    <SettingsField label="朗读间隔（秒）">
      <input
        type="number"
        min="0"
        step="0.1"
        class="input w-full"
        :value="chat.chatDraft.tts?.readGapSeconds ?? 0"
        @input="chat.updateChatTtsReadGapSeconds(($event.target as HTMLInputElement).value)"
      />
    </SettingsField>

    <SettingsField label="文本后处理">
      <SettingsSwitch
        label="启用文本后处理"
        :model-value="chat.chatDraft.tts?.preprocessEnabled === true"
        @update:model-value="chat.updateChatTtsPreprocessEnabled"
      />
      <SettingsSwitch
        v-if="!isDeepSeek"
        label="注入英文情绪标签"
        :model-value="chat.chatDraft.tts?.injectEmotionTags === true"
        :disabled="chat.chatDraft.tts?.preprocessEnabled !== true"
        @update:model-value="chat.updateChatTtsInjectEmotionTags"
      />
      <input
        v-if="chat.chatDraft.tts?.preprocessEnabled"
        type="text"
        class="input w-full"
        :value="chat.chatDraft.tts?.preprocessTargetLanguage ?? ''"
        placeholder="翻译成（可选）"
        @input="chat.updateChatTtsPreprocessTargetLanguage(($event.target as HTMLInputElement).value)"
      />
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
      <SettingsHint v-if="!isDeepSeek && chat.chatDraft.tts?.preprocessEnabled && chat.chatDraft.tts?.injectEmotionTags">
        请确认朗读模型支持情绪标签。
      </SettingsHint>
    </SettingsField>

    <SettingsField label="角色音色">
      <div v-if="chat.currentChatCharacterVoiceRows.length" class="space-y-2">
        <div
          v-for="row in chat.currentChatCharacterVoiceRows"
          :key="row.id"
          class="settings-item grid items-center gap-2 md:grid-cols-[minmax(0,11rem)_1fr]"
        >
          <div class="settings-label flex min-h-8 items-center">{{ row.name }}</div>
          <ModernSelect
            v-if="isDeepSeek"
            :aria-label="row.name + '的朗读音色'"
            :model-value="voiceSelection(chat.getCharacterVoiceValue(row.id))"
            :options="voiceOptions"
            placeholder="选择音色"
            @update:model-value="chat.updateCharacterVoiceValue(row.id, $event)"
          />
          <TtsVoiceInput
            v-else
            :model-value="chat.getCharacterVoiceValue(row.id)"
            :voices="chat.availableTtsVoices"
            placeholder="输入或下拉选择 voice_id"
            @update:model-value="chat.updateCharacterVoiceValue(row.id, $event)"
          />
        </div>
      </div>
      <div v-else class="settings-hint">当前会话没有可配置的角色。</div>
    </SettingsField>

    <SettingsField label="用户音色">
      <div v-if="chat.currentChatPersonaVoiceRows.length" class="space-y-2">
        <div
          v-for="row in chat.currentChatPersonaVoiceRows"
          :key="row.id"
          class="settings-item grid items-center gap-2 md:grid-cols-[minmax(0,11rem)_1fr]"
        >
          <div class="settings-label flex min-h-8 items-center">{{ row.name }}</div>
          <ModernSelect
            v-if="isDeepSeek"
            :aria-label="row.name + '的朗读音色'"
            :model-value="voiceSelection(chat.getPersonaVoiceValue(row.id))"
            :options="voiceOptions"
            placeholder="选择音色"
            @update:model-value="chat.updatePersonaVoiceValue(row.id, $event)"
          />
          <TtsVoiceInput
            v-else
            :model-value="chat.getPersonaVoiceValue(row.id)"
            :voices="chat.availableTtsVoices"
            placeholder="输入或下拉选择 voice_id"
            @update:model-value="chat.updatePersonaVoiceValue(row.id, $event)"
          />
        </div>
      </div>
      <div
        v-else-if="chat.chat && !chat.chat?.userPersonaId"
        class="settings-hint"
      >
        当前会话未绑定用户身份，请先在侧栏选择用户身份后再配置音色。
      </div>
      <div v-else class="settings-hint">当前没有可用的用户身份音色入口。</div>
      <p v-if="chat.availableTtsVoices.length === 0" class="settings-hint">
        当前预设还没有已拉取的音色列表。你可以回到 API 预设里点击「从 API 获取并筛选」勾选音色，也可以直接手输 voice_id。
      </p>
    </SettingsField>
  </div>
  </div>
</SettingsDrawerGlobalAccordion>
</template>
