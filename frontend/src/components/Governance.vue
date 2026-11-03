<script setup lang="ts">
import { t } from "../i18n";

import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api, write } from "../api";
import { useSession } from "../stores/session";
import type { Objective } from "../types";
const props = defineProps<{ objective: Objective }>();
const emit = defineEmits<{ changed: [] }>();
const session = useSession(),
  dialog = ref(false),
  busy = ref(false);
const changes = ref<
  {
    id: number;
    stage: string;
    status: string;
    reason: string;
    decisions: { comment: string; stage: string }[];
  }[]
>([]);
const snapshots = ref<
  { date: string; formula_version: string; value: Objective }[]
>([]);
const isOwner = computed(() => session.user?.id === props.objective.owner_id);
const reader = ref<number>();
const form = reactive({
  title: "",
  description: "",
  theme: "",
  start_date: "",
  end_date: "",
  reason: "",
  key_results: [] as {
    id: number;
    name: string;
    baseline: string;
    target: string;
    weight: string;
    evidence_source: string;
  }[],
});
async function load() {
  [changes.value, snapshots.value] = await Promise.all([
    api<typeof changes.value>(
      `/api/v1/change-requests?objective_id=${props.objective.id}`,
    ),
    api<typeof snapshots.value>(
      `/api/v1/objectives/${props.objective.id}/snapshots`,
    ),
  ]);
}
onMounted(load);
function open() {
  const o = props.objective;
  Object.assign(form, {
    title: o.title,
    description: o.description,
    theme: o.theme,
    start_date: o.start_date,
    end_date: o.end_date,
    reason: "",
    key_results:
      o.key_results?.map((k) => ({
        id: k.id,
        name: k.name,
        baseline: k.baseline,
        target: k.target,
        weight: k.weight,
        evidence_source: k.evidence_source || "",
      })) || [],
  });
  dialog.value = true;
}
async function submit() {
  busy.value = true;
  try {
    const o = props.objective;
    await write(
      `/api/v1/objectives/${o.id}/change-requests`,
      {
        objective: {
          title: form.title,
          description: form.description,
          theme: form.theme,
          start_date: form.start_date,
          end_date: form.end_date,
          cycle_id: o.cycle_id,
          level: o.level,
          priority: o.priority,
          visibility: o.visibility,
        },
        key_results: form.key_results.map(({ name, ...k }) => k),
        reason: form.reason,
      },
      o.etag,
    );
    dialog.value = false;
    ElMessage.success(t("变更已提交，批准前原定义继续生效"));
    await load();
  } finally {
    busy.value = false;
  }
}
async function withdraw(id: number) {
  await write(`/api/v1/change-requests/${id}/withdraw`, {});
  await load();
}
async function grant() {
  if (!reader.value) return;
  await write(`/api/v1/objectives/${props.objective.id}/readers`, {
    user_id: reader.value,
  });
  ElMessage.success(t("已授予此目标只读访问"));
  emit("changed");
}
async function revoke() {
  if (!reader.value) return;
  await api(
    `/api/v1/objectives/${props.objective.id}/readers/${reader.value}`,
    { method: "DELETE" },
  );
  ElMessage.success(t("额外只读授权已撤销；组织角色权限仍按规则计算"));
}
</script>
<template>
  <div style="padding-top: 15px">
    <div class="panel-title">
      <h2>{{ t("目标变更") }}</h2>
      <el-button
        v-if="isOwner && ['Approved', 'Active'].includes(objective.status)"
        :disabled="changes.some((c) => c.status === 'Pending')"
        @click="open"
      >
        {{ t("申请变更") }}
      </el-button>
    </div>
    <el-table :data="changes" :empty-text="t('暂无变更申请')"
      ><el-table-column
        prop="reason"
        :label="t('变更原因')"
        min-width="200"
      /><el-table-column
        prop="stage"
        :label="t('当前阶段')"
        width="150"
      /><el-table-column
        prop="status"
        :label="t('状态')"
        width="120"
      /><el-table-column width="90"
        ><template #default="{ row }"
          ><el-button
            v-if="isOwner && row.status === 'Pending'"
            link
            @click="withdraw(row.id)"
          >
            {{ t("撤回") }}
          </el-button></template
        ></el-table-column
      ></el-table
    ><template v-if="isOwner"
      ><h3 style="font-size: 14px; margin-top: 28px">
        {{ t("共享只读访问") }}
      </h3>
      <p class="muted">
        {{ t("获授权的同事可查看目标与证据；不会获得编辑或审批资格。") }}
      </p>
      <div class="toolbar">
        <el-select
          v-model="reader"
          filterable
          :placeholder="t('选择同事')"
          style="width: 260px"
          ><el-option
            v-for="u in session.catalog.users.filter(
              (u) => u.id !== session.user?.id && u.role !== 'System Admin',
            )"
            :key="u.id"
            :label="u.name"
            :value="u.id" /></el-select
        ><el-button @click="grant"> {{ t("授予访问") }} </el-button
        ><el-button @click="revoke"> {{ t("撤销授权") }} </el-button>
      </div></template
    >
    <h3 style="font-size: 14px; margin-top: 28px">{{ t("历史快照") }}</h3>
    <el-table
      :data="snapshots"
      :empty-text="t('后台任务运行后，每日保留一次历史快照')"
      ><el-table-column prop="date" :label="t('日期')" /><el-table-column
        :label="t('达成率')"
        ><template #default="{ row }">{{
          row.value.progress === null ? t("未计算") : row.value.progress + "%"
        }}</template></el-table-column
      ><el-table-column
        prop="value.org_name"
        :label="t('当时所属部门')" /><el-table-column
        prop="formula_version"
        :label="t('计算版本')"
    /></el-table>
  </div>
  <el-dialog v-model="dialog" :title="t('申请变更目标定义')" width="720px"
    ><el-form label-position="top"
      ><el-form-item :label="t('变更原因')"
        ><el-input v-model="form.reason" type="textarea" /></el-form-item
      ><el-form-item :label="t('目标名称')"
        ><el-input v-model="form.title" /></el-form-item
      ><el-form-item :label="t('目标说明')"
        ><el-input v-model="form.description" type="textarea" /></el-form-item
      ><el-form-item :label="t('战略主题')"
        ><el-input v-model="form.theme"
      /></el-form-item>
      <div class="form-grid">
        <el-form-item :label="t('开始日期')"
          ><el-date-picker
            v-model="form.start_date"
            value-format="YYYY-MM-DD" /></el-form-item
        ><el-form-item :label="t('截止日期')"
          ><el-date-picker v-model="form.end_date" value-format="YYYY-MM-DD"
        /></el-form-item>
      </div>
      <div v-for="k in form.key_results" :key="k.id">
        <h4>{{ k.name }}</h4>
        <div class="form-grid">
          <el-form-item :label="t('证据来源')"
            ><el-input v-model="k.evidence_source"
          /></el-form-item>
          <el-form-item :label="t('基线')"
            ><el-input v-model="k.baseline" /></el-form-item
          ><el-form-item :label="t('目标值')"
            ><el-input v-model="k.target" /></el-form-item
          ><el-form-item :label="t('权重')"
            ><el-input v-model="k.weight"
          /></el-form-item>
        </div></div></el-form
    ><template #footer
      ><el-button @click="dialog = false"> {{ t("取消") }} </el-button
      ><el-button type="primary" :loading="busy" @click="submit">
        {{ t("提交变更审批") }}
      </el-button></template
    ></el-dialog
  >
</template>
