<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { api, write } from "../api";
import { t } from "../i18n";
import { useSession } from "../stores/session";
import type { Objective } from "../types";
import { statusNames } from "../types";
const session = useSession();
interface Group {
  id: number;
  name: string;
  count: number;
  achievement: string | null;
  health: Record<string, number>;
  statuses: Record<string, number>;
  overdue_reviews: number;
  risk_concentration: string | null;
}
interface Analytics {
  divisions: Group[];
  departments: Group[];
  strategic_value: string | null;
  assessed_count: number;
  effective_count: number;
  unplanned_reviews: number;
  assessments: { objective_id: number; score: number; rationale: string }[];
}
const data = ref<Analytics>(),
  dialog = ref(false),
  busy = ref(false),
  objectives = ref<Objective[]>([]),
  error = ref(false);
const form = reactive({
  objective_id: undefined as number | undefined,
  score: 50,
  rationale: "",
});
const canAssess = computed(() =>
  ["Manager", "Division Head", "PMO"].includes(session.user?.role || ""),
);
async function load() {
  error.value = false;
  try {
    data.value = await api(
      "/api/v1/dashboards/organization" +
        (session.cycleId ? "?cycle_id=" + session.cycleId : ""),
    );
  } catch {
    error.value = true;
  }
}
onMounted(load);
async function open() {
  const result = await api<{ items: Objective[] }>(
    "/api/v1/objectives?page_size=100" +
      (session.cycleId ? "&cycle_id=" + session.cycleId : ""),
  );
  objectives.value = result.items;
  form.objective_id = undefined;
  form.rationale = "";
  dialog.value = true;
}
function select() {
  const old = data.value?.assessments?.find(
    (a) => a.objective_id === form.objective_id,
  );
  form.score = old?.score ?? 50;
  form.rationale = old?.rationale || "";
}
async function save() {
  if (!form.objective_id) return;
  busy.value = true;
  try {
    await write(
      `/api/v1/objectives/${form.objective_id}/strategic-assessment`,
      { score: form.score, rationale: form.rationale },
      undefined,
      "PUT",
    );
    dialog.value = false;
    await load();
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <section class="panel">
    <div class="panel-title">
      <h2>{{ t("组织与战略分析") }}</h2>
      <el-button v-if="canAssess" @click="open">{{
        t("评估战略价值")
      }}</el-button>
    </div>
    <el-alert
      v-if="error"
      type="error"
      :title="t('数据加载失败，请稍后重试')"
      :closable="false"
    />
    <template v-if="data">
      <p class="muted">
        {{
          t(
            "仅统计当前授权范围；达成率为有效目标等权平均，风险集中度为红黄KR占比。",
          )
        }}
      </p>
      <h3>{{ t("事业部评分") }}</h3>
      <el-table :data="data.divisions || []" :empty-text="t('暂无数据')"
        ><el-table-column
          prop="name"
          :label="t('事业部')"
          min-width="150"
        /><el-table-column
          prop="count"
          :label="t('目标数量')"
        /><el-table-column :label="t('达成率')"
          ><template #default="{ row }">{{
            row.achievement === null ? "—" : row.achievement + "%"
          }}</template></el-table-column
        ></el-table
      >
      <h3>{{ t("部门分析") }}</h3>
      <el-table :data="data.departments || []" :empty-text="t('暂无数据')"
        ><el-table-column
          prop="name"
          :label="t('部门')"
          min-width="150"
        /><el-table-column :label="t('目标状态')" min-width="200"
          ><template #default="{ row }"
            ><span
              v-for="(count, state) in row.statuses"
              :key="state"
              style="display: inline-block; margin-right: 10px"
              >{{ statusNames[state] || state }} {{ count }}</span
            ></template
          ></el-table-column
        ><el-table-column :label="t('KR健康度')" min-width="200"
          ><template #default="{ row }"
            >{{ t("进展正常") }} {{ row.health.Green }} · {{ t("存在风险") }}
            {{ row.health.Amber }} · {{ t("偏离计划") }} {{ row.health.Red }} ·
            {{ t("缺少更新") }} {{ row.health.Gray }}</template
          ></el-table-column
        ><el-table-column
          prop="overdue_reviews"
          :label="t('逾期评审')"
          min-width="110"
        /><el-table-column :label="t('风险集中度')" min-width="130"
          ><template #default="{ row }">{{
            row.risk_concentration === null ? "—" : row.risk_concentration + "%"
          }}</template></el-table-column
        ></el-table
      >
      <p class="muted">
        {{ t("未安排复盘的有效目标") }}: {{ data.unplanned_reviews ?? 0 }}
      </p>
      <div class="detail-meta">
        <span
          >{{ t("组合战略价值") }}
          <strong>{{ data.strategic_value ?? "—" }} / 100</strong></span
        ><span
          >{{ t("已评分目标") }}
          <strong
            >{{ data.assessed_count ?? 0 }} /
            {{ data.effective_count ?? 0 }}</strong
          ></span
        >
      </div>
      <p class="muted">
        {{
          t(
            "战略价值为人工评估的0至100分，按已评分有效目标等权平均；未评分不按零分计算。",
          )
        }}
      </p>
      <el-table
        :data="data.assessments || []"
        :empty-text="t('暂无战略价值评估')"
        ><el-table-column
          prop="objective_id"
          :label="t('目标ID')"
          width="100" /><el-table-column
          prop="score"
          :label="t('战略价值评分')"
          width="150" /><el-table-column
          prop="rationale"
          :label="t('评分依据')"
          min-width="200"
      /></el-table>
    </template>
  </section>
  <el-dialog v-model="dialog" :title="t('评估战略价值')" width="580px"
    ><el-form label-position="top"
      ><el-form-item :label="t('目标')"
        ><el-select v-model="form.objective_id" filterable @change="select"
          ><el-option
            v-for="o in objectives"
            :key="o.id"
            :label="o.title"
            :value="o.id" /></el-select></el-form-item
      ><el-form-item :label="t('战略价值评分')"
        ><el-input-number
          v-model="form.score"
          :min="0"
          :max="100"
          :precision="0" /></el-form-item
      ><el-form-item :label="t('评分依据')"
        ><el-input
          v-model="form.rationale"
          type="textarea"
          :rows="4" /></el-form-item></el-form
    ><template #footer
      ><el-button
        type="primary"
        :loading="busy"
        :disabled="!form.objective_id || !form.rationale.trim()"
        @click="save"
        >{{ t("保存记录") }}</el-button
      ></template
    ></el-dialog
  >
</template>
