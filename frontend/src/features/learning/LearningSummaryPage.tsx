import { BasicPage } from "../../components/BasicPage";
import { storyGroups } from "../../lib/storyMap";

export function LearningSummaryPage() {
  return <BasicPage title="这是 Learning Summary 页面" stories={[storyGroups.learning[1], storyGroups.chat[1]]} />;
}
