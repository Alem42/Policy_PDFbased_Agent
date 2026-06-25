import { BasicPage } from "../../components/BasicPage";
import { storyGroups } from "../../lib/storyMap";

export function AdminUploadPage() {
  return <BasicPage title="这是 Admin Upload 页面" stories={[...storyGroups.adminUpload]} />;
}
