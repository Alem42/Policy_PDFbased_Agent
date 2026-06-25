import { BasicPage } from "../../components/BasicPage";
import { storyGroups } from "../../lib/storyMap";

export function CompareCasesPage() {
  return <BasicPage title="这是 Compare Cases 页面" stories={[storyGroups.learning[0], storyGroups.learning[2]]} />;
}
