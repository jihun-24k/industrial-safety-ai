<script setup>
import { computed, ref, onUnmounted } from 'vue';
import { authApi } from '../api/authApi';
import { ragApi } from '../api/ragApi';
import { voiceApi } from '../api/voiceApi';
import ChatComposer from '../components/ChatComposer.vue';
import ChatHeader from '../components/ChatHeader.vue';
import ConversationSidebar from '../components/ConversationSidebar.vue';
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
const menu = ref(false);
const speakingId = ref(null);
const ttsLoading = ref(null);
const speechLanguage = ref('ko');
const messageList = ref(null);
const streamingEnabled = ref(true);
let audio = null;
let queryController = null;

const examples = [
  '작업 전 안전 점검 항목을 알려줘',
  '보호구 착용 기준이 궁금해요',
  '추락 사고 예방 수칙을 설명해줘',
];

const conversation = computed(() => conversations.value.find((chat) => chat.id === activeId.value));
const messages = computed(() => conversation.value?.messages || []);
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
  draft.value = '';
  error.value = '';
  notice.value = '';
  menu.value = false;
}

function selectChat(chat) {
  if (controlsDisabled.value) return;
  stopAudio();
  activeId.value = chat.id;
  error.value = '';
  menu.value = false;
  scroll();
}

async function send(text = '') {
  const prompt = (text || draft.value).trim();
  if (!prompt || controlsDisabled.value) return;

  if (!conversation.value) {
    const chat = {
      id: crypto.randomUUID(),
      title: prompt.slice(0, 26),
      messages: [],
    };
    conversations.value.unshift(chat);
    activeId.value = chat.id;
  }

  const chat = conversation.value;
  chat.messages.push({ id: crypto.randomUUID(), role: 'user', text: prompt });
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
      const data = streamingEnabled.value
        ? await ragApi.queryStream({ prompt }, {
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
        : await ragApi.query({ prompt }, { signal: queryController.signal });
      if (typeof data.answer !== 'string' || !data.answer.trim()) {
        throw new Error('답변이 비어 있습니다. 다시 질문해 주세요.');
      }
      assistantMessage.text = data.answer.trim();
      assistantMessage.pending = false;
      assistantMessage.streaming = false;
      assistantMessage.status = '';
      assistantMessage.source = data.handoff ? '근거 없음 · 안전관리자 확인 필요'
                              : (data.sources?.length ? '출처: ' + data.sources.join(', ') : '문서 자료 기반');
    }
  } catch (requestError) {
    if (assistantMessage) {
      const index = chat.messages.indexOf(assistantMessage);
      if (index !== -1) chat.messages.splice(index, 1);
    }
    if (requestError.name === 'AbortError' && queryController?.signal.aborted) return;
    error.value = requestError.message;
    draft.value = prompt;
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
  <div class="chat-layout">
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

    <main class="workspace">
      <ChatHeader
        :demo="demo"
        :streaming="streamingEnabled"
        :language="speechLanguage"
        @update:language="changeSpeechLanguage"
        :mode-disabled="controlsDisabled"
        @update:streaming="streamingEnabled = $event"
        @open-menu="menu = true"
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
  </div>
</template>
