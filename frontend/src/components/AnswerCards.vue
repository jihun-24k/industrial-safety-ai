<script setup>
import { answerFragments } from '../utils/answerPresentation';

defineProps({
  sections: { type: Array, default: () => [] },
  streaming: { type: Boolean, default: false },
  language: { type: String, default: 'ko' },
});
const immediate = heading => /즉시|응급|immediate|emergency|立即|紧急|緊急|応急|khẩn cấp/i.test(heading);
</script>

<template>
  <section v-for="(section, index) in sections" :key="index" class="answer-section glass-card" :class="{ 'answer-section--immediate': immediate(section.heading) }" :lang="language">
    <div v-if="section.heading" class="answer-card-heading"><span class="answer-step" aria-hidden="true">{{ section.number || String(index + 1).padStart(2, '0') }}</span><h2>{{ section.heading }}</h2></div>
    <div class="message-text"><template v-for="(fragment, fragmentIndex) in answerFragments(section.text)" :key="fragmentIndex"><span v-if="fragment.citation" class="citation-badge" :aria-label="`출처 ${fragment.text}`">{{ fragment.text }}</span><template v-else>{{ fragment.text }}</template></template><span v-if="streaming && index === sections.length - 1" class="dots">···</span></div>
  </section>
</template>
