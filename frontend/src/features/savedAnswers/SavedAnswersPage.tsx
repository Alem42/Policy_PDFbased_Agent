import { BasicPage } from "../../components/BasicPage";
import { storyGroups } from "../../lib/storyMap";

export function SavedAnswersPage() {
  return <BasicPage title="这是 Saved Answers 页面" stories={[...storyGroups.savedAnswers]} />;
}
