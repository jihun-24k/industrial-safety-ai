<script setup>
import { computed, onMounted, ref } from 'vue';
import BrandLogo from '../components/BrandLogo.vue';
import { opsApi } from '../api/opsApi';
import { dailyBars, formatCount, formatDateTime, formatLatency, formatPercent, logChips } from '../utils/opsFormat';

defineProps({ user: { type: String, required: true } });
const emit = defineEmits(['back']);

const periods = [{ days: 1, label: '오늘' }, { days: 7, label: '7일' }, { days: 30, label: '30일' }];
const days = ref(7);
const data = ref(null);
const verified = ref([]);
const loading = ref(false);
const error = ref('');
const notice = ref('');
const editing = ref(null);   // { logId, question, answer }
const saving = ref(false);

const totals = computed(() => data.value?.totals || {});
const chart = computed(() => dailyBars(data.value?.daily || []));
const hasLogs = computed(() => (totals.value.questions_all_time || 0) > 0);

const tiles = computed(() => {
  const t = totals.value;
  return [
    { label: '누적 질문', value: formatCount(t.questions_all_time), note: `기간 내 ${formatCount(t.questions)}건` },
    { label: '상담 대화', value: formatCount(t.conversations), note: `사용자 ${formatCount(t.users)}명` },
    { label: '근거 없음 (handoff)', value: formatPercent(t.handoff_rate), note: `${formatCount(t.handoff)}건 담당자 연결`,
      tone: t.handoff_rate >= 0.2 ? 'critical' : t.handoff_rate >= 0.1 ? 'warning' : 'good' },
    { label: '긴급 안내', value: formatCount(t.needs_review), note: '119 우선 안내한 질문' },
    { label: '응답 시간', value: formatLatency(t.avg_latency_ms), note: `p95 ${formatLatency(t.p95_latency_ms)}` },
    { label: '만족도', value: formatPercent(t.satisfaction), note: `▲ ${formatCount(t.feedback_up)} · ▼ ${formatCount(t.feedback_down)}`,
      tone: t.satisfaction === null || t.satisfaction === undefined ? '' : t.satisfaction >= 0.8 ? 'good' : 'warning' },
    { label: '검증 Q&A', value: formatCount(t.verified_active), note: `답변에 ${formatCount(t.verified_hits)}회 활용` },
  ];
});

const signals = computed(() => {
  const t = totals.value;
  return [
    `사고 질문 ${formatCount(t.incident)}건 (검색 계획 사용)`,
    `이전 대화 참고 ${formatCount(t.used_history)}건`,
    `오탈자 보정 ${formatCount(t.typo_fixed)}건`,
  ];
});

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const [metrics, qa] = await Promise.all([opsApi.metrics(days.value), opsApi.listVerified()]);
    data.value = metrics;
    verified.value = qa;
  } catch (loadError) {
    error.value = loadError.message;
  } finally {
    loading.value = false;
  }
}

function selectPeriod(value) {
  if (loading.value || days.value === value) return;
  days.value = value;
  load();
}

function startVerify(log) {
  notice.value = '';
  editing.value = { logId: log.id, question: log.normalized_question || log.question, answer: log.answer };
}

async function saveVerify() {
  if (!editing.value || saving.value) return;
  const { question, answer } = editing.value;
  if (question.trim().length < 2 || answer.trim().length < 2) {
    error.value = '질문과 답변을 2자 이상 입력해 주세요.';
    return;
  }
  saving.value = true;
  error.value = '';
  try {
    await opsApi.createVerified(editing.value);
    notice.value = '검증 Q&A로 등록했어요. 비슷한 질문부터 답변 근거로 함께 쓰입니다.';
    editing.value = null;
    await load();
  } catch (saveError) {
    error.value = saveError.message;
  } finally {
    saving.value = false;
  }
}

async function retire(item) {
  if (saving.value) return;
  saving.value = true;
  error.value = '';
  try {
    await opsApi.retireVerified(item.id);
    notice.value = `검증 Q&A #${item.id}를 사용 중지했어요.`;
    await load();
  } catch (retireError) {
    error.value = retireError.message;
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="ops-layout">
    <header class="ops-header">
      <div class="ops-title">
        <BrandLogo @click.prevent="emit('back')" />
        <div>
          <span class="section-tag">OPERATIONS</span>
          <h1>운영 현황</h1>
        </div>
      </div>
      <div class="ops-actions">
        <div class="ops-periods" role="group" aria-label="집계 기간">
          <button v-for="period in periods" :key="period.days" type="button"
                  :aria-pressed="days === period.days" :disabled="loading" @click="selectPeriod(period.days)">
            {{ period.label }}
          </button>
        </div>
        <button type="button" class="ops-secondary" :disabled="loading" @click="load">{{ loading ? '불러오는 중…' : '새로고침' }}</button>
        <button type="button" class="ops-primary" @click="emit('back')">상담 화면으로</button>
      </div>
    </header>

    <p v-if="error" class="ops-alert" role="alert">{{ error }} <button type="button" aria-label="닫기" @click="error = ''">×</button></p>
    <p v-if="notice" class="ops-notice" role="status">{{ notice }} <button type="button" aria-label="닫기" @click="notice = ''">×</button></p>

    <div v-if="!data && loading" class="ops-empty glass-card" role="status">운영 지표를 불러오고 있어요…</div>

    <template v-else-if="data">
      <!-- 누적 현황: 맨 위에서 한눈에 -->
      <section class="ops-tiles" aria-label="누적 현황">
        <article v-for="tile in tiles" :key="tile.label" class="ops-tile glass-card" :class="tile.tone && `tone-${tile.tone}`">
          <span class="ops-tile-label">{{ tile.label }}</span>
          <strong class="ops-tile-value">{{ tile.value }}</strong>
          <span class="ops-tile-note">{{ tile.note }}</span>
        </article>
      </section>
      <p class="ops-signals">{{ signals.join(' · ') }} · 기준 {{ data.window_days }}일 · {{ formatDateTime(data.generated_at) }} 집계</p>

      <div v-if="!hasLogs" class="ops-empty glass-card">
        <h2>아직 쌓인 상담 로그가 없어요</h2>
        <p>상담 화면에서 질문하면 질문·답변·출처·응답 시간이 자동으로 기록되고, 이곳에 누적 현황이 나타납니다.</p>
        <button type="button" class="ops-primary" @click="emit('back')">첫 질문 하러 가기</button>
      </div>

      <template v-else>
        <div class="ops-grid">
          <!-- 최근 상담 맥락 -->
          <section class="ops-panel glass-card ops-context" aria-labelledby="ops-recent">
            <div class="ops-panel-head">
              <h2 id="ops-recent">최근 상담 맥락</h2>
              <span>최근 {{ data.recent.length }}건</span>
            </div>
            <ol class="ops-logs">
              <li v-for="log in data.recent" :key="log.id">
                <div class="ops-log-meta">
                  <span class="ops-log-time">{{ formatDateTime(log.created_at) }}</span>
                  <span>{{ log.username }}</span>
                  <span v-if="log.conversation_title" class="ops-log-conv">대화: {{ log.conversation_title }}</span>
                  <span class="ops-log-latency">{{ formatLatency(log.latency_ms) }}</span>
                </div>
                <p v-if="log.conversation_summary" class="ops-log-summary">맥락 요약 · {{ log.conversation_summary }}</p>
                <p class="ops-log-q"><b>Q</b> {{ log.question }}</p>
                <p class="ops-log-a"><b>A</b> {{ log.answer_preview }}</p>
                <div class="ops-chips">
                  <span v-for="chip in logChips(log)" :key="chip.label" class="ops-chip" :class="`chip-${chip.kind}`">{{ chip.label }}</span>
                  <span v-if="log.sources.length" class="ops-chip chip-plain">출처 {{ log.sources[0] }}<template v-if="log.sources.length > 1"> 외 {{ log.sources.length - 1 }}</template></span>
                </div>
              </li>
            </ol>
          </section>

          <div class="ops-side">
            <!-- 일별 추이 -->
            <section class="ops-panel glass-card" aria-labelledby="ops-daily">
              <div class="ops-panel-head">
                <h2 id="ops-daily">일별 질문 수</h2>
                <span class="ops-legend"><i class="legend-q"></i>질문 <i class="legend-h"></i>근거 없음</span>
              </div>
              <div class="ops-chart-wrap">
                <svg class="ops-chart" :viewBox="`0 0 ${Math.max(chart.bars.length * 36 + 40, 240)} 160`" role="img"
                     :aria-label="`최근 ${chart.bars.length}일 질문 수, 최대 ${chart.max}건`">
                  <g v-for="tick in chart.ticks" :key="tick">
                    <line x1="32" :x2="chart.bars.length * 36 + 36" :y1="130 - (tick / chart.max) * 120" :y2="130 - (tick / chart.max) * 120" class="chart-grid" />
                    <text x="26" :y="134 - (tick / chart.max) * 120" text-anchor="end" class="chart-axis">{{ tick }}</text>
                  </g>
                  <g v-for="(bar, index) in chart.bars" :key="bar.date">
                    <rect :x="40 + index * 36" :y="130 - bar.questionHeight" width="22" :height="bar.questionHeight" rx="4" class="chart-bar">
                      <title>{{ bar.label }} 질문 {{ bar.questions }}건 · 근거 없음 {{ bar.handoff }}건</title>
                    </rect>
                    <rect v-if="bar.handoffHeight" :x="40 + index * 36" :y="130 - bar.handoffHeight" width="22" :height="bar.handoffHeight" rx="4" class="chart-bar-handoff" />
                    <text :x="51 + index * 36" y="150" text-anchor="middle" class="chart-axis">{{ chart.bars.length > 10 && index % 3 ? '' : bar.label }}</text>
                  </g>
                </svg>
              </div>
            </section>

            <section class="ops-panel glass-card" aria-labelledby="ops-frequent">
              <div class="ops-panel-head"><h2 id="ops-frequent">자주 묻는 질문</h2></div>
              <ol class="ops-rank">
                <li v-for="item in data.frequent_questions" :key="item.question">
                  <span>{{ item.question }}</span>
                  <b>{{ item.count }}회</b>
                  <em v-if="item.handoff" class="ops-chip chip-critical">근거 없음 {{ item.handoff }}</em>
                </li>
              </ol>
            </section>

            <section v-if="data.top_materials.length" class="ops-panel glass-card" aria-labelledby="ops-materials">
              <div class="ops-panel-head"><h2 id="ops-materials">많이 언급된 물질</h2></div>
              <ul class="ops-tags">
                <li v-for="item in data.top_materials" :key="item.name">{{ item.name }} <b>{{ item.count }}</b></li>
              </ul>
            </section>
          </div>
        </div>

        <!-- 질의응답 누적 → 검증 Q&A → RAG 반영 -->
        <div class="ops-grid ops-grid-even">
          <section class="ops-panel glass-card" aria-labelledby="ops-attention">
            <div class="ops-panel-head">
              <h2 id="ops-attention">확인이 필요한 답변</h2>
              <span>근거 없음 · ▼ 평가</span>
            </div>
            <p v-if="!data.attention.length" class="ops-muted">지금은 확인할 답변이 없어요.</p>
            <ol class="ops-logs compact">
              <li v-for="log in data.attention" :key="log.id">
                <div class="ops-log-meta"><span class="ops-log-time">{{ formatDateTime(log.created_at) }}</span><span>{{ log.username }}</span></div>
                <p class="ops-log-q"><b>Q</b> {{ log.question }}</p>
                <p class="ops-log-a"><b>A</b> {{ log.answer_preview }}</p>
                <p v-if="log.feedback_note" class="ops-log-summary">사용자 의견 · {{ log.feedback_note }}</p>
                <div class="ops-chips">
                  <span v-for="chip in logChips(log)" :key="chip.label" class="ops-chip" :class="`chip-${chip.kind}`">{{ chip.label }}</span>
                </div>
                <button type="button" class="ops-secondary small" @click="startVerify(log)">답변 고쳐서 검증 Q&A로 등록</button>
              </li>
            </ol>
          </section>

          <section class="ops-panel glass-card" aria-labelledby="ops-candidates">
            <div class="ops-panel-head">
              <h2 id="ops-candidates">검증 Q&A 후보</h2>
              <span>▲ 도움됨 평가</span>
            </div>
            <p v-if="!data.candidates.length" class="ops-muted">사용자가 ▲ 도움됐어요를 누른 답변이 여기에 모여요.</p>
            <ol class="ops-logs compact">
              <li v-for="log in data.candidates" :key="log.id">
                <div class="ops-log-meta"><span class="ops-log-time">{{ formatDateTime(log.created_at) }}</span><span>{{ log.username }}</span></div>
                <p class="ops-log-q"><b>Q</b> {{ log.question }}</p>
                <p class="ops-log-a"><b>A</b> {{ log.answer_preview }}</p>
                <button type="button" class="ops-primary small" @click="startVerify(log)">검증 Q&A로 등록</button>
              </li>
            </ol>
          </section>
        </div>

        <section v-if="editing" class="ops-panel glass-card ops-editor" aria-labelledby="ops-editor-title">
          <div class="ops-panel-head">
            <h2 id="ops-editor-title">검증 Q&A 등록 · 로그 #{{ editing.logId }}</h2>
            <span>등록하면 비슷한 질문의 답변 근거로 함께 쓰입니다</span>
          </div>
          <label for="ops-verify-question">대표 질문 (검색에 쓰임)</label>
          <input id="ops-verify-question" v-model="editing.question" maxlength="2000" />
          <label for="ops-verify-answer">확인한 답변 (필요하면 고쳐서 저장)</label>
          <textarea id="ops-verify-answer" v-model="editing.answer" rows="9" maxlength="8000"></textarea>
          <p class="ops-muted">매뉴얼 원문과 맞는지 확인한 뒤 등록하세요. 원래 답변의 출처가 함께 저장됩니다.</p>
          <div class="ops-actions">
            <button type="button" class="ops-secondary" :disabled="saving" @click="editing = null">취소</button>
            <button type="button" class="ops-primary" :disabled="saving" @click="saveVerify">{{ saving ? '저장 중…' : '검증 Q&A로 등록' }}</button>
          </div>
        </section>

        <section class="ops-panel glass-card" aria-labelledby="ops-verified">
          <div class="ops-panel-head">
            <h2 id="ops-verified">검증 Q&A ({{ verified.length }})</h2>
            <span>운영자가 확인한 답변 · RAG 근거로 함께 제공</span>
          </div>
          <p v-if="!verified.length" class="ops-muted">아직 등록된 검증 Q&A가 없어요. 위 목록에서 답변을 확인해 등록해 보세요.</p>
          <ol class="ops-logs compact">
            <li v-for="item in verified" :key="item.id">
              <div class="ops-log-meta">
                <span class="ops-chip chip-good">#{{ item.id }}</span>
                <span>{{ item.created_by }}</span>
                <span class="ops-log-time">{{ formatDateTime(item.created_at) }}</span>
                <span v-if="item.source_log_id">원본 로그 #{{ item.source_log_id }}</span>
              </div>
              <p class="ops-log-q"><b>Q</b> {{ item.question }}</p>
              <p class="ops-log-a"><b>A</b> {{ item.answer.length > 180 ? item.answer.slice(0, 179) + '…' : item.answer }}</p>
              <button type="button" class="ops-secondary small" :disabled="saving" @click="retire(item)">사용 중지</button>
            </li>
          </ol>
        </section>
      </template>
    </template>
  </div>
</template>
