<script setup lang="ts">
import { t } from "../i18n";

import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessageBox, ElMessage } from "element-plus";
import { api, write } from "../api";
import type { Objective } from "../types";
const router = useRouter(),
  loading = ref(false);
const tasks = ref<
  { id: number; stage: string; revision: number; objective: Objective }[]
>([]);
const changes = ref<
  {
    id: number;
    objective_id: number;
    stage: string;
    reason: string;
    proposed: {
      objective: {
        title: string;
        description: string;
        theme: string;
        start_date: string;
        end_date: string;
      };
      key_results: {
        id: number;
        baseline: string;
        target: string;
        weight: string;
      }[];
    };
  }[]
>([]);
async function load() {
  loading.value = true;
  try {
    [tasks.value, changes.value] = await Promise.all([
      api<typeof tasks.value>("/api/v1/approvals"),
      api<typeof changes.value>("/api/v1/change-requests"),
    ]);
  } finally {
    loading.value = false;
  }
}
async function decideChange(id: number, decision: string) {
  try {
    const { value } = await ElMessageBox.prompt(
      t("请输入变更审批意见"),
      t("审批目标变更"),
      {
        inputType: "textarea",
        inputValidator: (v) => !!v?.trim() || t("请填写意见"),
        confirmButtonText: t("确认"),
        cancelButtonText: t("取消"),
      },
    );
    await write(`/api/v1/change-requests/${id}/decisions`, {
      decision,
      comment: value,
    });
    await load();
    ElMessage.success(t("变更审批已处理"));
  } catch {
    /* cancellation or API error */
  }
}
async function decide(task: (typeof tasks.value)[number], decision: string) {
  try {
    const { value } = await ElMessageBox.prompt(
      t("请输入审批意见"),
      decision === "Approved" ? t("通过审批") : t("驳回目标"),
      {
        inputType: "textarea",
        inputValidator: (value) => !!value?.trim() || t("请填写审批意见"),
        confirmButtonText: t("确认"),
        cancelButtonText: t("取消"),
      },
    );
    await write(
      `/api/v1/workflow-tasks/${task.id}/decisions`,
      { decision, comment: value },
      task.objective.etag,
    );
    ElMessage.success(t("审批已处理"));
    await load();
  } catch {
    /* Prompt cancellation / API error */
  }
}
onMounted(load);
</script>
<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">REVIEW & APPROVE</div>
      <h1>{{ t("审批中心") }}</h1>
      <p>{{ t("审阅目标与关键结果，对齐预期后再开始执行。") }}</p>
    </div>
    <el-button @click="load"> {{ t("刷新待办") }} </el-button>
  </div>
  <section class="panel" v-loading="loading">
    <div class="panel-title">
      <h2>{{ t("我的待审批") }}</h2>
      <span class="muted">{{ tasks.length }} {{ t("项待办") }} </span>
    </div>
    <el-table :data="tasks" :empty-text="t('暂无待审批目标')"
      ><el-table-column :label="t('目标')" min-width="250"
        ><template #default="{ row }"
          ><div
            class="table-title"
            @click="router.push('/objectives/' + row.objective.id)"
          >
            {{ row.objective.title }}
          </div>
          <div class="table-subtitle">
            {{ row.objective.code }} {{ t("· 版本") }} {{ row.revision }}
          </div></template
        ></el-table-column
      ><el-table-column :label="t('提交人')" width="160"
        ><template #default="{ row }">{{
          row.objective.owner_name
        }}</template></el-table-column
      ><el-table-column :label="t('审批阶段')" width="130"
        ><template #default="{ row }">{{
          row.stage === "Completion"
            ? t("结项确认")
            : row.stage === "Manager"
              ? t("经理评审")
              : t("事业部评审")
        }}</template></el-table-column
      ><el-table-column width="210"
        ><template #default="{ row }"
          ><el-button
            link
            @click="router.push('/objectives/' + row.objective.id)"
          >
            {{ t("审阅") }} </el-button
          ><el-button type="primary" plain @click="decide(row, 'Approved')">
            {{ t("通过") }} </el-button
          ><el-button @click="decide(row, 'Rejected')">
            {{ t("驳回") }}
          </el-button></template
        ></el-table-column
      ></el-table
    >
  </section>
  <section class="panel">
    <div class="panel-title">
      <h2>{{ t("待审批的目标变更") }}</h2>
      <span class="muted"> {{ t("批准前，当前目标定义继续生效") }} </span>
    </div>
    <el-empty v-if="!changes.length" :description="t('暂无待审批变更')" />
    <article v-for="c in changes" :key="c.id" class="kr-card">
      <div class="panel-title">
        <h2>{{ c.proposed.objective.title }}</h2>
        <el-button link @click="router.push('/objectives/' + c.objective_id)">
          {{ t("查看当前目标") }}
        </el-button>
      </div>
      <p style="font-size: 13px">{{ t("变更原因：") }} {{ c.reason }}</p>
      <p class="muted">
        {{ t("新主题：") }} {{ c.proposed.objective.theme }}
        {{ t("· 新周期：") }} {{ c.proposed.objective.start_date }} —
        {{ c.proposed.objective.end_date }}
      </p>
      <p class="muted">
        {{ t("新说明：") }} {{ c.proposed.objective.description }}
      </p>
      <el-table :data="c.proposed.key_results"
        ><el-table-column prop="id" :label="t('KR编号')" /><el-table-column
          prop="baseline"
          :label="t('新基线')" /><el-table-column
          prop="target"
          :label="t('新目标值')" /><el-table-column
          prop="weight"
          :label="t('新权重')"
      /></el-table>
      <div class="heading-actions" style="margin-top: 15px">
        <el-button type="primary" @click="decideChange(c.id, 'Approved')">
          {{ t("通过变更") }} </el-button
        ><el-button @click="decideChange(c.id, 'Rejected')">
          {{ t("驳回变更") }}
        </el-button>
      </div>
    </article>
  </section>
</template>
