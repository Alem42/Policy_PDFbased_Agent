import { BasicPage } from "../../components/BasicPage";
import { storyGroups } from "../../lib/storyMap";

export function ChatPage() {
  return <BasicPage title="这是 Ask AI 页面" stories={[...storyGroups.chat]} />;
}
