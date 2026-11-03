<script setup lang="ts">
import { t, formatDate } from "../i18n";

import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, ArrowLeft, Upload } from "@element-plus/icons-vue";
import { api, write } from "../api";
import { useSession } from "../stores/session";
import { healthNames, statusNames } from "../types";
import type { Objective, KR } from "../types";
import Governance from "../components/Governance.vue";
const route = useRoute(),
  router = useRouter(),
  session = useSession();
const obj = ref<Objective>(),
  loading = ref(false),
  busy = ref(false),
  tab = ref("krs");
const krDialog = ref(false),
  checkDialog = ref(false),
  historyDialog = ref(false),
  linkDialog = ref(false),
  editDialog = ref(false),
  relationDialog = ref(false);
const selectedKR = ref<KR>(),
  history = ref<
    {
      id: number;
      actor: string;
      current_value: string;
      commentary: string;
      risks: string;
      blockers: string;
      next_action: string;
      effective_at: string;
    }[]
  >([]);
const sourceDialog = ref(false),
  sourceValue = ref("");
function openSource(k: KR) {
  selectedKR.value = k;
  sourceValue.value = k.evidence_source || "";
  sourceDialog.value = true;
}
async function saveSource() {
  if (!selectedKR.value) return;
  busy.value = true;
  try {
    await write(
      `/api/v1/key-results/${selectedKR.value.id}/evidence-source`,
      { evidence_source: sourceValue.value },
      selectedKR.value.etag,
      "PATCH",
    );
    sourceDialog.value = false;
    await load();
  } finally {
    busy.value = false;
  }
}
const kr = reactive({
  name: "",
  value_type: "number",
  direction: "increase",
  baseline: "0",
  target: "100",
  weight: "100",
  unit: "%",
  currency: "",
  frequency: "monthly",
  evidence_source: "",
  milestones: [] as { name: string; weight: string; due_date: string }[],
});
const check = reactive({
  current_value: "",
  confidence: 80,
  commentary: "",
  risks: "",
  blockers: "",
  next_action: "",
  severe_blocker: false,
  evidence_version_ids: [] as number[],
});
const link = reactive({
  name: "",
  url: "",
  previous_id: undefined as number | undefined,
});
const relation = reactive({
  target_id: undefined as number | undefined,
  kind: "contributes_to",
});
const edit = reactive({
  title: "",
  description: "",
  cycle_id: 0,
  theme: "",
  priority: "",
  level: "",
  visibility: "organization",
  start_date: "",
  end_date: "",
});
const targets = ref<Objective[]>([]),
  previousFile = ref<number>(),
  fileInput = ref<HTMLInputElement>();
const isOwner = computed(() => obj.value?.owner_id === session.user?.id);
const isManager = computed(
  () =>
    ["Manager", "Division Head"].includes(session.user?.role || "") &&
    !isOwner.value,
);
const totalWeight = computed(
  () =>
    obj.value?.key_results?.reduce(
      (sum, item) => sum + Number(item.weight),
      0,
    ) || 0,
);
const checkProgress = computed(() => {
  const k = selectedKR.value;
  return k
    ? Math.max(
        0,
        Math.min(
          100,
          ((Number(check.current_value) - Number(k.baseline)) /
            (Number(k.target) - Number(k.baseline))) *
            100,
        ),
      ).toFixed(2)
    : "0";
});
async function load() {
  loading.value = true;
  try {
    obj.value = await api(`/api/v1/objectives/${route.params.id}`);
  } finally {
    loading.value = false;
  }
}
onMounted(load);
async function submit() {
  if (!obj.value) return;
  busy.value = true;
  try {
    await write(
      `/api/v1/objectives/${obj.value.id}/submit`,
      {},
      obj.value.etag,
    );
    ElMessage.success(t("已提交审批"));
    await load();
  } finally {
    busy.value = false;
  }
}
async function transition(action: string) {
  if (!obj.value) return;
  try {
    const { value } = await ElMessageBox.prompt(
      t("请填写操作原因或结项说明"),
      t("确认操作"),
      {
        inputValidator: (v) => !!v?.trim() || t("原因不能为空"),
        confirmButtonText: t("确认"),
        cancelButtonText: t("取消"),
      },
    );
    busy.value = true;
    await write(
      `/api/v1/objectives/${obj.value.id}/transitions`,
      { action, reason: value },
      obj.value.etag,
    );
    await load();
  } catch (e) {
    if (e !== "cancel" && e !== "close")
      console.debug("Transition not completed");
  } finally {
    busy.value = false;
  }
}
async function addKR() {
  if (!obj.value) return;
  busy.value = true;
  try {
    await write(
      `/api/v1/objectives/${obj.value.id}/key-results`,
      {
        ...kr,
        currency: kr.currency || null,
        milestones: kr.value_type === "milestone" ? kr.milestones : [],
      },
      obj.value.etag,
    );
    krDialog.value = false;
    kr.name = "";
    await load();
  } finally {
    busy.value = false;
  }
}
function openCheck(k: KR) {
  selectedKR.value = k;
  Object.assign(check, {
    current_value: k.current_value,
    confidence: k.confidence,
    commentary: "",
    risks: "",
    blockers: "",
    next_action: "",
    severe_blocker: false,
    evidence_version_ids: [],
  });
  checkDialog.value = true;
}
async function saveCheck() {
  if (!selectedKR.value) return;
  busy.value = true;
  try {
    await write(
      `/api/v1/key-results/${selectedKR.value.id}/check-ins`,
      { ...check, effective_at: new Date().toISOString() },
      selectedKR.value.etag,
    );
    checkDialog.value = false;
    await load();
    ElMessage.success(t("进展已更新"));
  } finally {
    busy.value = false;
  }
}
async function showHistory(k: KR) {
  selectedKR.value = k;
  history.value = await api(`/api/v1/key-results/${k.id}/check-ins`);
  historyDialog.value = true;
}
async function removeKR(k: KR) {
  try {
    await ElMessageBox.confirm(
      t("删除尚未发布的关键结果？"),
      t("删除关键结果"),
      {
        type: "warning",
      },
    );
    await api(`/api/v1/key-results/${k.id}`, {
      method: "DELETE",
      headers: { "If-Match": k.etag },
    });
    await load();
  } catch {
    /* Cancellation or API error already shown */
  }
}
async function accept(k: KR, id: number) {
  busy.value = true;
  try {
    await write(`/api/v1/milestones/${id}/accept`, {}, k.etag);
    await load();
  } finally {
    busy.value = false;
  }
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file || !obj.value) return;
  const data = new FormData();
  data.append("objective_id", String(obj.value.id));
  data.append("file", file);
  if (previousFile.value)
    data.append("previous_id", String(previousFile.value));
  busy.value = true;
  try {
    await api("/api/v1/evidence/uploads", { method: "POST", body: data });
    ElMessage.success(t("已上传至隔离区，扫描通过后可下载"));
    await load();
  } finally {
    busy.value = false;
    input.value = "";
    previousFile.value = undefined;
  }
}
async function saveLink() {
  if (!obj.value) return;
  busy.value = true;
  try {
    await write("/api/v1/evidence/links", {
      ...link,
      objective_id: obj.value.id,
    });
    linkDialog.value = false;
    await load();
  } finally {
    busy.value = false;
  }
}
function openEdit() {
  if (!obj.value) return;
  const o = obj.value;
  Object.assign(edit, {
    title: o.title,
    description: o.description,
    cycle_id: o.cycle_id,
    theme: o.theme,
    priority: o.priority,
    level: o.level,
    visibility: o.visibility,
    start_date: o.start_date,
    end_date: o.end_date,
  });
  editDialog.value = true;
}
async function saveEdit() {
  if (!obj.value) return;
  busy.value = true;
  try {
    await write(
      `/api/v1/objectives/${obj.value.id}`,
      edit,
      obj.value.etag,
      "PATCH",
    );
    editDialog.value = false;
    await load();
  } finally {
    busy.value = false;
  }
}
async function openRelation() {
  const result = await api<{ items: Objective[] }>(
    `/api/v1/objectives?cycle_id=${obj.value?.cycle_id}&page_size=100`,
  );
  targets.value = result.items.filter((o) => o.id !== obj.value?.id);
  relationDialog.value = true;
}
async function saveRelation() {
  if (!obj.value || !relation.target_id) return;
  busy.value = true;
  try {
    await write(
      `/api/v1/objectives/${obj.value.id}/relations`,
      relation,
      obj.value.etag,
    );
    relationDialog.value = false;
    await load();
    ElMessage.success(t("对齐关系已保存"));
  } finally {
    busy.value = false;
  }
}
function pickVersion(id?: number) {
  previousFile.value = id;
  fileInput.value?.click();
}
</script>
<template>
  <el-dialog v-model="sourceDialog" :title="t('证据来源')" width="520px"
    ><el-input v-model="sourceValue" :maxlength="255" /><template #footer
      ><el-button
        type="primary"
        :loading="busy"
        :disabled="!sourceValue.trim()"
        @click="saveSource"
        >{{ t("保存修改") }}</el-button
      ></template
    ></el-dialog
  >
  <div v-loading="loading">
    <el-button
      link
      :icon="ArrowLeft"
      style="margin-bottom: 20px"
      @click="router.push('/objectives')"
    >
      {{ t("返回目标列表") }} </el-button
    ><template v-if="obj"
      ><div class="page-heading">
        <div>
          <div class="eyebrow">{{ obj.code }}</div>
          <h1>{{ obj.title }}</h1>
          <p>{{ obj.description }}</p>
        </div>
        <div class="heading-actions">
          <span :class="['status-badge', obj.status]">{{
            statusNames[obj.status]
          }}</span
          ><el-button
            v-if="isOwner && obj.status === 'Draft'"
            @click="openEdit"
          >
            {{ t("编辑") }} </el-button
          ><el-button
            v-if="isOwner && obj.status === 'Draft'"
            type="primary"
            :loading="busy"
            @click="submit"
          >
            {{ t("提交审批") }} </el-button
          ><el-button
            v-if="isOwner && obj.status === 'Submitted'"
            @click="transition('withdraw')"
          >
            {{ t("撤回") }} </el-button
          ><el-button
            v-if="isOwner && obj.status === 'Approved'"
            type="primary"
            @click="transition('activate')"
          >
            {{ t("开始执行") }} </el-button
          ><el-button
            v-if="isOwner && obj.status === 'Active'"
            :disabled="
              obj.approvals?.some(
                (a) => a.stage === 'Completion' && a.status === 'Pending',
              )
            "
            @click="transition('request_completion')"
          >
            {{ t("申请结项") }} </el-button
          ><el-button
            v-if="
              isManager &&
              obj.status === 'Active' &&
              obj.approvals?.some(
                (a) =>
                  a.stage === 'Completion' &&
                  a.status === 'Pending' &&
                  a.assignee_id === session.user?.id,
              )
            "
            type="primary"
            @click="transition('complete')"
          >
            {{ t("确认结项") }} </el-button
          ><el-dropdown
            v-if="(isOwner && obj.status === 'Draft') || isManager"
            @command="transition"
            ><el-button> {{ t("更多操作") }} </el-button
            ><template #dropdown
              ><el-dropdown-menu
                ><el-dropdown-item
                  v-if="
                    ['Draft', 'Submitted', 'Approved', 'Active'].includes(
                      obj.status,
                    )
                  "
                  command="cancel"
                >
                  {{ t("取消目标") }} </el-dropdown-item
                ><el-dropdown-item
                  v-if="['Completed', 'Cancelled'].includes(obj.status)"
                  command="archive"
                >
                  {{ t("归档目标") }}
                </el-dropdown-item></el-dropdown-menu
              ></template
            ></el-dropdown
          >
        </div>
      </div>
      <section class="panel">
        <div class="panel-title">
          <div>
            <span class="muted"> {{ t("目标达成率") }} </span
            ><strong style="font-size: 26px; margin-left: 15px">{{
              obj.progress === null ? t("未计算") : obj.progress + "%"
            }}</strong>
          </div>
          <span class="muted">
            {{ t("版本") }} {{ obj.revision }} · {{ obj.kr_count }}
            {{ t("个关键结果") }}
          </span>
        </div>
        <el-progress
          :percentage="Number(obj.progress || 0)"
          :show-text="false"
          :stroke-width="7"
          color="#c93616"
        />
        <div class="detail-meta">
          <span>
            {{ t("负责人") }} <strong>{{ obj.owner_name }}</strong></span
          ><span>
            {{ t("所属部门") }} <strong>{{ obj.org_name }}</strong></span
          ><span>
            {{ t("战略主题") }} <strong>{{ obj.theme }}</strong></span
          ><span>
            {{ t("目标周期") }}
            <strong>{{ obj.start_date }} — {{ obj.end_date }}</strong></span
          >
        </div>
      </section>
      <section class="panel">
        <el-tabs v-model="tab"
          ><el-tab-pane :label="t('关键结果')" name="krs"
            ><div class="panel-title" style="margin-top: 15px">
              <span class="muted">
                {{ t("权重合计") }} {{ totalWeight }}
                {{ t("% · 提交前须等于100%") }}
              </span>
              <div v-if="isOwner && obj.status === 'Draft'">
                <el-button @click="openRelation">
                  {{ t("设置战略对齐") }} </el-button
                ><el-button :icon="Plus" @click="krDialog = true">
                  {{ t("添加关键结果") }}
                </el-button>
              </div>
            </div>
            <el-empty
              v-if="!obj.key_results?.length"
              :description="t('添加可衡量的关键结果，让目标落地')"
            />
            <article v-for="k in obj.key_results" :key="k.id" class="kr-card">
              <div class="kr-title">
                <h3>{{ k.name }}</h3>
                <span :class="['health-pill', k.health]">{{
                  healthNames[k.health]
                }}</span>
              </div>
              <p class="muted">
                {{ t("证据来源") }}: {{ k.evidence_source || "—" }}
                <el-button
                  v-if="isOwner && obj.status === 'Draft'"
                  link
                  @click="openSource(k)"
                  >{{ t("编辑") }}</el-button
                >
              </p>
              <div class="kr-metrics">
                <div>
                  <span> {{ t("基线") }} </span
                  ><strong
                    >{{ Number(k.baseline) }}
                    <small>{{ k.unit }}</small></strong
                  >
                </div>
                <div>
                  <span> {{ t("当前值") }} </span
                  ><strong
                    >{{ Number(k.current_value) }}
                    <small>{{ k.unit }}</small></strong
                  >
                </div>
                <div>
                  <span> {{ t("目标值") }} </span
                  ><strong
                    >{{ Number(k.target) }} <small>{{ k.unit }}</small></strong
                  >
                </div>
                <div>
                  <span> {{ t("达成率") }} </span
                  ><strong>{{ k.progress }}%</strong>
                </div>
              </div>
              <el-progress
                :percentage="Number(k.progress)"
                :stroke-width="5"
                :show-text="false"
                color="#c93616"
              />
              <ul v-if="k.milestones.length" class="action-list">
                <li v-for="m in k.milestones" :key="m.id">
                  <span
                    >{{ m.name }}
                    <small class="muted"
                      >{{ m.weight }}% · {{ m.due_date }}</small
                    ></span
                  ><span v-if="m.accepted_at" class="health-pill Green">
                    {{ t("已验收") }} </span
                  ><el-button
                    v-else-if="isManager && obj.status === 'Active'"
                    link
                    @click="accept(k, m.id)"
                  >
                    {{ t("验收") }} </el-button
                  ><span v-else class="muted"> {{ t("待验收") }} </span>
                </li>
              </ul>
              <div class="kr-footer">
                <span class="muted">
                  {{ t("权重") }} {{ Number(k.weight) }} {{ t("% · 信心") }}
                  {{ k.confidence }} {{ t("· 下次更新") }}
                  {{ k.next_due }}</span
                >
                <div>
                  <el-button link @click="showHistory(k)">
                    {{ t("更新历史") }} </el-button
                  ><el-button
                    v-if="isOwner && obj.status === 'Draft'"
                    link
                    type="danger"
                    @click="removeKR(k)"
                  >
                    {{ t("删除") }} </el-button
                  ><el-button
                    v-if="
                      isOwner &&
                      obj.status === 'Active' &&
                      k.value_type !== 'milestone'
                    "
                    @click="openCheck(k)"
                  >
                    {{ t("更新进展") }}
                  </el-button>
                </div>
              </div>
            </article></el-tab-pane
          ><el-tab-pane :label="t('证据与附件')" name="evidence"
            ><div class="panel-title" style="margin-top: 15px">
              <span class="muted">
                {{ t("每次上传保留独立版本，扫描通过后可下载") }}
              </span>
              <div v-if="isOwner && ['Draft', 'Active'].includes(obj.status)">
                <el-button @click="linkDialog = true">
                  {{ t("添加链接") }} </el-button
                ><el-button
                  :icon="Upload"
                  :loading="busy"
                  @click="pickVersion()"
                >
                  {{ t("上传文件") }}
                </el-button>
              </div>
              <input
                ref="fileInput"
                style="display: none"
                type="file"
                accept=".xlsx,.pptx,.pdf,.png,.jpg,.jpeg"
                @change="upload"
              />
            </div>
            <el-table :data="obj.evidence" :empty-text="t('暂无证据')"
              ><el-table-column
                prop="name"
                :label="t('名称')"
                min-width="200"
              /><el-table-column
                prop="uploader"
                :label="t('上传人')"
                min-width="130"
              /><el-table-column :label="t('上传时间')" min-width="180"
                ><template #default="{ row }">{{
                  formatDate(row.uploaded_at)
                }}</template></el-table-column
              ><el-table-column :label="t('版本关系')" width="120"
                ><template #default="{ row }">{{
                  row.previous_id
                    ? t("替代 #") + row.previous_id
                    : t("首次上传")
                }}</template></el-table-column
              ><el-table-column
                prop="status"
                :label="t('扫描状态')"
                width="130"
              /><el-table-column width="190"
                ><template #default="{ row }"
                  ><a
                    v-if="row.kind === 'link'"
                    :href="row.url"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {{ t("打开源链接 ↗") }} </a
                  ><a
                    v-else-if="row.status === 'Available'"
                    :href="'/api/v1/evidence/versions/' + row.id + '/download'"
                  >
                    {{ t("下载") }} </a
                  ><el-button
                    v-if="
                      isOwner &&
                      ['Draft', 'Active'].includes(obj.status) &&
                      row.kind === 'file'
                    "
                    link
                    @click="pickVersion(row.id)"
                  >
                    {{ t("上传新版本") }}
                  </el-button></template
                ></el-table-column
              ></el-table
            ></el-tab-pane
          ><el-tab-pane :label="t('审批记录')" name="approval"
            ><el-empty
              v-if="!obj.approvals?.length"
              :description="t('目标提交后将在此显示审批记录')"
            />
            <div
              v-for="a in obj.approvals"
              :key="a.id"
              class="timeline-item"
              style="margin-top: 20px"
            >
              <h4>
                {{
                  a.stage === "Completion"
                    ? t("结项确认")
                    : a.stage === "Manager"
                      ? t("经理评审")
                      : t("事业部评审")
                }}
                · {{ a.assignee_name }}
                <span class="status-badge">{{ a.status }}</span>
              </h4>
              <span class="muted">
                {{ t("版本") }} {{ a.revision }} ·
                {{
                  a.decided_at ? formatDate(a.decided_at) : t("等待处理")
                }}</span
              >
              <p>{{ a.comment || t("暂无审批意见") }}</p>
            </div></el-tab-pane
          ><el-tab-pane :label="t('变更与权限')" name="governance" lazy
            ><Governance :objective="obj" @changed="load" /></el-tab-pane
        ></el-tabs></section
    ></template>
  </div>

  <el-dialog v-model="krDialog" :title="t('添加关键结果')" width="660px"
    ><el-form label-position="top"
      ><el-form-item :label="t('关键结果名称')"
        ><el-input v-model="kr.name" :placeholder="t('描述可衡量的业务结果')"
      /></el-form-item>
      <el-form-item :label="t('证据来源')"
        ><el-input
          v-model="kr.evidence_source"
          :placeholder="t('填写指标数据的来源')"
      /></el-form-item>
      <div class="form-grid">
        <el-form-item :label="t('指标类型')"
          ><el-select v-model="kr.value_type"
            ><el-option
              v-for="(name, key) in {
                number: t('数值'),
                count: t('计数'),
                percentage: t('百分比'),
                currency: t('货币'),
                milestone: t('里程碑'),
              }"
              :key="key"
              :label="name"
              :value="key" /></el-select></el-form-item
        ><el-form-item :label="t('权重 %')"
          ><el-input v-model="kr.weight" /></el-form-item
        ><el-form-item
          v-if="kr.value_type !== 'milestone'"
          :label="t('计算方向')"
          ><el-select v-model="kr.direction"
            ><el-option :label="t('越高越好')" value="increase" /><el-option
              :label="t('越低越好')"
              value="decrease" /></el-select></el-form-item
        ><el-form-item :label="t('更新频率')"
          ><el-select v-model="kr.frequency"
            ><el-option :label="t('每周')" value="weekly" /><el-option
              :label="t('每两周')"
              value="biweekly" /><el-option
              :label="t('每月')"
              value="monthly" /></el-select></el-form-item
        ><template v-if="kr.value_type !== 'milestone'"
          ><el-form-item :label="t('基线值')"
            ><el-input v-model="kr.baseline" /></el-form-item
          ><el-form-item :label="t('目标值')"
            ><el-input v-model="kr.target" /></el-form-item></template
        ><el-form-item :label="t('单位')"
          ><el-input
            v-model="kr.unit"
            :placeholder="t('小时 / 元 / %')" /></el-form-item
        ><el-form-item v-if="kr.value_type === 'currency'" :label="t('币种')"
          ><el-input v-model="kr.currency" placeholder="CNY"
        /></el-form-item>
      </div>
      <template v-if="kr.value_type === 'milestone'"
        ><div v-for="(m, i) in kr.milestones" :key="i" class="form-grid">
          <el-form-item :label="t('节点名称')"
            ><el-input v-model="m.name" /></el-form-item
          ><el-form-item :label="t('节点权重')"
            ><el-input v-model="m.weight" /></el-form-item
          ><el-form-item :label="t('到期日期')"
            ><el-date-picker
              v-model="m.due_date"
              value-format="YYYY-MM-DD" /></el-form-item
          ><el-button link @click="kr.milestones.splice(i, 1)">
            {{ t("移除节点") }}
          </el-button>
        </div>
        <el-button
          @click="
            kr.milestones.push({
              name: '',
              weight: '100',
              due_date: obj?.end_date || '',
            })
          "
        >
          {{ t("添加里程碑节点") }}
        </el-button></template
      ></el-form
    ><template #footer
      ><el-button @click="krDialog = false"> {{ t("取消") }} </el-button
      ><el-button type="primary" :loading="busy" @click="addKR">
        {{ t("保存关键结果") }}
      </el-button></template
    ></el-dialog
  >
  <el-dialog v-model="checkDialog" :title="t('更新关键结果')" width="660px"
    ><p class="muted">{{ selectedKR?.name }}</p>
    <el-form label-position="top"
      ><div class="form-grid">
        <el-form-item :label="t('当前值')"
          ><el-input v-model="check.current_value" /></el-form-item
        ><el-form-item :label="t('信心指数 0至100')"
          ><el-input-number v-model="check.confidence" :min="0" :max="100"
        /></el-form-item>
      </div>
      <p class="muted">
        {{ t("预计达成率") }} {{ checkProgress }}
        {{ t("% · 最终结果由服务端计算") }}
      </p>
      <el-form-item :label="t('进展说明')"
        ><el-input v-model="check.commentary" type="textarea" :rows="3"
      /></el-form-item>
      <div class="form-grid">
        <el-form-item :label="t('风险')"
          ><el-input v-model="check.risks" type="textarea" /></el-form-item
        ><el-form-item :label="t('阻碍')"
          ><el-input v-model="check.blockers" type="textarea"
        /></el-form-item>
      </div>
      <el-form-item :label="t('下一步行动')"
        ><el-input v-model="check.next_action" type="textarea" /></el-form-item
      ><el-form-item :label="t('引用证据版本')"
        ><el-select
          v-model="check.evidence_version_ids"
          multiple
          :placeholder="t('选择已通过扫描的证据')"
          ><el-option
            v-for="e in obj?.evidence?.filter((e) => e.status === 'Available')"
            :key="e.id"
            :label="'#' + e.id + ' ' + e.name"
            :value="e.id" /></el-select></el-form-item
      ><el-checkbox v-model="check.severe_blocker">
        {{ t("存在严重阻碍") }}
      </el-checkbox></el-form
    ><template #footer
      ><el-button @click="checkDialog = false"> {{ t("取消") }} </el-button
      ><el-button type="primary" :loading="busy" @click="saveCheck">
        {{ t("提交更新") }}
      </el-button></template
    ></el-dialog
  >
  <el-dialog v-model="historyDialog" :title="t('更新历史')" width="650px"
    ><el-empty v-if="!history.length" :description="t('暂无更新记录')" />
    <div v-for="h in history" :key="h.id" class="timeline-item">
      <h4>{{ h.actor }} {{ t("· 当前值") }} {{ h.current_value }}</h4>
      <span class="muted">{{ formatDate(h.effective_at) }}</span>
      <p>{{ h.commentary }}</p>
      <p v-if="h.risks">{{ t("风险：") }} {{ h.risks }}</p>
      <p v-if="h.blockers">{{ t("阻碍：") }} {{ h.blockers }}</p>
      <p v-if="h.next_action">{{ t("下一步：") }} {{ h.next_action }}</p>
    </div></el-dialog
  >
  <el-dialog v-model="linkDialog" :title="t('登记证据链接')" width="540px"
    ><el-form label-position="top"
      ><el-form-item :label="t('证据名称')"
        ><el-input v-model="link.name" /></el-form-item
      ><el-form-item :label="t('Power BI 或 SharePoint HTTPS链接')"
        ><el-input v-model="link.url" /></el-form-item
    ></el-form>
    <p class="muted">
      {{ t("源系统独立控制访问权限。登记链接不会保存历史内容快照。") }}
    </p>
    <template #footer
      ><el-button type="primary" :loading="busy" @click="saveLink">
        {{ t("保存链接") }}
      </el-button></template
    ></el-dialog
  >
  <el-dialog v-model="editDialog" :title="t('编辑目标草稿')" width="600px"
    ><el-form label-position="top"
      ><el-form-item :label="t('目标名称')"
        ><el-input v-model="edit.title" /></el-form-item
      ><el-form-item :label="t('目标说明')"
        ><el-input
          v-model="edit.description"
          type="textarea"
          :rows="3" /></el-form-item
      ><el-form-item :label="t('战略主题')"
        ><el-input v-model="edit.theme" /></el-form-item
      ><el-form-item :label="t('可见范围')"
        ><el-select v-model="edit.visibility"
          ><el-option
            :label="t('按角色和组织授权')"
            value="organization" /><el-option
            :label="t('仅负责人、共享人员及指定审批人')"
            value="restricted" /></el-select
      ></el-form-item>
      <div class="form-grid">
        <el-form-item :label="t('开始日期')"
          ><el-date-picker
            v-model="edit.start_date"
            value-format="YYYY-MM-DD" /></el-form-item
        ><el-form-item :label="t('结束日期')"
          ><el-date-picker v-model="edit.end_date" value-format="YYYY-MM-DD"
        /></el-form-item></div></el-form
    ><template #footer
      ><el-button type="primary" :loading="busy" @click="saveEdit">
        {{ t("保存修改") }}
      </el-button></template
    ></el-dialog
  >
  <el-dialog v-model="relationDialog" :title="t('设置战略对齐')" width="540px"
    ><el-form label-position="top"
      ><el-form-item :label="t('关系类型')"
        ><el-select v-model="relation.kind"
          ><el-option :label="t('主父目标')" value="parent" /><el-option
            :label="t('贡献于')"
            value="contributes_to" /><el-option
            :label="t('依赖于')"
            value="depends_on" /></el-select></el-form-item
      ><el-form-item :label="t('关联目标')"
        ><el-select v-model="relation.target_id" filterable
          ><el-option
            v-for="t in targets"
            :key="t.id"
            :label="t.title"
            :value="t.id" /></el-select></el-form-item></el-form
    ><template #footer
      ><el-button type="primary" :loading="busy" @click="saveRelation">
        {{ t("保存关系") }}
      </el-button></template
    ></el-dialog
  >
</template>
