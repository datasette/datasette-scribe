import "@shoelace-style/shoelace/dist/themes/light.css";
import { setBasePath } from "@shoelace-style/shoelace/dist/utilities/base-path.js";
setBasePath(
  "https://cdn.jsdelivr.net/npm/@shoelace-style/shoelace@2.14.0/cdn/"
);

export { default as SlButton } from "@shoelace-style/shoelace/dist/react/button/index.js";
export { default as SlSelect } from "@shoelace-style/shoelace/dist/react/select/index.js";
export { default as SlOption } from "@shoelace-style/shoelace/dist/react/option/index.js";
export { default as SlDialog } from "@shoelace-style/shoelace/dist/react/dialog/index.js";
export { default as SlInput } from "@shoelace-style/shoelace/dist/react/input/index.js";
