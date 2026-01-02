<script setup lang="ts">
import { RouterView } from 'vue-router'
import { NConfigProvider, darkTheme, NGlobalStyle } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'

const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#a230ed',
    primaryColorHover: '#b558f0',
    primaryColorPressed: '#8e23d1',
    primaryColorSuppl: '#a230ed',
    infoColor: '#a230ed',
    successColor: '#7c3aed',
    warningColor: '#c026d3',
    errorColor: '#be185d',
  },
  Button: {
    textColorPrimary: '#fff',
    textColorHoverPrimary: '#fff',
    textColorPressedPrimary: '#fff',
    textColorFocusPrimary: '#fff',
  },
  Tag: {
    colorInfo: 'rgba(162, 48, 237, 0.15)',
    textColorInfo: '#a230ed',
    borderInfo: '1px solid rgba(162, 48, 237, 0.3)',
    colorSuccess: 'rgba(124, 58, 237, 0.15)',
    textColorSuccess: '#7c3aed',
    borderSuccess: '1px solid rgba(124, 58, 237, 0.3)',
  },
}
</script>

<template>
  <NConfigProvider :theme="darkTheme" :theme-overrides="themeOverrides">
    <NGlobalStyle />
    <RouterView />
  </NConfigProvider>
</template>
