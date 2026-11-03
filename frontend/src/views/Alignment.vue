<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api";
import { t } from "../i18n";
import { useSession } from "../stores/session";
import { statusNames } from "../types";
import AlignmentMap, {
  type AlignmentNode,
  type AlignmentEdge,
} from "../components/AlignmentMap.vue";
const session = useSession(),
  router = useRouter();
const graph = ref<{ nodes: AlignmentNode[]; edges: AlignmentEdge[] }>({
    nodes: [],
    edges: [],
  }),
  loading = ref(false),
  error = ref(false);
async function load() {
  loading.value = true;
  error.value = false;
  try {
    graph.value = await api(
      `/api/v1/alignment${session.cycleId ? "?cycle_id=" + session.cycleId : ""}`,
    );
  } catch {
    error.value = true;
  } finally {
    loading.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">STRATEGIC ALIGNMENT</div>
      <h1>{{ t("战略对齐") }}</h1>
      <p>{{ t("从团队行动到企业战略，看见目标之间的联系。") }}</p>
    </div>
    <span class="muted"
      >{{ graph.nodes.length }} {{ t("个目标 ·") }} {{ graph.edges.length }}
      {{ t("条关系") }}</span
    >
  </div>
  <section class="panel" v-loading="loading">
    <div class="panel-title">
      <h2>{{ t("目标关系图") }}</h2>
      <el-button @click="load">{{ t("刷新数据") }}</el-button>
    </div>
    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      :title="t('数据加载失败，请稍后重试')"
    />
    <AlignmentMap
      v-if="graph.nodes.length"
      :nodes="graph.nodes"
      :edges="graph.edges"
      @select="(id) => router.push('/objectives/' + id)"
    />
    <el-empty
      v-else-if="!error"
      :description="t('暂无目标，创建目标后即可设置对齐关系')"
    />
  </section>
  <section v-if="graph.nodes.length" class="panel">
    <div class="panel-title">
      <h2>{{ t("可访问目标") }}</h2>
      <span class="muted">{{ t("关系仅在双方均有访问权限时展示") }}</span>
    </div>
    <el-table :data="graph.nodes"
      ><el-table-column
        prop="title"
        :label="t('目标')"
        min-width="240"
      /><el-table-column
        prop="owner_name"
        :label="t('负责人')"
        min-width="140"
      /><el-table-column
        prop="org_name"
        :label="t('所属部门')"
        min-width="140"
      /><el-table-column :label="t('状态')" min-width="130"
        ><template #default="{ row }">{{
          statusNames[row.status] || row.status
        }}</template></el-table-column
      ><el-table-column width="120"
        ><template #default="{ row }"
          ><el-button link @click="router.push('/objectives/' + row.id)">{{
            t("查看详情")
          }}</el-button></template
        ></el-table-column
      ></el-table
    >
  </section>
</template>
