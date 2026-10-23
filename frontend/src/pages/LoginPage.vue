<script setup>
import { ref } from 'vue';
import { authApi } from '../api/authApi';
import BrandLogo from '../components/BrandLogo.vue';

const emit = defineEmits(['authenticated', 'preview']);
const username = ref('');
const password = ref('');
const busy = ref(false);
const error = ref('');

async function login() {
  if (busy.value) return;
  busy.value = true;
  error.value = '';

  try {
    const normalizedUsername = username.value.trim();
    const data = await authApi.login(normalizedUsername, password.value);
    if (!data.ok) throw new Error('아이디와 비밀번호를 확인해 주세요.');
    password.value = '';
    emit('authenticated', normalizedUsername);
  } catch (loginError) {
    error.value = loginError.message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <main class="login-layout">
    <section class="login-story">
      <BrandLogo show-label />
      <div class="story-copy">
        <div class="eyebrow">YOUR SAFETY, OUR PRIORITY</div>
        <h1>안전한 하루의 시작,<br>물어보는 것부터.</h1>
        <p>작업 전 궁금한 안전 수칙부터 현장의 작은 질문까지.<br>산업안전 AI 파트너와 함께 확인하세요.</p>
        <div class="story-illustration" aria-hidden="true">
          <div class="orbit orbit-one"></div>
          <div class="orbit orbit-two"></div>
          <div class="illustration-shield">◇<span>✓</span></div>
          <div class="floating-note note-one"><span>✓</span> 작업 전 안전 확인</div>
          <div class="floating-note note-two"><span>◖</span> 듣는 안전 가이드</div>
        </div>
      </div>
      <div class="story-footer">작은 확인이 더 안전한 현장을 만듭니다.</div>
    </section>

    <section class="login-panel">
      <div class="login-form">
        <span class="section-tag">산업안전 AI 어시스턴트</span>
        <h2>다시 만나 반가워요</h2>
        <p class="muted">로그인하고 안전에 대한 대화를 시작하세요.</p>
        <form @submit.prevent="login">
          <label for="username">아이디</label>
          <input id="username" v-model="username" autocomplete="username" placeholder="아이디를 입력해 주세요" required :disabled="busy">
          <label for="password">비밀번호</label>
          <input id="password" v-model="password" type="password" autocomplete="current-password" placeholder="비밀번호를 입력해 주세요" required :disabled="busy">
          <p v-if="error" class="error" role="alert">{{ error }}</p>
          <button class="primary login-submit" :disabled="busy">{{ busy ? '로그인 중…' : '로그인' }} <span>→</span></button>
        </form>
        <div class="divider"><span>먼저 둘러보고 싶다면</span></div>
        <button class="preview-button" :disabled="busy" @click="emit('preview')">화면 미리보기 <span>↗</span></button>
        <p class="login-footnote">미리보기에서는 예시 대화와 음성 재생을 체험할 수 있어요.</p>
      </div>
      <p class="login-copyright">© SAFEMATE · 더 안전한 일상을 함께</p>
    </section>
  </main>
</template>
