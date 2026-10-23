<script setup>
defineProps({ showLabel: { type: Boolean, default: false } });
</script>
<template>
  <a class="brand" href="/" aria-label="SafeOps 홈">
    <img src="/brand/safeops-symbol.svg" alt="" width="30" height="30">
    <span class="brand-wordmark">SafeOps</span>
    <span v-if="showLabel" class="brand-label">산업안전 AI</span>
  </a>
</template>
