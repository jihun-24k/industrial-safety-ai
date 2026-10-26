<script setup>
import { t } from '../utils/i18n';
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
    <p v-if="error" class="error inline-error" role="alert">{{ t(error) }} <button :aria-label="t(&quot;알림 닫기&quot;)" @click="$emit('dismiss-error')">×</button></p>
    <p v-if="notice" class="notice" role="status">{{ t(notice) }} <button :aria-label="t(&quot;알림 닫기&quot;)" @click="$emit('dismiss-notice')">×</button></p>
    <form class="composer" @submit.prevent="$emit('send')">
      <label class="composer-title" for="safety-question">{{ t("상황을 자세히 알려주세요") }}</label>
      <textarea id="safety-question"
        :value="draft"
        :aria-label="t(&quot;안전 질문&quot;)"
        :placeholder="t(&quot;물질명, 노출된 사람, 화재 여부 등을 알려주세요…&quot;)"
        rows="2"
        maxlength="6000"
        :disabled="inputDisabled"
        @input="$emit('update:draft', $event.target.value)"
        @keydown="handleKeydown"
      ></textarea>
      <div class="composer-tools">
        <div>
          <input ref="pdf" type="file" accept="application/pdf,.pdf" hidden @change="handleFile">
          <button type="button" class="attach" :disabled="inputDisabled" :aria-label="t(&quot;PDF 자료 첨부&quot;)" :title="t(&quot;PDF 자료 첨부&quot;)" @click="$refs.pdf.click()">＋</button>
          <span class="tool-divider"></span>
          <span class="document-mode">{{ t("문서 기반 답변") }}</span>
          <span v-if="uploading" class="upload-label" role="status">{{ t("PDF 처리 중…") }}</span>
        </div>
        <div class="input-actions">
          <button type="button" class="microphone-button" :class="{recording:voiceState === 'recording'}" :aria-label="voiceLabel" :title="voiceLabel" :aria-pressed="voiceState === 'recording'" :disabled="busy || uploading || ttsLoading" @click="$emit('voice')">
            <svg v-if="voiceState !== 'recording'" viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0014 0v-2M12 19v3m-4 0h8"/></svg>
            <span v-else aria-hidden="true">■</span>
          </button>
          <button class="send-button" :aria-label="t(&quot;질문 보내기&quot;)" :disabled="!props.draft.trim() || inputDisabled"><span>{{ t("질문 보내기") }}</span> ↑</button>
        </div>
      </div>
      <p class="voice-status" :class="{recording:voiceState === 'recording'}" role="status">{{ t(voiceState === 'recording' ? '실시간 인식 중 · 말한 뒤 3초간 조용하면 자동으로 질문해요. 최대 60초' : voiceState === 'idle' ? '마이크로 말하면 실시간 입력 · 3초 무음 뒤 자동 질문' : voiceLabel) }}</p>
    </form>
    <p class="emergency-note">{{ t("긴급한 구조가 필요하면 AI 응답을 기다리지 말고 119에 연락하세요.") }}</p>
    <p class="composer-disclaimer">{{ t("AI 답변은 참고용입니다. 실제 작업 시 현장 안전 지침을 우선 확인하세요.") }}</p>
  </div>
</template>
