import { BasicPage } from "../../components/BasicPage";
import { storyGroups } from "../../lib/storyMap";

export function DocumentDetailPage() {
  return <BasicPage title="这是 Document Detail 页面" stories={[storyGroups.documents[1]]} />;
}
