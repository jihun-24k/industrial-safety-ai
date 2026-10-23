<script setup>
import { computed } from 'vue';

const props = defineProps({
  draft: { type: String, default: '' },
  busy: { type: Boolean, default: false },
  uploading: { type: Boolean, default: false },
  voiceState: { type: String, default: 'idle' },
  ttsLoading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  notice: { type: String, default: '' },
});

const emit = defineEmits([
  'update:draft',
  'send',
  'upload',
  'voice',
  'dismiss-error',
  'dismiss-notice',
]);

const inputDisabled = computed(() => props.busy || props.uploading || props.voiceState !== 'idle' || props.ttsLoading);
const voiceLabel = computed(() => ({idle:'음성으로 질문하기 · 3초 무음 후 자동 전송', connecting:'음성 서버 연결 중 · 누르면 취소', requesting:'마이크 권한 확인 중 · 누르면 취소', recording:'녹음 중지 · 직접 전송하기', transcribing:'최종 인식 중 · 누르면 취소'})[props.voiceState]);

function handleKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    emit('send');
  }
}

function handleFile(event) {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (file) emit('upload', file);
}
</script>

<template>
  <div class="composer-wrap">
    <p v-if="error" class="error inline-error" role="alert">{{ error }} <button aria-label="알림 닫기" @click="$emit('dismiss-error')">×</button></p>
    <p v-if="notice" class="notice" role="status">{{ notice }} <button aria-label="알림 닫기" @click="$emit('dismiss-notice')">×</button></p>
    <form class="composer" @submit.prevent="$emit('send')">
      <textarea
        :value="draft"
        aria-label="안전 질문"
        placeholder="안전에 대해 궁금한 점을 물어보세요…"
        rows="2"
        maxlength="6000"
        :disabled="inputDisabled"
        @input="$emit('update:draft', $event.target.value)"
        @keydown="handleKeydown"
      ></textarea>
      <div class="composer-tools">
        <div>
          <input ref="pdf" type="file" accept="application/pdf,.pdf" hidden @change="handleFile">
          <button type="button" class="attach" :disabled="inputDisabled" aria-label="PDF 자료 첨부" title="PDF 자료 첨부" @click="$refs.pdf.click()">＋</button>
          <span class="tool-divider"></span>
          <span class="document-mode">문서 기반 답변</span>
          <span v-if="uploading" class="upload-label" role="status">PDF 처리 중…</span>
        </div>
        <div class="input-actions">
          <button type="button" class="microphone-button" :class="{recording:voiceState === 'recording'}" :aria-label="voiceLabel" :title="voiceLabel" :aria-pressed="voiceState === 'recording'" :disabled="busy || uploading || ttsLoading" @click="$emit('voice')">
            <svg v-if="voiceState !== 'recording'" viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0014 0v-2M12 19v3m-4 0h8"/></svg>
            <span v-else aria-hidden="true">■</span>
          </button>
          <button class="send-button" aria-label="질문 보내기" :disabled="!props.draft.trim() || inputDisabled">↑</button>
        </div>
      </div>
      <p class="voice-status" :class="{recording:voiceState === 'recording'}" role="status">{{voiceState === 'recording' ? '실시간 인식 중 · 말한 뒤 3초간 조용하면 자동으로 질문해요. 최대 60초' : voiceState === 'idle' ? '마이크로 말하면 실시간 입력 · 3초 무음 뒤 자동 질문' : voiceLabel}}</p>
    </form>
    <p class="composer-disclaimer">AI 답변은 참고용입니다. 실제 작업 시 현장 안전 지침을 우선 확인하세요.</p>
  </div>
</template>
