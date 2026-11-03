<script setup lang="ts">
import { computed, ref } from "vue";
import { t } from "../i18n";
import { statusNames, healthNames } from "../types";
export interface AlignmentNode {
  id: number;
  title: string;
  level: string;
  status: string;
  owner_name?: string;
  org_id?: number;
  org_name?: string;
  progress?: string | null;
  kr_count?: number;
  key_results?: {
    id: number;
    name: string;
    progress: string;
    health: string;
  }[];
}
export interface AlignmentEdge {
  source: number;
  target: number;
  kind: string;
}
const props = defineProps<{ nodes: AlignmentNode[]; edges: AlignmentEdge[] }>();
const emit = defineEmits<{ select: [id: number] }>();
const zoom = ref(0.85),
  selected = ref<number>(),
  viewport = ref<HTMLDivElement>();
const showParent = ref(true),
  showContribution = ref(true),
  showDependency = ref(true),
  crossOnly = ref(false);
const levels = ["corporate", "division", "department", "team", "personal"];
const names = ["企业", "事业部", "部门", "团队", "个人"];
const width = 270,
  height = 234,
  gapX = 100,
  gapY = 38,
  pad = 32,
  header = 60;
const layout = computed(() => {
  const ids = new Set(props.nodes.map((n) => n.id));
  const depth = new Map(
    props.nodes.map((n) => [n.id, Math.max(0, levels.indexOf(n.level))]),
  );
  // Only parent edges determine hierarchy; lateral contributions and dependencies remain lateral.
  const structural = props.edges.filter(
    (e) => e.kind === "parent" && ids.has(e.source) && ids.has(e.target),
  );
  for (let pass = 0; pass < props.nodes.length; pass++) {
    let changed = false;
    for (const e of structural) {
      const value = Math.min(props.nodes.length + 4, depth.get(e.target)! + 1);
      if (depth.get(e.source)! < value) {
        depth.set(e.source, value);
        changed = true;
      }
    }
    if (!changed) break;
  }
  const columns = [...new Set(depth.values())].sort((a, b) => a - b);
  const rows = columns.map((d) =>
    props.nodes
      .filter((n) => depth.get(n.id) === d)
      .sort((a, b) => a.id - b.id),
  );
  const totalRows = Math.max(1, ...rows.map((r) => r.length));
  const canvasHeight = header + pad * 2 + totalRows * (height + gapY) - gapY;
  const placed = rows.flatMap((row, column) =>
    row.map((n, index) => ({
      ...n,
      x: pad + column * (width + gapX),
      y:
        header +
        pad +
        (canvasHeight -
          header -
          pad * 2 -
          (row.length * (height + gapY) - gapY)) /
          2 +
        index * (height + gapY),
    })),
  );
  return {
    nodes: placed,
    width: pad * 2 + columns.length * (width + gapX) - gapX,
    height: canvasHeight,
    columns: columns.map((d, i) => {
      const kinds = [...new Set(rows[i].map((n) => n.level))];
      return {
        x: pad + i * (width + gapX),
        label:
          kinds.length === 1
            ? names[levels.indexOf(kinds[0])] || "对齐层级"
            : "对齐层级",
        depth: d,
      };
    }),
  };
});
const byId = computed(() => new Map(layout.value.nodes.map((n) => [n.id, n])));
const links = computed(() =>
  props.edges.flatMap((e, index) => {
    const source = byId.value.get(e.source),
      target = byId.value.get(e.target);
    if (!source || !target) return [];
    const cross =
      source.org_id !== undefined &&
      target.org_id !== undefined &&
      source.org_id !== target.org_id;
    if (
      (crossOnly.value && !cross) ||
      (e.kind === "parent" && !showParent.value) ||
      (e.kind === "contributes_to" && !showContribution.value) ||
      (e.kind === "depends_on" && !showDependency.value)
    )
      return [];
    const from = e.kind === "parent" ? target : source,
      to = e.kind === "parent" ? source : target;
    const forward = to.x > from.x;
    const sx = from.x + (forward ? width : 0),
      sy = from.y + height / 2,
      tx = to.x + (forward ? 0 : width),
      ty = to.y + height / 2;
    const bend = Math.max(60, Math.abs(tx - sx) * 0.5);
    const path =
      from.x === to.x
        ? `M ${from.x + width} ${sy} C ${from.x + width + 60} ${sy}, ${to.x + width + 60} ${ty}, ${to.x + width} ${ty}`
        : `M ${sx} ${sy} C ${sx + (forward ? bend : -bend)} ${sy}, ${tx + (forward ? -bend : bend)} ${ty}, ${tx} ${ty}`;
    return [
      {
        ...e,
        index,
        cross,
        path,
        label: `${source.title} → ${target.title}: ${t(e.kind === "parent" ? "父子关系" : e.kind === "contributes_to" ? "贡献关系" : "依赖关系")}`,
        focus:
          selected.value === undefined ||
          selected.value === e.source ||
          selected.value === e.target,
      },
    ];
  }),
);
const connected = computed(
  () =>
    new Set([
      selected.value,
      ...props.edges
        .filter(
          (e) => e.source === selected.value || e.target === selected.value,
        )
        .flatMap((e) => [e.source, e.target]),
    ]),
);
function fit() {
  if (viewport.value)
    zoom.value = Math.max(
      0.25,
      Math.min(1, (viewport.value.clientWidth - 10) / layout.value.width),
    );
}
function percent(value: string | null | undefined) {
  return value === undefined || value === null
    ? "—"
    : Number(value).toFixed(0) + "%";
}
</script>
<template>
  <div class="alignment-tools">
    <div class="alignment-legend">
      <el-checkbox v-model="showParent"
        ><i class="legend-line parent" />{{ t("父子关系") }}</el-checkbox
      ><el-checkbox v-model="showContribution"
        ><i class="legend-line contribution" />{{ t("贡献关系") }}</el-checkbox
      ><el-checkbox v-model="showDependency"
        ><i class="legend-line dependency" />{{ t("依赖关系") }}</el-checkbox
      ><el-checkbox v-model="crossOnly">{{ t("仅跨部门") }}</el-checkbox>
    </div>
    <div class="alignment-zoom">
      <el-button
        size="small"
        :disabled="zoom <= 0.25"
        @click="zoom = Math.max(0.25, zoom - 0.1)"
        :aria-label="t('缩小')"
        >−</el-button
      ><span>{{ Math.round(zoom * 100) }}%</span
      ><el-button
        size="small"
        :disabled="zoom >= 1.5"
        @click="zoom = Math.min(1.5, zoom + 0.1)"
        :aria-label="t('放大')"
        >+</el-button
      ><el-button size="small" @click="fit">{{ t("适应宽度") }}</el-button
      ><el-button
        v-if="selected !== undefined"
        size="small"
        @click="selected = undefined"
        >{{ t("清除选择") }}</el-button
      >
    </div>
  </div>
  <p class="muted alignment-help">
    {{
      t(
        "从战略到执行，沿曲线查看目标关联。点选卡片突出直接关系，点击标题进入详情。",
      )
    }}
  </p>
  <div
    ref="viewport"
    class="alignment-viewport"
    tabindex="0"
    :aria-label="t('可滚动的战略对齐图')"
  >
    <div
      :style="{
        width: layout.width * zoom + 'px',
        height: layout.height * zoom + 'px',
      }"
    >
      <div
        class="alignment-canvas"
        :style="{
          width: layout.width + 'px',
          height: layout.height + 'px',
          transform: `scale(${zoom})`,
        }"
      >
        <div
          v-for="column in layout.columns"
          :key="column.depth"
          class="alignment-column"
          :style="{ left: column.x + 'px', width: width + 'px' }"
        >
          <span
            >{{ t(column.label)
            }}<template v-if="column.depth >= names.length">
              {{ column.depth + 1 }}</template
            ></span
          >
        </div>
        <svg
          class="alignment-wires"
          :width="layout.width"
          :height="layout.height"
          aria-hidden="true"
        >
          <defs>
            <marker
              v-for="kind in ['parent', 'contributes_to', 'depends_on']"
              :key="kind"
              :id="'arrow-' + kind"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
              markerUnits="userSpaceOnUse"
            >
              <path
                d="M 0 1 L 9 5 L 0 9 z"
                :fill="
                  kind === 'parent'
                    ? '#ed9228'
                    : kind === 'contributes_to'
                      ? '#53b5cf'
                      : '#8c72b9'
                "
              />
            </marker>
          </defs>
          <g
            v-for="edge in links"
            :key="edge.index"
            :style="{ opacity: edge.focus ? 1 : 0.12 }"
          >
            <path
              :d="edge.path"
              :class="['alignment-wire', edge.kind]"
              :marker-end="`url(#arrow-${edge.kind})`"
            />
            <path v-if="edge.cross" :d="edge.path" class="cross-wire" />
            <title>{{ edge.label }}</title>
          </g>
        </svg>
        <article
          v-for="node in layout.nodes"
          :key="node.id"
          :class="[
            'alignment-card',
            {
              selected: selected === node.id,
              dimmed: selected !== undefined && !connected.has(node.id),
            },
          ]"
          :style="{
            left: node.x + 'px',
            top: node.y + 'px',
            width: width + 'px',
            height: height + 'px',
          }"
          tabindex="0"
          :aria-label="node.title"
          @click="selected = node.id"
          @keydown.enter.self.prevent="selected = node.id"
          @keydown.space.self.prevent="selected = node.id"
        >
          <div class="alignment-card-top">
            <span>{{ t(names[levels.indexOf(node.level)] || "目标") }}</span
            ><span>{{ statusNames[node.status] || node.status }}</span>
          </div>
          <button class="alignment-title" @click.stop="emit('select', node.id)">
            {{ node.title }}
          </button>
          <div class="alignment-owner">
            <span class="alignment-avatar">{{
              node.owner_name?.slice(0, 1) || "—"
            }}</span>
            <div>
              <strong>{{ node.owner_name || "—" }}</strong
              ><span>{{ node.org_name || "—" }}</span>
            </div>
            <span class="alignment-score">{{ percent(node.progress) }}</span>
          </div>
          <div class="alignment-progress">
            <span
              :style="{
                width:
                  Math.max(0, Math.min(100, Number(node.progress) || 0)) + '%',
              }"
            />
          </div>
          <div class="alignment-krs">
            <div v-for="kr in node.key_results || []" :key="kr.id">
              <span
                :class="['alignment-health', kr.health]"
                :title="healthNames[kr.health]"
              /><span :title="kr.name">{{ kr.name }}</span
              ><strong>{{ percent(kr.progress) }}</strong>
            </div>
            <span v-if="!node.key_results?.length" class="muted">{{
              t("暂无关键结果")
            }}</span
            ><small v-else-if="(node.kr_count || 0) > 2"
              >+{{ (node.kr_count || 0) - 2 }} {{ t("个关键结果") }}</small
            >
          </div>
        </article>
      </div>
    </div>
  </div>
  <div class="alignment-relation-list">
    <details>
      <summary>{{ t("关系明细") }} ({{ links.length }})</summary>
      <ul>
        <li v-for="edge in links" :key="edge.index">
          <span
            >{{ byId.get(edge.source)?.title }} <b>→</b>
            {{ byId.get(edge.target)?.title }}</span
          ><small
            >{{
              t(
                edge.kind === "parent"
                  ? "父目标"
                  : edge.kind === "contributes_to"
                    ? "贡献于"
                    : "依赖于",
              )
            }}<template v-if="edge.cross">
              · {{ t("跨部门") }}: {{ byId.get(edge.source)?.org_name }} /
              {{ byId.get(edge.target)?.org_name }}</template
            ></small
          >
        </li>
      </ul>
    </details>
  </div>
</template>
<style scoped>
.alignment-tools {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.alignment-legend,
.alignment-zoom {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.alignment-legend .el-checkbox {
  margin-right: 0;
}
.legend-line {
  display: inline-block;
  width: 22px;
  border-top: 5px solid #efa633;
  margin-right: 7px;
  vertical-align: middle;
}
.legend-line.contribution {
  border-color: #67c0d6;
}
.legend-line.dependency {
  border-top: 3px dashed #8c72b9;
}
.alignment-zoom span {
  font-size: 12px;
  min-width: 35px;
  text-align: center;
}
.alignment-zoom .el-button + .el-button {
  margin-left: 0;
}
.alignment-help {
  line-height: 1.8;
}
.alignment-viewport {
  overflow: auto;
  max-height: 780px;
  min-height: 360px;
  background:
    radial-gradient(#e8e9ed 1px, transparent 1px) 0 0/18px 18px,
    #fafbfc;
  border: 1px solid #e9e9e9;
  border-radius: 5px;
  overscroll-behavior: contain;
}
.alignment-canvas {
  position: relative;
  transform-origin: top left;
}
.alignment-column {
  position: absolute;
  top: 22px;
  padding-bottom: 14px;
  border-bottom: 2px solid #e5e7eb;
  font-size: 13px;
  font-weight: 600;
  color: #667080;
}
.alignment-wires {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.alignment-wire {
  fill: none;
  stroke: #efa633;
  stroke-width: 12;
  stroke-opacity: 0.5;
}
.alignment-wire.contributes_to {
  stroke: #67c0d6;
  stroke-width: 9;
  stroke-opacity: 0.55;
}
.alignment-wire.depends_on {
  stroke: #8c72b9;
  stroke-width: 2.5;
  stroke-dasharray: 7 6;
  stroke-opacity: 0.9;
}
.cross-wire {
  fill: none;
  stroke: #436c85;
  stroke-width: 1;
  stroke-dasharray: 2 7;
  opacity: 0.7;
}
.alignment-card {
  position: absolute;
  background: #fff;
  border: 1px solid #dfe4e9;
  border-top: 3px solid #efa633;
  border-radius: 6px;
  box-shadow: 0 4px 15px #1d34420a;
  padding: 13px 15px;
  cursor: pointer;
  transition:
    opacity 0.15s,
    border-color 0.15s;
}
.alignment-card.selected {
  border-color: #d84b20;
  box-shadow: 0 0 0 2px #ed431c26;
}
.alignment-card.dimmed {
  opacity: 0.3;
}
.alignment-card:focus-visible {
  outline: 2px solid #c93616;
  outline-offset: 3px;
}
.alignment-card-top {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: #7c8794;
  gap: 8px;
}
.alignment-title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-align: left;
  line-height: 1.5;
  font-weight: 650;
  font-size: 14px;
  background: none;
  border: 0;
  padding: 0;
  margin: 10px 0;
  color: #283846;
  max-height: 42px;
  min-height: 42px;
  width: 100%;
}
.alignment-title:hover {
  color: #c93616;
}
.alignment-owner {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}
.alignment-avatar {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #eef4f6;
  color: #51829a;
  flex-shrink: 0;
}
.alignment-owner > div {
  min-width: 0;
}
.alignment-owner strong,
.alignment-owner div > span {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 150px;
}
.alignment-owner strong {
  font-weight: 500;
}
.alignment-owner div > span {
  font-size: 10px;
  color: #83909d;
  margin-top: 3px;
}
.alignment-score {
  margin-left: auto;
  color: #ba5b19;
  font-weight: 650;
}
.alignment-progress {
  height: 3px;
  background: #f0f1f3;
  margin: 12px 0;
  border-radius: 3px;
}
.alignment-progress > span {
  display: block;
  height: 100%;
  background: #efa633;
  border-radius: 3px;
}
.alignment-krs > div {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  margin: 9px 0;
}
.alignment-krs > div > span:nth-child(2) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}
.alignment-krs strong {
  font-weight: 500;
}
.alignment-krs small {
  font-size: 9px;
  color: #8b95a0;
}
.alignment-health {
  width: 5px;
  height: 5px;
  flex-shrink: 0;
  border-radius: 50%;
  background: #b9bec5;
}
.alignment-health.Green {
  background: #4b8660;
}
.alignment-health.Amber {
  background: #d9b565;
}
.alignment-health.Red {
  background: #c47565;
}
.alignment-relation-list {
  font-size: 12px;
  color: #647381;
  margin-top: 18px;
}
.alignment-relation-list summary {
  cursor: pointer;
}
.alignment-relation-list ul {
  padding-left: 20px;
}
.alignment-relation-list li {
  padding: 8px 0;
}
.alignment-relation-list small {
  display: block;
  margin-top: 5px;
  color: #83909d;
}
</style>
