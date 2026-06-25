import { BasicPage } from "../../components/BasicPage";
import { storyGroups } from "../../lib/storyMap";

export function AdminDocumentsPage() {
  return <BasicPage title="这是 Admin Documents 页面" stories={[...storyGroups.adminDocuments]} />;
}
