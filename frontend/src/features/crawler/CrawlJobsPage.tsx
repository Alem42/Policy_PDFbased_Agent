import { BasicPage } from "../../components/BasicPage";
import { storyGroups } from "../../lib/storyMap";

export function CrawlJobsPage() {
  return <BasicPage title="这是 Crawl Jobs 页面" stories={[storyGroups.crawler[0]]} />;
}
