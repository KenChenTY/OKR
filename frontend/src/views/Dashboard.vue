<script setup lang="ts">
import { t, formatDate } from "../i18n";

import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { Plus, ArrowRight } from "@element-plus/icons-vue";
import { api } from "../api";
import { useSession } from "../stores/session";
import type { Objective } from "../types";
import { statusNames } from "../types";
import Chart from "../components/Chart.vue";
import OrganizationAnalytics from "../components/OrganizationAnalytics.vue";
const session = useSession(),
  router = useRouter();
interface Dashboard {
  total: number;
  effective_count: number;
  achievement: string | null;
  health: Record<string, number>;
  statuses: Record<string, number>;
  attention: Objective[];
  as_of: string;
  themes: { name: string; count: number }[];
}
const data = ref<Dashboard>(),
  loading = ref(true),
  error = ref(false);
const notices = ref<{ id: number; objective_id: number; message: string }[]>(
  [],
);
async function load() {
  loading.value = true;
  error.value = false;
  try {
    data.value = await api(
      `/api/v1/dashboards/executive${session.cycleId ? "?cycle_id=" + session.cycleId : ""}`,
    );
    notices.value = await api("/api/v1/notifications");
  } catch {
    error.value = true;
  } finally {
    loading.value = false;
  }
}
onMounted(load);
const healthOption = computed(() => ({
  tooltip: { trigger: "item" as const },
  legend: {
    bottom: 0,
    icon: "circle",
    itemWidth: 8,
    textStyle: { color: "#666666", fontSize: 11 },
  },
  color: ["#4b8660", "#d9b565", "#c47565", "#dce2d5"],
  series: [
    {
      type: "pie" as const,
      radius: ["53%", "72%"],
      center: ["50%", "43%"],
      label: { show: false },
      data: [
        { name: t("进展正常"), value: data.value?.health.Green || 0 },
        { name: t("存在风险"), value: data.value?.health.Amber || 0 },
        { name: t("偏离计划"), value: data.value?.health.Red || 0 },
        { name: t("缺少更新"), value: data.value?.health.Gray || 0 },
      ],
    },
  ],
}));
const themeOption = computed(() => ({
  tooltip: { trigger: "axis" as const },
  grid: { left: 15, right: 25, top: 20, bottom: 15, containLabel: true },
  xAxis: {
    type: "value" as const,
    minInterval: 1,
    splitLine: { lineStyle: { color: "#eeeeee" } },
  },
  yAxis: {
    type: "category" as const,
    data: data.value?.themes.map((t) => t.name),
    axisLine: { show: false },
    axisTick: { show: false },
  },
  series: [
    {
      type: "bar" as const,
      barMaxWidth: 19,
      itemStyle: { color: "#c93616", borderRadius: [0, 3, 3, 0] },
      data: data.value?.themes.map((t) => t.count),
    },
  ],
}));
</script>
<template>
  <div v-loading="loading">
    <div class="page-heading">
      <div>
        <div class="eyebrow">YOUR STRATEGY, IN MOTION</div>
        <h1>{{ t("工作总览") }}</h1>
        <p>{{ t("聚焦重要目标，掌握每一项关键结果的进展。") }}</p>
      </div>
      <el-button
        type="primary"
        :icon="Plus"
        @click="router.push('/objectives?create=1')"
      >
        {{ t("创建目标") }}
      </el-button>
    </div>
    <el-alert
      v-if="error"
      class="error-banner"
      :title="t('数据加载失败，请稍后重试')"
      type="error"
      :closable="false"
      ><el-button link @click="load"> {{ t("重新加载") }} </el-button></el-alert
    ><template v-if="data"
      ><div class="kpi-grid">
        <div class="kpi featured">
          <div class="label">{{ t("整体达成率") }} <span>↗</span></div>
          <div class="value">
            {{ data.achievement ?? "—"
            }}<small v-if="data.achievement !== null">%</small>
          </div>
          <div class="caption">
            {{ data.effective_count }} {{ t("个有效目标 · 等权计算") }}
          </div>
        </div>
        <div class="kpi">
          <div class="label">{{ t("本周期目标") }} <span>◎</span></div>
          <div class="value">{{ data.total }}</div>
          <div class="caption">
            {{ data.statuses.Active }} {{ t("个执行中 ·") }}
            {{ data.statuses.Completed }} {{ t("个已完成") }}
          </div>
        </div>
        <div class="kpi">
          <div class="label">{{ t("需要关注的 KR") }} <span>◷</span></div>
          <div class="value">{{ data.health.Red + data.health.Amber }}</div>
          <div class="caption">
            {{ data.health.Red }} {{ t("个偏离计划 ·") }}
            {{ data.health.Amber }} {{ t("个存在风险") }}
          </div>
        </div>
        <div class="kpi">
          <div class="label">{{ t("待更新的 KR") }} <span>↻</span></div>
          <div class="value">{{ data.health.Gray }}</div>
          <div class="caption">{{ t("尚未更新或已超过更新宽限期") }}</div>
        </div>
      </div>
      <div class="two-column">
        <section class="panel">
          <div class="panel-title">
            <h2>{{ t("战略主题分布") }}</h2>
            <span class="muted"> {{ t("目标数量") }} </span>
          </div>
          <Chart v-if="data.themes.length" :option="themeOption" /><el-empty
            v-else
            :description="t('创建目标后，战略主题将在这里呈现')"
            :image-size="90"
          />
        </section>
        <section class="panel">
          <div class="panel-title">
            <h2>{{ t("关键结果健康度") }}</h2>
            <span class="muted"> {{ t("当前有效目标") }} </span>
          </div>
          <Chart
            v-if="Object.values(data.health).some(Boolean)"
            :option="healthOption"
          /><el-empty
            v-else
            :description="t('暂无可统计的关键结果')"
            :image-size="90"
          />
        </section>
      </div>
      <section class="panel">
        <div class="panel-title">
          <h2>{{ t("需要关注的目标") }}</h2>
          <el-button link @click="router.push('/objectives')">
            {{ t("查看全部") }} <el-icon><ArrowRight /></el-icon
          ></el-button>
        </div>
        <el-table
          :data="data.attention"
          :empty-text="t('暂时没有需要关注的目标')"
          ><el-table-column :label="t('目标')" min-width="250"
            ><template #default="{ row }"
              ><div
                class="table-title"
                @click="router.push('/objectives/' + row.id)"
              >
                {{ row.title }}
              </div>
              <div class="table-subtitle">
                {{ row.code }} · {{ row.theme }}
              </div></template
            ></el-table-column
          ><el-table-column
            prop="owner_name"
            :label="t('负责人')"
            width="150" /><el-table-column :label="t('状态')" width="110"
            ><template #default="{ row }"
              ><span :class="['status-badge', row.status]">{{
                statusNames[row.status]
              }}</span></template
            ></el-table-column
          ><el-table-column :label="t('达成率')" width="170"
            ><template #default="{ row }"
              ><el-progress
                :percentage="Number(row.progress || 0)"
                :stroke-width="5"
                color="#c93616" /></template></el-table-column
        ></el-table>
      </section>
      <section v-if="notices.length" class="panel">
        <div class="panel-title">
          <h2>{{ t("我的提醒") }}</h2>
        </div>
        <ul class="action-list">
          <li v-for="n in notices" :key="n.id">
            <span>{{ n.message }}</span
            ><el-button
              link
              @click="router.push('/objectives/' + n.objective_id)"
            >
              {{ t("查看") }}
            </el-button>
          </li>
        </ul>
      </section>
      <p class="muted">
        {{
          t(
            "统计范围为当前授权范围及所选周期，取消和归档目标不参与达成率。更新时间：",
          )
        }}
        {{ formatDate(data.as_of) }}
      </p></template
    >
    <OrganizationAnalytics />
  </div>
</template>
