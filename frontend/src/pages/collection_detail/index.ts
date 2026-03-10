import { mount } from "svelte";
import CollectionDetailPage from "./CollectionDetailPage.svelte";

const app = mount(CollectionDetailPage, {
  target: document.getElementById("app-root")!,
});

export default app;
