<script setup lang="ts">
import { t } from "../i18n";

import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import { init, use, type EChartsType } from "echarts/core";
import { BarChart, PieChart, GraphChart } from "echarts/charts";
import {
  TooltipComponent,
  LegendComponent,
  GridComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts";
use([
  BarChart,
  PieChart,
  GraphChart,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  CanvasRenderer,
]);
const props = defineProps<{ option: EChartsOption }>();
const emit = defineEmits<{ select: [id: number] }>();
const container = ref<HTMLDivElement>();
let chart: EChartsType | undefined;
let observer: ResizeObserver | undefined;
onMounted(() => {
  chart = init(container.value!);
  chart.setOption(props.option);
  observer = new ResizeObserver(() => chart?.resize());
  observer.observe(container.value!);
  chart.on("click", (params) => {
    const data = params.data as { objectiveId?: number };
    if (data?.objectiveId) emit("select", data.objectiveId);
  });
});
watch(
  () => props.option,
  (option) => chart?.setOption(option, true),
  { deep: true },
);
onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
});
</script>
<template>
  <div
    ref="container"
    class="chart"
    role="img"
    :aria-label="t('业务数据可视化图表')"
  ></div>
</template>
