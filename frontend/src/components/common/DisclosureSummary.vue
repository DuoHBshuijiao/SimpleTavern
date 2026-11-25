<script setup lang="ts">
import { ChevronDown } from 'lucide-vue-next'
</script>

<template>
  <summary class="disclosure-summary">
    <slot />
    <ChevronDown class="disclosure-chevron h-4 w-4 shrink-0" aria-hidden="true" />
  </summary>
</template>
