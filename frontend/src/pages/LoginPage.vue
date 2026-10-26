<script setup>
import { t } from '../utils/i18n';
import { ref } from 'vue';
import { authApi } from '../api/authApi';
import BrandLogo from '../components/BrandLogo.vue';
import SafetyAssistant from '../components/SafetyAssistant.vue';

const emit = defineEmits(['authenticated', 'preview']);
const username = ref('');
const password = ref('');
const busy = ref(false);
const error = ref('');
const mode = ref('login');
const confirmation = ref('');
const success = ref('');

function switchMode() {
  if (busy.value) return;
  mode.value = mode.value === 'login' ? 'signup' : 'login';
  password.value = '';
  confirmation.value = '';
  error.value = '';
  success.value = '';
}

async function login() {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  success.value = '';

  try {
    const normalizedUsername = username.value.trim();
    if (!normalizedUsername) throw new Error('아이디를 입력해 주세요.');
    if (mode.value === 'signup') {
      if (password.value !== confirmation.value) throw new Error('비밀번호가 일치하지 않습니다.');
      if (password.value !== password.value.trim()) throw new Error('비밀번호 앞뒤에는 공백을 사용할 수 없습니다.');
      if (new TextEncoder().encode(password.value).length > 72) throw new Error('비밀번호는 UTF-8 기준 72바이트 이내로 입력해 주세요.');
      await authApi.signup(normalizedUsername, password.value);
      mode.value = 'login';
      password.value = '';
      confirmation.value = '';
      success.value = '회원가입이 완료되었습니다. 등록한 계정으로 로그인해 주세요.';
      return;
    }
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
        <h1>{{ t("안전한 하루의 시작,") }}<br>{{ t("물어보는 것부터.") }}</h1>
        <p>{{ t("작업 전 궁금한 안전 수칙부터 현장의 작은 질문까지.") }}<br>{{ t("산업안전 AI 파트너와 함께 확인하세요.") }}</p>
        <div class="story-illustration"><SafetyAssistant /></div>
      </div>
      <div class="story-footer">{{ t("작은 확인이 더 안전한 현장을 만듭니다.") }}</div>
    </section>

    <section class="login-panel">
      <div class="login-form">
        <span class="section-tag">{{ t("산업안전 AI 어시스턴트") }}</span>
        <h2>{{ t(mode === 'signup' ? '안전한 시작을 함께해요' : '다시 만나 반가워요') }}</h2>
        <p class="muted">{{ t(mode === 'signup' ? '계정을 만들고 산업안전 AI와 대화를 시작하세요.' : '로그인하고 안전에 대한 대화를 시작하세요.') }}</p>
        <form @submit.prevent="login">
          <label for="username">{{ t("아이디") }}</label>
          <input id="username" v-model="username" autocomplete="username" :placeholder="t(&quot;아이디를 입력해 주세요&quot;)" maxlength="100" required :disabled="busy">
          <label for="password">{{ t("비밀번호") }}</label>
          <input id="password" v-model="password" type="password" :autocomplete="mode === 'signup' ? 'new-password' : 'current-password'" :placeholder="t(&quot;비밀번호를 입력해 주세요&quot;)" required :disabled="busy">
          <template v-if="mode === 'signup'">
            <label for="confirmation">{{ t("비밀번호 확인") }}</label>
            <input id="confirmation" v-model="confirmation" type="password" autocomplete="new-password" :placeholder="t(&quot;비밀번호를 다시 입력해 주세요&quot;)" required :disabled="busy">
          </template>
          <p v-if="error" class="error" role="alert">{{ t(error) }}</p>
          <p v-if="success" class="auth-success" role="status">{{ t(success) }}</p>
          <button class="primary login-submit" :disabled="busy">{{ t(busy ? '처리 중…' : mode === 'signup' ? '회원가입' : '로그인') }} <span>→</span></button>
        </form>
        <p class="auth-switch">{{ t(mode === 'signup' ? '이미 계정이 있으신가요?' : '처음 방문하셨나요?') }} <button type="button" :disabled="busy" @click="switchMode">{{ t(mode === 'signup' ? '로그인하기' : '회원가입') }}</button></p>
        <div class="divider"><span>{{ t("먼저 둘러보고 싶다면") }}</span></div>
        <button class="preview-button" :disabled="busy" @click="emit('preview')">{{ t("화면 미리보기 ") }}<span>↗</span></button>
        <p class="login-footnote">{{ t("미리보기에서는 예시 대화와 음성 재생을 체험할 수 있어요.") }}</p>
      </div>
      <p class="login-copyright">{{ t("© SafeOps · 더 안전한 일상을 함께") }}</p>
    </section>
  </main>
</template>
