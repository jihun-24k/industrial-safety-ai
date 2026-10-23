<script setup>
import BrandLogo from './BrandLogo.vue';

defineProps({
  user: { type: String, required: true },
  demo: { type: Boolean, default: false },
  conversations: { type: Array, default: () => [] },
  activeId: { type: String, default: null },
  open: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
});

defineEmits(['new-chat', 'select-chat', 'logout', 'close']);
</script>

<template>
  <button v-if="open" class="sidebar-overlay" aria-label="메뉴 닫기" @click="$emit('close')"></button>
  <aside class="sidebar" :class="{ open }">
    <BrandLogo @click.prevent="$emit('new-chat')" />
    <span class="sidebar-subtitle">산업안전 AI 파트너</span>
    <button class="new-chat" :disabled="disabled" @click="$emit('new-chat')">
      ＋ <span>새 대화 시작</span><span>↗</span>
    </button>

    <div class="history-label">대화 기록 <span>{{ conversations.length }}</span></div>
    <nav class="history" aria-label="대화 기록">
      <p v-if="!conversations.length" class="empty-history">첫 번째 대화를 시작해 보세요.</p>
      <button
        v-for="chat in conversations"
        :key="chat.id"
        :class="{ selected: activeId === chat.id }"
        :disabled="disabled"
        @click="$emit('select-chat', chat)"
      >
        <span>◌</span> {{ chat.title }}
      </button>
    </nav>

    <div class="sidebar-bottom">
      <div class="privacy-note"><span>◇</span><p>안전을 위한 질문,<br><strong>언제든 편하게 물어보세요.</strong></p></div>
      <div class="account">
        <span class="avatar">{{ user.slice(0, 1) }}</span>
        <div><strong>{{ user }}</strong><small>{{ demo ? '화면 미리보기' : '로그인됨' }}</small></div>
        <button :disabled="disabled" aria-label="로그아웃" title="로그아웃" @click="$emit('logout')">↪</button>
      </div>
    </div>
  </aside>
</template>
