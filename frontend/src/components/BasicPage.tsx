import { SimpleNav } from "./SimpleNav";

interface BasicPageProps {
  title: string;
  stories: string[];
}

export function BasicPage({ title, stories }: BasicPageProps) {
  return (
    <main>
      <SimpleNav />
      <h1>{title}</h1>
      <p>建议添加这些 stories:</p>
      <ul>
        {stories.map((story) => (
          <li key={story}>{story}</li>
        ))}
      </ul>
    </main>
  );
}
