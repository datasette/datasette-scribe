/**
 * Load page data from the embedded JSON script tag.
 *
 * The server renders page data as:
 * <script type="application/json" id="pageData">{"key": "value"}</script>
 */
export function loadPageData<T>(): T {
  const script = document.querySelector<HTMLScriptElement>("#pageData");
  if (!script) {
    throw new Error("Page data script not found");
  }
  return JSON.parse(script.textContent || "{}") as T;
}
