import { BasicPage } from "../../components/BasicPage";
import { storyGroups } from "../../lib/storyMap";

export function ProcessingStatusPage() {
  return <BasicPage title="这是 Processing Status 页面" stories={[...storyGroups.processing]} />;
}
