import { BasicPage } from "../../components/BasicPage";
import { storyGroups } from "../../lib/storyMap";

export function AdminLoginPage() {
  return <BasicPage title="这是 Admin Login 页面" stories={[...storyGroups.adminLogin]} />;
}
