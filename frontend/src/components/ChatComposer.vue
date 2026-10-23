<script setup>
const props = defineProps({
  draft: { type: String, default: '' },
  source: { type: String, default: 'web' },
  busy: { type: Boolean, default: false },
  uploading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  notice: { type: String, default: '' },
});

const emit = defineEmits([
  'update:draft',
  'update:source',
  'send',
  'upload',
  'dismiss-error',
  'dismiss-notice',
]);

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
        :disabled="busy || uploading"
        @input="$emit('update:draft', $event.target.value)"
        @keydown="handleKeydown"
      ></textarea>
      <div class="composer-tools">
        <div>
          <input ref="pdf" type="file" accept="application/pdf,.pdf" hidden @change="handleFile">
          <button type="button" class="attach" :disabled="busy || uploading" aria-label="PDF 자료 첨부" title="PDF 자료 첨부" @click="$refs.pdf.click()">＋</button>
          <span class="tool-divider"></span>
          <label class="source-select">
            <span class="sr-only">검색 자료</span>
            <select :value="source" :disabled="busy || uploading" @change="$emit('update:source', $event.target.value)">
              <option value="web">웹 자료</option>
              <option value="pdf">PDF 자료</option>
            </select>
          </label>
          <span v-if="uploading" class="upload-label" role="status">PDF 처리 중…</span>
        </div>
        <button class="send-button" aria-label="질문 보내기" :disabled="!props.draft.trim() || busy || uploading">↑</button>
      </div>
    </form>
    <p class="composer-disclaimer">AI 답변은 참고용입니다. 실제 작업 시 현장 안전 지침을 우선 확인하세요.</p>
  </div>
</template>
