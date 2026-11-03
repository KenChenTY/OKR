<script setup lang="ts">
import { t, localizedRecord } from "../i18n";

import { onMounted, reactive, ref } from "vue";
import { ElMessageBox, ElMessage } from "element-plus";
import { useRouter } from "vue-router";
import { api, write } from "../api";
import { useSession } from "../stores/session";
import type { Objective } from "../types";
import OrganizationAnalytics from "../components/OrganizationAnalytics.vue";
const session = useSession(),
  router = useRouter(),
  loading = ref(false),
  busy = ref(false),
  tab = ref("initiatives");
const categoryNames: Record<string, string> = localizedRecord({
  cost_saving: "节约成本",
  hours_saved: "节约工时",
  revenue: "新增收入",
  risk_reduction: "风险降低",
  compliance_improvement: "合规改善",
});
const initiativeNames: Record<string, string> = localizedRecord({
  Planned: "计划中",
  InProgress: "执行中",
  Completed: "已完成",
  Cancelled: "已取消",
});
interface Initiative {
  id: number;
  title: string;
  description: string;
  kr_id: number;
  kr_name: string;
  objective_id: number;
  objective_title: string;
  owner_id: number;
  status: string;
  start_date: string;
  end_date: string;
  effort_hours: string;
  investment: string;
  currency: string;
  etag: string;
  links: { system: string; external_id: string; url: string }[];
}
interface Claim {
  id: number;
  value: string | null;
  narrative: string;
  evidence_id: number;
  submitted_by: number;
  status: string;
  verification: {
    value: string | null;
    comment: string;
    reviewer: string;
    decision: string;
  } | null;
}
interface Benefit {
  kr_id: number | null;
  kr_name: string | null;
  id: number;
  objective_id: number;
  objective_title: string;
  reference: string;
  name: string;
  category: string;
  unit: string;
  currency: string | null;
  method: string;
  claimed_value: string | null;
  verified_value: string | null;
  has_verified: boolean;
  claims: Claim[];
}
interface Portfolio {
  initiative_count: number;
  completed_count: number;
  effort_hours: string;
  investment: { currency: string; value: string }[];
  verified_benefits: { category: string; unit: string; value: string }[];
  qualitative: {
    id: number;
    name: string;
    category: string;
    value: string | null;
    unit: string;
  }[];
}
const initiatives = ref<Initiative[]>([]),
  benefits = ref<Benefit[]>([]),
  summary = ref<Portfolio>(),
  objectives = ref<Objective[]>([]),
  detail = ref<Objective>();
const editingInitiative = ref<Initiative>();
const initiativeDialog = ref(false),
  benefitDialog = ref(false),
  claimDialog = ref(false),
  verifyDialog = ref(false),
  linkDialog = ref(false),
  historyDialog = ref(false);
const chosenObjective = ref<number>(),
  chosenBenefit = ref<Benefit>(),
  chosenClaim = ref<Claim>(),
  chosenInitiative = ref<Initiative>();
const initiativeForm = reactive({
  kr_id: undefined as number | undefined,
  title: "",
  description: "",
  start_date: "",
  end_date: "",
  effort_hours: "0",
  investment: "0",
  currency: "CNY",
});
const benefitForm = reactive({
  kr_id: undefined as number | undefined,
  objective_id: undefined as number | undefined,
  reference: "",
  name: "",
  category: "cost_saving",
  unit: "CNY",
  currency: "CNY",
  period_start: "",
  period_end: "",
  method: "",
});
const claimForm = reactive({
  claimed_value: "",
  narrative: "",
  evidence_id: undefined as number | undefined,
});
const verifyForm = reactive({
  decision: "Approved",
  verified_value: "",
  comment: "",
});
const assignDialog = ref(false),
  assignKR = ref<number>();
async function openAssign(item: Benefit) {
  chosenBenefit.value = item;
  assignKR.value = undefined;
  detail.value = await api(`/api/v1/objectives/${item.objective_id}`);
  assignDialog.value = true;
}
async function assignBenefit() {
  busy.value = true;
  try {
    await write(
      `/api/v1/benefits/${chosenBenefit.value?.id}/key-result`,
      { kr_id: assignKR.value },
      undefined,
      "PATCH",
    );
    assignDialog.value = false;
    await load();
  } finally {
    busy.value = false;
  }
}
const linkForm = reactive({ system: "Jira", external_id: "", url: "" });
const query = () => (session.cycleId ? "?cycle_id=" + session.cycleId : "");
async function load() {
  loading.value = true;
  try {
    [initiatives.value, benefits.value, summary.value] = await Promise.all([
      api<Initiative[]>("/api/v1/initiatives" + query()),
      api<Benefit[]>("/api/v1/benefits" + query()),
      api<Portfolio>("/api/v1/dashboards/portfolio" + query()),
    ]);
  } finally {
    loading.value = false;
  }
}
onMounted(load);
async function options() {
  const result = await api<{ items: Objective[] }>(
    "/api/v1/objectives" +
      (session.cycleId ? "?cycle_id=" + session.cycleId + "&" : "?") +
      "page_size=100",
  );
  objectives.value = result.items;
}
async function selectObjective(id: number) {
  const loaded = await api<Objective>(`/api/v1/objectives/${id}`);
  detail.value = loaded;
  initiativeForm.start_date = loaded.start_date;
  initiativeForm.end_date = loaded.end_date;
  initiativeForm.kr_id = loaded.key_results?.[0]?.id;
}
async function openInitiative() {
  editingInitiative.value = undefined;
  await options();
  chosenObjective.value = undefined;
  detail.value = undefined;
  initiativeDialog.value = true;
}
async function saveInitiative() {
  busy.value = true;
  try {
    await write(
      editingInitiative.value
        ? "/api/v1/initiatives/" + editingInitiative.value.id
        : "/api/v1/initiatives",
      initiativeForm,
      editingInitiative.value?.etag,
      editingInitiative.value ? "PATCH" : "POST",
    );
    initiativeDialog.value = false;
    await load();
  } finally {
    busy.value = false;
  }
}
async function transition(item: Initiative, status: string) {
  try {
    const { value } = await ElMessageBox.prompt(
      t("请输入举措状态变更说明"),
      t("更新举措"),
      {
        inputValidator: (v) => !!v?.trim() || t("请填写说明"),
        confirmButtonText: t("确认"),
        cancelButtonText: t("取消"),
      },
    );
    await write(
      `/api/v1/initiatives/${item.id}/transitions`,
      { status, reason: value },
      item.etag,
    );
    await load();
  } catch {
    /* cancellation or error */
  }
}
async function editInitiative(item: Initiative) {
  await options();
  await selectObjective(item.objective_id);
  editingInitiative.value = item;
  chosenObjective.value = item.objective_id;
  Object.assign(initiativeForm, {
    kr_id: item.kr_id,
    title: item.title,
    description: item.description,
    start_date: item.start_date,
    end_date: item.end_date,
    effort_hours: item.effort_hours,
    investment: item.investment,
    currency: item.currency,
  });
  initiativeDialog.value = true;
}
function openLink(item: Initiative) {
  chosenInitiative.value = item;
  Object.assign(linkForm, { system: "Jira", external_id: "", url: "" });
  linkDialog.value = true;
}
async function saveLink() {
  busy.value = true;
  try {
    await write(
      `/api/v1/initiatives/${chosenInitiative.value?.id}/links`,
      linkForm,
    );
    linkDialog.value = false;
    await load();
  } finally {
    busy.value = false;
  }
}
async function selectBenefitObjective(id: number) {
  benefitForm.kr_id = undefined;
  detail.value = undefined;
  const loaded = await api<Objective>(`/api/v1/objectives/${id}`);
  if (benefitForm.objective_id === id) detail.value = loaded;
}
async function openBenefit() {
  detail.value = undefined;
  benefitForm.kr_id = undefined;
  await options();
  const cycle = session.catalog.cycles.find((c) => c.id === session.cycleId);
  benefitForm.period_start = cycle?.start_date || "";
  benefitForm.period_end = cycle?.end_date || "";
  benefitDialog.value = true;
}
async function saveBenefit() {
  busy.value = true;
  try {
    const money = ["cost_saving", "revenue"].includes(benefitForm.category);
    await write("/api/v1/benefits", {
      ...benefitForm,
      currency: money ? benefitForm.currency : null,
    });
    benefitDialog.value = false;
    await load();
  } finally {
    busy.value = false;
  }
}
async function openClaim(benefit: Benefit) {
  chosenBenefit.value = benefit;
  detail.value = await api(`/api/v1/objectives/${benefit.objective_id}`);
  Object.assign(claimForm, {
    claimed_value: "",
    narrative: "",
    evidence_id: undefined,
  });
  claimDialog.value = true;
}
async function saveClaim() {
  busy.value = true;
  try {
    await write(`/api/v1/benefits/${chosenBenefit.value?.id}/claims`, {
      ...claimForm,
      claimed_value: claimForm.claimed_value || null,
    });
    claimDialog.value = false;
    ElMessage.success(t("收益已提交独立核验"));
    await load();
  } finally {
    busy.value = false;
  }
}
function openVerify(benefit: Benefit, claim: Claim) {
  chosenBenefit.value = benefit;
  chosenClaim.value = claim;
  Object.assign(verifyForm, {
    decision: "Approved",
    verified_value: claim.value || "",
    comment: "",
  });
  verifyDialog.value = true;
}
async function saveVerify() {
  busy.value = true;
  try {
    await write(
      `/api/v1/benefit-claims/${chosenClaim.value?.id}/verifications`,
      { ...verifyForm, verified_value: verifyForm.verified_value || null },
    );
    verifyDialog.value = false;
    await load();
  } finally {
    busy.value = false;
  }
}
function history(benefit: Benefit) {
  chosenBenefit.value = benefit;
  historyDialog.value = true;
}
</script>
<template>
  <el-dialog v-model="assignDialog" :title="t('关联关键结果')" width="520px"
    ><el-select v-model="assignKR"
      ><el-option
        v-for="k in detail?.key_results || []"
        :key="k.id"
        :label="k.name"
        :value="k.id" /></el-select
    ><template #footer
      ><el-button
        type="primary"
        :loading="busy"
        :disabled="!assignKR"
        @click="assignBenefit"
        >{{ t("保存修改") }}</el-button
      ></template
    ></el-dialog
  >
  <div v-loading="loading">
    <div class="page-heading">
      <div>
        <div class="eyebrow">FROM EXECUTION TO IMPACT</div>
        <h1>{{ t("举措与收益") }}</h1>
        <p>{{ t("连接执行计划与业务价值，以独立核验确认实际收益。") }}</p>
      </div>
      <el-button @click="load"> {{ t("刷新数据") }} </el-button>
    </div>
    <div v-if="summary" class="kpi-grid">
      <div class="kpi featured">
        <div class="label">{{ t("实施举措") }}</div>
        <div class="value">{{ summary.initiative_count }}</div>
        <div class="caption">
          {{ summary.completed_count }} {{ t("项已完成") }}
        </div>
      </div>
      <div class="kpi">
        <div class="label">{{ t("计划投入工时") }}</div>
        <div class="value">
          {{ Number(summary.effort_hours) }}<small> {{ t("小时") }} </small>
        </div>
        <div class="caption">{{ t("不与节约工时相抵扣") }}</div>
      </div>
      <div class="kpi">
        <div class="label">{{ t("计划投入金额") }}</div>
        <div v-if="summary.investment.length" style="margin: 20px 0">
          <div
            v-for="v in summary.investment"
            :key="v.currency"
            style="font-size: 20px"
          >
            {{ Number(v.value).toLocaleString() }}
            <small>{{ v.currency }}</small>
          </div>
        </div>
        <div v-else class="value">—</div>
        <div class="caption">{{ t("按币种独立统计") }}</div>
      </div>
      <div class="kpi">
        <div class="label">{{ t("已核验收益") }}</div>
        <div v-if="summary.verified_benefits.length" style="margin: 15px 0">
          <div
            v-for="v in summary.verified_benefits"
            :key="v.category + v.unit"
            style="font-size: 13px; margin: 8px 0"
          >
            {{ categoryNames[v.category] }} ·
            <strong>{{ Number(v.value).toLocaleString() }} {{ v.unit }}</strong>
          </div>
        </div>
        <div v-else class="value">—</div>
        <div class="caption">{{ t("共享收益按比例计入，不重复加总") }}</div>
      </div>
    </div>
    <section class="panel">
      <el-tabs v-model="tab"
        ><el-tab-pane :label="t('实施举措')" name="initiatives"
          ><div class="panel-title" style="margin-top: 15px">
            <span class="muted"> {{ t("项目状态不自动替代KR结果") }} </span
            ><el-button type="primary" @click="openInitiative">
              {{ t("登记举措") }}
            </el-button>
          </div>
          <el-table :data="initiatives" :empty-text="t('暂无实施举措')"
            ><el-table-column :label="t('举措与目标')" min-width="250"
              ><template #default="{ row }"
                ><div class="table-title">{{ row.title }}</div>
                <div
                  class="table-subtitle"
                  @click="router.push('/objectives/' + row.objective_id)"
                >
                  {{ row.objective_title }} · {{ row.kr_name }}
                </div>
                <div
                  v-for="link in row.links"
                  :key="link.url"
                  class="table-subtitle"
                >
                  <a :href="link.url" target="_blank" rel="noopener noreferrer"
                    >{{ link.system }} · {{ link.external_id }} ↗</a
                  >
                </div></template
              ></el-table-column
            ><el-table-column :label="t('状态')" width="100"
              ><template #default="{ row }">{{
                initiativeNames[row.status]
              }}</template></el-table-column
            ><el-table-column
              prop="end_date"
              :label="t('计划完成')"
              width="115"
            /><el-table-column :label="t('计划投入')" width="135"
              ><template #default="{ row }"
                >{{ Number(row.investment) }} {{ row.currency }}
                <div class="table-subtitle">
                  {{ Number(row.effort_hours) }} {{ t("小时") }}
                </div></template
              ></el-table-column
            ><el-table-column width="210"
              ><template #default="{ row }"
                ><template v-if="row.owner_id === session.user?.id"
                  ><el-button
                    v-if="row.status === 'Planned'"
                    link
                    @click="transition(row, 'InProgress')"
                  >
                    {{ t("开始") }} </el-button
                  ><el-button
                    v-if="row.status === 'InProgress'"
                    link
                    @click="transition(row, 'Completed')"
                  >
                    {{ t("完成") }} </el-button
                  ><el-button
                    v-if="['Planned', 'InProgress'].includes(row.status)"
                    link
                    @click="transition(row, 'Cancelled')"
                  >
                    {{ t("取消") }} </el-button
                  ><el-button
                    v-if="['Planned', 'InProgress'].includes(row.status)"
                    link
                    @click="editInitiative(row)"
                  >
                    {{ t("编辑") }} </el-button
                  ><el-button link @click="openLink(row)">
                    {{ t("关联项目") }}
                  </el-button></template
                ></template
              ></el-table-column
            ></el-table
          ></el-tab-pane
        ><el-tab-pane :label="t('收益申报与核验')" name="benefits"
          ><div class="panel-title" style="margin-top: 15px">
            <span class="muted">
              {{ t("申报值与核验值分别保存，修改通过新的申报版本记录") }} </span
            ><el-button type="primary" @click="openBenefit">
              {{ t("登记收益") }}
            </el-button>
          </div>
          <el-table :data="benefits" :empty-text="t('暂无收益记录')"
            ><el-table-column :label="t('收益')" min-width="230"
              ><template #default="{ row }"
                ><div class="table-title">{{ row.name }}</div>
                <div class="table-subtitle">
                  {{ row.reference }} ·
                  {{ row.kr_name || t("历史收益待关联KR") }} ·
                  {{ categoryNames[row.category] }}
                </div></template
              ></el-table-column
            ><el-table-column :label="t('最近申报')" width="130"
              ><template #default="{ row }">{{
                row.claimed_value === null
                  ? t("定性 / 未申报")
                  : Number(row.claimed_value) + " " + row.unit
              }}</template></el-table-column
            ><el-table-column :label="t('有效核验值')" width="130"
              ><template #default="{ row }">{{
                !row.has_verified
                  ? t("未核验")
                  : row.verified_value === null
                    ? t("已核验定性结论")
                    : Number(row.verified_value) + " " + row.unit
              }}</template></el-table-column
            ><el-table-column min-width="200"
              ><template #default="{ row }"
                ><el-button v-if="!row.kr_id" link @click="openAssign(row)">{{
                  t("关联关键结果")
                }}</el-button
                ><el-button link @click="history(row)">
                  {{ t("查看记录") }} </el-button
                ><el-button
                  v-if="!row.claims.some((c: Claim) => c.status === 'Pending')"
                  link
                  @click="openClaim(row)"
                >
                  {{ t("申报收益") }} </el-button
                ><template v-for="claim in row.claims" :key="claim.id"
                  ><el-button
                    v-if="
                      claim.status === 'Pending' &&
                      claim.submitted_by !== session.user?.id &&
                      ['Manager', 'Division Head', 'PMO'].includes(
                        session.user?.role || '',
                      )
                    "
                    type="primary"
                    plain
                    @click="openVerify(row, claim)"
                  >
                    {{ t("核验") }} </el-button
                  ><span
                    v-else-if="claim.status === 'Pending'"
                    class="status-badge"
                  >
                    {{ t("待核验") }}
                  </span></template
                ></template
              ></el-table-column
            ></el-table
          ></el-tab-pane
        ></el-tabs
      >
      <p class="muted">
        {{
          t(
            "显示当前周期和权限范围内最新200条记录。外部项目链接仅用于跳转，不代表已接入自动同步。",
          )
        }}
      </p>
    </section>
    <section v-if="summary?.qualitative.length" class="panel">
      <div class="panel-title">
        <h2>{{ t("风险与合规改善") }}</h2>
        <span class="muted"> {{ t("独立列示，不折算为货币") }} </span>
      </div>
      <ul class="action-list">
        <li v-for="b in summary.qualitative" :key="b.id">
          <span>{{ b.name }}</span
          ><span>{{
            b.value === null
              ? t("已核验定性结果")
              : Number(b.value) + " " + b.unit
          }}</span>
        </li>
      </ul>
    </section>
  </div>
  <OrganizationAnalytics />
  <el-dialog v-model="initiativeDialog" :title="t('登记实施举措')" width="660px"
    ><el-form label-position="top"
      ><el-form-item :label="t('关联目标')"
        ><el-select
          v-model="chosenObjective"
          :disabled="!!editingInitiative"
          filterable
          @change="selectObjective"
          ><el-option
            v-for="o in objectives.filter(
              (o) => o.owner_id === session.user?.id,
            )"
            :key="o.id"
            :label="o.title"
            :value="o.id" /></el-select></el-form-item
      ><el-form-item :label="t('关联关键结果')"
        ><el-select
          v-model="initiativeForm.kr_id"
          :disabled="!!editingInitiative"
          ><el-option
            v-for="k in detail?.key_results"
            :key="k.id"
            :label="k.name"
            :value="k.id" /></el-select></el-form-item
      ><el-form-item :label="t('举措名称')"
        ><el-input v-model="initiativeForm.title" /></el-form-item
      ><el-form-item :label="t('说明')"
        ><el-input v-model="initiativeForm.description" type="textarea"
      /></el-form-item>
      <div class="form-grid">
        <el-form-item :label="t('计划开始')"
          ><el-date-picker
            v-model="initiativeForm.start_date"
            value-format="YYYY-MM-DD" /></el-form-item
        ><el-form-item :label="t('计划完成')"
          ><el-date-picker
            v-model="initiativeForm.end_date"
            value-format="YYYY-MM-DD" /></el-form-item
        ><el-form-item :label="t('计划工时')"
          ><el-input v-model="initiativeForm.effort_hours" /></el-form-item
        ><el-form-item :label="t('计划投入金额')"
          ><el-input v-model="initiativeForm.investment" /></el-form-item
        ><el-form-item :label="t('币种')"
          ><el-input v-model="initiativeForm.currency" placeholder="CNY"
        /></el-form-item></div></el-form
    ><template #footer
      ><el-button type="primary" :loading="busy" @click="saveInitiative">
        {{ t("保存举措") }}
      </el-button></template
    ></el-dialog
  >
  <el-dialog v-model="benefitDialog" :title="t('登记业务收益')" width="660px"
    ><el-form label-position="top"
      ><el-form-item :label="t('关联目标')"
        ><el-select
          v-model="benefitForm.objective_id"
          @change="selectBenefitObjective"
          filterable
          ><el-option
            v-for="o in objectives.filter(
              (o) =>
                o.owner_id === session.user?.id || session.user?.role === 'PMO',
            )"
            :key="o.id"
            :label="o.title"
            :value="o.id" /></el-select></el-form-item
      ><el-form-item :label="t('关联关键结果')"
        ><el-select
          v-model="benefitForm.kr_id"
          :disabled="!detail || detail.id !== benefitForm.objective_id"
          ><el-option
            v-for="k in detail?.key_results || []"
            :key="k.id"
            :label="k.name"
            :value="k.id" /></el-select></el-form-item
      ><el-form-item :label="t('收益名称')"
        ><el-input v-model="benefitForm.name" /></el-form-item
      ><el-form-item :label="t('业务参考号')"
        ><el-input
          v-model="benefitForm.reference"
          :placeholder="t('使用统一业务参考号，避免重复登记同一收益')"
      /></el-form-item>
      <div class="form-grid">
        <el-form-item :label="t('收益类型')"
          ><el-select v-model="benefitForm.category"
            ><el-option
              v-for="(name, key) in categoryNames"
              :key="key"
              :label="name"
              :value="key" /></el-select></el-form-item
        ><el-form-item
          v-if="['cost_saving', 'revenue'].includes(benefitForm.category)"
          :label="t('币种')"
          ><el-input v-model="benefitForm.currency" /></el-form-item
        ><el-form-item v-else :label="t('计量单位')"
          ><el-input
            v-model="benefitForm.unit"
            :placeholder="t('小时 / % / 等级')" /></el-form-item
        ><el-form-item :label="t('收益期间开始')"
          ><el-date-picker
            v-model="benefitForm.period_start"
            value-format="YYYY-MM-DD" /></el-form-item
        ><el-form-item :label="t('收益期间结束')"
          ><el-date-picker
            v-model="benefitForm.period_end"
            value-format="YYYY-MM-DD"
        /></el-form-item>
      </div>
      <el-form-item :label="t('计算或评价方法')"
        ><el-input
          v-model="benefitForm.method"
          type="textarea"
          :rows="3"
          :placeholder="
            t('记录基准、统计期间和计算依据')
          " /></el-form-item></el-form
    ><template #footer
      ><el-button type="primary" :loading="busy" @click="saveBenefit">
        {{ t("保存收益") }}
      </el-button></template
    ></el-dialog
  >
  <el-dialog v-model="claimDialog" :title="t('申报收益')" width="570px"
    ><p class="muted">{{ chosenBenefit?.name }} · {{ chosenBenefit?.unit }}</p>
    <el-form label-position="top"
      ><el-form-item :label="t('申报值（定性收益可留空）')"
        ><el-input v-model="claimForm.claimed_value" /></el-form-item
      ><el-form-item :label="t('申报说明')"
        ><el-input
          v-model="claimForm.narrative"
          type="textarea"
          :rows="3" /></el-form-item
      ><el-form-item :label="t('核验证据')"
        ><el-select v-model="claimForm.evidence_id"
          ><el-option
            v-for="e in detail?.evidence?.filter(
              (e) => e.status === 'Available',
            )"
            :key="e.id"
            :label="e.name"
            :value="e.id" /></el-select></el-form-item
    ></el-form>
    <p class="muted">
      {{ t("没有可用证据时，请先到目标详情上传证据或登记受信链接。") }}
    </p>
    <template #footer
      ><el-button type="primary" :loading="busy" @click="saveClaim">
        {{ t("提交独立核验") }}
      </el-button></template
    ></el-dialog
  >
  <el-dialog v-model="verifyDialog" :title="t('核验收益')" width="570px"
    ><p>{{ chosenBenefit?.name }}</p>
    <p class="muted">
      {{ t("申报值：") }} {{ chosenClaim?.value ?? t("定性") }}
      {{ chosenBenefit?.unit }} ·
      {{ chosenClaim?.narrative }}
    </p>
    <el-button
      link
      @click="router.push('/objectives/' + chosenBenefit?.objective_id)"
    >
      {{ t("前往目标审阅证据") }} </el-button
    ><el-form label-position="top"
      ><el-form-item :label="t('核验结果')"
        ><el-radio-group v-model="verifyForm.decision"
          ><el-radio value="Approved"> {{ t("通过") }} </el-radio
          ><el-radio value="Rejected">
            {{ t("驳回") }}
          </el-radio></el-radio-group
        ></el-form-item
      ><el-form-item
        v-if="verifyForm.decision === 'Approved'"
        :label="t('核验值（定性结论可留空）')"
        ><el-input v-model="verifyForm.verified_value" /></el-form-item
      ><el-form-item :label="t('核验依据与意见')"
        ><el-input
          v-model="verifyForm.comment"
          type="textarea"
          :rows="3" /></el-form-item></el-form
    ><template #footer
      ><el-button type="primary" :loading="busy" @click="saveVerify">
        {{ t("确认核验") }}
      </el-button></template
    ></el-dialog
  >
  <el-dialog v-model="linkDialog" :title="t('关联外部项目')" width="540px"
    ><el-form label-position="top"
      ><el-form-item :label="t('系统')"
        ><el-select v-model="linkForm.system"
          ><el-option
            v-for="s in ['Jira', 'Azure DevOps', 'ServiceNow', 'Planner']"
            :key="s"
            :label="s"
            :value="s" /></el-select></el-form-item
      ><el-form-item :label="t('项目参考号')"
        ><el-input v-model="linkForm.external_id" /></el-form-item
      ><el-form-item :label="t('项目HTTPS链接')"
        ><el-input v-model="linkForm.url" /></el-form-item
    ></el-form>
    <p class="muted">
      {{ t("仅接受企业配置的受信域名，本操作不会读写外部项目。") }}
    </p>
    <template #footer
      ><el-button type="primary" :loading="busy" @click="saveLink">
        {{ t("保存链接") }}
      </el-button></template
    ></el-dialog
  >
  <el-dialog
    v-model="historyDialog"
    :title="t('收益申报与核验记录')"
    width="650px"
    ><p class="muted">{{ t("计算方法：") }} {{ chosenBenefit?.method }}</p>
    <el-empty
      v-if="!chosenBenefit?.claims.length"
      :description="t('尚未申报收益')"
    />
    <article
      v-for="c in chosenBenefit?.claims"
      :key="c.id"
      class="timeline-item"
    >
      <h4>
        {{ t("申报") }} {{ c.value ?? t("定性结论") }} {{ chosenBenefit?.unit }}
        <span class="status-badge">{{ c.status }}</span>
      </h4>
      <p>{{ c.narrative }}</p>
      <p v-if="c.verification">
        {{ t("核验人：") }} {{ c.verification.reviewer }} {{ t("· 核验值：") }}
        {{ c.verification.value ?? t("定性") }}<br />{{
          c.verification.comment
        }}
      </p>
    </article></el-dialog
  >
</template>
