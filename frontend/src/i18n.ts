import { ref, watch } from "vue";
import en from "./locales/en.json";

export type Locale = "zh-CN" | "en";
let saved: string | null = null;
try {
  saved = localStorage.getItem("okr-language");
} catch {
  /* Storage can be unavailable. */
}
export const locale = ref<Locale>(saved === "zh-CN" ? "zh-CN" : "en");
const messages: Record<string, string> = en;
const reverse = Object.fromEntries(
  Object.entries(messages).map(([zh, english]) => [english, zh]),
);

export function t(message: unknown): string {
  const text = String(message ?? "");
  const source = reverse[text] || text;
  return locale.value === "en" ? messages[source] || text : source;
}

export function setLocale(value: Locale) {
  locale.value = value;
}
export function localizedRecord(values: Record<string, string>) {
  return new Proxy(values, {
    get(target, key: string) {
      return t(target[key]);
    },
  });
}
export function formatDate(value: string) {
  if (!value) return "—";
  const date = new Date(
    value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : value + "Z",
  );
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(locale.value === "en" ? "en-GB" : "zh-CN");
}
watch(
  locale,
  (value) => {
    document.documentElement.lang = value;
    document.title = value === "en" ? "OKR Workspace" : "OKR 工作空间";
    try {
      localStorage.setItem("okr-language", value);
    } catch {
      /* Optional preference. */
    }
  },
  { immediate: true },
);
