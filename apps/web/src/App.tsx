import { useState } from "react";

import { ChatHeader, MessageComposer, MessageList } from "@/components/chat";
import { Button, Modal } from "@/components/common";
import {
  DatabasePanel,
  DatabaseSettingsModal,
  EmbeddingModelSettingsModal,
  ModelSettingsModal,
  ModelSettingsPanel,
  SessionPanel,
  WorkflowPanel,
} from "@/components/panels";
import { useChatWorkspace } from "@/hooks/useChatWorkspace";

export default function App() {
  const { actions, dialogs, drafts, refs, workspace } = useChatWorkspace();
  const { activeModelName, activeSession, modelNames, state } = workspace;
  const [leftHidden, setLeftHidden] = useState(false);
  const [rightHidden, setRightHidden] = useState(false);

  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>

      <div className="app-frame">
        <div className="app-backdrop app-backdrop--top" aria-hidden="true" />
        <div className="app-backdrop app-backdrop--bottom" aria-hidden="true" />

        <div
          className={`app-shell${leftHidden ? " app-shell--left-hidden" : ""}${rightHidden ? " app-shell--right-hidden" : ""}${
            leftHidden && rightHidden ? " app-shell--both-hidden" : ""
          }`}
        >
          <aside className="app-shell__sidebar">
            <SessionPanel
              activeSessionId={state.sessionId}
              busy={state.busy}
              onCreate={() => {
                void actions.createSession();
              }}
              onDelete={actions.openDeleteSessionDialog}
              onRename={(session, title) => {
                void actions.renameSession(session, title);
              }}
              onSelect={(sessionId) => {
                void actions.selectSession(sessionId);
              }}
              ready={state.ready}
              sessions={state.sessions}
            />

            <DatabasePanel
              activeDatabaseId={state.activeDatabaseId}
              busy={state.busy}
              databases={state.databases}
              documents={workspace.databaseDocuments}
              onOpenEmbeddingSettings={actions.openEmbeddingModelSettings}
              onOpenSettings={actions.openDatabaseSettings}
              onUploadFiles={(files) => {
                void actions.uploadDatabaseDocuments(files);
              }}
              onSelect={(databaseId) => {
                void actions.selectDatabase(databaseId);
              }}
            />
          </aside>

          <main className="app-shell__main" id="main-content">
            <button
              aria-label={leftHidden ? "Show sessions panel" : "Hide sessions panel"}
              className="panel-toggle panel-toggle--left"
              onClick={() => {
                setLeftHidden((current) => !current);
              }}
              type="button"
            >
              {leftHidden ? ">" : "<"}
            </button>

            <button
              aria-label={rightHidden ? "Show settings panel" : "Hide settings panel"}
              className="panel-toggle panel-toggle--right"
              onClick={() => {
                setRightHidden((current) => !current);
              }}
              type="button"
            >
              {rightHidden ? "<" : ">"}
            </button>

            <section className="chat-workspace">
              <ChatHeader
                totalTokens={activeSession?.total_tokens ?? 0}
                title={activeSession?.title ?? "Workspace"}
              />

              <MessageList
                messages={state.messages}
                onDelete={actions.openDeleteMessageDialog}
                onEdit={(message, content) => {
                  void actions.updateMessageContent(message, content);
                }}
                onRegenerate={(message) => {
                  void actions.regenerateMessage(message);
                }}
                onRollback={actions.openRollbackDialog}
                ready={state.ready}
              />

              <MessageComposer
                busy={state.busy}
                inputRef={refs.messageInputRef}
                onChange={drafts.setMessageDraft}
                onSubmit={() => {
                  void actions.sendMessage();
                }}
                value={drafts.messageDraft}
              />
            </section>
          </main>

          <aside className="app-shell__rail">
            <ModelSettingsPanel
              activeModelName={activeModelName}
              busy={state.busy}
              modelNames={modelNames}
              onOpenSettings={actions.openModelSettings}
              onSelectActiveModel={(name) => {
                void actions.selectActiveChatModel(name);
              }}
            />

            <WorkflowPanel workflow={state.workflow} />
          </aside>
        </div>
      </div>

      <Modal
        description={dialogs.confirmDialog?.description}
        footer={
          dialogs.confirmDialog ? (
            <>
              <Button
                onClick={() => {
                  dialogs.setConfirmDialog(null);
                }}
                variant="ghost"
              >
                Cancel
              </Button>
              <Button
                onClick={() => {
                  void dialogs.confirmDialog?.onConfirm();
                }}
                variant={dialogs.confirmDialog.tone === "danger" ? "danger" : "primary"}
              >
                {dialogs.confirmDialog.confirmLabel}
              </Button>
            </>
          ) : null
        }
        onClose={() => {
          dialogs.setConfirmDialog(null);
        }}
        open={Boolean(dialogs.confirmDialog)}
        title={dialogs.confirmDialog?.title ?? "Confirm Action"}
      >
        <p className="modal-copy">{dialogs.confirmDialog?.description}</p>
      </Modal>

      <ModelSettingsModal
        busy={state.busy}
        onAddChatModel={drafts.addChatModel}
        onAddEmbeddingModel={drafts.addEmbeddingModel}
        onChangeActiveChatModel={drafts.setActiveChatModel}
        onChangeActiveEmbeddingModel={drafts.setActiveEmbeddingModel}
        onClose={actions.closeModelSettings}
        onRemoveChatModel={drafts.removeChatModel}
        onRemoveEmbeddingModel={drafts.removeEmbeddingModel}
        onSave={actions.saveModelSettings}
        onUpdateChatModel={drafts.updateChatModel}
        onUpdateEmbeddingModel={drafts.updateEmbeddingModel}
        open={drafts.modelSettingsOpen}
        settings={drafts.modelSettingsDraft}
      />

      <EmbeddingModelSettingsModal
        busy={state.busy}
        onAddEmbeddingModel={drafts.addEmbeddingModel}
        onChangeActiveEmbeddingModel={drafts.setActiveEmbeddingModel}
        onClose={actions.closeEmbeddingModelSettings}
        onRemoveEmbeddingModel={drafts.removeEmbeddingModel}
        onSave={actions.saveEmbeddingModelSettings}
        onUpdateEmbeddingModel={drafts.updateEmbeddingModel}
        open={drafts.embeddingModelSettingsOpen}
        settings={drafts.modelSettingsDraft}
      />

      <DatabaseSettingsModal
        activeDatabaseId={state.activeDatabaseId}
        busy={state.busy}
        databases={state.databases}
        embeddingModelNames={workspace.embeddingModelNames}
        onClose={actions.closeDatabaseSettings}
        onCreate={(name, embeddingModelName) => {
          void actions.createDatabase(name, embeddingModelName);
        }}
        onDelete={actions.openDeleteDatabaseDialog}
        onRename={(database, name) => {
          void actions.renameDatabase(database, name);
        }}
        onSelect={(databaseId) => {
          void actions.selectDatabase(databaseId);
        }}
        open={drafts.databaseSettingsOpen}
      />
    </>
  );
}
