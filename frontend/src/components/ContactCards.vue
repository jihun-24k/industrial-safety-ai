<script setup>
import { contactName } from '../utils/answerPresentation';
defineProps({ contacts: { type: Array, default: () => [] }, demo: Boolean });
</script>
<template>
            <section v-for="contact in contacts" :key="contact.number" class="contact-card glass-card">
              <h2>{{ contactName(contact) }}</h2>
              <strong class="contact-number">{{ contact.number }}</strong>
              <span v-if="contact.availability" class="contact-note">{{ contact.availability }}</span>
              <details v-if="!demo && contact.dialable" class="call-confirmation">
                <summary class="call-button">☎ 전화하기</summary>
                <p>현재 기관에 맞는 번호인지 확인한 뒤 전화 앱을 여세요.</p>
                <a class="call-button" :href="`tel:${contact.dialNumber}`">{{ contact.number }} 전화 앱 열기</a>
              </details>
              <button v-else class="call-button" disabled>☎ 전화하기 · 미리보기</button>
            </section>
            <section v-if="!contacts.length" class="contact-card glass-card">
              <h2>담당 연락처</h2>
              <p>답변에서 통화 가능한 번호가 확인되지 않았어요.</p>
              <p class="contact-note">기관의 비상연락망을 확인하세요. 지역번호나 담당자를 임의로 보충하지 않습니다.</p>
            </section>

</template>
