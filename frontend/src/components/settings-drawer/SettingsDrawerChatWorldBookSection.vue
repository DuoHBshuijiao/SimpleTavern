<script setup lang="ts">
import { inject } from 'vue'
import { SETTINGS_DRAWER_CHAT_KEY } from '../../composables/settingsDrawerChatKey'
import ModernSelect from '../ModernSelect.vue'
import { GripVertical } from 'lucide-vue-next'

const chat = inject(SETTINGS_DRAWER_CHAT_KEY)!
</script>

<template>
<div class="space-y-2">
  <div class="flex flex-wrap items-center justify-between gap-2">
    <div class="text-sm font-medium text-[var(--color-text-secondary)]">世界书</div>
    <template v-if="!chat.worldBookCreateExpanded">
      <button type="button" class="btn btn-xs btn-secondary" @click="chat.worldBookCreateExpanded = true">
        新建世界书
      </button>
    </template>
    <div v-else class="flex flex-wrap items-center gap-2 justify-end flex-1 min-w-0">
      <input
        v-model="chat.worldBookNewNameDraft"
        type="text"
        class="input input-sm flex-1 min-w-[140px] max-w-[240px]"
        placeholder="世界书名称"
        @keydown.enter.prevent="chat.confirmCreateWorldBook"
      />
      <button type="button" class="btn btn-xs btn-primary" @click="chat.confirmCreateWorldBook">创建</button>
      <button type="button" class="btn btn-xs btn-secondary" @click="chat.cancelWorldBookCreate">取消</button>
    </div>
  </div>
  <div class="rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted p-3 text-xs text-[var(--color-text-muted)]">
    全局激活的世界书会自动对当前会话生效；你也可以把世界书仅绑定到当前会话。会话内顺序用于预算淘汰优先级（靠后更先被丢弃）。
  </div>
  <div class="flex items-center gap-2">
    <ModernSelect
      v-model="chat.addWorldBookId"
      :options="chat.worldBookAddOptions"
      placeholder="选择世界书加入会话顺序..."
      class="flex-1"
    />
    <button class="btn btn-sm btn-secondary" @click="chat.addWorldBookToOrder">加入顺序</button>
  </div>
  <div class="drawer-scroll max-h-[180px] space-y-2 overflow-y-auto rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay p-2">
    <div
      v-for="book in chat.currentChatWorldbooks"
      :key="book.id"
      class="rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted p-2"
    >
      <div class="flex items-center justify-between gap-2">
        <div class="text-sm text-[var(--color-text)]">
          {{ book.name }}
          <span v-if="book.globalActive" class="ml-1 text-xs text-brand">{{
            (chat.chatDraft?.worldBookGlobalExclusions || []).includes(book.id)
              ? '（全局，该会话禁用）'
              : '（全局）'
          }}</span>
        </div>
        <div class="flex items-center gap-1">
          <button class="btn btn-xs btn-secondary" @click="chat.setWorldBookGlobalActive(book, !book.globalActive)">
            {{ book.globalActive ? '改为会话' : '设为全局' }}
          </button>
          <button class="btn btn-xs btn-secondary" @click="chat.detachWorldBookFromCurrentChat(book)">移除会话</button>
          <button class="btn btn-xs btn-secondary" @click="chat.openWorldBookEditor(book.id)">编辑</button>
        </div>
      </div>
    </div>
    <div v-if="chat.currentChatWorldbooks.length === 0" class="text-xs text-[var(--color-text-muted)]">
      当前会话暂无已激活世界书。
    </div>
  </div>
  <div class="rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay overflow-hidden">
    <button
      type="button"
      class="w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-xs font-medium text-[var(--color-text-secondary)] hover:bg-surface-muted transition-colors"
      @click="chat.toggleAllWorldBooksSection"
    >
      <span>全部世界书（{{ chat.worldbooks.length }} 本）</span>
      <span class="text-[var(--color-text-muted)]">{{ chat.allWorldBooksSectionOpen ? '收起' : '展开' }}</span>
    </button>
    <div v-show="chat.allWorldBooksSectionOpen" class="px-2 pb-2 space-y-1.5 border-t border-[var(--color-border-subtle)] pt-2">
      <div
        v-for="book in chat.worldBooksListVisible"
        :key="book.id"
        class="flex items-center justify-between gap-2 rounded-md border border-[var(--color-border-subtle)] bg-surface-muted px-2 py-1.5"
      >
        <div class="min-w-0 flex-1">
          <div class="text-xs text-[var(--color-text)] truncate">{{ book.name || book.id }}</div>
          <div class="text-[10px] text-[var(--color-text-muted)] leading-tight mt-0.5">
            {{ chat.worldbookTokenHint(book.id) }}
          </div>
        </div>
        <button type="button" class="btn btn-xs btn-secondary shrink-0" @click="chat.openWorldBookEditor(book.id)">
          编辑
        </button>
      </div>
      <div v-if="chat.worldbooks.length === 0" class="text-xs text-[var(--color-text-muted)] px-1 py-1">暂无世界书。</div>
      <div v-else-if="chat.worldbooks.length > 5" class="flex justify-center pt-1">
        <button type="button" class="btn btn-xs btn-secondary" @click="chat.allWorldBooksListExpanded = !chat.allWorldBooksListExpanded">
          {{ chat.allWorldBooksListExpanded ? '收起列表' : `展开全部（${chat.worldbooks.length} 本）` }}
        </button>
      </div>
    </div>
  </div>
  <div class="space-y-1 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay p-2">
    <div class="text-xs text-[var(--color-text-muted)]">会话世界书顺序</div>
    <p class="text-[10px] text-[var(--color-text-muted)] mb-1 leading-snug">
      拖动条目或用上移/下移调整顺序（预算淘汰时靠后的书先被丢弃）。扫描深度与插入深度在「编辑」中设置（按会话）。
    </p>
    <div
      v-for="(att, idx) in (chat.chatDraft.worldBookAttachments || [])"
      :key="`${att.worldBookId}-${idx}`"
      class="flex items-center justify-between gap-2 rounded-md border border-[var(--color-border-subtle)] bg-surface-muted px-2 py-1 transition-[border-color,opacity,background-color]"
      :class="chat.worldBookOrderDraggingIdx === idx ? 'opacity-50 border-brand-a50' : ''"
      draggable="true"
      @dragstart="chat.handleWorldBookOrderDragStart(idx)"
      @dragover="chat.handleWorldBookOrderDragOver($event, idx)"
      @dragend="chat.handleWorldBookOrderDragEnd"
    >
      <div class="flex min-w-0 flex-1 items-center gap-1.5">
        <span class="shrink-0 cursor-grab text-[var(--color-text-muted)] active:cursor-grabbing" aria-hidden="true">
          <GripVertical class="w-4 h-4" />
        </span>
        <div class="flex min-w-0 flex-1 flex-col gap-0.5">
          <span class="truncate text-xs text-[var(--color-text)]">{{ Number(idx) + 1 }}. {{ chat.worldBookName(att.worldBookId) }}</span>
          <div class="text-[10px] text-[var(--color-text-muted)] leading-tight">
            扫描：{{ chat.scanDepthDisplay(att.scanDepth) }}　深度：{{ att.insertDepth ?? 5 }}
          </div>
        </div>
      </div>
      <div class="flex shrink-0 flex-wrap items-center gap-1 justify-end">
        <button type="button" class="btn btn-xs btn-secondary" @click.stop="chat.openSessionAttachEdit(idx)">编辑</button>
        <button type="button" class="btn btn-xs btn-secondary" @click.stop="chat.moveWorldBookOrder(att.worldBookId, -1)">上移</button>
        <button type="button" class="btn btn-xs btn-secondary" @click.stop="chat.moveWorldBookOrder(att.worldBookId, 1)">下移</button>
        <button type="button" class="btn btn-xs btn-secondary" @click.stop="chat.clearWorldBookSessionActivationById(att.worldBookId)">删除</button>
      </div>
    </div>
  </div>
</div>
</template>
