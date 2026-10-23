import { createApp, nextTick } from 'vue/dist/vue.esm-bundler.js';
import './style.css';

const icon = (name) => ({ shield: '◇', plus: '+', arrow: '↑', sound: '◖', close: '×', file: '↥' }[name]);
createApp({
  data: () => ({
    user: null, demo: false, checking: true, username: '', password: '', loginBusy: false,
    loginError: '', error: '', notice: '', draft: '', busy: false, uploading: false, source: 'web',
    conversations: [], activeId: null, menu: false, speakingId: null, ttsLoading: null,
    examples: ['작업 전 안전 점검 항목을 알려줘', '보호구 착용 기준이 궁금해요', '추락 사고 예방 수칙을 설명해줘'],
  }),
  computed: {
    conversation() { return this.conversations.find(c => c.id === this.activeId); },
    messages() { return this.conversation?.messages || []; },
  },
  async mounted() {
    try { const data = await this.request('/auth-api/auth/check'); if (data.ok) this.user = data.username; } catch { /* Signed-out state. */ }
    this.checking = false;
  },
  methods: {
    icon,
    async request(url, options = {}) {
      const response = await fetch(url, { ...options, credentials: 'include', signal: options.signal || AbortSignal.timeout(90000) });
      const type = response.headers.get('content-type') || '';
      const data = type.includes('application/json') ? await response.json() : await response.text();
      if (!response.ok) {
        if (response.status === 401) throw new Error('로그인이 필요하거나 만료되었습니다. 다시 로그인해 주세요.');
        throw new Error(typeof data === 'object' ? (typeof data.detail === 'string' ? data.detail : data.error || '요청을 처리하지 못했습니다.') : '서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.');
      }
      return data;
    },
    async login() {
      if (this.loginBusy) return;
      this.loginBusy = true; this.loginError = '';
      try {
        const data = await this.request('/auth-api/login', { method: 'POST', body: new URLSearchParams({ username: this.username.trim(), password: this.password }) });
        if (!data.ok) throw new Error('아이디와 비밀번호를 확인해 주세요.');
        this.user = this.username.trim(); this.password = ''; this.demo = false;
      } catch (e) { this.loginError = e.message; }
      finally { this.loginBusy = false; }
    },
    preview() { this.user = '미리보기'; this.demo = true; this.loginError = ''; },
    stopAudio() {
      this.audio?.pause(); this.audio = null;
      window.speechSynthesis?.cancel(); this.speakingId = null;
    },
    async logout() {
      if (this.busy || this.uploading || this.ttsLoading) return;
      try {
        if (!this.demo) {
          // Logout redirects to the Java login page; the proxy serves that response.
          await this.request('/auth-api/logout', { method: 'POST' });
        }
        this.stopAudio(); this.user = null; this.demo = false; this.conversations = []; this.activeId = null; this.error = ''; this.menu = false;
      } catch (e) { this.error = e.message; }
    },
    newChat() {
      if (this.busy || this.uploading || this.ttsLoading) return;
      this.stopAudio(); this.activeId = null; this.draft = ''; this.error = ''; this.source = 'web'; this.notice = ''; this.menu = false;
    },
    selectChat(chat) {
      if (this.busy || this.uploading || this.ttsLoading) return;
      this.stopAudio(); this.activeId = chat.id; this.source = chat.source; this.error = ''; this.menu = false; this.scroll();
    },
    async scroll() { await nextTick(); this.$refs.messages?.scrollTo({ top: this.$refs.messages.scrollHeight, behavior: 'smooth' }); },
    async send(text) {
      const prompt = (text || this.draft).trim();
      if (!prompt || this.busy || this.uploading) return;
      if (!this.conversation) {
        const chat = { id: crypto.randomUUID(), title: prompt.slice(0, 26), source: this.source, messages: [] };
        this.conversations.unshift(chat); this.activeId = chat.id;
      }
      const chat = this.conversation;
      chat.source = this.source;
      chat.messages.push({ id: crypto.randomUUID(), role: 'user', text: prompt });
      this.draft = ''; this.error = ''; this.busy = true; this.scroll();
      try {
        let answer;
        if (this.demo) {
          answer = '이 답변은 화면과 음성 재생을 확인하기 위한 예시입니다. 실제 자료 검색은 수행하지 않았습니다.\n\n로그인 후 질문을 보내면 연결된 자료를 검색해 답변합니다. PDF를 첨부하거나 검색 자료를 선택할 수 있습니다.\n\n답변 아래의 ‘답변 듣기’를 누르면 음성이 재생됩니다.';
        } else {
          const data = await this.request('/rag-api/rag-query', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt, source: this.source, top_k: 5 }) });
          if (typeof data.response !== 'string' || !data.response.trim()) throw new Error('답변이 비어 있습니다. 다시 질문해 주세요.');
          answer = data.response;
        }
        chat.messages.push({ id: crypto.randomUUID(), role: 'assistant', text: answer, source: this.demo ? '화면 미리보기' : this.source === 'pdf' ? 'PDF 자료 기반' : '웹 자료 기반' });
      } catch (e) { this.error = e.message; this.draft = prompt; }
      finally { this.busy = false; this.scroll(); this.$refs.draft?.focus(); }
    },
    onKey(event) { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); this.send(); } },
    async upload(event) {
      const file = event.target.files?.[0]; event.target.value = '';
      if (!file || this.busy || this.uploading) return;
      if (!file.name.toLowerCase().endsWith('.pdf')) { this.error = 'PDF 파일을 선택해 주세요.'; return; }
      if (this.demo) { this.error = '미리보기에서는 파일을 전송하지 않습니다. 실제 로그인 후 첨부해 주세요.'; return; }
      this.uploading = true; this.error = '';
      try {
        const body = new FormData(); body.append('file', file);
        await this.request('/rag-api/upload-paper', { method: 'POST', body });
        this.source = 'pdf'; this.notice = `${file.name} 자료가 준비되었습니다.`;
      } catch (e) { this.error = e.message; }
      finally { this.uploading = false; }
    },
    async speak(message) {
      if (this.ttsLoading) return;
      if (this.speakingId === message.id) { this.stopAudio(); return; }
      this.stopAudio(); this.error = ''; this.ttsLoading = message.id;
      try {
        if (this.demo) {
          if (!window.speechSynthesis) throw new Error('이 브라우저에서는 음성 미리보기를 지원하지 않습니다.');
          const utterance = new SpeechSynthesisUtterance(message.text); utterance.lang = 'ko-KR';
          utterance.onend = () => { this.speakingId = null; };
          utterance.onerror = () => { this.speakingId = null; };
          this.speakingId = message.id; window.speechSynthesis.speak(utterance);
        } else {
          const data = await this.request('/voice-api/tts/', { method: 'POST', body: new URLSearchParams({ text: message.text }) });
          if (!data.file_path?.startsWith('/uploads/')) throw new Error('음성 파일을 받지 못했습니다.');
          this.audio = new Audio(`/voice-api${data.file_path}?t=${Date.now()}`);
          this.audio.onended = () => { this.speakingId = null; };
          this.audio.onerror = () => { this.speakingId = null; this.error = '음성 파일을 재생하지 못했습니다.'; };
          await this.audio.play(); this.speakingId = message.id;
        }
      } catch (e) { this.error = e.message; this.stopAudio(); }
      finally { this.ttsLoading = null; }
    },
  },
  template: `
    <div v-if="checking" class="boot" role="status">세이프메이트를 준비하고 있어요…</div>
    <main v-else-if="!user" class="login-layout">
      <section class="login-story"><a class="brand" href="/"> <span class="brand-icon">◇</span> 세이프메이트<span class="brand-label">SAFEMATE</span></a>
        <div class="story-copy"><div class="eyebrow">YOUR SAFETY, OUR PRIORITY</div><h1>안전한 하루의 시작,<br>물어보는 것부터.</h1><p>작업 전 궁금한 안전 수칙부터 현장의 작은 질문까지.<br>산업안전 AI 파트너와 함께 확인하세요.</p>
        <div class="story-illustration" aria-hidden="true"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="illustration-shield">◇<span>✓</span></div><div class="floating-note note-one"><span>✓</span> 작업 전 안전 확인</div><div class="floating-note note-two"><span>◖</span> 듣는 안전 가이드</div></div></div>
        <div class="story-footer">작은 확인이 더 안전한 현장을 만듭니다.</div>
      </section>
      <section class="login-panel"><div class="login-form"><span class="section-tag">산업안전 AI 어시스턴트</span><h2>다시 만나 반가워요</h2><p class="muted">로그인하고 안전에 대한 대화를 시작하세요.</p>
        <form @submit.prevent="login"><label for="username">아이디</label><input id="username" v-model="username" autocomplete="username" placeholder="아이디를 입력해 주세요" required :disabled="loginBusy"><label for="password">비밀번호</label><input id="password" v-model="password" type="password" autocomplete="current-password" placeholder="비밀번호를 입력해 주세요" required :disabled="loginBusy"><p v-if="loginError" class="error" role="alert">{{loginError}}</p><button class="primary login-submit" :disabled="loginBusy">{{loginBusy ? '로그인 중…' : '로그인'}} <span>→</span></button></form>
        <div class="divider"><span>먼저 둘러보고 싶다면</span></div><button class="preview-button" @click="preview" :disabled="loginBusy">화면 미리보기 <span>↗</span></button><p class="login-footnote">미리보기에서는 예시 대화와 음성 재생을 체험할 수 있어요.</p>
      </div><p class="login-copyright">© SAFEMATE · 더 안전한 일상을 함께</p></section>
    </main>
    <div v-else class="chat-layout">
      <button v-if="menu" class="sidebar-overlay" @click="menu=false" aria-label="메뉴 닫기"></button>
      <aside class="sidebar" :class="{open:menu}"><a class="brand" href="/" @click.prevent="newChat"><span class="brand-icon">◇</span> 세이프메이트</a><span class="sidebar-subtitle">산업안전 AI 파트너</span>
        <button class="new-chat" @click="newChat" :disabled="busy || uploading || !!ttsLoading">＋ <span>새 대화 시작</span><span>↗</span></button>
        <div class="history-label">대화 기록 <span>{{conversations.length}}</span></div><nav class="history" aria-label="대화 기록"><p v-if="!conversations.length" class="empty-history">첫 번째 대화를 시작해 보세요.</p><button v-for="chat in conversations" :key="chat.id" :class="{selected:activeId===chat.id}" @click="selectChat(chat)" :disabled="busy || uploading || !!ttsLoading"><span>◌</span> {{chat.title}}</button></nav>
        <div class="sidebar-bottom"><div class="privacy-note"><span>◇</span><p>안전을 위한 질문,<br><strong>언제든 편하게 물어보세요.</strong></p></div><div class="account"><span class="avatar">{{user.slice(0,1)}}</span><div><strong>{{user}}</strong><small>{{demo ? '화면 미리보기' : '로그인됨'}}</small></div><button @click="logout" :disabled="busy || uploading || !!ttsLoading" aria-label="로그아웃" title="로그아웃">↪</button></div></div>
      </aside>
      <main class="workspace"><header class="chat-header"><div><button class="mobile-menu" @click="menu=true" aria-label="메뉴 열기">☰</button><strong>안전 어시스턴트</strong><span class="header-separator">/</span><span class="header-caption">함께 만드는 안전한 현장</span></div><span class="status-badge"><i></i>{{demo ? '미리보기' : 'AI 어시스턴트'}}</span></header>
        <div v-if="demo" class="demo-banner">화면 미리보기 모드입니다. 답변은 예시이며 실제 자료를 검색하지 않습니다.</div>
        <div ref="messages" class="message-scroll" :class="{welcome:!messages.length}">
          <section v-if="!messages.length" class="welcome-content"><div class="welcome-emblem">◇<span>✦</span></div><span class="section-tag">현장의 모든 질문을 함께</span><h1>오늘도 안전하게,<br>무엇을 도와드릴까요?</h1><p>작업 수칙부터 안전 점검까지 편하게 질문하세요.<br>답변은 음성으로도 들을 수 있어요.</p><div class="suggestions"><button v-for="(example,i) in examples" :key="example" @click="send(example)"><span class="suggestion-icon">{{['☑','◇','↗'][i]}}</span><span>{{example}}</span><span class="suggestion-arrow">↗</span></button></div></section>
          <div v-else class="messages"><article v-for="message in messages" :key="message.id" class="message" :class="message.role"><div class="message-avatar">{{message.role==='assistant' ? '◇' : user.slice(0,1)}}</div><div class="message-content"><div class="message-author">{{message.role==='assistant' ? '세이프메이트' : user}} <span v-if="message.source">{{message.source}}</span></div><div class="message-text">{{message.text}}</div><button v-if="message.role==='assistant'" class="listen-button" @click="speak(message)" :disabled="!!ttsLoading" :aria-pressed="speakingId===message.id">{{ttsLoading===message.id ? '◌ 음성 준비 중…' : speakingId===message.id ? '■ 재생 중지' : '◖ 답변 듣기'}}</button></div></article><div v-if="busy" class="thinking" role="status"><span>◇</span> 자료를 확인하고 답변을 준비하고 있어요<span class="dots">···</span></div></div>
        </div>
        <div class="composer-wrap"><p v-if="error" class="error inline-error" role="alert">{{error}} <button @click="error=''" aria-label="알림 닫기">×</button></p><p v-if="notice" class="notice" role="status">{{notice}} <button @click="notice=''" aria-label="알림 닫기">×</button></p><form class="composer" @submit.prevent="send()"><textarea ref="draft" v-model="draft" @keydown="onKey" aria-label="안전 질문" placeholder="안전에 대해 궁금한 점을 물어보세요…" rows="2" maxlength="6000" :disabled="busy || uploading"></textarea><div class="composer-tools"><div><input ref="pdf" type="file" accept="application/pdf,.pdf" hidden @change="upload"><button type="button" class="attach" @click="$refs.pdf.click()" :disabled="busy || uploading" aria-label="PDF 자료 첨부" title="PDF 자료 첨부">＋</button><span class="tool-divider"></span><label class="source-select"><span class="sr-only">검색 자료</span><select v-model="source" :disabled="busy || uploading"><option value="web">웹 자료</option><option value="pdf">PDF 자료</option></select></label><span v-if="uploading" class="upload-label" role="status">PDF 처리 중…</span></div><button class="send-button" aria-label="질문 보내기" :disabled="!draft.trim() || busy || uploading">↑</button></div></form><p class="composer-disclaimer">AI 답변은 참고용입니다. 실제 작업 시 현장 안전 지침을 우선 확인하세요.</p></div>
      </main>
    </div>`,
}).mount('#app');
