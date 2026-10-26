<script setup>
import { t } from '../utils/i18n';
import { computed } from 'vue';
import { contactName } from '../utils/answerPresentation';
import { contactUi } from '../utils/contactUi';
const props = defineProps({ contacts: { type: Array, default: () => [] }, demo: Boolean, language: { type: String, default: 'ko' } });
const copy = computed(() => contactUi(props.language));
</script>
<template>
  <section v-for="contact in contacts" :key="contact.number" class="contact-card glass-card" :lang="language">
    <h2>{{ t(contact.displayName || contactName(contact)) }}</h2>
    <span v-if="contact.originalName && contact.originalName !== contact.displayName" class="contact-original-name" lang="ko">{{ t(contact.originalName) }}</span>
    <strong class="contact-number">{{ t(contact.number) }}</strong>
    <span v-if="contact.displayAvailability || contact.availability" class="contact-note">{{ t(contact.displayAvailability || contact.availability) }}</span>
    <details v-if="!demo && contact.dialable" class="call-confirmation">
      <summary class="call-button">☎ {{ t(copy.call) }}</summary>
      <p>{{ t(copy.confirm) }}</p>
      <a class="call-button" :href="`tel:${contact.dialNumber}`">{{ t(contact.number) }} {{ t(copy.open) }}</a>
    </details>
    <button v-else class="call-button" disabled>☎ {{ t(copy.preview) }}</button>
  </section>
  <section v-if="!contacts.length" class="contact-card glass-card" :lang="language">
    <h2>{{ t(copy.heading) }}</h2>
    <p>{{ t(copy.empty) }}</p>
    <p class="contact-note">{{ t(copy.note) }}</p>
  </section>
</template>
