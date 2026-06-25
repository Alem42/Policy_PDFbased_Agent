import { BasicPage } from "../../components/BasicPage";
import { storyGroups } from "../../lib/storyMap";

export function TrustedSourcesPage() {
  return <BasicPage title="这是 Trusted Sources 页面" stories={[storyGroups.crawler[1]]} />;
}
