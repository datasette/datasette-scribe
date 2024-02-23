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
export { default as SlBreadcrumb } from "@shoelace-style/shoelace/dist/react/breadcrumb/index.js";
export { default as SlBreadcrumbItem } from "@shoelace-style/shoelace/dist/react/breadcrumb-item/index.js";
export { default as SlIcon } from "@shoelace-style/shoelace/dist/react/icon/index.js";
export { default as SlCheckbox } from "@shoelace-style/shoelace/dist/react/checkbox/index.js";
export { default as SlSpinner } from "@shoelace-style/shoelace/dist/react/spinner/index.js";

// Why does SlTag break YT video embeds?
//export { default as SlTag } from "@shoelace-style/shoelace/dist/react/tag/index.js";
