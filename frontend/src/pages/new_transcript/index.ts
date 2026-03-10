import { mount } from "svelte";
import NewTranscriptionPage from "./NewTranscriptionPage.svelte";

const app = mount(NewTranscriptionPage, {
  target: document.getElementById("app-root")!,
});

export default app;
