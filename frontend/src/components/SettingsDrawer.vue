<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import {
  NButton,
  NDivider,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSelect,
  NSpace,
  NSwitch,
  NTabPane,
  NTabs,
  NText,
} from 'naive-ui'

import type { Chat, ChatOverrides, Settings } from '../types/models'
import { useChatsStore, useSettingsStore } from '../stores'

const props = defineProps<{
  show: boolean
  chat: Chat | null
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
}>()

const settingsStore = useSettingsStore()
const chatsStore = useChatsStore()

const tab = ref<'global' | 'chat'>('global')

const globalDraft = ref<Settings | null>(null)
const chatDraft = ref<ChatOverrides | null>(null)

const modelOptions = ref<{ label: string; value: string }[]>([])
const modelsLoading = ref(false)

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T
}

function ensureOverrides(v?: Partial<ChatOverrides> | null): ChatOverrides {
  return {
    prompt: v?.prompt ?? null,
    params: {
      model: v?.params?.model ?? null,
      temperature: v?.params?.temperature ?? null,
      top_p: v?.params?.top_p ?? null,
      max_tokens: v?.params?.max_tokens ?? null,
    },
  }
}

watch(
  () => props.show,
  async (open) => {
    if (!open) return
    if (!settingsStore.settings) await settingsStore.load()
    const s = clone(settingsStore.settings!)
    // 确保 streamEnabled 存在
    if (s.streamEnabled === undefined) {
      s.streamEnabled = true
    }
    globalDraft.value = s
    chatDraft.value = props.chat ? clone(props.chat.overrides) : ensureOverrides()
  },
)

async function refreshModels() {
  modelOptions.value = []
  modelsLoading.value = true
  try {
    const r = await fetch('/api/llm/models')
    if (!r.ok) throw new Error(await r.text())
    const models = (await r.json()) as string[]
    modelOptions.value = models.map((m) => ({ label: m, value: m }))
  } catch {
    modelOptions.value = []
  } finally {
    modelsLoading.value = false
  }
}

const showModelSelect = computed(() => modelOptions.value.length > 0)

async function saveGlobal() {
  if (!globalDraft.value) return
  await settingsStore.save(globalDraft.value)
}

async function saveChatOverrides() {
  if (!props.chat || !chatDraft.value) return
  await chatsStore.updateOverrides(props.chat.id, chatDraft.value)
}
</script>

<template>
  <NDrawer :show="show" width="520" placement="right" @update:show="(v) => emit('update:show', v)">
    <NDrawerContent title="高级设置" closable>
      <NTabs v-model:value="tab" type="line" animated>
        <NTabPane name="global" tab="全局">
          <div v-if="!globalDraft" style="padding: 20px; text-align: center"><NText depth="3">加载中…</NText></div>
          <NForm v-else label-placement="top">
            <NSpace vertical size="large">
              <NText depth="3">这些设置会写入本地 `data/settings.json`（API Key 明文）。</NText>

              <NFormItem label="流式传输">
                <NSpace align="center">
                  <NSwitch v-model:value="globalDraft.streamEnabled" />
                  <NText depth="3" style="font-size: 12px">
                    {{ globalDraft.streamEnabled ? '已开启：逐字显示回复' : '已关闭：等待完整回复后显示' }}
                  </NText>
                </NSpace>
              </NFormItem>

              <NFormItem label="Base URL（OpenAI 兼容）">
                <NInput v-model:value="globalDraft.llm.baseUrl" placeholder="https://api.openai.com" />
              </NFormItem>
              <NFormItem label="API Key（明文存储）">
                <NInput v-model:value="globalDraft.llm.apiKey" type="password" show-password-on="click" />
              </NFormItem>
              <NFormItem label="默认模型">
                <NSpace vertical style="width: 100%">
                  <NSpace>
                    <NInput v-model:value="globalDraft.llm.defaultModel" placeholder="留空，或手动输入模型名" style="width: 280px" />
                    <NButton :loading="modelsLoading" @click="refreshModels">获取模型列表</NButton>
                  </NSpace>
                  <NSelect
                    v-if="showModelSelect"
                    v-model:value="globalDraft.llm.defaultModel"
                    :options="modelOptions"
                    :loading="modelsLoading"
                    filterable
                    clearable
                    placeholder="从API获取的模型中选择..."
                  />
                </NSpace>
              </NFormItem>
              <NFormItem label="全局高级提示词（globalSystem）">
                <NInput
                  v-model:value="globalDraft.prompts.globalSystem"
                  type="textarea"
                  :autosize="{ minRows: 4, maxRows: 12 }"
                />
              </NFormItem>
              <NDivider />
              <NFormItem label="Temperature（默认，留空则不传）">
                <NInputNumber
                  v-model:value="globalDraft.generationDefaults.temperature"
                  :min="0"
                  :max="2"
                  :step="0.1"
                  placeholder="留空"
                  clearable
                  style="width: 200px"
                />
              </NFormItem>
              <NFormItem label="Top_p（默认，留空则不传）">
                <NInputNumber
                  v-model:value="globalDraft.generationDefaults.top_p"
                  :min="0"
                  :max="1"
                  :step="0.1"
                  placeholder="留空"
                  clearable
                  style="width: 200px"
                />
              </NFormItem>
              <NFormItem label="Max tokens（默认）">
                <NInputNumber v-model:value="globalDraft.generationDefaults.max_tokens" :min="1" :step="64" clearable />
              </NFormItem>
              <NSpace justify="end">
                <NButton type="primary" @click="saveGlobal">保存全局</NButton>
              </NSpace>
            </NSpace>
          </NForm>
        </NTabPane>

        <NTabPane name="chat" tab="当前会话">
          <div v-if="!chat" style="padding: 20px; text-align: center"><NText depth="3">请先选择一个会话。</NText></div>
          <NForm v-else-if="chatDraft && globalDraft" label-placement="top">
            <NSpace vertical size="large">
              <NText depth="3">这些覆盖会写入当前会话对应的 chat.json。</NText>
              <NFormItem label="会话高级提示词（overrides.prompt）">
                <NInput v-model:value="chatDraft.prompt" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }" />
              </NFormItem>
              <NFormItem label="模型（覆盖）">
                <NSpace vertical style="width: 100%">
                  <NInput v-model:value="chatDraft.params.model" placeholder="留空则用全局默认" />
                  <NSelect
                    v-if="showModelSelect"
                    v-model:value="chatDraft.params.model"
                    :options="modelOptions"
                    :loading="modelsLoading"
                    clearable
                    filterable
                    placeholder="从API获取的模型中选择..."
                  />
                </NSpace>
              </NFormItem>
              <NFormItem label="Temperature（覆盖，留空则用全局）">
                <NInputNumber
                  v-model:value="chatDraft.params.temperature"
                  :min="0"
                  :max="2"
                  :step="0.1"
                  placeholder="留空"
                  clearable
                  style="width: 200px"
                />
              </NFormItem>
              <NFormItem label="Top_p（覆盖，留空则用全局）">
                <NInputNumber
                  v-model:value="chatDraft.params.top_p"
                  :min="0"
                  :max="1"
                  :step="0.1"
                  placeholder="留空"
                  clearable
                  style="width: 200px"
                />
              </NFormItem>
              <NFormItem label="Max tokens（覆盖）">
                <NInputNumber v-model:value="chatDraft.params.max_tokens" :min="1" :step="64" clearable />
              </NFormItem>
              <NSpace justify="end">
                <NButton type="primary" @click="saveChatOverrides(); saveGlobal()">保存</NButton>
              </NSpace>
            </NSpace>
          </NForm>
        </NTabPane>
      </NTabs>
    </NDrawerContent>
  </NDrawer>
</template>
