<script setup>
import { onMounted, ref } from 'vue';
import { authApi } from './api/authApi';
import LoginPage from './pages/LoginPage.vue';
import ChatPage from './pages/ChatPage.vue';

const user = ref(null);
const demo = ref(false);
const checking = ref(true);

onMounted(async () => {
  try {
    const data = await authApi.check();
    if (data.ok) user.value = data.username;
  } catch {
    // A failed check means the visitor should see the signed-out screen.
  } finally {
    checking.value = false;
  }
});

function handleAuthenticated(username) {
  user.value = username;
  demo.value = false;
}

function handlePreview() {
  user.value = '미리보기';
  demo.value = true;
}

function handleSignedOut() {
  user.value = null;
  demo.value = false;
}
</script>

<template>
  <div v-if="checking" class="boot" role="status">SafeOps를 준비하고 있어요…</div>
  <LoginPage
    v-else-if="!user"
    @authenticated="handleAuthenticated"
    @preview="handlePreview"
  />
  <ChatPage
    v-else
    :user="user"
    :demo="demo"
    @signed-out="handleSignedOut"
  />
</template>
