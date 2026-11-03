import { createRouter, createWebHistory } from "vue-router";
import { useSession } from "./stores/session";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: () => import("./views/Login.vue") },
    {
      path: "/",
      component: () => import("./views/Dashboard.vue"),
      meta: { title: "工作总览" },
    },
    {
      path: "/objectives",
      component: () => import("./views/Objectives.vue"),
      meta: { title: "目标与关键结果" },
    },
    {
      path: "/objectives/:id",
      component: () => import("./views/ObjectiveDetail.vue"),
      meta: { title: "目标详情" },
    },
    {
      path: "/alignment",
      component: () => import("./views/Alignment.vue"),
      meta: { title: "战略对齐" },
    },
    {
      path: "/approvals",
      component: () => import("./views/Approvals.vue"),
      meta: { title: "审批中心" },
    },
    {
      path: "/reviews",
      component: () => import("./views/Reviews.vue"),
      meta: { title: "评审与行动" },
    },
    {
      path: "/portfolio",
      component: () => import("./views/Portfolio.vue"),
      meta: { title: "举措与收益" },
    },
    {
      path: "/operations",
      component: () => import("./views/Operations.vue"),
      meta: { title: "任务运维" },
    },
    {
      path: "/people",
      component: () => import("./views/People.vue"),
      meta: { title: "人员管理", adminOnly: true },
    },
    {
      path: "/audit",
      component: () => import("./views/Audit.vue"),
      meta: { title: "审计记录" },
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});
router.beforeEach(async (to) => {
  if (to.path === "/login") return true;
  const session = useSession();
  if (!session.user) {
    try {
      await session.load();
    } catch {
      return "/login";
    }
  }
  if (to.meta.adminOnly && session.user?.role !== "System Admin") return "/";
  return true;
});
