import { SettingsScreen, WorkspaceScreen } from "@/components/app";
import { useChatWorkspace } from "@/hooks/useChatWorkspace";

export default function App() {
  const app = useChatWorkspace();

  return app.settings.pageOpen ? <SettingsScreen app={app} /> : <WorkspaceScreen app={app} />;
}
