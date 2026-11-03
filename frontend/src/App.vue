<script setup lang="ts">
import { t } from "./i18n";
import LanguageSwitcher from "./components/LanguageSwitcher.vue";

import { computed } from "vue";
import { useRoute } from "vue-router";
import {
  Aim,
  Grid,
  Connection,
  CircleCheck,
  Calendar,
  Document,
  ArrowRight,
} from "@element-plus/icons-vue";
import { useSession } from "./stores/session";
const route = useRoute();
const session = useSession();
const links = [
  { path: "/", name: "工作总览", icon: Grid },
  { path: "/objectives", name: "目标与关键结果", icon: Aim },
  { path: "/alignment", name: "战略对齐", icon: Connection },
  { path: "/approvals", name: "审批中心", icon: CircleCheck },
  { path: "/reviews", name: "评审与行动", icon: Calendar },
  { path: "/portfolio", name: "举措与收益", icon: Aim },
  { path: "/audit", name: "审计记录", icon: Document },
  { path: "/operations", name: "任务运维", icon: Grid },
  { path: "/people", name: "人员管理", icon: Document },
];
const visibleLinks = computed(() =>
  links.filter(
    (l) =>
      (l.path !== "/audit" ||
        ["Audit", "PMO", "Manager", "Division Head"].includes(
          session.user?.role || "",
        )) &&
      (!["/operations", "/people"].includes(l.path) ||
        session.user?.role === "System Admin"),
  ),
);
</script>

<template>
  <router-view v-if="route.path === '/login'" />
  <div v-else class="shell">
    <aside class="sidebar">
      <router-link to="/" class="brand"
        ><span class="brand-mark">O<span>↗</span></span>
        <div>OKR<span>ENTERPRISE WORKSPACE</span></div></router-link
      >
      <div class="nav-label">{{ t("目标管理") }}</div>
      <nav>
        <router-link
          v-for="link in visibleLinks"
          :key="link.path"
          :to="link.path"
          :class="{
            active:
              link.path === '/'
                ? route.path === '/'
                : route.path.startsWith(link.path),
          }"
          ><el-icon><component :is="link.icon" /></el-icon>{{ t(link.name)
          }}<el-icon class="nav-arrow"><ArrowRight /></el-icon
        ></router-link>
      </nav>
      <div class="sidebar-note">
        <span class="live-dot"></span> {{ t("让每一步进展") }} <br /><strong>
          {{ t("都连接到战略目标。") }}
        </strong>
      </div>
      <div class="user-block">
        <span class="avatar">{{ session.user?.name.slice(0, 1) }}</span>
        <div>
          <strong>{{ session.user?.name }}</strong
          ><small>{{ session.user?.role }}</small>
        </div>
        <button class="text-button" @click="session.logout">
          {{ t("退出") }}
        </button>
      </div>
    </aside>
    <main class="main">
      <header class="topbar">
        <div class="breadcrumbs">
          {{ t("工作空间") }} <span>/</span>
          <strong>{{ t(route.meta.title) }}</strong>
        </div>
        <div class="topbar-right">
          <LanguageSwitcher />
          <span class="period-label"> {{ t("当前周期") }} </span
          ><el-select
            v-model="session.cycleId"
            style="width: 135px"
            :placeholder="t('请选择周期')"
            ><el-option
              v-for="c in session.catalog.cycles"
              :key="c.id"
              :label="c.name"
              :value="c.id"
          /></el-select>
        </div>
      </header>
      <div class="page">
        <router-view :key="String(session.cycleId) + route.path" />
      </div>
      <footer>
        {{ t("OKR 工作空间") }}
        <span> {{ t("目标清晰 · 进展可见 · 结果可追溯") }} </span>
      </footer>
    </main>
  </div>
</template>
