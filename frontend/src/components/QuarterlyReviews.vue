<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { api, write } from "../api";
import { t } from "../i18n";
import { useSession } from "../stores/session";
import type { Objective } from "../types";
const session = useSession();
interface Review {
  id: number;
  objective_id: number;
  objective_title: string;
  reviewer_id: number;
  reviewer: string;
  due_date: string;
  status: string;
  overdue: boolean;
  summary: string;
  lessons: string;
  next_steps: string;
}
const items = ref<Review[]>([]),
  objectives = ref<Objective[]>([]),
  planDialog = ref(false),
  completionDialog = ref(false),
  busy = ref(false),
  selected = ref<Review>();
const canPlan = computed(() =>
  ["Manager", "Division Head", "PMO"].includes(session.user?.role || ""),
);
const plan = reactive({
  objective_id: undefined as number | undefined,
  reviewer_id: undefined as number | undefined,
  due_date: "",
});
const result = reactive({ summary: "", lessons: "", next_steps: "" });
const reviewers = computed(() =>
  session.catalog.users.filter(
    (u) =>
      ["Manager", "Division Head", "PMO"].includes(u.role) &&
      u.id !==
        objectives.value.find((o) => o.id === plan.objective_id)?.owner_id,
  ),
);
async function load() {
  const response = await api<Review[]>(
    "/api/v1/quarterly-reviews" +
      (session.cycleId ? "?cycle_id=" + session.cycleId : ""),
  );
  items.value = Array.isArray(response) ? response : [];
}
onMounted(load);
async function open() {
  const data = await api<{ items: Objective[] }>(
    "/api/v1/objectives?page_size=100" +
      (session.cycleId ? "&cycle_id=" + session.cycleId : ""),
  );
  objectives.value = data.items.filter((o) =>
    ["Approved", "Active", "Completed"].includes(o.status),
  );
  planDialog.value = true;
}
async function schedule() {
  busy.value = true;
  try {
    await write("/api/v1/quarterly-reviews", plan);
    planDialog.value = false;
    await load();
  } finally {
    busy.value = false;
  }
}
function complete(item: Review) {
  selected.value = item;
  Object.assign(result, { summary: "", lessons: "", next_steps: "" });
  completionDialog.value = true;
}
async function save() {
  busy.value = true;
  try {
    await write(
      `/api/v1/quarterly-reviews/${selected.value?.id}/complete`,
      result,
    );
    completionDialog.value = false;
    await load();
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <section class="panel">
    <div class="panel-title">
      <h2>{{ t("季度复盘") }}</h2>
      <el-button v-if="canPlan" @click="open">{{ t("安排复盘") }}</el-button>
    </div>
    <p class="muted">
      {{
        t(
          "为目标指定独立评审人和截止日期；复盘完成后保留结论、经验和后续计划。",
        )
      }}
    </p>
    <el-table :data="items" :empty-text="t('暂无复盘计划')"
      ><el-table-column :label="t('目标')" min-width="200"
        ><template #default="{ row }"
          ><router-link :to="'/objectives/' + row.objective_id">{{
            row.objective_title
          }}</router-link></template
        ></el-table-column
      ><el-table-column
        prop="reviewer"
        :label="t('评审人')"
        min-width="120"
      /><el-table-column
        prop="due_date"
        :label="t('截止日期')"
        width="130"
      /><el-table-column :label="t('状态')" min-width="130"
        ><template #default="{ row }">{{
          t(
            row.status === "Completed"
              ? "已完成"
              : row.overdue
                ? "已逾期"
                : "待完成",
          )
        }}</template></el-table-column
      ><el-table-column min-width="130"
        ><template #default="{ row }"
          ><el-button
            v-if="
              row.reviewer_id === session.user?.id && row.status === 'Pending'
            "
            @click="complete(row)"
            >{{ t("完成复盘") }}</el-button
          ></template
        ></el-table-column
      ></el-table
    >
    <details
      v-for="r in items.filter((i) => i.status === 'Completed')"
      :key="r.id"
      class="timeline-item"
    >
      <summary>{{ r.objective_title }}</summary>
      <p>{{ t("复盘结论") }}: {{ r.summary }}</p>
      <p>{{ t("经验与改进") }}: {{ r.lessons }}</p>
      <p>{{ t("下一周期计划") }}: {{ r.next_steps }}</p>
    </details>
  </section>
  <el-dialog v-model="planDialog" :title="t('安排复盘')" width="580px"
    ><el-form label-position="top"
      ><el-form-item :label="t('目标')"
        ><el-select
          v-model="plan.objective_id"
          filterable
          @change="plan.reviewer_id = undefined"
          ><el-option
            v-for="o in objectives"
            :key="o.id"
            :label="o.title"
            :value="o.id" /></el-select></el-form-item
      ><el-form-item :label="t('评审人')"
        ><el-select v-model="plan.reviewer_id"
          ><el-option
            v-for="u in reviewers"
            :key="u.id"
            :label="u.name"
            :value="u.id" /></el-select></el-form-item
      ><el-form-item :label="t('截止日期')"
        ><el-date-picker
          v-model="plan.due_date"
          value-format="YYYY-MM-DD" /></el-form-item></el-form
    ><template #footer
      ><el-button
        type="primary"
        :disabled="!plan.objective_id || !plan.reviewer_id || !plan.due_date"
        :loading="busy"
        @click="schedule"
        >{{ t("保存记录") }}</el-button
      ></template
    ></el-dialog
  >
  <el-dialog v-model="completionDialog" :title="t('完成复盘')" width="620px"
    ><el-form label-position="top"
      ><el-form-item :label="t('复盘结论')"
        ><el-input
          v-model="result.summary"
          type="textarea"
          :rows="3" /></el-form-item
      ><el-form-item :label="t('经验与改进')"
        ><el-input
          v-model="result.lessons"
          type="textarea"
          :rows="3" /></el-form-item
      ><el-form-item :label="t('下一周期计划')"
        ><el-input
          v-model="result.next_steps"
          type="textarea"
          :rows="3" /></el-form-item></el-form
    ><template #footer
      ><el-button
        type="primary"
        :disabled="
          !result.summary.trim() ||
          !result.lessons.trim() ||
          !result.next_steps.trim()
        "
        :loading="busy"
        @click="save"
        >{{ t("保存记录") }}</el-button
      ></template
    ></el-dialog
  >
</template>
