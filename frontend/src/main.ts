import { createApp, defineComponent, h } from "vue";
import { createPinia } from "pinia";
import ElementPlus, { ElConfigProvider } from "element-plus";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import en from "element-plus/es/locale/lang/en";
import { locale } from "./i18n";
import "element-plus/dist/index.css";
import "./style.css";
import App from "./App.vue";
import { router } from "./router";

const app = createApp(
  defineComponent({
    setup: () => () =>
      h(ElConfigProvider, { locale: locale.value === "en" ? en : zhCn }, () =>
        h(App),
      ),
  }),
);
app
  .use(createPinia())
  .use(router)
  .use(ElementPlus, { locale: zhCn })
  .mount("#app");
