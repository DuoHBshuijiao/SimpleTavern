<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { ChevronDown, Globe } from 'lucide-vue-next'
import type { ChatWebSource } from '../../utils/markdownIt'
import { discoverWebSourceIcon, webSourceIconOrigin } from '../../utils/webSourceIcons'

const props = defineProps<{ sources: ChatWebSource[] }>()

const expanded = ref(false)
const listId = useId()
const icons = ref(new Map<string, string | null>())

watch(() => props.sources, () => { expanded.value = false })

const visibleSources = computed(() => {
  if (!expanded.value) return []
  const siteOrder = new Map<string, number>()
  const bySite = new Map<string, number>()
  const sources = props.sources.map(source => {
    const site = new URL(source.url).hostname.replace(/^www\./i, '')
    bySite.set(site, (bySite.get(site) ?? 0) + 1)
    return { ...source, site }
  })
  return sources.map(source => {
    const origin = webSourceIconOrigin(source.url)
    const icon = origin && (icons.value.has(origin) ? icons.value.get(origin) : `${origin}/favicon.ico`)
    const order = (siteOrder.get(source.site) ?? 0) + 1
    siteOrder.set(source.site, order)
    const hasTitle = source.label.toLowerCase().replace(/^www\./i, '') !== source.site
    const repeated = (bySite.get(source.site) ?? 0) > 1
    const label = hasTitle ? source.label : `${source.site}${repeated ? ` · ${order}` : ''}`
    return { ...source, origin, icon, label, hasTitle }
  })
})

async function handleIconError(origin: string | null, failedIcon: string) {
  if (!origin) return
  const cached = icons.value.get(origin)
  if (cached !== undefined) {
    if (cached === failedIcon) icons.value.set(origin, null)
    return
  }

  icons.value.set(origin, null)
  const icon = await discoverWebSourceIcon(origin)
  if (icon !== `${origin}/favicon.ico`) icons.value.set(origin, icon)
}
</script>

<template>
  <div v-if="sources.length || $slots.default" class="message-web-sources">
    <div class="message-web-source-toolbar">
      <div v-if="$slots.default" class="message-web-source-leading">
        <slot />
      </div>
      <button
        v-if="sources.length"
        type="button"
        class="message-web-source message-web-source-toggle"
        :aria-expanded="expanded"
        :aria-controls="listId"
        @click="expanded = !expanded"
      >
        来源 · {{ sources.length }} 篇
        <ChevronDown class="h-3.5 w-3.5 shrink-0" :class="{ 'rotate-180': expanded }" aria-hidden="true" />
      </button>
    </div>
    <nav v-if="sources.length" v-show="expanded" :id="listId" class="message-web-source-list" aria-label="引用来源">
      <a
        v-for="source in visibleSources"
        :key="source.url"
        :href="source.url"
        :title="`${source.label}\n${source.url}`"
        target="_blank"
        rel="noopener noreferrer"
        class="message-web-source"
      >
        <img
          v-if="source.icon"
          :src="source.icon"
          alt=""
          width="16"
          height="16"
          loading="lazy"
          referrerpolicy="no-referrer"
          class="message-web-source-icon"
          @error="handleIconError(source.origin, source.icon)"
        />
        <Globe v-else class="message-web-source-icon" aria-hidden="true" />
        <span class="min-w-0">
          <span class="block truncate">{{ source.label }}</span>
          <span v-if="source.hasTitle" class="block truncate text-[var(--color-text-secondary)]">{{ source.site }}</span>
        </span>
      </a>
    </nav>
  </div>
</template>

<style scoped>
.message-web-sources {
  min-width: 0;
}

.message-web-source-toolbar {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 0.25rem;
}

.message-web-source-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-block-start: 0.375rem;
}

.message-web-source-leading {
  max-width: 100%;
}

.message-web-source {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  min-width: 0;
  min-height: 1.75rem;
  max-width: min(18rem, 100%);
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--color-border-subtle);
  border-radius: 0.5rem;
  background: var(--color-popover-surface);
  color: var(--color-text);
  font-size: 0.75rem;
  line-height: 1.25;
  text-decoration: none;
}

.message-web-source:hover {
  background: var(--color-surface-hover);
}

.message-web-source:focus-visible {
  outline: 2px solid var(--color-focus-ring);
  outline-offset: 2px;
}

.message-web-source-icon {
  width: 1rem;
  height: 1rem;
  flex: none;
  border-radius: 0.25rem;
  object-fit: contain;
  color: var(--color-text-secondary);
}

.message-web-source-toggle {
  flex: none;
  margin-inline-start: auto;
  border-radius: var(--radius-full);
  cursor: pointer;
}
</style>
