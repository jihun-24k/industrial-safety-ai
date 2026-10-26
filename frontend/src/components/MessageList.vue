<script setup>
import { nextTick, ref } from 'vue';
import AnswerCards from './AnswerCards.vue';
import ContactCards from './ContactCards.vue';
import { translationFor, speechLanguages, localizedContacts } from '../utils/translation';
import { contactUi } from '../utils/contactUi';
import SafetyAssistant from './SafetyAssistant.vue';
import { answerSections, displayAnswerSections, answerContacts, compactSources, contactCondensedText, isInformationOnly, questionForReply } from '../utils/answerPresentation';

const props = defineProps({
  messages: { type: Array, default: () => [] },
  user: { type: String, required: true },
  busy: { type: Boolean, default: false },
  speechLanguage: { type: String, default: 'ko' },
  ttsLoading: { type: String, default: null },
  speakingId: { type: String, default: null },
  examples: { type: Array, default: () => [] },
  demo: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
});
defineEmits(['send-example', 'speak', 'feedback']);
const container = ref(null);
const descriptions = ['누출과 확산 상황 확인', '화재 관련 근거 확인', '피부, 눈, 흡입 상황 확인'];
const informational = message => isInformationOnly(questionForReply(props.messages, message));
const contactsFor = message => informational(message) ? [] : (message.contacts || answerContacts(message.text));
const translated = message => props.speechLanguage === 'ko' || message.streaming ? null : translationFor(message, props.speechLanguage);
const translatedSections = message => answerSections(translated(message)?.translated_text || '');
const languageLabel = () => speechLanguages.find(item => item.code === props.speechLanguage)?.label;
const sectionsFor = message => message.streaming ? answerSections(message.text) : displayAnswerSections(contactCondensedText(message.text, contactsFor(message)));
async function scrollToBottom() {
  await nextTick();
  container.value?.scrollTo({ top: container.value.scrollHeight, behavior: 'smooth' });
}
defineExpose({ scrollToBottom });
</script>

<template>
  <div ref="container" class="message-scroll" :class="{ welcome: !messages.length }">
    <section v-if="!messages.length" class="welcome-content">
      <div class="welcome-hero">
        <div class="welcome-copy">
          <span class="section-tag">INTELLIGENCE FOR SAFER OPERATIONS</span>
          <h1 class="desktop-greeting">안전을 위한 다음 행동,<br>함께 확인해요.</h1>
          <h1 class="mobile-greeting">안녕하세요!<br>어떤 상황인가요?</h1>
          <p>지금 상황을 선택하거나, 아래에 직접 이야기해 주세요.</p>
        </div>
        <SafetyAssistant />
      </div>
      <div class="suggestions">
        <button v-for="(example, index) in examples" :key="example" :disabled="disabled" @click="$emit('send-example', example)">
          <strong>{{ example }}<span class="mobile-arrow"> →</span></strong>
          <span class="suggestion-description">{{ descriptions[index] }}</span>
          <span class="suggestion-cta">상황 선택 →</span>
        </button>
      </div>
    </section>

    <div v-else class="messages">
      <article v-for="message in messages" :key="message.id" class="message" :class="message.role">
        <div class="message-author">
          <img v-if="message.role === 'assistant'" src="/brand/safeops-symbol.svg" alt="" width="30" height="30">
          <span v-else class="avatar">{{ user.slice(0, 1) }}</span>
          <strong>{{ message.role === 'assistant' ? 'SafeOps' : user }}</strong>
          <span v-if="message.preview" class="preview-label">예시 답변 · 실제 검색 없음</span>
        </div>
        <div v-if="message.pending" class="thinking glass-card" role="status">{{ message.status || '답변을 준비하고 있어요…' }}<span class="dots">···</span></div>
        <div v-else-if="message.role === 'user'" class="user-message">
          {{ message.text }}
          <details v-if="message.normalizedText && message.normalizedText !== message.text" class="input-translation">
            <summary>한국어로 해석한 질문</summary>
            <div lang="ko">{{ message.normalizedText }}</div>
          </details>
        </div>
        <div v-else class="response-layout">
          <div class="response-main">
            <section v-if="message.handoff || (message.needsReview && !informational(message))" class="review-card glass-card">
              <h2>! {{ message.handoff ? '담당자 확인이 필요해요' : '추가 확인이 필요해요' }}</h2>
              <p>{{ message.handoff ? '관련 문서 근거가 충분하지 않습니다. 기관의 안전관리자에게 확인하세요.' : '사람의 노출 여부와 현장 상황을 확인해 주세요. AI가 사고 심각도를 확정하지 않습니다.' }}</p>
            </section>
            <section v-if="message.clarifyingQuestions?.length && !informational(message)" class="glass-card">
              <h2>상황 확인</h2>
              <ul><li v-for="question in message.clarifyingQuestions" :key="question">{{ question }}</li></ul>
            </section>
            <template v-if="translated(message)">
              <p class="translation-label" role="status">{{ languageLabel() }} 번역</p>
              <AnswerCards :sections="translatedSections(message)" :language="speechLanguage" />
              <details class="original-answer glass-card">
                <summary>한국어 원문 보기</summary>
                <div class="original-answer-cards"><AnswerCards :sections="sectionsFor(message)" /></div>
              </details>
            </template>
            <AnswerCards v-else :sections="sectionsFor(message)" :streaming="message.streaming" />
            <details v-if="message.sources?.length" class="sources-card glass-card">
              <summary>근거 문서 확인 <span>{{ message.sources.length }}개</span></summary>
              <ul><li v-for="source in message.sources" :key="source">{{ compactSources(source) }}</li></ul>
            </details>
            <p v-else-if="!message.streaming" class="source-note">{{ message.source }}</p>
            <button v-if="!message.streaming && message.text" class="listen-button" :disabled="!!ttsLoading" :aria-pressed="speakingId === message.id" @click="$emit('speak', message)">
              {{ ttsLoading === message.id ? '◌ 음성 준비 중…' : speakingId === message.id ? '■ 재생 중지' : speechLanguage === 'ko' ? '◖ 답변 듣기' : '◖ 번역하고 듣기' }}
            </button>
            <div v-if="message.logId && !message.streaming && !demo" class="feedback-row" role="group" aria-label="답변 평가">
              <span>이 답변이 도움이 됐나요?</span>
              <button type="button" :aria-pressed="message.feedback === 1" :disabled="message.feedbackSaving" @click="$emit('feedback', message, 1)">▲ 도움됐어요</button>
              <button type="button" :aria-pressed="message.feedback === -1" :disabled="message.feedbackSaving" @click="$emit('feedback', message, -1)">▼ 아쉬워요</button>
            </div>
          </div>
          <aside v-if="!message.streaming && contactsFor(message).length" class="response-contacts" :aria-label="contactUi(speechLanguage).heading">
            <ContactCards :contacts="localizedContacts(message, speechLanguage, contactsFor(message))" :demo="demo" :language="speechLanguage" />
          </aside>
        </div>
      </article>
    </div>
  </div>
</template>
