<script setup lang="ts">
import { inject } from 'vue'
import { Eye, EyeOff, Loader2, X } from 'lucide-vue-next'
import ModernSelect from '../ModernSelect.vue'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import LlmPresetNameCombobox from '../LlmPresetNameCombobox.vue'
import { SETTINGS_DRAWER_PRESETS_KEY } from '../../composables/settingsDrawerPresetsKey'

const presets = inject(SETTINGS_DRAWER_PRESETS_KEY)!
</script>

<template>
  <div class="space-y-6">
            <div v-if="!presets.globalDraft" class="text-center text-[var(--color-text-muted)] py-8">加载中...</div>
            <div v-else class="flex gap-3 items-start">
                <!-- Preset List：sticky 吸附，右侧长表单滚动时左栏留在可视区；列表过长时仅内层滚动 -->
                <div
                  class="sticky top-0 z-10 flex min-w-0 flex-[0_0_min(11rem,34%)] flex-col self-start border-r border-[var(--color-border-subtle)] pr-3"
                >
                    <div :ref="presets.bindPresetListHeader" class="mb-2 flex items-center justify-between gap-1.5">
                        <span class="shrink-0 text-xs text-[var(--color-text-secondary)] sm:text-sm">预设列表</span>
                        <button
                          type="button"
                          class="inline-flex min-h-8 shrink-0 items-center rounded-md bg-brand-a20 px-2 py-0.5 text-2xs font-medium leading-tight text-brand transition-colors hover:bg-brand-a30 touch-manipulation sm:px-2.5 sm:text-xs"
                          @click="presets.createPreset"
                        >
                          + 新建
                        </button>
                    </div>
                    <div
                      class="drawer-scroll space-y-1 overflow-y-auto custom-scrollbar"
                      :style="
                        presets.presetListMaxHeightPx != null
                          ? { maxHeight: `${presets.presetListMaxHeightPx}px` }
                          : { maxHeight: 'min(55vh, 22rem)' }
                      "
                    >
                        <div
                            v-for="(presetItem, idx) in presets.globalDraft!.apiPresets"
                            :key="presetItem.id"
                            draggable="true"
                            class="group relative flex min-h-10 cursor-pointer items-center rounded-lg py-1.5 pl-2 pr-1 text-sm transition-colors"
                            :class="[
                              presets.editingPresetId === presetItem.id ? 'bg-brand-a10 text-brand' : 'text-[var(--color-text-secondary)] hover:bg-surface-muted',
                              presets.apiPresetOrderDraggingIdx === idx ? 'opacity-50 ring-1 ring-brand-a50' : '',
                            ]"
                            @click="presets.editingPresetId = presetItem.id"
                            @dragstart="presets.handleApiPresetOrderDragStart(idx)"
                            @dragover="presets.handleApiPresetOrderDragOver($event, idx)"
                            @dragend="presets.handleApiPresetOrderDragEnd"
                        >
                            <span class="min-w-0 max-w-full truncate pr-7">{{ presetItem.name }}</span>
                            <span
                              v-if="presets.isTtsPreset(presetItem)"
                              draggable="false"
                              class="absolute right-8 top-1.5 text-2xs leading-none text-brand"
                              aria-label="TTS 预设"
                            >t</span>
                            <button
                              type="button"
                              draggable="false"
                              class="absolute right-0.5 top-1/2 inline-flex min-h-8 min-w-8 -translate-y-1/2 items-center justify-center rounded-md text-[var(--color-text-muted)] opacity-0 pointer-events-none touch-manipulation hover:text-error group-hover:pointer-events-auto group-hover:opacity-100"
                              @click.stop="presets.deletePreset(presetItem.id)"
                            >
                              <X class="h-3.5 w-3.5" />
                            </button>
                        </div>
                         <div v-if="presets.globalDraft!.apiPresets.length === 0" class="text-xs text-[var(--color-text-muted)] text-center py-4">无预设</div>
                    </div>
                </div>

                <!-- Preset Editor -->
                <div class="min-w-0 flex-1 flex flex-col" v-if="presets.editingPreset">
                     <div class="min-w-0 space-y-4 pb-4">
                        <div class="space-y-1.5">
                            <div class="flex items-center justify-between gap-3">
                              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">预设名称</label>
                              <button
                                type="button"
                                class="inline-flex items-center gap-2 text-xs text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text)]"
                                @click="presets.setPresetTtsService(presets.editingPreset!, !presets.isTtsPreset(presets.editingPreset))"
                              >
                                <ThemedCheckbox :checked="presets.isTtsPreset(presets.editingPreset)" />
                                <span>作为 TTS 服务</span>
                              </button>
                            </div>
                            <LlmPresetNameCombobox
                              v-if="!presets.isTtsPreset(presets.editingPreset)"
                              v-model="presets.editingPreset!.name"
                              class="block"
                              placeholder="输入或下拉选择供应商/预设名称"
                              @select="presets.onLlmPresetSelect"
                            />
                            <input
                              v-else
                              v-model="presets.editingPreset!.name"
                              type="text"
                              class="input input-sm w-full"
                            />
                            <div v-if="presets.isTtsPreset(presets.editingPreset)" class="space-y-1.5">
                              <label class="block text-2xs font-medium text-[var(--color-text-muted)]">TTS 提供商</label>
                              <ModernSelect
                                :model-value="presets.editingPresetTtsProvider"
                                :options="presets.TTS_PROVIDER_OPTIONS"
                                class="w-full"
                                placeholder="选择 TTS 提供商…"
                                @update:model-value="presets.onEditingPresetTtsProviderChange"
                              />
                            </div>
                        </div>

                         <div class="space-y-1.5">
                            <label class="block text-xs font-medium text-[var(--color-text-secondary)]">API 基础地址</label>
                            <input 
                                v-model="presets.editingPreset!.baseUrl" 
                                type="text" 
                                :placeholder="presets.editingPresetBaseUrlPlaceholder"
                                class="input input-sm w-full"
                            />
                            <p class="text-xs text-[var(--color-text-muted)]">{{ presets.editingPresetBaseUrlHint }}</p>
                        </div>

                        <div class="space-y-1.5">
                            <label class="block text-xs font-medium text-[var(--color-text-secondary)]">API Key</label>
                             <div class="relative">
                                <input 
                                    v-model="presets.editingPreset!.apiKey" 
                                    :type="presets.editingPresetShowApiKey ? 'text' : 'password'"
                                    class="input input-sm w-full pr-8"
                                />
                                <button 
                                    type="button"
                                    class="absolute right-1.5 top-1/2 inline-flex min-h-9 min-w-9 -translate-y-1/2 items-center justify-center rounded-md text-[var(--color-text-muted)] touch-manipulation hover:text-[var(--color-text-secondary)]"
                                    @click="presets.editingPresetShowApiKey = !presets.editingPresetShowApiKey"
                                >
                                    <component :is="presets.editingPresetShowApiKey ? Eye : EyeOff" class="w-4 h-4" />
                                </button>
                             </div>
                        </div>

                        <div class="space-y-2">
                             <div class="flex justify-between items-center gap-2 flex-wrap">
                                 <label class="block text-xs font-medium text-[var(--color-text-secondary)]">模型列表</label>
                                 <button 
                                    class="text-xs text-brand hover:text-brand-hover flex items-center gap-1 shrink-0" 
                                    :disabled="presets.presetModelsLoading"
                                    @click="presets.openModelSelector(presets.editingPreset!)"
                                 >
                                    <Loader2 v-if="presets.presetModelsLoading" class="animate-spin w-3 h-3" />
                                    <span>从 API 获取并筛选</span>
                                 </button>
                             </div>
                             <div
                               v-if="presets.editingPreset!.models.length"
                               class="flex flex-wrap items-center gap-x-1 gap-y-0.5 text-2xs leading-tight text-[var(--color-text-secondary)]"
                             >
                               <button
                                 type="button"
                                 class="min-h-0 rounded px-0.5 py-0 text-brand hover:underline disabled:pointer-events-none disabled:opacity-40"
                                 @click="presets.selectAllPresetModelNames"
                               >
                                 全选
                               </button>
                               <span class="select-none text-[var(--color-text-muted)]">·</span>
                               <button
                                 type="button"
                                 class="min-h-0 rounded px-0.5 py-0 text-brand hover:underline disabled:pointer-events-none disabled:opacity-40"
                                 :disabled="presets.presetModelListSelection.size === 0"
                                 @click="presets.clearPresetModelListSelection"
                               >
                                 清空选择
                               </button>
                               <span class="select-none text-[var(--color-text-muted)]">·</span>
                               <button
                                 type="button"
                                 class="min-h-0 rounded px-0.5 py-0 text-error/90 hover:underline disabled:pointer-events-none disabled:opacity-40"
                                 :disabled="presets.presetModelListSelection.size === 0"
                                 @click="presets.removeSelectedPresetModelNames"
                               >
                                 删除所选
                               </button>
                               <span class="select-none text-[var(--color-text-muted)]">·</span>
                               <button
                                 type="button"
                                 class="min-h-0 rounded px-0.5 py-0 text-error/90 hover:underline disabled:pointer-events-none disabled:opacity-40"
                                 @click="presets.clearAllPresetModelNames"
                               >
                                 清空全部
                               </button>
                             </div>
                             <div class="drawer-scroll bg-surface-overlay border border-[var(--color-border)] rounded-lg p-2 min-h-[100px] max-h-[200px] overflow-y-auto custom-scrollbar">
                                 <div class="flex flex-wrap gap-2">
                                     <div
                                       v-for="(m, idx) in presets.editingPreset!.models"
                                       :key="`${idx}-${m}`"
                                       role="button"
                                       tabindex="0"
                                       class="group relative inline-flex max-w-full cursor-pointer items-center gap-1 rounded-md border border-[var(--color-border-subtle)] bg-surface-overlay/55 px-2 py-1 text-xs text-[var(--color-text-secondary)] backdrop-blur-[var(--glass-blur-soft)] transition-[box-shadow,border-color] hover:bg-surface-overlay/80"
                                       :class="presets.presetModelListSelection.has(m) ? 'ring-1 ring-brand/50 border-brand/35 shadow-[0_0_0_1px_color-mix(in_srgb,var(--color-brand)_25%,transparent)]' : ''"
                                       @click="presets.togglePresetModelListSelection(m)"
                                       @keydown.enter.prevent="presets.togglePresetModelListSelection(m)"
                                       @keydown.space.prevent="presets.togglePresetModelListSelection(m)"
                                     >
                                         <span class="min-w-0 truncate">{{ m }}</span>
                                         <button
                                           type="button"
                                           class="shrink-0 rounded p-0.5 text-[var(--color-text-muted)] opacity-0 transition-opacity hover:text-error group-hover:opacity-100 focus:opacity-100 focus:outline-none"
                                           aria-label="移除此模型"
                                           @click.stop="presets.removeSinglePresetModelAt(idx)"
                                         >
                                          <X class="w-3 h-3" />
                                         </button>
                                     </div>
                                      <div v-if="!presets.editingPreset!.models.length" class="text-xs text-[var(--color-text-muted)] w-full text-center py-4">
                                          点击上方「从 API 获取并筛选」或手动添加
                                      </div>
                                 </div>
                             </div>
                             <!-- 手动添加模型 -->
                              <div class="flex gap-2">
                                 <input 
                                    type="text" 
                                    placeholder="手动输入模型名..."
                                    class="input input-sm flex-1 rounded px-2 py-1 text-xs outline-none"
                                    @keydown.enter="(e) => {
                                        const val = (e.target as HTMLInputElement).value.trim();
                                        if(val && !presets.editingPreset!.models.includes(val)) {
                                            presets.editingPreset!.models.push(val);
                                            (e.target as HTMLInputElement).value = '';
                                        }
                                    }"
                                 />
                              </div>
                        </div>

                        <div v-if="presets.isTtsPreset(presets.editingPreset)" class="space-y-3 rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-settings-control-bg)] p-3">
                          <p class="text-2xs text-[var(--color-text-muted)]">
                            当前提供商：{{ presets.formatTtsProviderLabel(presets.editingPresetTtsProvider) }}
                          </p>

                          <!-- GLM-TTS 本地专属配置 -->
                          <template v-if="presets.editingPresetIsGlmLocal">
                            <div class="space-y-2">
                              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">仓库路径</label>
                              <input v-model="presets.editingPreset!.ttsGlmLocalRepoPath" type="text" class="input input-sm w-full" placeholder="E:\GLM-TTS（GLM-TTS 仓库根目录）" />
                              <p class="text-2xs text-[var(--color-text-muted)]">指向包含 run_api_gpu.ps1 的已就绪 GLM-TTS 目录。</p>
                            </div>
                            <div class="flex items-center gap-3">
                              <div class="flex-1 space-y-1">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">端口</label>
                                <input v-model.number="presets.editingPreset!.ttsGlmLocalPort" type="number" min="1" max="65535" class="input input-sm w-full" placeholder="8088" />
                              </div>
                              <div class="flex-1 space-y-1">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">托管启动</label>
                                <button type="button" class="btn btn-xs w-full" :class="presets.editingPreset!.ttsGlmLocalManaged ? 'btn-primary' : 'btn-secondary'" @click="presets.editingPreset!.ttsGlmLocalManaged = !presets.editingPreset!.ttsGlmLocalManaged">
                                  {{ presets.editingPreset!.ttsGlmLocalManaged ? '由程序启动' : '手动启动' }}
                                </button>
                              </div>
                            </div>
                            <p class="text-2xs text-[var(--color-text-muted)]">「由程序启动」会在首次合成前自动运行 run_api_gpu.ps1；「手动启动」需自行启动本地 API。</p>
                          </template>

                          <template v-else-if="presets.editingPresetIsQwen3Local">
                            <div class="space-y-2">
                              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">仓库路径</label>
                              <input v-model="presets.editingPreset!.ttsQwen3LocalRepoPath" type="text" class="input input-sm w-full" placeholder="E:\Qwen3-TTS（Qwen3-TTS 仓库根目录）" />
                              <p class="text-2xs text-[var(--color-text-muted)]">指向安装好 Qwen3-TTS 与 its gateway 的仓库目录；托管模式会从这里启动 uvicorn 网关。</p>
                            </div>
                            <div class="grid gap-3 md:grid-cols-2">
                              <div class="space-y-1">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">主端口（CustomVoice 网关）</label>
                                <input v-model.number="presets.editingPreset!.ttsQwen3LocalPort" type="number" min="1" max="65535" class="input input-sm w-full" placeholder="8080" />
                              </div>
                              <div class="space-y-1">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">语音克隆端口（Base 网关）</label>
                                <input
                                  :value="presets.editingPreset!.ttsQwen3LocalVoiceClonePort ?? ''"
                                  type="number"
                                  min="1"
                                  max="65535"
                                  class="input input-sm w-full"
                                  placeholder="留空 = 主端口 + 1"
                                  @input="presets.onQwen3VoiceClonePortInput"
                                />
                              </div>
                            </div>
                            <div class="grid gap-3 md:grid-cols-2">
                              <div class="space-y-1">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">托管启动</label>
                                <button type="button" class="btn btn-xs w-full" :class="presets.editingPreset!.ttsQwen3LocalManaged ? 'btn-primary' : 'btn-secondary'" @click="presets.editingPreset!.ttsQwen3LocalManaged = !presets.editingPreset!.ttsQwen3LocalManaged">
                                  {{ presets.editingPreset!.ttsQwen3LocalManaged ? '由程序启动' : '手动启动' }}
                                </button>
                              </div>
                              <div class="space-y-1">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">设备</label>
                                <input v-model="presets.editingPreset!.ttsQwen3LocalDevice" type="text" class="input input-sm w-full" placeholder="cuda:0" />
                              </div>
                            </div>
                            <div class="grid gap-3 md:grid-cols-2">
                              <div class="space-y-1">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">CustomVoice 模型 ID（/custom_voice）</label>
                                <input v-model="presets.editingPreset!.ttsQwen3LocalModelId" type="text" class="input input-sm w-full" placeholder="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice" />
                              </div>
                              <div class="space-y-1">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">Base 模型 ID（/voice_clone）</label>
                                <input v-model="presets.editingPreset!.ttsQwen3LocalBaseModelId" type="text" class="input input-sm w-full" placeholder="Qwen/Qwen3-TTS-12Hz-1.7B-Base" />
                              </div>
                            </div>
                            <div class="space-y-1">
                              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">默认语言</label>
                              <input v-model="presets.editingPreset!.ttsQwen3LocalDefaultLanguage" type="text" class="input input-sm w-full" placeholder="Auto" />
                            </div>
                            <p class="text-2xs text-[var(--color-text-muted)]">
                              托管模式会启动<strong>两个</strong> uvicorn：主端口加载 CustomVoice（仅 speaker → /v1/tts/custom_voice）；语音克隆端口加载 Base（参考音频+转写 → /v1/tts/voice_clone）。两端口必须不同；手动启动时需自行各启一个网关并填好 Base URL（主地址对应主端口）。
                            </p>
                          </template>

                          <template v-else-if="presets.editingPresetIsOmniVoiceLocal">
                            <div class="space-y-2">
                              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">仓库路径</label>
                              <input v-model="presets.editingPreset!.ttsOmniVoiceLocalRepoPath" type="text" class="input input-sm w-full" placeholder="E:\OmniVoice（OmniVoice 仓库根目录）" />
                              <p class="text-2xs text-[var(--color-text-muted)]">指向安装好 OmniVoice 与其 .venv 的仓库目录；托管模式会从这里启动 uvicorn。</p>
                            </div>
                            <div class="grid gap-3 md:grid-cols-2">
                              <div class="space-y-1">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">端口</label>
                                <input v-model.number="presets.editingPreset!.ttsOmniVoiceLocalPort" type="number" min="1" max="65535" class="input input-sm w-full" placeholder="8089" />
                              </div>
                              <div class="space-y-1">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">托管启动</label>
                                <button type="button" class="btn btn-xs w-full" :class="presets.editingPreset!.ttsOmniVoiceLocalManaged ? 'btn-primary' : 'btn-secondary'" @click="presets.editingPreset!.ttsOmniVoiceLocalManaged = !presets.editingPreset!.ttsOmniVoiceLocalManaged">
                                  {{ presets.editingPreset!.ttsOmniVoiceLocalManaged ? '由程序启动' : '手动启动' }}
                                </button>
                              </div>
                            </div>
                            <div class="grid gap-3 md:grid-cols-2">
                              <div class="space-y-1">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">模型 ID / 路径</label>
                                <input v-model="presets.editingPreset!.ttsOmniVoiceLocalModelId" type="text" class="input input-sm w-full" placeholder="k2-fsa/OmniVoice" />
                              </div>
                              <div class="space-y-1">
                                <label class="block text-xs font-medium text-[var(--color-text-secondary)]">设备</label>
                                <input v-model="presets.editingPreset!.ttsOmniVoiceLocalDevice" type="text" class="input input-sm w-full" placeholder="cuda:0（留空则交给 OmniVoice 自动选择）" />
                              </div>
                            </div>
                            <div class="space-y-1">
                              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">默认语言</label>
                              <input v-model="presets.editingPreset!.ttsOmniVoiceLocalDefaultLanguage" type="text" class="input input-sm w-full" placeholder="例如 zh、Chinese、English（可留空）" />
                            </div>
                            <p class="text-2xs text-[var(--color-text-muted)]">托管模式会执行 python -m uvicorn omnivoice.api.server:app --host 127.0.0.1 --port &lt;port&gt;，并通过环境变量传入模型与 device；后端调用 JSON 接口 /v1/tts。</p>
                          </template>

                          <div class="flex items-center justify-between gap-2 flex-wrap">
                            <label class="block text-xs font-medium text-[var(--color-text-secondary)]">音色列表</label>
                            <button
                              v-if="presets.editingPresetSupportsVoiceFetch"
                              type="button"
                              class="text-xs text-brand hover:text-brand-hover flex items-center gap-1 shrink-0"
                              :disabled="presets.presetVoicesLoading"
                              @click="presets.openVoiceSelector(presets.editingPreset!)"
                            >
                              <Loader2 v-if="presets.presetVoicesLoading" class="animate-spin w-3 h-3" />
                              <span>从 API 获取并筛选</span>
                            </button>
                          </div>

                          <div
                            v-if="presets.editingPresetVoiceCatalog.length"
                            class="flex flex-wrap items-center gap-x-1 gap-y-0.5 text-2xs leading-tight text-[var(--color-text-secondary)]"
                          >
                            <button type="button" class="min-h-0 rounded px-0.5 py-0 text-brand hover:underline" @click="presets.selectAllPresetVoices">全选</button>
                            <span class="select-none text-[var(--color-text-muted)]">·</span>
                            <button type="button" class="min-h-0 rounded px-0.5 py-0 text-brand hover:underline disabled:pointer-events-none disabled:opacity-40" :disabled="presets.presetVoiceListSelection.size === 0" @click="presets.clearPresetVoiceSelection">清空选择</button>
                            <span class="select-none text-[var(--color-text-muted)]">·</span>
                            <button type="button" class="min-h-0 rounded px-0.5 py-0 text-error/90 hover:underline disabled:pointer-events-none disabled:opacity-40" :disabled="presets.presetVoiceListSelection.size === 0" @click="presets.removeSelectedPresetVoices">删除所选</button>
                            <span class="select-none text-[var(--color-text-muted)]">·</span>
                            <button type="button" class="min-h-0 rounded px-0.5 py-0 text-error/90 hover:underline disabled:pointer-events-none disabled:opacity-40" :disabled="presets.editingPresetVoiceCatalog.length === 0" @click="presets.clearAllPresetVoices">清空全部</button>
                          </div>

                          <div class="drawer-scroll bg-surface-overlay border border-[var(--color-border)] rounded-lg p-2 min-h-[96px] max-h-[200px] overflow-y-auto custom-scrollbar">
                            <div class="flex flex-wrap gap-2">
                              <button
                                v-for="voice in presets.editingPresetVoiceCatalog"
                                :key="voice.voiceId"
                                type="button"
                                class="group relative inline-flex max-w-full cursor-pointer items-center gap-1 rounded-md border border-[var(--color-border-subtle)] bg-surface-overlay/55 px-2 py-1 text-xs text-[var(--color-text-secondary)] backdrop-blur-[var(--glass-blur-soft)] transition-[box-shadow,border-color] hover:bg-surface-overlay/80"
                                :class="presets.presetVoiceListSelection.has(voice.voiceId) ? 'ring-1 ring-brand/50 border-brand/35 shadow-[0_0_0_1px_color-mix(in_srgb,var(--color-brand)_25%,transparent)]' : ''"
                                @click="presets.togglePresetVoiceSelection(voice.voiceId)"
                              >
                                <span class="min-w-0 truncate">{{ voice.name }}</span>
                                <span class="rounded-full bg-surface-muted px-1.5 py-0.5 text-2xs text-[var(--color-text-muted)]">{{ voice.voiceType }}</span>
                              </button>
                              <div v-if="!presets.editingPresetVoiceCatalog.length" class="text-xs text-[var(--color-text-muted)] w-full text-center py-4">{{ presets.editingPresetIsGlmLocal ? '请在下方添加本地参考音色' : presets.editingPresetIsQwen3Local ? '请在下方添加 Qwen3 音色条目' : presets.editingPresetIsOmniVoiceLocal ? '请在下方添加 OmniVoice 音色条目' : '点击上方「从 API 获取并筛选」或下方手动添加 voice_id' }}</div>
                            </div>
                          </div>

                          <div v-if="!presets.editingPresetIsGlmLocal && !presets.editingPresetIsQwen3Local && !presets.editingPresetIsOmniVoiceLocal" class="flex gap-2">
                            <input
                              type="text"
                              placeholder="手动输入 voice_id 后按回车添加…"
                              class="input input-sm flex-1 rounded px-2 py-1 text-xs outline-none font-mono"
                              @keydown.enter="
                                (e) => {
                                  const val = (e.target as HTMLInputElement).value.trim()
                                  if (val) {
                                    presets.upsertEditingPresetVoiceCatalog([{ voiceId: val, name: val, voiceType: presets.editingPresetTtsProvider === 'glm' ? 'private' : 'system' }])
                                    ;(e.target as HTMLInputElement).value = ''
                                  }
                                }
                              "
                            />
                          </div>

                          <!-- GLM-TTS（本地）参考音色编辑 -->
                          <template v-if="presets.editingPresetIsGlmLocal">
                            <div class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3">
                              <div class="text-xs font-medium text-[var(--color-text-secondary)]">添加本地参考音色</div>
                              <input v-model="presets.glmLocalVoiceDraft.voiceId" type="text" class="input input-sm w-full" placeholder="音色 ID（唯一标识）" />
                              <input v-model="presets.glmLocalVoiceDraft.name" type="text" class="input input-sm w-full" placeholder="音色名称（显示用）" />
                              <input v-model="presets.glmLocalVoiceDraft.promptAudioPath" type="text" class="input input-sm w-full font-mono" placeholder="参考音频路径（wav/flac 绝对路径）" />
                              <input v-model="presets.glmLocalVoiceDraft.promptText" type="text" class="input input-sm w-full" placeholder="参考音频对应转写文本（推荐填写）" />
                              <p class="text-2xs text-[var(--color-text-muted)]">每条音色需要一段参考音频和对应文本。路径为本机文件绝对路径。</p>
                              <button
                                type="button"
                                class="btn btn-sm btn-primary w-full"
                                :disabled="!presets.glmLocalVoiceDraft.voiceId.trim()"
                                @click="presets.addGlmLocalVoice"
                              >添加音色</button>
                            </div>

                            <!-- 已添加的音色详情编辑 -->
                            <div v-for="voice in presets.editingPresetVoiceCatalog" :key="'detail-' + voice.voiceId" class="space-y-1 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay/60 px-3 py-2 text-xs">
                              <div class="flex items-center justify-between">
                                <span class="font-medium text-[var(--color-text-secondary)]">{{ voice.name }} <span class="text-2xs text-[var(--color-text-muted)]">({{ voice.voiceId }})</span></span>
                              </div>
                              <input :value="voice.promptAudioPath ?? ''" type="text" class="input input-sm w-full font-mono text-2xs" placeholder="参考音频路径" @change="(e) => presets.updateGlmLocalVoiceField(voice.voiceId, 'promptAudioPath', (e.target as HTMLInputElement).value)" />
                              <input :value="voice.promptText ?? ''" type="text" class="input input-sm w-full text-2xs" placeholder="参考转写文本" @change="(e) => presets.updateGlmLocalVoiceField(voice.voiceId, 'promptText', (e.target as HTMLInputElement).value)" />
                            </div>
                          </template>

                          <template v-else-if="presets.editingPresetIsQwen3Local">
                            <div class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3">
                              <div class="text-xs font-medium text-[var(--color-text-secondary)]">添加 Qwen3 音色</div>
                              <input v-model="presets.qwen3LocalVoiceDraft.voiceId" type="text" class="input input-sm w-full font-mono" placeholder="音色 ID（唯一标识；无参考音频时作为 speaker 传给 custom_voice）" />
                              <input v-model="presets.qwen3LocalVoiceDraft.name" type="text" class="input input-sm w-full" placeholder="显示名称（可选）" />
                              <input v-model="presets.qwen3LocalVoiceDraft.promptAudioPath" type="text" class="input input-sm w-full font-mono" placeholder="参考音频路径（wav/flac 绝对路径，语音克隆时填写）" />
                              <input v-model="presets.qwen3LocalVoiceDraft.promptText" type="text" class="input input-sm w-full" placeholder="参考音频对应转写文本（语音克隆时推荐填写）" />
                              <input v-model="presets.qwen3LocalVoiceDraft.instruction" type="text" class="input input-sm w-full" placeholder="instruction（可选，仅 custom_voice 模式）" />
                              <p class="text-2xs text-[var(--color-text-muted)]">参考音频与转写走第二端口上的 Base 网关（/voice_clone）；仅 speaker 走主端口 CustomVoice（/custom_voice）。路径为本机绝对路径。</p>
                              <button
                                type="button"
                                class="btn btn-sm btn-primary w-full"
                                :disabled="!presets.qwen3LocalVoiceDraft.voiceId.trim()"
                                @click="presets.addQwen3LocalVoice"
                              >添加音色</button>
                            </div>

                            <div v-for="voice in presets.editingPresetVoiceCatalog" :key="'detail-qwen-' + voice.voiceId" class="space-y-1 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay/60 px-3 py-2 text-xs">
                              <div class="font-medium text-[var(--color-text-secondary)]">{{ voice.voiceId }}</div>
                              <input :value="voice.name" type="text" class="input input-sm w-full text-2xs" placeholder="显示名称" @change="(e) => presets.updateQwen3LocalVoiceField(voice.voiceId, 'name', (e.target as HTMLInputElement).value)" />
                              <input :value="voice.promptAudioPath ?? ''" type="text" class="input input-sm w-full font-mono text-2xs" placeholder="参考音频路径" @change="(e) => presets.updateQwen3LocalVoiceField(voice.voiceId, 'promptAudioPath', (e.target as HTMLInputElement).value)" />
                              <input :value="voice.promptText ?? ''" type="text" class="input input-sm w-full text-2xs" placeholder="参考转写文本" @change="(e) => presets.updateQwen3LocalVoiceField(voice.voiceId, 'promptText', (e.target as HTMLInputElement).value)" />
                              <input :value="voice.instruction ?? ''" type="text" class="input input-sm w-full text-2xs" placeholder="instruction（可选）" @change="(e) => presets.updateQwen3LocalVoiceField(voice.voiceId, 'instruction', (e.target as HTMLInputElement).value)" />
                            </div>
                          </template>

                          <template v-else-if="presets.editingPresetIsOmniVoiceLocal">
                            <div class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3">
                              <div class="text-xs font-medium text-[var(--color-text-secondary)]">添加 OmniVoice 音色条目</div>
                              <input v-model="presets.omniVoiceLocalVoiceDraft.voiceId" type="text" class="input input-sm w-full font-mono" placeholder="音色 ID（用于会话里选择）" />
                              <input v-model="presets.omniVoiceLocalVoiceDraft.name" type="text" class="input input-sm w-full" placeholder="显示名称（可选）" />
                              <input v-model="presets.omniVoiceLocalVoiceDraft.promptAudioPath" type="text" class="input input-sm w-full font-mono" placeholder="参考音频路径（克隆模式，可选）" />
                              <input v-model="presets.omniVoiceLocalVoiceDraft.promptText" type="text" class="input input-sm w-full" placeholder="参考音频转写文本（克隆模式，可选）" />
                              <input v-model="presets.omniVoiceLocalVoiceDraft.instruction" type="text" class="input input-sm w-full" placeholder="instruction / instruct（音色设计模式，可选）" />
                              <p class="text-2xs text-[var(--color-text-muted)]">优先级为：参考音频可读则走克隆；否则有 instruction 走音色设计；两者都留空时仅按文本自动生成音色。</p>
                              <button
                                type="button"
                                class="btn btn-sm btn-primary w-full"
                                :disabled="!presets.omniVoiceLocalVoiceDraft.voiceId.trim()"
                                @click="presets.addOmniVoiceLocalVoice"
                              >添加音色</button>
                            </div>

                            <div v-for="voice in presets.editingPresetVoiceCatalog" :key="'detail-omnivoice-' + voice.voiceId" class="space-y-1 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay/60 px-3 py-2 text-xs">
                              <div class="font-medium text-[var(--color-text-secondary)]">{{ voice.voiceId }}</div>
                              <input :value="voice.name" type="text" class="input input-sm w-full text-2xs" placeholder="显示名称" @change="(e) => presets.updateOmniVoiceLocalVoiceField(voice.voiceId, 'name', (e.target as HTMLInputElement).value)" />
                              <input :value="voice.promptAudioPath ?? ''" type="text" class="input input-sm w-full font-mono text-2xs" placeholder="参考音频路径（可选）" @change="(e) => presets.updateOmniVoiceLocalVoiceField(voice.voiceId, 'promptAudioPath', (e.target as HTMLInputElement).value)" />
                              <input :value="voice.promptText ?? ''" type="text" class="input input-sm w-full text-2xs" placeholder="参考转写文本（可选）" @change="(e) => presets.updateOmniVoiceLocalVoiceField(voice.voiceId, 'promptText', (e.target as HTMLInputElement).value)" />
                              <input :value="voice.instruction ?? ''" type="text" class="input input-sm w-full text-2xs" placeholder="instruction / instruct（可选）" @change="(e) => presets.updateOmniVoiceLocalVoiceField(voice.voiceId, 'instruction', (e.target as HTMLInputElement).value)" />
                            </div>
                          </template>

                          <template v-else-if="presets.editingPresetIsSiliconflow">
                            <div class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3">
                              <div class="text-xs font-medium text-[var(--color-text-secondary)]">硅基流动 · 上传参考音频</div>
                              <p class="text-2xs text-[var(--color-text-muted)]">
                                需提供参考音频文件、与音频一致的转写文本，以及自定义音色名（对应官方 customName）；成功后返回的 uri 将写入音色目录。
                              </p>
                              <div class="flex flex-wrap gap-2">
                                <button type="button" class="btn btn-xs btn-secondary" @click="presets.pickTtsCloneSourceFile">选择参考音频</button>
                                <span class="text-2xs text-[var(--color-text-muted)]">{{ presets.ttsCloneSourceFile?.name || '未选择文件' }}</span>
                              </div>
                              <input :ref="presets.bindTtsCloneSourceInput" type="file" class="hidden" accept=".mp3,.wav,.m4a,.opus" @change="presets.onTtsCloneSourceChange" />
                              <input v-model="presets.ttsCloneDraft.voiceId" type="text" class="input input-sm w-full" placeholder="自定义音色名称（customName）" />
                              <ModernSelect
                                v-model="presets.ttsCloneDraft.model"
                                :options="presets.ttsSessionModelOptions"
                                searchable
                                allow-create
                                placeholder="TTS 模型（如 FunAudioLLM/CosyVoice2-0.5B）"
                                @select="(option) => { presets.ttsCloneDraft.model = option.value }"
                              />
                              <textarea v-model="presets.ttsCloneDraft.previewText" rows="3" class="input textarea w-full resize-y" placeholder="参考音频对应文本（必填）"></textarea>
                              <button type="button" class="btn btn-sm btn-primary w-full" :disabled="presets.ttsCloneLoading" @click="presets.submitTtsClone">{{ presets.ttsCloneLoading ? '上传中...' : '上传并写入音色' }}</button>
                              <audio v-if="presets.ttsClonePreviewUrl" :src="presets.ttsClonePreviewUrl" controls class="w-full"></audio>
                            </div>
                            <div class="rounded-lg border border-dashed border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3 text-xs text-[var(--color-text-muted)]">
                              硅基流动不提供与本应用内 MiniMax「音色设计」等价的云端接口；可使用上方上传或模型预置音色。
                            </div>
                          </template>

                          <template v-else-if="presets.editingPresetIsOpenrouter">
                            <div class="rounded-lg border border-dashed border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3 text-xs text-[var(--color-text-muted)] space-y-2">
                              <p>OpenRouter TTS 不支持在本面板内上传参考音频：请在下方「音色目录」填写模型文档要求的 <span class="font-mono">voice</span>；上游路由与偏好请在 OpenRouter 网站自行配置。</p>
                              <p>详见 <a href="https://openrouter.ai/docs" target="_blank" rel="noopener noreferrer" class="text-brand underline">OpenRouter 文档</a>。</p>
                            </div>
                          </template>

                          <!-- MiniMax / GLM（云端）：手动添加 + 克隆 + 设计 -->
                          <template v-else>
                            <div class="flex flex-col gap-3">
                              <div class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3">
                                <div class="text-xs font-medium text-[var(--color-text-secondary)]">音色快速复刻</div>
                              <div class="flex flex-wrap gap-2">
                                <button type="button" class="btn btn-xs btn-secondary" @click="presets.pickTtsCloneSourceFile">选择源音频</button>
                                <span class="text-2xs text-[var(--color-text-muted)]">{{ presets.ttsCloneSourceFile?.name || '未选择文件' }}</span>
                              </div>
                              <input :ref="presets.bindTtsCloneSourceInput" type="file" class="hidden" accept=".mp3,.wav,.m4a" @change="presets.onTtsCloneSourceChange" />
                              <input v-model="presets.ttsCloneDraft.voiceId" type="text" class="input input-sm w-full" placeholder="voice_id" />
                              <ModernSelect
                                v-model="presets.ttsCloneDraft.model"
                                :options="presets.ttsSessionModelOptions"
                                searchable
                                allow-create
                                :placeholder="presets.editingPresetTtsProvider === 'glm' ? '复刻模型（可选，默认 glm-tts-clone）' : '试听模型（可选）'"
                                @select="(option) => { presets.ttsCloneDraft.model = option.value }"
                              />
                              <textarea v-model="presets.ttsCloneDraft.previewText" rows="2" class="input textarea w-full resize-y" :placeholder="presets.editingPresetTtsProvider === 'glm' ? '试听文本（GLM 必填，留空则后端用默认试听文案）' : '试听文本（可选）'"></textarea>
                              <div v-if="presets.editingPresetSupportsPromptAudio" class="flex flex-wrap gap-2">
                                <button type="button" class="btn btn-xs btn-secondary" @click="presets.pickTtsClonePromptFile">选择示例音频</button>
                                <span class="text-2xs text-[var(--color-text-muted)]">{{ presets.ttsClonePromptFile?.name || '可选' }}</span>
                              </div>
                              <input v-if="presets.editingPresetSupportsPromptAudio" :ref="presets.bindTtsClonePromptInput" type="file" class="hidden" accept=".mp3,.wav,.m4a" @change="presets.onTtsClonePromptChange" />
                              <input v-model="presets.ttsCloneDraft.promptText" type="text" class="input input-sm w-full" :placeholder="presets.editingPresetTtsProvider === 'glm' ? '示例音频文本（可选）' : '示例音频对应文本（可选）'" />
                              <div v-if="presets.editingPresetSupportsPromptAudio" class="flex flex-wrap gap-4 text-xs text-[var(--color-text-secondary)]">
                                <button type="button" class="inline-flex items-center gap-2 transition-colors hover:text-[var(--color-text)]" @click="presets.ttsCloneDraft.needNoiseReduction = !presets.ttsCloneDraft.needNoiseReduction">
                                  <ThemedCheckbox :checked="presets.ttsCloneDraft.needNoiseReduction" />
                                  <span>降噪</span>
                                </button>
                                <button type="button" class="inline-flex items-center gap-2 transition-colors hover:text-[var(--color-text)]" @click="presets.ttsCloneDraft.needVolumeNormalization = !presets.ttsCloneDraft.needVolumeNormalization">
                                  <ThemedCheckbox :checked="presets.ttsCloneDraft.needVolumeNormalization" />
                                  <span>音量归一</span>
                                </button>
                              </div>
                              <p v-if="presets.editingPresetTtsProvider === 'glm'" class="text-2xs text-[var(--color-text-muted)]">GLM 复刻会使用上传的源音频作为样本；额外示例音频与降噪/归一化参数不适用。</p>
                              <button type="button" class="btn btn-sm btn-primary w-full" :disabled="presets.ttsCloneLoading" @click="presets.submitTtsClone">{{ presets.ttsCloneLoading ? '复刻中...' : '复刻并试听' }}</button>
                              <audio v-if="presets.ttsClonePreviewUrl" :src="presets.ttsClonePreviewUrl" controls class="w-full"></audio>
                            </div>

                            <div v-if="presets.editingPresetSupportsVoiceDesign" class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3">
                              <div class="text-xs font-medium text-[var(--color-text-secondary)]">音色设计</div>
                              <textarea v-model="presets.ttsDesignDraft.prompt" rows="3" class="input textarea w-full resize-y" placeholder="用自然语言描述想要的声音"></textarea>
                              <textarea v-model="presets.ttsDesignDraft.previewText" rows="2" class="input textarea w-full resize-y" placeholder="试听文本"></textarea>
                              <input v-model="presets.ttsDesignDraft.voiceId" type="text" class="input input-sm w-full" placeholder="voice_id（可选，不填则自动生成）" />
                              <button type="button" class="btn btn-sm btn-primary w-full" :disabled="presets.ttsDesignLoading" @click="presets.submitTtsDesign">{{ presets.ttsDesignLoading ? '设计中...' : '生成并试听' }}</button>
                              <audio v-if="presets.ttsDesignPreviewUrl" :src="presets.ttsDesignPreviewUrl" controls class="w-full"></audio>
                            </div>

                            <div v-else class="rounded-lg border border-dashed border-[var(--color-border-subtle)] bg-surface-overlay px-3 py-3 text-xs text-[var(--color-text-muted)]">
                              GLM TTS 暂不支持音色设计，当前仅支持音色列表、上传与音色复刻。
                            </div>
                          </div>
                          </template>
                        </div>
                     </div>
                </div>
                <div v-else class="flex min-h-[12rem] flex-1 items-center justify-center text-[var(--color-text-muted)] text-sm">
                    选择或创建一个预设
                </div>
            </div>
  </div>
</template>
