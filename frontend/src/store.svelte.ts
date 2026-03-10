import { loadPageData } from "./page_data/load";

export interface Database {
  name: string;
  color: string;
  path: string;
}

interface BasePageData {
  database_name: string;
}

const pageData = loadPageData<BasePageData>();

export const appState = $state({
  databases: [] as Database[],
  selectedDatabase: pageData.database_name,
});
