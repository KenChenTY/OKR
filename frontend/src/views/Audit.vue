<script setup lang="ts">
import { t, formatDate } from "../i18n";

import { onMounted, ref } from "vue";
import { api } from "../api";
const items = ref<
    {
      id: number;
      action: string;
      actor: string;
      objective_id: number;
      detail: unknown;
      request_id: string;
      occurred_at: string;
    }[]
  >([]),
  page = ref(1),
  loading = ref(false);
async function load() {
  loading.value = true;
  try {
    items.value = await api("/api/v1/audit-events?page=" + page.value);
  } finally {
    loading.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">TRACEABLE BY DESIGN</div>
      <h1>{{ t("审计记录") }}</h1>
      <p>{{ t("查询授权范围内的业务操作与变更轨迹。") }}</p>
    </div>
    <el-button @click="load"> {{ t("刷新记录") }} </el-button>
  </div>
  <section class="panel">
    <el-table
      v-loading="loading"
      :data="items"
      :empty-text="t('暂无可访问的审计记录')"
      ><el-table-column type="expand"
        ><template #default="{ row }">
          <pre class="code-detail" style="padding: 15px">{{
            JSON.stringify(row.detail, null, 2)
          }}</pre>
        </template></el-table-column
      ><el-table-column
        prop="action"
        :label="t('操作')"
        width="170" /><el-table-column
        prop="actor"
        :label="t('操作者')"
        width="170" /><el-table-column
        prop="objective_id"
        :label="t('目标ID')"
        width="100" /><el-table-column :label="t('发生时间')" width="190"
        ><template #default="{ row }">{{
          formatDate(row.occurred_at)
        }}</template></el-table-column
      ><el-table-column prop="request_id" :label="t('追踪ID')" min-width="180"
    /></el-table>
    <div class="pagination">
      <el-button
        :disabled="page === 1"
        @click="
          page--;
          load();
        "
      >
        {{ t("上一页") }} </el-button
      ><span style="margin: 8px" class="muted">
        {{ t("第") }} {{ page }} {{ t("页") }} </span
      ><el-button
        :disabled="items.length < 50"
        @click="
          page++;
          load();
        "
      >
        {{ t("下一页") }}
      </el-button>
    </div>
  </section>
</template>
