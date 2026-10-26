<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue';
import { speechLanguages } from '../utils/translation';
import BrandLogo from './BrandLogo.vue';
const props = defineProps({
  language: { type: String, default: 'ko' },
  demo: { type: Boolean, default: false },
  streaming: { type: Boolean, default: true },
  modeDisabled: { type: Boolean, default: false },
});

const emit = defineEmits(['open-menu', 'new-chat', 'update:language', 'update:streaming', 'open-dashboard']);
const languageMenu = ref(null);
const languageTrigger = ref(null);
const selectedLanguage = computed(() => speechLanguages.find(item => item.code === props.language)?.label || '한국어');
function closeLanguage(event) {
  if (!languageMenu.value?.open) return;
  if (event.type === 'keydown' && event.key !== 'Escape') return;
  if (event.type === 'pointerdown' && languageMenu.value?.contains(event.target)) return;
  if (languageMenu.value) languageMenu.value.open = false;
  if (event.type === 'keydown') languageTrigger.value?.focus();
}
function selectLanguage(code) {
  emit('update:language', code);
  languageMenu.value.open = false;
  languageTrigger.value?.focus();
}
onMounted(() => {
  document.addEventListener('pointerdown', closeLanguage);
  document.addEventListener('keydown', closeLanguage);
});
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeLanguage);
  document.removeEventListener('keydown', closeLanguage);
});
</script>

<template>
  <header class="chat-header">
    <div>
      <button class="mobile-menu" aria-label="메뉴 열기" @click="$emit('open-menu')">☰</button>
      <BrandLogo @click.prevent="$emit('new-chat')" />
    </div>
    <div class="header-actions">
      <button class="history-toggle" @click="$emit('open-menu')">상담 기록</button>
      <button v-if="!demo" type="button" class="ops-toggle" :disabled="modeDisabled" @click="$emit('open-dashboard')">운영 현황</button>
      <details ref="languageMenu" class="speech-language" @toggle="(modeDisabled || demo) && languageMenu && (languageMenu.open = false)">
        <summary ref="languageTrigger" class="language-trigger" :aria-disabled="modeDisabled || demo" aria-label="답변 음성 언어 선택" @click="(modeDisabled || demo) && $event.preventDefault()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z"/></svg>
          <span>{{ selectedLanguage }}</span>
          <svg class="language-chevron" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m6 8 4 4 4-4"/></svg>
        </summary>
        <div class="language-options" aria-label="답변 음성 언어">
          <span class="language-menu-label">답변 음성 언어</span>
          <button v-for="item in speechLanguages" :key="item.code" type="button" :class="{ selected: item.code === language }" :aria-label="item.label" :aria-pressed="item.code === language" :disabled="modeDisabled || demo" @click="selectLanguage(item.code)">
            <span>{{ item.label }}</span><span class="language-check" aria-hidden="true">{{ item.code === language ? '✓' : '' }}</span>
          </button>
        </div>
      </details>
      <button
        type="button"
        class="stream-toggle"
        :class="{ active: streaming }"
        aria-label="답변 스트리밍"
        role="switch"
        :aria-checked="streaming"
        :disabled="modeDisabled || demo"
        :title="streaming ? '토큰이 생성될 때마다 표시합니다.' : '답변 완료 후 한 번에 표시합니다.'"
        @click="$emit('update:streaming', !streaming)"
      >
        <span class="toggle-track"><i></i></span>
        <span class="stream-label">{{ streaming ? '스트리밍' : '한 번에' }}</span>
      </button>
      <span class="status-badge"><i></i>{{ demo ? '미리보기' : 'AI 어시스턴트' }}</span>
    </div>
  </header>
</template>
