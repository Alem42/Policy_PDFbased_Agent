import { BasicPage } from "../../components/BasicPage";
import { storyGroups } from "../../lib/storyMap";

export function AdminDashboardPage() {
  return <BasicPage title="这是 Admin Dashboard 页面" stories={[...storyGroups.admin, ...storyGroups.crawler]} />;
}
