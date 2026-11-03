<script setup lang="ts">
import { t } from "../i18n";

import { onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Plus, Search } from "@element-plus/icons-vue";
import { api, write } from "../api";
import { useSession } from "../stores/session";
import type { Objective } from "../types";
import { statusNames } from "../types";
import Exports from "../components/Exports.vue";
const session = useSession(),
  router = useRouter(),
  route = useRoute();
const items = ref<Objective[]>([]),
  total = ref(0),
  page = ref(1),
  search = ref(""),
  status = ref(""),
  selectedLevel = ref(""),
  selectedOrg = ref<number>(),
  loading = ref(false),
  dialog = ref(false),
  saving = ref(false);
const form = reactive({
  title: "",
  description: "",
  cycle_id: session.cycleId,
  theme: "",
  priority: "Medium",
  level: "department",
  visibility: "organization",
  start_date: "",
  end_date: "",
});
function open() {
  const cycle = session.catalog.cycles.find((c) => c.id === session.cycleId);
  form.cycle_id = cycle?.id;
  form.start_date = cycle?.start_date || "";
  form.end_date = cycle?.end_date || "";
  dialog.value = true;
}
async function load() {
  loading.value = true;
  try {
    const query = new URLSearchParams({
      page: String(page.value),
      q: search.value,
    });
    if (session.cycleId) query.set("cycle_id", String(session.cycleId));
    if (selectedLevel.value) query.set("level", selectedLevel.value);
    if (selectedOrg.value) query.set("org_id", String(selectedOrg.value));
    if (status.value) query.set("status", status.value);
    const result = await api<{ items: Objective[]; total: number }>(
      "/api/v1/objectives?" + query,
    );
    items.value = result.items;
    total.value = result.total;
  } finally {
    loading.value = false;
  }
}
async function filter(value: string) {
  status.value = value;
  page.value = 1;
  await load();
}
async function create() {
  saving.value = true;
  try {
    const obj = await write<Objective>("/api/v1/objectives", form);
    dialog.value = false;
    await router.push("/objectives/" + obj.id);
  } finally {
    saving.value = false;
  }
}
onMounted(() => {
  load();
  if (route.query.create) open();
});
</script>
<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">OBJECTIVES & KEY RESULTS</div>
      <h1>{{ t("目标与关键结果") }}</h1>
      <p>{{ t("把战略变成清晰的目标与可衡量的结果。") }}</p>
    </div>
    <div class="heading-actions">
      <Exports /><el-button type="primary" :icon="Plus" @click="open">
        {{ t("创建目标") }}
      </el-button>
    </div>
  </div>
  <section class="panel">
    <div class="toolbar" style="flex-wrap: wrap">
      <el-select
        v-model="selectedLevel"
        clearable
        :placeholder="t('目标层级')"
        style="width: 160px"
        @change="
          page = 1;
          load();
        "
        ><el-option
          v-for="(label, key) in {
            corporate: t('企业'),
            division: t('事业部'),
            department: t('部门'),
            team: t('团队'),
            personal: t('个人'),
          }"
          :key="key"
          :value="key"
          :label="label"
      /></el-select>
      <el-select
        v-model="selectedOrg"
        clearable
        :placeholder="t('所属部门')"
        style="width: 180px"
        @change="
          page = 1;
          load();
        "
        ><el-option
          v-for="o in session.catalog.org_units"
          :key="o.id"
          :value="o.id"
          :label="o.name"
      /></el-select>
      <el-input
        v-model="search"
        :placeholder="t('搜索目标名称')"
        :prefix-icon="Search"
        clearable
        @keyup.enter="load"
        @clear="load"
      /><el-button @click="load"> {{ t("搜索") }} </el-button
      ><span class="muted" style="margin-left: auto">
        {{ t("共") }} {{ total }} {{ t("个目标") }}
      </span>
    </div>
    <div class="filter-tabs" style="margin-bottom: 18px">
      <button :class="{ active: status === '' }" @click="filter('')">
        {{ t("全部目标") }}</button
      ><button
        v-for="s in ['Draft', 'Submitted', 'Approved', 'Active', 'Completed']"
        :key="s"
        :class="{ active: status === s }"
        @click="filter(s)"
      >
        {{ statusNames[s] }}
      </button>
    </div>
    <el-table
      v-loading="loading"
      :data="items"
      :empty-text="t('尚未创建目标，点击右上角开始')"
      ><el-table-column :label="t('目标')" min-width="280"
        ><template #default="{ row }"
          ><div
            class="table-title"
            @click="router.push('/objectives/' + row.id)"
          >
            {{ row.title }}
          </div>
          <div class="table-subtitle">
            {{ row.code }} · {{ row.kr_count }} {{ t("个关键结果 ·") }}
            {{ row.theme }}
          </div></template
        ></el-table-column
      ><el-table-column :label="t('负责人 / 部门')" width="170"
        ><template #default="{ row }"
          >{{ row.owner_name }}
          <div class="table-subtitle">{{ row.org_name }}</div></template
        ></el-table-column
      ><el-table-column :label="t('状态')" width="110"
        ><template #default="{ row }"
          ><span :class="['status-badge', row.status]">{{
            statusNames[row.status]
          }}</span></template
        ></el-table-column
      ><el-table-column :label="t('进度')" width="160"
        ><template #default="{ row }"
          ><el-progress
            v-if="row.progress !== null"
            :percentage="Number(row.progress)"
            :stroke-width="5"
            color="#c93616"
          /><span v-else class="muted"> {{ t("未计算") }} </span></template
        ></el-table-column
      ><el-table-column
        prop="end_date"
        :label="t('截止日期')"
        width="115"
      /><el-table-column width="65"
        ><template #default="{ row }"
          ><el-button link @click="router.push('/objectives/' + row.id)">
            {{ t("查看") }}
          </el-button></template
        ></el-table-column
      ></el-table
    >
    <div class="pagination">
      <el-pagination
        v-model:current-page="page"
        :total="total"
        :page-size="20"
        layout="prev, pager, next"
        @current-change="load"
      />
    </div>
  </section>
  <el-dialog v-model="dialog" :title="t('创建目标')" width="650px"
    ><el-form label-position="top"
      ><el-form-item :label="t('目标名称')"
        ><el-input
          v-model="form.title"
          maxlength="200"
          :placeholder="
            t('例如：提升运营效率，释放团队创新时间')
          " /></el-form-item
      ><el-form-item :label="t('目标说明')"
        ><el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          :placeholder="t('说明目标的业务价值与预期结果')"
      /></el-form-item>
      <div class="form-grid">
        <el-form-item :label="t('可见范围')"
          ><el-select v-model="form.visibility"
            ><el-option
              :label="t('按角色和组织授权')"
              value="organization" /><el-option
              :label="t('仅负责人、共享人员及指定审批人')"
              value="restricted" /></el-select></el-form-item
        ><el-form-item :label="t('战略主题')"
          ><el-input
            v-model="form.theme"
            :placeholder="t('例如：运营效率')" /></el-form-item
        ><el-form-item :label="t('优先级')"
          ><el-select v-model="form.priority"
            ><el-option :label="t('高')" value="High" /><el-option
              :label="t('中')"
              value="Medium" /><el-option
              :label="t('低')"
              value="Low" /></el-select></el-form-item
        ><el-form-item :label="t('目标层级')"
          ><el-select v-model="form.level"
            ><el-option
              v-for="(label, key) in {
                corporate: t('企业'),
                division: t('事业部'),
                department: t('部门'),
                team: t('团队'),
                personal: t('个人'),
              }"
              :key="key"
              :label="label"
              :value="key" /></el-select></el-form-item
        ><el-form-item :label="t('周期')"
          ><el-select v-model="form.cycle_id"
            ><el-option
              v-for="c in session.catalog.cycles"
              :key="c.id"
              :label="c.name"
              :value="c.id" /></el-select></el-form-item
        ><el-form-item :label="t('开始日期')"
          ><el-date-picker
            v-model="form.start_date"
            value-format="YYYY-MM-DD" /></el-form-item
        ><el-form-item :label="t('截止日期')"
          ><el-date-picker v-model="form.end_date" value-format="YYYY-MM-DD"
        /></el-form-item></div></el-form
    ><template #footer
      ><el-button @click="dialog = false"> {{ t("取消") }} </el-button
      ><el-button type="primary" :loading="saving" @click="create">
        {{ t("创建并添加关键结果") }}
      </el-button></template
    ></el-dialog
  >
</template>
