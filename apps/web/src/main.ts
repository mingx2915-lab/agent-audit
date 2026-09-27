// Team attribution: 鉴权未来. See repository-root AUTHORS.md.
import { createApp } from "vue";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import "./styles.css";
import App from "./App.vue";
import { initializeApiBase } from "./api";

async function bootstrap(): Promise<void> {
  try {
    await initializeApiBase();
  } catch (error) {
    const message = error instanceof Error ? error.message : "桌面后台未就绪";
    const root = document.querySelector<HTMLDivElement>("#app");
    if (root) {
      root.textContent = `知盾 AgentAudit 无法连接本机后台：${message}`;
    }
    return;
  }

  createApp(App).use(ElementPlus).mount("#app");
}

void bootstrap();
