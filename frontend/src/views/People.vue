<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api, write } from "../api";
import { t } from "../i18n";
import { useSession } from "../stores/session";
const session = useSession();
interface Person {
  id: number;
  name: string;
  username: string | null;
  role: string;
  org_id: number;
  org_name: string;
  active: boolean;
  etag: string;
}
const items = ref<Person[]>([]),
  total = ref(0),
  page = ref(1),
  query = ref(""),
  active = ref("all"),
  loading = ref(false),
  busy = ref(false),
  error = ref(false);
const organizations = ref<{ id: number; name: string }[]>([]),
  roles = ref<string[]>([]),
  dialog = ref(false),
  passwordDialog = ref(false),
  selected = ref<Person>(),
  password = ref(""),
  confirmPassword = ref("");
const form = reactive({
  name: "",
  username: "",
  org_id: undefined as number | undefined,
  role: "Employee",
  password: "",
  confirmation: "",
});
async function load() {
  loading.value = true;
  error.value = false;
  try {
    const qs = new URLSearchParams({
      q: query.value,
      page: String(page.value),
    });
    if (active.value !== "all") qs.set("active", active.value);
    const result = await api<{ items: Person[]; total: number }>(
      "/api/v1/admin/people?" + qs,
    );
    items.value = result.items;
    total.value = result.total;
  } catch {
    error.value = true;
  } finally {
    loading.value = false;
  }
}
onMounted(async () => {
  const options = await api<{
    organizations: { id: number; name: string }[];
    roles: string[];
  }>("/api/v1/admin/people/options");
  organizations.value = options.organizations;
  roles.value = options.roles;
  await load();
});
function open(person?: Person) {
  selected.value = person;
  Object.assign(form, {
    name: person?.name || "",
    username: person?.username || "",
    org_id: person?.org_id,
    role: person?.role || "Employee",
    password: "",
    confirmation: "",
  });
  dialog.value = true;
}
function clearSecrets() {
  form.password = "";
  form.confirmation = "";
  password.value = "";
  confirmPassword.value = "";
}
async function save() {
  if (!selected.value && form.password !== form.confirmation) {
    ElMessage.error(t("两次输入的密码不一致"));
    return;
  }
  busy.value = true;
  try {
    if (selected.value) {
      await write(
        `/api/v1/admin/people/${selected.value.id}`,
        { name: form.name, org_id: form.org_id, role: form.role },
        selected.value.etag,
        "PATCH",
      );
    } else {
      await write("/api/v1/admin/people", {
        name: form.name,
        username: form.username,
        org_id: form.org_id,
        role: form.role,
        password: form.password,
      });
    }
    dialog.value = false;
    clearSecrets();
    if (selected.value?.id === session.user?.id) {
      location.assign("/login");
      return;
    }
    await load();
    ElMessage.success(t("人员资料已保存"));
  } finally {
    busy.value = false;
  }
}
async function toggle(person: Person) {
  try {
    await ElMessageBox.confirm(
      t(
        person.active
          ? "停用后，此人员将立即退出且无法登录。确认停用？"
          : "确认重新启用此人员？",
      ),
      t(person.active ? "停用人员" : "启用人员"),
      {
        confirmButtonText: t("确认"),
        cancelButtonText: t("取消"),
        type: "warning",
      },
    );
  } catch {
    return;
  }
  busy.value = true;
  try {
    await write(
      `/api/v1/admin/people/${person.id}/active`,
      { active: !person.active },
      person.etag,
    );
    await load();
  } finally {
    busy.value = false;
  }
}
function openPassword(person: Person) {
  selected.value = person;
  password.value = "";
  confirmPassword.value = "";
  passwordDialog.value = true;
}
async function reset() {
  if (password.value !== confirmPassword.value) {
    ElMessage.error(t("两次输入的密码不一致"));
    return;
  }
  if (!selected.value) return;
  busy.value = true;
  try {
    await write(
      `/api/v1/admin/people/${selected.value.id}/password`,
      { password: password.value },
      selected.value.etag,
    );
    passwordDialog.value = false;
    clearSecrets();
    ElMessage.success(t("密码已重设，旧会话已失效"));
    if (selected.value.id === session.user?.id) location.assign("/login");
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">PEOPLE & ACCESS</div>
      <h1>{{ t("人员管理") }}</h1>
      <p>{{ t("仅系统管理员可新增人员、设置角色、停用账号和重设密码。") }}</p>
    </div>
    <el-button type="primary" @click="open()">{{ t("新增人员") }}</el-button>
  </div>
  <section class="panel" v-loading="loading">
    <div class="toolbar" style="flex-wrap: wrap">
      <el-input
        v-model="query"
        :placeholder="t('搜索姓名或账号')"
        clearable
        @keyup.enter="
          page = 1;
          load();
        "
      /><el-select
        v-model="active"
        style="width: 150px"
        @change="
          page = 1;
          load();
        "
        ><el-option :label="t('全部人员')" value="all" /><el-option
          :label="t('已启用')"
          value="true" /><el-option
          :label="t('已停用')"
          value="false" /></el-select
      ><el-button
        @click="
          page = 1;
          load();
        "
        >{{ t("搜索") }}</el-button
      >
    </div>
    <el-alert
      v-if="error"
      :title="t('数据加载失败，请稍后重试')"
      type="error"
      :closable="false"
    />
    <el-table :data="items" :empty-text="t('暂无人员')"
      ><el-table-column
        prop="name"
        :label="t('姓名')"
        min-width="140"
      /><el-table-column
        prop="username"
        :label="t('账号')"
        min-width="140"
      /><el-table-column
        prop="org_name"
        :label="t('所属部门')"
        min-width="140"
      /><el-table-column :label="t('角色')" min-width="140"
        ><template #default="{ row }">{{
          t(row.role)
        }}</template></el-table-column
      ><el-table-column :label="t('状态')" width="100"
        ><template #default="{ row }">{{
          t(row.active ? "已启用" : "已停用")
        }}</template></el-table-column
      ><el-table-column :label="t('操作')" min-width="250"
        ><template #default="{ row }"
          ><el-button link :disabled="busy" @click="open(row)">{{
            t("编辑")
          }}</el-button
          ><el-button
            link
            :disabled="busy || !row.username"
            @click="openPassword(row)"
            >{{ t("重设密码") }}</el-button
          ><el-button
            link
            :type="row.active ? 'danger' : 'primary'"
            :disabled="busy || row.id === session.user?.id"
            @click="toggle(row)"
            >{{ t(row.active ? "停用" : "启用") }}</el-button
          ></template
        ></el-table-column
      ></el-table
    >
    <div class="pagination">
      <el-pagination
        v-model:current-page="page"
        :total="total"
        :page-size="20"
        layout="prev,pager,next,total"
        @current-change="load"
      />
    </div>
    <p class="muted">
      {{ t("角色或组织变更、停用和重设密码会使该人员的现有会话失效。") }}
    </p>
  </section>
  <el-dialog
    v-model="dialog"
    :title="t(selected ? '编辑人员' : '新增人员')"
    width="580px"
    @closed="clearSecrets"
    ><el-form label-position="top"
      ><el-form-item :label="t('姓名')"
        ><el-input v-model="form.name" :maxlength="100" /></el-form-item
      ><el-form-item v-if="!selected" :label="t('账号')"
        ><el-input
          v-model="form.username"
          autocomplete="off"
          :maxlength="64"
        /><span class="muted">{{
          t("账号为3至64位字母、数字或 . _ @ -，不区分大小写。")
        }}</span></el-form-item
      ><el-form-item :label="t('所属部门')"
        ><el-select v-model="form.org_id"
          ><el-option
            v-for="o in organizations"
            :key="o.id"
            :label="o.name"
            :value="o.id" /></el-select></el-form-item
      ><el-form-item :label="t('角色')"
        ><el-select
          v-model="form.role"
          :disabled="selected?.id === session.user?.id"
          ><el-option
            v-for="r in roles"
            :key="r"
            :label="t(r)"
            :value="r" /></el-select></el-form-item
      ><template v-if="!selected"
        ><el-form-item :label="t('初始密码')"
          ><el-input
            v-model="form.password"
            type="password"
            show-password
            autocomplete="new-password"
            :maxlength="128" /></el-form-item
        ><el-form-item :label="t('确认密码')"
          ><el-input
            v-model="form.confirmation"
            type="password"
            autocomplete="new-password"
            :maxlength="128" /></el-form-item
      ></template>
      <p v-if="!selected" class="muted">
        {{ t("密码长度须为12至128个字符。") }}
      </p></el-form
    ><template #footer
      ><el-button @click="dialog = false">{{ t("取消") }}</el-button
      ><el-button
        type="primary"
        :loading="busy"
        :disabled="
          !form.name.trim() ||
          !form.org_id ||
          (!selected && (!form.username.trim() || form.password.length < 12))
        "
        @click="save"
        >{{ t("保存修改") }}</el-button
      ></template
    ></el-dialog
  >
  <el-dialog
    v-model="passwordDialog"
    :title="t('重设密码')"
    width="500px"
    @closed="clearSecrets"
    ><p>{{ selected?.name }} · {{ selected?.username }}</p>
    <el-form label-position="top"
      ><el-form-item :label="t('新密码')"
        ><el-input
          v-model="password"
          type="password"
          show-password
          autocomplete="new-password"
          :maxlength="128" /></el-form-item
      ><el-form-item :label="t('确认密码')"
        ><el-input
          v-model="confirmPassword"
          type="password"
          autocomplete="new-password"
          :maxlength="128" /></el-form-item
    ></el-form>
    <p class="muted">{{ t("密码长度须为12至128个字符。") }}</p>
    <template #footer
      ><el-button @click="passwordDialog = false">{{ t("取消") }}</el-button
      ><el-button
        type="primary"
        :loading="busy"
        :disabled="password.length < 12 || !confirmPassword"
        @click="reset"
        >{{ t("确认重设") }}</el-button
      ></template
    ></el-dialog
  >
</template>
