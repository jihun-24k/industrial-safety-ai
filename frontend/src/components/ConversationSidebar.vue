<script setup>
import { t } from '../utils/i18n';
import BrandLogo from './BrandLogo.vue';
import { watch, nextTick, ref } from 'vue';

const props = defineProps({
  user: { type: String, required: true },
  demo: { type: Boolean, default: false },
  conversations: { type: Array, default: () => [] },
  activeId: { type: String, default: null },
  open: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
});

const emit = defineEmits(['new-chat', 'select-chat', 'logout', 'close']);
const drawer = ref(null);
let previousFocus;
watch(() => props.open, async open => {
  if (open) { previousFocus = document.activeElement; await nextTick(); drawer.value?.querySelector('button')?.focus(); }
  else previousFocus?.focus();
});
function onKeydown(event) {
  if (event.key === 'Escape') { emit('close'); return; }
  if (event.key !== 'Tab') return;
  const items = [...drawer.value.querySelectorAll('button:not(:disabled), a[href]')];
  const first = items[0], last = items.at(-1);
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
}
</script>

<template>
  <button v-if="open" class="sidebar-overlay" :aria-label="t(&quot;메뉴 닫기&quot;)" @click="$emit('close')"></button>
  <aside ref="drawer" class="sidebar" :class="{ open }" :inert="!open" :aria-hidden="!open" role="dialog" :aria-modal="open" :aria-label="t(&quot;상담 기록 메뉴&quot;)" @keydown="onKeydown">
    <button class="sidebar-close" :aria-label="t(&quot;메뉴 닫기&quot;)" @click="$emit('close')">×</button>
    <BrandLogo @click.prevent="$emit('new-chat')" />
    <span class="sidebar-subtitle">{{ t("산업안전 AI 파트너") }}</span>
    <button class="new-chat" :disabled="disabled" @click="$emit('new-chat')">
      ＋ <span>{{ t("새 대화 시작") }}</span><span>↗</span>
    </button>

    <div class="history-label">{{ t("대화 기록 ") }}<span>{{ t(conversations.length) }}</span></div>
    <nav class="history" :aria-label="t(&quot;대화 기록&quot;)">
      <p v-if="!conversations.length" class="empty-history">{{ t("첫 번째 대화를 시작해 보세요.") }}</p>
      <button
        v-for="chat in conversations"
        :key="chat.id"
        :class="{ selected: activeId === chat.id }"
        :disabled="disabled"
        @click="$emit('select-chat', chat)"
      >
        <span>◌</span> {{ t(chat.title) }}
      </button>
    </nav>

    <div class="sidebar-bottom">
      <div class="privacy-note"><span>◇</span><p>{{ t("안전을 위한 질문,") }}<br><strong>{{ t("언제든 편하게 물어보세요.") }}</strong></p></div>
      <div class="account">
        <span class="avatar">{{ t(user.slice(0, 1)) }}</span>
        <div><strong>{{ t(user) }}</strong><small>{{ t(demo ? '화면 미리보기' : '로그인됨') }}</small></div>
        <button :disabled="disabled" :aria-label="t(&quot;로그아웃&quot;)" :title="t(&quot;로그아웃&quot;)" @click="$emit('logout')">↪</button>
      </div>
    </div>
  </aside>
</template>
