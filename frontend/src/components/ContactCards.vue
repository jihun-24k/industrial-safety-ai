<script setup>
import { computed } from 'vue';
import { contactName } from '../utils/answerPresentation';
import { contactUi } from '../utils/contactUi';
const props = defineProps({ contacts: { type: Array, default: () => [] }, demo: Boolean, language: { type: String, default: 'ko' } });
const copy = computed(() => contactUi(props.language));
</script>
<template>
  <section v-for="contact in contacts" :key="contact.number" class="contact-card glass-card" :lang="language">
    <h2>{{ contact.displayName || contactName(contact) }}</h2>
    <span v-if="contact.originalName && contact.originalName !== contact.displayName" class="contact-original-name" lang="ko">{{ contact.originalName }}</span>
    <strong class="contact-number">{{ contact.number }}</strong>
    <span v-if="contact.displayAvailability || contact.availability" class="contact-note">{{ contact.displayAvailability || contact.availability }}</span>
    <details v-if="!demo && contact.dialable" class="call-confirmation">
      <summary class="call-button">☎ {{ copy.call }}</summary>
      <p>{{ copy.confirm }}</p>
      <a class="call-button" :href="`tel:${contact.dialNumber}`">{{ contact.number }} {{ copy.open }}</a>
    </details>
    <button v-else class="call-button" disabled>☎ {{ copy.preview }}</button>
  </section>
  <section v-if="!contacts.length" class="contact-card glass-card" :lang="language">
    <h2>{{ copy.heading }}</h2>
    <p>{{ copy.empty }}</p>
    <p class="contact-note">{{ copy.note }}</p>
  </section>
</template>
