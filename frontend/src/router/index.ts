import { createRouter, createWebHistory } from 'vue-router'

import ChatPage from '../views/ChatPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/characters', redirect: '/chat' },
    { path: '/chat', component: ChatPage },
  ],
})


