import { mount } from "svelte";
import TranscriptionDetailPage from "./TranscriptionDetailPage.svelte";

const app = mount(TranscriptionDetailPage, {
  target: document.getElementById("app-root")!,
});

export default app;
