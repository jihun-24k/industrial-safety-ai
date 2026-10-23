<script setup>
import { nextTick, ref } from 'vue';

defineProps({
  messages: { type: Array, default: () => [] },
  user: { type: String, required: true },
  busy: { type: Boolean, default: false },
  ttsLoading: { type: String, default: null },
  speakingId: { type: String, default: null },
  examples: { type: Array, default: () => [] },
});

defineEmits(['send-example', 'speak']);
const container = ref(null);

async function scrollToBottom() {
  await nextTick();
  container.value?.scrollTo({ top: container.value.scrollHeight, behavior: 'smooth' });
}

defineExpose({ scrollToBottom });
</script>

<template>
  <div ref="container" class="message-scroll" :class="{ welcome: !messages.length }">
    <section v-if="!messages.length" class="welcome-content">
      <div class="welcome-emblem">◇<span>✦</span></div>
      <span class="section-tag">현장의 모든 질문을 함께</span>
      <h1>오늘도 안전하게,<br>무엇을 도와드릴까요?</h1>
      <p>작업 수칙부터 안전 점검까지 편하게 질문하세요.<br>답변은 음성으로도 들을 수 있어요.</p>
      <div class="suggestions">
        <button v-for="(example, index) in examples" :key="example" @click="$emit('send-example', example)">
          <span class="suggestion-icon">{{ ['☑', '◇', '↗'][index] }}</span>
          <span>{{ example }}</span>
          <span class="suggestion-arrow">↗</span>
        </button>
      </div>
    </section>

    <div v-else class="messages">
      <article v-for="message in messages" :key="message.id" class="message" :class="message.role">
        <div class="message-avatar">{{ message.role === 'assistant' ? '◇' : user.slice(0, 1) }}</div>
        <div class="message-content">
          <div class="message-author">
            {{ message.role === 'assistant' ? '세이프메이트' : user }}
            <span v-if="message.source">{{ message.source }}</span>
          </div>
          <div class="message-text">{{ message.text }}</div>
          <button
            v-if="message.role === 'assistant'"
            class="listen-button"
            :disabled="!!ttsLoading"
            :aria-pressed="speakingId === message.id"
            @click="$emit('speak', message)"
          >
            {{ ttsLoading === message.id ? '◌ 음성 준비 중…' : speakingId === message.id ? '■ 재생 중지' : '◖ 답변 듣기' }}
          </button>
        </div>
      </article>
      <div v-if="busy" class="thinking" role="status"><span>◇</span> 자료를 확인하고 답변을 준비하고 있어요<span class="dots">···</span></div>
    </div>
  </div>
</template>
