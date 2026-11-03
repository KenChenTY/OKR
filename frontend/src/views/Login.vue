<script setup lang="ts">
import { t } from "../i18n";
import LanguageSwitcher from "../components/LanguageSwitcher.vue";

import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api, write } from "../api";
import { useSession } from "../stores/session";
const router = useRouter(),
  session = useSession();
const development = ref(false),
  passwordMode = ref(true),
  username = ref(""),
  password = ref(""),
  loginError = ref(""),
  users = ref<{ id: number; name: string; role: string }[]>([]),
  selected = ref<number>(),
  busy = ref(false),
  ready = ref<boolean | null>(null),
  error = ref("");
async function checkService() {
  ready.value = null;
  error.value = "";
  try {
    const config = await api<{
      development_login: boolean;
      password_login?: boolean;
    }>("/auth/config", { signal: AbortSignal.timeout(15000) }, true);
    development.value = config.development_login;
    passwordMode.value = config.password_login ?? false;
    await api("/api/status", { signal: AbortSignal.timeout(15000) }, true);
    ready.value = true;
    if (development.value) {
      users.value = await api("/auth/development/users", {}, true);
      selected.value = users.value[0]?.id;
    }
  } catch (e) {
    ready.value = false;
    error.value = e instanceof Error ? e.message : t("服务尚未就绪");
  }
}
onMounted(checkService);
async function login() {
  if (!selected.value) return;
  busy.value = true;
  try {
    await write("/auth/development/login", { user_id: selected.value });
    await session.load();
    await router.push("/");
  } finally {
    busy.value = false;
  }
}
async function passwordLogin() {
  if (busy.value) return;
  if (!username.value.trim() || !password.value) {
    loginError.value = !username.value.trim()
      ? t("请输入账号")
      : t("请输入密码");
    return;
  }
  busy.value = true;
  loginError.value = "";
  try {
    await api(
      "/auth/password/login",
      {
        method: "POST",
        body: JSON.stringify({
          username: username.value.trim(),
          password: password.value,
        }),
      },
      true,
    );
    password.value = "";
    await session.load();
    await router.push("/");
  } catch (e) {
    loginError.value = e instanceof Error ? e.message : t("登录失败，请重试");
    password.value = "";
  } finally {
    busy.value = false;
  }
}
function enterpriseLogin() {
  window.location.assign("/auth/login");
}
</script>
<template>
  <div class="login-page">
    <div class="login-language"><LanguageSwitcher /></div>
    <section class="login-story">
      <div class="brand">
        <span class="brand-mark">O<span>↗</span></span>
        <div>OKR<span>ENTERPRISE WORKSPACE</span></div>
      </div>
      <div class="eyebrow">ALIGN. FOCUS. ACHIEVE.</div>
      <h1>
        {{ t("连接战略与行动") }} <br />
        {{ t("让进展清晰可见") }}
      </h1>
      <p>
        {{ t("聚焦共同的目标，用可衡量的关键结果，记录每一次有依据的进步。") }}
      </p>
    </section>
    <section class="login-content">
      <div class="login-card">
        <div class="eyebrow">WELCOME BACK</div>
        <h2>{{ t("欢迎进入工作空间") }}</h2>
        <p>
          {{ t("登录企业账号，查看目标、更新进展") }} <br />
          {{ t("并与团队协作。") }}
        </p>
        <form v-if="passwordMode" @submit.prevent="passwordLogin">
          <el-form-item :label="t('账号')" label-position="top">
            <el-input
              v-model="username"
              :aria-label="t('账号')"
              autocomplete="username"
              :placeholder="t('请输入账号')"
              :maxlength="64"
            />
          </el-form-item>
          <el-form-item :label="t('密码')" label-position="top">
            <el-input
              v-model="password"
              :aria-label="t('密码')"
              type="password"
              autocomplete="current-password"
              show-password
              :placeholder="t('请输入密码')"
              :maxlength="128"
            />
          </el-form-item>
          <el-alert
            v-if="loginError"
            :title="t(loginError)"
            type="error"
            :closable="false"
            show-icon
            style="margin-bottom: 16px"
            role="alert"
          />
          <el-button
            type="primary"
            native-type="submit"
            :loading="busy"
            :disabled="busy"
          >
            {{ t("登录工作空间 →") }}
          </el-button>
          <p class="muted" style="margin-top: 18px">
            {{ t("忘记密码？请联系管理员重置。") }}
          </p>
        </form>
        <template v-else-if="development && ready"
          ><el-form label-position="top"
            ><el-form-item :label="t('开发环境测试身份')"
              ><el-select v-model="selected" style="width: 100%"
                ><el-option
                  v-for="u in users"
                  :key="u.id"
                  :label="u.name"
                  :value="u.id" /></el-select></el-form-item></el-form
          ><el-button
            type="primary"
            :loading="busy"
            :disabled="!selected"
            @click="login"
          >
            {{ t("进入工作空间 →") }}
          </el-button>
          <p class="muted">
            {{ t("仅限隔离开发环境，生产环境禁止此登录方式。") }}
          </p></template
        ><el-button
          v-else
          type="primary"
          :disabled="ready !== true"
          @click="enterpriseLogin()"
        >
          {{ t("通过 Microsoft 企业账号登录 →") }}
        </el-button>
        <div v-if="ready === false" class="login-health">
          <el-alert
            :title="t('服务尚未就绪')"
            :description="t(error)"
            type="info"
            :closable="false"
            show-icon
          />
          <el-button text @click="checkService">
            {{ t("重新检查连接") }}
          </el-button>
        </div>
        <div v-else-if="ready === null" class="login-health muted">
          {{ t("正在检查服务状态…") }}
        </div>
        <div class="login-foot">
          {{ t("企业身份认证 · 按角色授权 · 操作全程留痕") }}
        </div>
      </div>
    </section>
  </div>
</template>
