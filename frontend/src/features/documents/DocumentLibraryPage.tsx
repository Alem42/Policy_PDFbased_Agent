import { BasicPage } from "../../components/BasicPage";
import { storyGroups } from "../../lib/storyMap";

export function DocumentLibraryPage() {
  return <BasicPage title="这是 Document Library 页面" stories={[...storyGroups.documents]} />;
}
