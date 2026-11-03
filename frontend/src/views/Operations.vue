<script setup lang="ts">
import { t } from "../i18n";

import { onMounted, ref } from "vue";
import { ElMessageBox } from "element-plus";
import { api, write } from "../api";
const jobs = ref<
  {
    id: number;
    kind: string;
    status: string;
    attempts: number;
    next_run: string;
    error: string;
  }[]
>([]);
async function load() {
  jobs.value = await api("/api/v1/admin/jobs");
}
async function retry(id: number) {
  try {
    await ElMessageBox.confirm(
      t("确认依赖已恢复，并重试此失败任务？"),
      t("重放任务"),
      { confirmButtonText: t("重试"), cancelButtonText: t("取消") },
    );
    await write(`/api/v1/admin/jobs/${id}/retry`, {});
    await load();
  } catch {
    /* cancelled */
  }
}
onMounted(load);
</script>
<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">BACKGROUND OPERATIONS</div>
      <h1>{{ t("任务运维") }}</h1>
      <p>{{ t("检查任务状态，在依赖恢复后重放失败任务。") }}</p>
    </div>
    <el-button @click="load"> {{ t("刷新任务") }} </el-button>
  </div>
  <section class="panel">
    <el-table :data="jobs" :empty-text="t('暂无后台任务')"
      ><el-table-column
        prop="id"
        :label="t('任务')"
        width="90"
      /><el-table-column
        prop="kind"
        :label="t('类型')"
        width="120"
      /><el-table-column
        prop="status"
        :label="t('状态')"
        width="110"
      /><el-table-column
        prop="attempts"
        :label="t('尝试次数')"
        width="100"
      /><el-table-column
        prop="error"
        :label="t('失败原因')"
        min-width="250"
      /><el-table-column width="100"
        ><template #default="{ row }"
          ><el-button
            v-if="row.status === 'Failed'"
            link
            @click="retry(row.id)"
          >
            {{ t("重试") }}
          </el-button></template
        ></el-table-column
      ></el-table
    >
    <p class="muted">
      {{
        t("显示最新200条任务。任务重放写入审计，不改变业务审批及证据扫描规则。")
      }}
    </p>
  </section>
</template>
