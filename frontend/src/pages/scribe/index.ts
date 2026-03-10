import { mount } from "svelte";
import ScribePage from "./ScribePage.svelte";

const app = mount(ScribePage, {
  target: document.getElementById("app-root")!,
});

export default app;
