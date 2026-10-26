<script setup>
import { speechLanguages } from '../utils/translation';
defineProps({
  language: { type: String, default: 'ko' },
  demo: { type: Boolean, default: false },
  streaming: { type: Boolean, default: true },
  modeDisabled: { type: Boolean, default: false },
});

defineEmits(['open-menu', 'update:language', 'update:streaming']);
</script>

<template>
  <header class="chat-header">
    <div>
      <button class="mobile-menu" aria-label="메뉴 열기" @click="$emit('open-menu')">☰</button>
      <strong>안전 어시스턴트</strong>
      <span class="header-separator">/</span>
      <span class="header-caption">함께 만드는 안전한 현장</span>
    </div>
    <div class="header-actions">
      <label class="speech-language">
        <span class="sr-only">답변 음성 언어</span>
        <select :value="language" :disabled="modeDisabled || demo" aria-label="답변 음성 언어" @change="$emit('update:language', $event.target.value)">
          <option v-for="item in speechLanguages" :key="item.code" :value="item.code">{{ item.label }}</option>
        </select>
      </label>
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
