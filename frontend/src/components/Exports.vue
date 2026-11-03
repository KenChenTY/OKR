<script setup lang="ts">
import { t, formatDate } from "../i18n";

import { ref } from "vue";
import { api, write } from "../api";
import { useSession } from "../stores/session";
const session = useSession(),
  dialog = ref(false),
  busy = ref(false);
const items = ref<
  { id: number; status: string; created_at: string; expires_at: string }[]
>([]);
async function load() {
  items.value = await api("/api/v1/exports");
}
async function open() {
  dialog.value = true;
  await load();
}
async function create() {
  busy.value = true;
  try {
    await write("/api/v1/exports", { cycle_id: session.cycleId || null });
    await load();
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <el-button
    v-if="
      ['Manager', 'Division Head', 'PMO', 'Audit'].includes(
        session.user?.role || '',
      )
    "
    @click="open"
  >
    {{ t("导出报表") }} </el-button
  ><el-dialog v-model="dialog" :title="t('报表导出')" width="650px"
    ><p class="muted">
      {{
        t(
          "按当前周期和授权范围生成CSV，文件保留24小时。生成后刷新状态查看下载入口。",
        )
      }}
    </p>
    <div class="toolbar">
      <el-button type="primary" :loading="busy" @click="create">
        {{ t("创建导出任务") }} </el-button
      ><el-button @click="load"> {{ t("刷新状态") }} </el-button>
    </div>
    <el-table :data="items" :empty-text="t('暂无导出任务')"
      ><el-table-column :label="t('创建时间')" min-width="180"
        ><template #default="{ row }">{{
          formatDate(row.created_at)
        }}</template></el-table-column
      ><el-table-column prop="status" :label="t('状态')" /><el-table-column
        width="90"
        ><template #default="{ row }"
          ><a
            v-if="row.status === 'Completed'"
            :href="'/api/v1/exports/' + row.id + '/download'"
          >
            {{ t("下载CSV") }}
          </a></template
        ></el-table-column
      ></el-table
    ></el-dialog
  >
</template>
