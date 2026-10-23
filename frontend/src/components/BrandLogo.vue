<script setup>
defineProps({
  showLabel: { type: Boolean, default: false },
});
</script>

<template>
  <a class="brand" href="/">
    <span class="brand-icon">◇</span>
    세이프메이트
    <span v-if="showLabel" class="brand-label">SAFEMATE</span>
  </a>
</template>
