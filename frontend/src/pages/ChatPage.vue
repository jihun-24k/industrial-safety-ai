<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue';
import { authApi } from '../api/authApi';
import { ragApi } from '../api/ragApi';
import { voiceApi } from '../api/voiceApi';
import ChatComposer from '../components/ChatComposer.vue';
import ChatHeader from '../components/ChatHeader.vue';
import ConversationSidebar from '../components/ConversationSidebar.vue';
import ContactCards from '../components/ContactCards.vue';
import { answerContacts, isInformationOnly, questionForReply } from '../utils/answerPresentation';
import MessageList from '../components/MessageList.vue';
import { createLiveVoiceInput } from '../utils/liveVoiceInput';
import { captureMicrophone } from '../utils/microphone';

const props = defineProps({
  user: { type: String, required: true },
  demo: { type: Boolean, default: false },
});
const emit = defineEmits(['signed-out']);

const draft = ref('');
const busy = ref(false);
const uploading = ref(false);
const voiceState = ref('idle');
const error = ref('');
const notice = ref('');
const conversations = ref([]);
const activeId = ref(null);
const pendingConversation = ref(null);
const menu = ref(false);
const speakingId = ref(null);
const ttsLoading = ref(null);
const speechLanguage = ref('ko');
const messageList = ref(null);
const streamingEnabled = ref(true);
let audio = null;
let queryController = null;

const examples = [
  '물질을 쏟았어요',
  '불이나 연기가 보여요',
  '사람에게 노출됐어요',
];

const conversation = computed(() => pendingConversation.value || conversations.value.find((chat) => chat.id === activeId.value));
const messages = computed(() => conversation.value?.messages || []);
const latestReply = computed(() => [...messages.value].reverse().find(message => message.role === 'assistant'));
const railContacts = computed(() => {
  const reply = latestReply.value;
  return !reply || reply.pending || reply.streaming || isInformationOnly(questionForReply(messages.value, reply)) ? [] : (reply.contacts || answerContacts(reply.text));
});
const controlsDisabled = computed(() => busy.value || uploading.value || !!ttsLoading.value || voiceState.value !== 'idle');

let voiceBase = '';
function updateVoiceDraft(text) {
  const combined = [voiceBase, text].filter(Boolean).join('\n');
  if (combined.length > 6000) throw new Error('음성 질문이 6,000자 제한을 초과합니다. 질문을 짧게 나누어 주세요.');
  draft.value = combined;
}
const voiceRecorder = createLiveVoiceInput({
  openSocket: voiceApi.openStream,
  capture: captureMicrophone,
  onState: state => { voiceState.value = state; },
  onPartial: updateVoiceDraft,
  onFinal: (text, {autoSend}) => {
    updateVoiceDraft(text);
    if (autoSend) {notice.value='';return send();}
    notice.value = '음성을 입력했어요. 내용을 확인하거나 수정한 뒤 보내기를 눌러 주세요.';
  },
  onError: message => { error.value = message; },
});

function toggleVoice() {
  if (voiceState.value === 'recording') { voiceRecorder.stop(); return; }
  if (voiceState.value !== 'idle') { voiceRecorder.cancel(); notice.value='음성 입력을 취소했습니다.'; return; }
  if (controlsDisabled.value) return;
  if (props.demo) { error.value = '음성 질문은 실제 로그인 후 사용할 수 있습니다.'; return; }
  error.value = '';
  notice.value = '';
  stopAudio();
  voiceBase = draft.value.trim();
  voiceRecorder.start();
}

onUnmounted(() => { queryController?.abort(); voiceRecorder.cancel(); stopAudio(); });

onMounted(async () => {
  if (props.demo) return;
  busy.value = true;
  try {
    conversations.value = await ragApi.listConversations();
    if (conversations.value.length) await loadConversation(conversations.value[0]);
  } catch (loadError) {
    error.value = loadError.message;
  } finally {
    busy.value = false;
    scroll();
  }
});

function scroll() {
  messageList.value?.scrollToBottom();
}

function changeSpeechLanguage(language) {
  stopAudio();
  speechLanguage.value = language;
}

function stopAudio() {
  audio?.pause();
  audio = null;
  window.speechSynthesis?.cancel();
  speakingId.value = null;
}

async function logout() {
  if (controlsDisabled.value) return;
  try {
    if (!props.demo) await authApi.logout();
    stopAudio();
    emit('signed-out');
  } catch (logoutError) {
    error.value = logoutError.message;
  }
}

function newChat() {
  if (controlsDisabled.value) return;
  stopAudio();
  activeId.value = null;
  pendingConversation.value = null;
  draft.value = '';
  error.value = '';
  notice.value = '';
  menu.value = false;
}

async function loadConversation(chat) {
  const restored = await ragApi.getConversationMessages(chat.id);
  const index = conversations.value.findIndex(item => item.id === chat.id);
  if (index !== -1) conversations.value[index] = restored;
  activeId.value = restored.id;
  pendingConversation.value = null;
}

async function selectChat(chat) {
  if (controlsDisabled.value) return;
  stopAudio();
  error.value = '';
  menu.value = false;
  if (props.demo) {
    activeId.value = chat.id;
    scroll();
    return;
  }
  busy.value = true;
  try {
    await loadConversation(chat);
  } catch (loadError) {
    error.value = loadError.message;
  } finally {
    busy.value = false;
    scroll();
  }
}

async function send(text = '') {
  const prompt = (text || draft.value).trim();
  if (!prompt || controlsDisabled.value) return;

  if (!conversation.value) {
    const chat = {
      id: props.demo ? crypto.randomUUID() : null,
      title: prompt.slice(0, 26),
      messages: [],
    };
    if (props.demo) {
      conversations.value.unshift(chat);
      activeId.value = chat.id;
    } else {
      pendingConversation.value = chat;
    }
  }

  const chat = conversation.value;
  const userMessage = { id: crypto.randomUUID(), role: 'user', text: prompt };
  chat.messages.push(userMessage);
  draft.value = '';
  error.value = '';
  busy.value = true;
  scroll();

  let assistantMessage = null;
  try {
    if (props.demo) {
      chat.messages.push({
        id: crypto.randomUUID(),
        role: 'assistant',
        text: '이 답변은 화면과 음성 재생을 확인하기 위한 예시입니다. 실제 자료 검색은 수행하지 않았습니다.\n\n로그인 후 문서에 관해 질문하거나 마이크 버튼으로 음성 질문을 입력할 수 있습니다.\n\n답변 아래의 ‘답변 듣기’를 누르면 음성이 재생됩니다.',
        source: '화면 미리보기',
        preview: true,
        needsReview: true,
        clarifyingQuestions: ['어떤 물질인가요?', '노출된 사람이 있나요?', '불꽃이나 연기가 보이나요?'],
        contacts: [{ number: '033-741-0114', context: '원주세브란스 기독병원 · Figma 시안 예시', dialable: false }],
      });
    } else {
      const placeholder = {
        id: crypto.randomUUID(),
        role: 'assistant',
        text: '',
        source: '문서 자료 기반',
        pending: true,
        streaming: false,
        status: '관련 자료를 찾고 있어요…',
      };
      chat.messages.push(placeholder);
      // Vue가 감시하는 proxy를 수정해야 토큰마다 화면이 갱신된다.
      assistantMessage = chat.messages[chat.messages.length - 1];
      queryController = new AbortController();
      const request = { prompt, conversationId: chat.id };
      const data = streamingEnabled.value
        ? await ragApi.queryStream(request, {
            signal: queryController.signal,
            onStatus: ({ message }) => {
              if (assistantMessage.pending && message) assistantMessage.status = message;
              scroll();
            },
            onToken: token => {
              if (!token) return;
              assistantMessage.pending = false;
              assistantMessage.streaming = true;
              assistantMessage.status = '';
              assistantMessage.text += token;
              scroll();
            },
          })
        : await ragApi.query(request, { signal: queryController.signal });
      if (typeof data.answer !== 'string' || !data.answer.trim()) {
        throw new Error('답변이 비어 있습니다. 다시 질문해 주세요.');
      }
      if (typeof data.conversation_id !== 'string' || !data.conversation_id
          || typeof data.title !== 'string' || !data.title) {
        throw new Error('대화 정보를 받지 못했습니다. 다시 질문해 주세요.');
      }
      assistantMessage.sources = Array.isArray(data.sources) ? data.sources : [];
      assistantMessage.needsReview = data.needs_review === true;
      assistantMessage.handoff = data.handoff === true;
      assistantMessage.clarifyingQuestions = Array.isArray(data.clarifying_questions) ? data.clarifying_questions : [];
      assistantMessage.text = data.answer.trim();
      assistantMessage.pending = false;
      assistantMessage.streaming = false;
      assistantMessage.status = '';
      assistantMessage.source = data.handoff ? '근거 없음 · 안전관리자 확인 필요'
                              : (data.sources?.length ? '출처: ' + data.sources.join(', ') : '문서 자료 기반');
      chat.id = data.conversation_id;
      chat.title = data.title;
      const index = conversations.value.indexOf(chat);
      if (index !== -1) conversations.value.splice(index, 1);
      conversations.value.unshift(chat);
      activeId.value = chat.id;
      pendingConversation.value = null;
    }
  } catch (requestError) {
    if (assistantMessage) {
      const index = chat.messages.indexOf(assistantMessage);
      if (index !== -1) chat.messages.splice(index, 1);
    }
    const userIndex = chat.messages.indexOf(userMessage);
    if (userIndex !== -1) chat.messages.splice(userIndex, 1);
    if (pendingConversation.value === chat) pendingConversation.value = null;
    draft.value = prompt;
    if (requestError.name === 'AbortError' && queryController?.signal.aborted) return;
    error.value = requestError.message;
  } finally {
    queryController = null;
    busy.value = false;
    scroll();
  }
}

async function upload(file) {
  if (controlsDisabled.value) return;
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    error.value = 'PDF 파일을 선택해 주세요.';
    return;
  }
  if (props.demo) {
    error.value = '미리보기에서는 파일을 전송하지 않습니다. 실제 로그인 후 첨부해 주세요.';
    return;
  }

  uploading.value = true;
  error.value = '';
  try {
    await ragApi.uploadPaper(file);
    notice.value = `${file.name} 자료가 준비되었습니다.`;
  } catch (uploadError) {
    error.value = uploadError.message;
  } finally {
    uploading.value = false;
  }
}

async function speak(message) {
  if (controlsDisabled.value && speakingId.value !== message.id) return;
  if (speakingId.value === message.id) {
    stopAudio();
    return;
  }

  stopAudio();
  error.value = '';
  ttsLoading.value = message.id;
  try {
    if (props.demo) {
      if (!window.speechSynthesis) throw new Error('이 브라우저에서는 음성 미리보기를 지원하지 않습니다.');
      const utterance = new SpeechSynthesisUtterance(message.text);
      utterance.lang = 'ko-KR';
      utterance.onend = () => { speakingId.value = null; };
      utterance.onerror = () => { speakingId.value = null; };
      speakingId.value = message.id;
      window.speechSynthesis.speak(utterance);
    } else {
      if (message.text.length > 4096) throw new Error('음성으로 읽을 수 있는 길이(4,096자)를 초과합니다. 답변을 짧게 나누어 주세요.');
      const language = speechLanguage.value;
      const data = await voiceApi.synthesize(message.text, language);
      if (data.target_language !== language || data.original_text !== message.text || !data.translated_text) {
        throw new Error('번역 결과를 확인하지 못했습니다. 다시 시도해 주세요.');
      }
      message.speechTranslation = data;
      if (!data.file_path?.startsWith('/uploads/')) throw new Error('음성 파일을 받지 못했습니다.');
      audio = new Audio(`/voice-api${data.file_path}?t=${Date.now()}`);
      audio.onended = () => { speakingId.value = null; };
      audio.onerror = () => {
        speakingId.value = null;
        error.value = '음성 파일을 재생하지 못했습니다.';
      };
      await audio.play();
      speakingId.value = message.id;
    }
  } catch (speechError) {
    error.value = speechError.message;
    stopAudio();
  } finally {
    ttsLoading.value = null;
  }
}
</script>

<template>
  <div class="chat-layout" :class="{ 'has-contact-rail': railContacts.length }">
    <ConversationSidebar
      :user="user"
      :demo="demo"
      :conversations="conversations"
      :active-id="activeId"
      :open="menu"
      :disabled="controlsDisabled"
      @new-chat="newChat"
      @select-chat="selectChat"
      @logout="logout"
      @close="menu = false"
    />

    <main class="workspace" :class="{ 'is-welcome': !messages.length }">
      <ChatHeader
        :demo="demo"
        :streaming="streamingEnabled"
        :language="speechLanguage"
        @update:language="changeSpeechLanguage"
        :mode-disabled="controlsDisabled"
        @update:streaming="streamingEnabled = $event"
        @open-menu="menu = true"
        @new-chat="newChat"
      />
      <div v-if="demo" class="demo-banner">화면 미리보기 모드입니다. 답변은 예시이며 실제 자료를 검색하지 않습니다.</div>
      <MessageList
        ref="messageList"
        :messages="messages"
        :user="user"
        :busy="busy"
        :tts-loading="ttsLoading"
        :speaking-id="speakingId"
        :speech-language="speechLanguage"
        :examples="examples"
        :demo="demo"
        :disabled="controlsDisabled"
        @send-example="send"
        @speak="speak"
      />
      <ChatComposer
        v-model:draft="draft"
        :busy="busy"
        :uploading="uploading"
        :voice-state="voiceState"
        :tts-loading="!!ttsLoading"
        :error="error"
        :notice="notice"
        @send="send()"
        @upload="upload"
        @voice="toggleVoice"
        @dismiss-error="error = ''"
        @dismiss-notice="notice = ''"
      />
    </main>
    <aside v-if="railContacts.length" class="desktop-contact-rail" aria-label="최근 답변 연락처">
      <p class="rail-label">최근 답변 연락처</p>
      <ContactCards :contacts="railContacts" :demo="demo" />
    </aside>
  </div>
</template>
