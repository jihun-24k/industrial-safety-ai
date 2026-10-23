<script setup>
import BrandLogo from './BrandLogo.vue';
defineProps({
  demo: { type: Boolean, default: false },
  streaming: { type: Boolean, default: true },
  modeDisabled: { type: Boolean, default: false },
});

defineEmits(['open-menu', 'new-chat', 'update:streaming']);
</script>

<template>
  <header class="chat-header">
    <div>
      <button class="mobile-menu" aria-label="메뉴 열기" @click="$emit('open-menu')">☰</button>
      <BrandLogo @click.prevent="$emit('new-chat')" />
    </div>
    <div class="header-actions">
      <button class="history-toggle" @click="$emit('open-menu')">상담 기록</button>
      <span class="language-label">한국어</span>
      <button
        type="button"
        class="stream-toggle"
        :class="{ active: streaming }"
        role="switch"
        :aria-checked="streaming"
        :disabled="modeDisabled || demo"
        :title="streaming ? '토큰이 생성될 때마다 표시합니다.' : '답변 완료 후 한 번에 표시합니다.'"
        @click="$emit('update:streaming', !streaming)"
      >
        <span class="toggle-track"><i></i></span>
        {{ streaming ? '스트리밍' : '한 번에' }}
      </button>
      <span class="status-badge"><i></i>{{ demo ? '미리보기' : 'AI 어시스턴트' }}</span>
    </div>
  </header>
</template>
