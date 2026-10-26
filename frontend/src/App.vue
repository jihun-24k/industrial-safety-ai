<script setup>
import { onMounted, ref } from 'vue';
import { authApi } from './api/authApi';
import LoginPage from './pages/LoginPage.vue';
import ChatPage from './pages/ChatPage.vue';
import DashboardPage from './pages/DashboardPage.vue';

const user = ref(null);
const demo = ref(false);
const checking = ref(true);
const view = ref(window.location.hash === '#ops' ? 'ops' : 'chat');

function showView(next) {
  view.value = next;
  const hash = next === 'ops' ? '#ops' : '';
  if (window.location.hash !== hash) history.replaceState(null, '', `${window.location.pathname}${window.location.search}${hash}`);
}

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
  showView('chat');
}
</script>

<template>
  <div v-if="checking" class="boot" role="status">SafeOps를 준비하고 있어요…</div>
  <LoginPage
    v-else-if="!user"
    @authenticated="handleAuthenticated"
    @preview="handlePreview"
  />
  <DashboardPage
    v-else-if="view === 'ops' && !demo"
    :user="user"
    @back="showView('chat')"
  />
  <ChatPage
    v-else
    :user="user"
    :demo="demo"
    @signed-out="handleSignedOut"
    @open-dashboard="showView('ops')"
  />
</template>
