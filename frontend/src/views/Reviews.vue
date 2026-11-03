<script setup lang="ts">
import { t, formatDate } from "../i18n";

import { onMounted, reactive, ref } from "vue";
import { api, write } from "../api";
import { useSession } from "../stores/session";
import QuarterlyReviews from "../components/QuarterlyReviews.vue";
const session = useSession();
interface Meeting {
  id: number;
  title: string;
  meeting_at: string;
  decisions: string;
  risks: string;
  actions: {
    id: number;
    title: string;
    owner_id: number;
    owner_name: string;
    due_date: string;
    status: string;
  }[];
}
const meetings = ref<Meeting[]>([]),
  dialog = ref(false),
  busy = ref(false);
const form = reactive({
  title: "",
  meeting_at: "",
  decisions: "",
  risks: "",
  actions: [] as {
    title: string;
    owner_id: number | undefined;
    due_date: string;
  }[],
});
async function load() {
  meetings.value = await api("/api/v1/review-meetings");
}
onMounted(load);
async function save() {
  busy.value = true;
  try {
    await write("/api/v1/review-meetings", {
      ...form,
      cycle_id: session.cycleId,
      meeting_at: new Date(form.meeting_at).toISOString(),
    });
    dialog.value = false;
    await load();
  } finally {
    busy.value = false;
  }
}
async function finish(id: number) {
  await write(`/api/v1/review-actions/${id}/complete`, {});
  await load();
}
</script>
<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">REFLECT & MOVE FORWARD</div>
      <h1>{{ t("评审与行动") }}</h1>
      <p>{{ t("记录讨论结论，明确责任人与下一步行动。") }}</p>
    </div>
    <el-button
      v-if="
        ['Manager', 'Division Head', 'PMO'].includes(session.user?.role || '')
      "
      type="primary"
      @click="dialog = true"
    >
      {{ t("记录评审会议") }}
    </el-button>
  </div>
  <QuarterlyReviews />
  <section v-if="!meetings.length" class="panel">
    <el-empty :description="t('暂无评审会议记录')" />
  </section>
  <section v-for="m in meetings" :key="m.id" class="panel">
    <div class="panel-title">
      <h2>{{ m.title }}</h2>
      <span class="muted">{{ formatDate(m.meeting_at) }}</span>
    </div>
    <p style="font-size: 13px; white-space: pre-wrap; line-height: 1.8">
      {{ m.decisions }}
    </p>
    <p v-if="m.risks" class="muted">{{ t("风险：") }} {{ m.risks }}</p>
    <ul class="action-list">
      <li v-for="a in m.actions" :key="a.id">
        <div>
          {{ a.title }}
          <div class="table-subtitle">
            {{ a.owner_name }} · {{ a.due_date }}
          </div>
        </div>
        <el-button
          v-if="a.owner_id === session.user?.id && a.status === 'Open'"
          @click="finish(a.id)"
        >
          {{ t("完成行动") }} </el-button
        ><span v-else class="status-badge">{{
          a.status === "Open" ? t("待完成") : t("已完成")
        }}</span>
      </li>
    </ul>
  </section>
  <el-dialog v-model="dialog" :title="t('记录评审会议')" width="650px"
    ><el-form label-position="top"
      ><el-form-item :label="t('会议主题')"
        ><el-input v-model="form.title" /></el-form-item
      ><el-form-item :label="t('会议时间')"
        ><el-date-picker
          v-model="form.meeting_at"
          type="datetime" /></el-form-item
      ><el-form-item :label="t('决策与结论')"
        ><el-input
          v-model="form.decisions"
          type="textarea"
          :rows="3" /></el-form-item
      ><el-form-item :label="t('风险')"
        ><el-input v-model="form.risks" type="textarea"
      /></el-form-item>
      <div v-for="(a, i) in form.actions" :key="i" class="form-grid">
        <el-form-item class="wide" :label="t('后续行动')"
          ><el-input v-model="a.title" /></el-form-item
        ><el-form-item :label="t('责任人')"
          ><el-select v-model="a.owner_id"
            ><el-option
              v-for="u in session.catalog.users"
              :key="u.id"
              :label="u.name"
              :value="u.id" /></el-select></el-form-item
        ><el-form-item :label="t('截止日期')"
          ><el-date-picker
            v-model="a.due_date"
            value-format="YYYY-MM-DD" /></el-form-item
        ><el-button link @click="form.actions.splice(i, 1)">
          {{ t("移除行动") }}
        </el-button>
      </div>
      <el-button
        @click="
          form.actions.push({ title: '', owner_id: undefined, due_date: '' })
        "
      >
        {{ t("添加行动") }}
      </el-button></el-form
    ><template #footer
      ><el-button type="primary" :loading="busy" @click="save">
        {{ t("保存记录") }}
      </el-button></template
    ></el-dialog
  >
</template>
