import { defineStore } from "pinia";
import { ref } from "vue";
import { api, setCsrf } from "../api";
import type { Catalog, User } from "../types";

export const useSession = defineStore("session", () => {
  const user = ref<User | null>(null);
  const catalog = ref<Catalog>({ cycles: [], org_units: [], users: [] });
  const cycleId = ref<number | undefined>();
  async function load() {
    user.value = await api<User>("/api/v1/me", {}, true);
    setCsrf(user.value.csrf);
    catalog.value = await api<Catalog>("/api/v1/catalog");
    const today = new Date().toISOString().slice(0, 10);
    cycleId.value ??=
      catalog.value.cycles.find(
        (c) => c.start_date <= today && c.end_date >= today,
      )?.id ?? catalog.value.cycles[0]?.id;
  }
  async function logout() {
    await api("/auth/logout", { method: "POST" });
    user.value = null;
    setCsrf("");
    location.assign("/login");
  }
  return { user, catalog, cycleId, load, logout };
});
