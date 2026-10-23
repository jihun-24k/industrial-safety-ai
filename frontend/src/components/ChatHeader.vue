<script setup>
defineProps({
  demo: { type: Boolean, default: false },
});

defineEmits(['open-menu']);
</script>

<template>
  <header class="chat-header">
    <div>
      <button class="mobile-menu" aria-label="메뉴 열기" @click="$emit('open-menu')">☰</button>
      <strong>안전 어시스턴트</strong>
      <span class="header-separator">/</span>
      <span class="header-caption">함께 만드는 안전한 현장</span>
    </div>
    <span class="status-badge"><i></i>{{ demo ? '미리보기' : 'AI 어시스턴트' }}</span>
  </header>
</template>
