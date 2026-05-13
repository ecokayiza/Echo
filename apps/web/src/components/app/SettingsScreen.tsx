import { ManagementSettingsPage } from "@/components/settings";
import type { useChatWorkspace } from "@/hooks/useChatWorkspace";

import { ConfirmDialogModal } from "./ConfirmDialogModal";

type ChatWorkspace = ReturnType<typeof useChatWorkspace>;

interface SettingsScreenProps {
  app: ChatWorkspace;
}

export function SettingsScreen({ app }: SettingsScreenProps) {
  const { dialogs, settings, workspace } = app;

  return (
    <>
      <ManagementSettingsPage
        appSettings={settings.drafts.appSettings}
        busy={workspace.state.busy}
        modelSettings={settings.drafts.modelSettings}
        onAddChatModel={settings.actions.addChatModel}
        onAddEmbeddingModel={settings.actions.addEmbeddingModel}
        onAddSkill={settings.actions.addSkill}
        onBack={settings.actions.close}
        onChangeActiveChatModel={settings.actions.setActiveChatModel}
        onChangeActiveEmbeddingModel={settings.actions.setActiveEmbeddingModel}
        onRemoveChatModel={settings.actions.removeChatModel}
        onRemoveEmbeddingModel={settings.actions.removeEmbeddingModel}
        onRemoveSkill={settings.actions.removeSkill}
        onSave={settings.actions.save}
        onTestChatModel={settings.actions.testChatModel}
        onTestEmbeddingModel={settings.actions.testEmbeddingModel}
        onUpdateAppSetting={settings.actions.updateAppSetting}
        onUpdateChatModel={settings.actions.updateChatModel}
        onUpdateEmbeddingModel={settings.actions.updateEmbeddingModel}
        onUpdateSkill={settings.actions.updateSkill}
        skillSettings={settings.drafts.skillSettings}
        statusText={workspace.state.statusText}
        statusTone={workspace.state.statusTone}
      />
      <ConfirmDialogModal dialogs={dialogs} />
    </>
  );
}
