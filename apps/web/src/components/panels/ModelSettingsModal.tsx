import { useState, useEffect } from "react";
import { Button, Field, Modal, SectionCard } from "@/components/common";
import { createEmptyChatModel } from "@/lib/model-settings";
import type { ChatModelConfig, EmbeddingModelConfig, ModelSettingsDocument } from "@/types/chat";

interface ModelSettingsModalProps {
  busy: boolean;
  open: boolean;
  settings: ModelSettingsDocument;
  onAddChatModel: (initial?: Partial<ChatModelConfig>) => void;
  onAddEmbeddingModel: () => void;
  onChangeActiveChatModel: (name: string) => void;
  onChangeActiveEmbeddingModel: (name: string) => void;
  onClose: () => void;
  onRemoveChatModel: (index: number) => void;
  onRemoveEmbeddingModel: (index: number) => void;
  onSave: (doc?: ModelSettingsDocument) => void | Promise<void>;
  onUpdateChatModel: <Key extends keyof ChatModelConfig>(index: number, key: Key, value: ChatModelConfig[Key]) => void;
  onUpdateEmbeddingModel: <Key extends keyof EmbeddingModelConfig>(
    index: number,
    key: Key,
    value: EmbeddingModelConfig[Key]
  ) => void;
}

export function ModelSettingsModal({
  busy,
  open,
  settings,
  onAddChatModel,
  onChangeActiveChatModel,
  onClose,
  onRemoveChatModel,
  onSave,
  onUpdateChatModel,
}: ModelSettingsModalProps) {
  const [selectedModelIndex, setSelectedModelIndex] = useState<number>(0);
  const [isAddingNew, setIsAddingNew] = useState<boolean>(false);
  const [newModel, setNewModel] = useState<Partial<ChatModelConfig>>({
    name: "New Chat Model",
    model: "",
    base_url: "",
    api_key: "",
    temperature: 1,
    top_p: null,
    enable_thinking: false,
  });

  // Sync selected model with active chat model on open
  useEffect(() => {
    if (open && !isAddingNew) {
      const activeIdx = settings.chat_models.findIndex(m => m.name === settings.active_chat_model);
      setSelectedModelIndex(activeIdx >= 0 ? activeIdx : 0);
    }
  }, [open, settings.active_chat_model, settings.chat_models, isAddingNew]);

  const activeModel = settings.chat_models[selectedModelIndex] ?? settings.chat_models[0];
  const activeIndex = selectedModelIndex < settings.chat_models.length ? selectedModelIndex : 0;

  const isNameDuplicate = (name: string, skipIndex?: number) => {
    return settings.chat_models.some((m, idx) => idx !== skipIndex && m.name.trim() === name.trim());
  };

  return (
    <Modal
      description="Edit chat model definitions stored in the root models.json file."
      onClose={onClose}
      open={open}
      panelClassName="modal__panel--wide"
      title="Model Settings"
    >
      <div className="model-settings-page">
        <SectionCard
          description={isAddingNew ? "Configure the new chat model." : "Configure the selected chat model."}
          title={isAddingNew ? "New Chat Model" : "Chat Model Settings"}
          actions={
            <div style={{ display: "flex", gap: "8px" }}>
              {isAddingNew ? (
                <>
                  <Button
                    disabled={busy || !newModel.name?.trim() || isNameDuplicate(newModel.name)}
                    onClick={() => {
                      const finalModel = createEmptyChatModel(settings.chat_models.length + 1, newModel);
                      onAddChatModel(newModel);
                      onChangeActiveChatModel(finalModel.name);
                      setIsAddingNew(false);
                      const nextSettings = {
                        ...settings,
                        chat_models: [...settings.chat_models, finalModel],
                        active_chat_model: finalModel.name
                      };
                      void onSave(nextSettings);
                    }}
                    size="sm"
                    variant="primary"
                  >
                    Save
                  </Button>
                  <Button
                    disabled={busy}
                    onClick={() => {
                      setIsAddingNew(false);
                    }}
                    size="sm"
                    variant="ghost"
                  >
                    Cancel
                  </Button>
                </>
              ) : settings.chat_models.length > 0 && activeModel ? (
                <>
                  <Button
                    disabled={busy || !activeModel?.name?.trim() || isNameDuplicate(activeModel.name, activeIndex)}
                    onClick={() => void onSave()}
                    size="sm"
                    variant="primary"
                  >
                    Save
                  </Button>
                  <Button
                    disabled={busy}
                    onClick={() => {
                      if (window.confirm("Are you sure you want to remove this model?")) {
                        const newModels = [...settings.chat_models];
                        newModels.splice(activeIndex, 1);
                        const nextSettings = { ...settings, chat_models: newModels };
                        
                        onRemoveChatModel(activeIndex);
                        const newActiveIndex = Math.max(0, activeIndex - 1);
                        setSelectedModelIndex(newActiveIndex);
                        
                        if (settings.active_chat_model === activeModel.name) {
                          const newActiveName = newModels[newActiveIndex]?.name ?? "";
                          onChangeActiveChatModel(newActiveName);
                          nextSettings.active_chat_model = newActiveName;
                        }
                        
                        void onSave(nextSettings);
                      }
                    }}
                    size="sm"
                    variant="danger"
                  >
                    Remove
                  </Button>
                </>
              ) : null}
            </div>
          }
        >
          <div className="form-grid" style={{ marginBottom: "1rem" }}>
            <Field htmlFor="modal-model-list" label="Selected Model">
              <select
                disabled={busy}
                id="modal-model-list"
                onChange={(event) => {
                  const val = event.target.value;
                  if (val === "ADD_NEW") {
                    setIsAddingNew(true);
                    setNewModel({
                      name: "New Chat Model",
                      model: "",
                      base_url: "",
                      api_key: "",
                      temperature: 1,
                      top_p: null,
                      enable_thinking: false,
                    });
                    setSelectedModelIndex(-1);
                  } else {
                    setIsAddingNew(false);
                    const idx = Number.parseInt(val, 10);
                    setSelectedModelIndex(idx);
                    onChangeActiveChatModel(settings.chat_models[idx]?.name ?? "");
                  }
                }}
                value={isAddingNew ? "ADD_NEW" : String(activeIndex)}
              >
                {settings.chat_models.map((item, idx) => (
                  <option key={`${item.name}-${idx}`} value={String(idx)}>
                    {item.name || "Unnamed Model"}
                  </option>
                ))}
                <option value="ADD_NEW">[+] Add Chat Model</option>
              </select>
            </Field>
          </div>

          {(isAddingNew || (settings.chat_models.length > 0 && activeModel)) && (
            <div className="form-grid form-grid--two">
              <Field htmlFor={isAddingNew ? "new-chat-name" : `chat-name-${activeIndex}`} label="Display Name">
                <input
                  disabled={busy}
                  id={isAddingNew ? "new-chat-name" : `chat-name-${activeIndex}`}
                  onChange={(event) => {
                    const val = event.target.value;
                    if (isAddingNew) {
                      setNewModel(prev => ({ ...prev, name: val }));
                    } else {
                      onUpdateChatModel(activeIndex, "name", val);
                      if (settings.active_chat_model === activeModel.name) {
                        onChangeActiveChatModel(val);
                      }
                    }
                  }}
                  type="text"
                  value={isAddingNew ? (newModel.name ?? "") : activeModel.name}
                />
              </Field>

              <Field htmlFor={isAddingNew ? "new-chat-model" : `chat-model-${activeIndex}`} label="Request Model">
                <input
                  disabled={busy}
                  id={isAddingNew ? "new-chat-model" : `chat-model-${activeIndex}`}
                  onChange={(event) => {
                    const val = event.target.value;
                    if (isAddingNew) {
                      setNewModel(prev => ({ ...prev, model: val }));
                    } else {
                      onUpdateChatModel(activeIndex, "model", val);
                    }
                  }}
                  type="text"
                  value={isAddingNew ? (newModel.model ?? "") : (activeModel.model ?? "")}
                />
              </Field>

              <Field htmlFor={isAddingNew ? "new-chat-base-url" : `chat-base-url-${activeIndex}`} label="Base URL">
                <input
                  disabled={busy}
                  id={isAddingNew ? "new-chat-base-url" : `chat-base-url-${activeIndex}`}
                  onChange={(event) => {
                    const val = event.target.value;
                    if (isAddingNew) {
                      setNewModel(prev => ({ ...prev, base_url: val }));
                    } else {
                      onUpdateChatModel(activeIndex, "base_url", val);
                    }
                  }}
                  type="text"
                  value={isAddingNew ? (newModel.base_url ?? "") : (activeModel.base_url ?? "")}
                />
              </Field>

              <Field htmlFor={isAddingNew ? "new-chat-api-key" : `chat-api-key-${activeIndex}`} label="API Key">
                <input
                  disabled={busy}
                  id={isAddingNew ? "new-chat-api-key" : `chat-api-key-${activeIndex}`}
                  onChange={(event) => {
                    const val = event.target.value;
                    if (isAddingNew) {
                      setNewModel(prev => ({ ...prev, api_key: val }));
                    } else {
                      onUpdateChatModel(activeIndex, "api_key", val);
                    }
                  }}
                  type="password"
                  value={isAddingNew ? (newModel.api_key ?? "") : (activeModel.api_key ?? "")}
                />
              </Field>

              <Field htmlFor={isAddingNew ? "new-chat-temperature" : `chat-temperature-${activeIndex}`} label="Temperature">
                <input
                  disabled={busy}
                  id={isAddingNew ? "new-chat-temperature" : `chat-temperature-${activeIndex}`}
                  onChange={(event) => {
                    const val = event.target.value;
                    const num = val === "" ? 1 : Number.parseFloat(val);
                    if (isAddingNew) {
                      setNewModel(prev => ({ ...prev, temperature: num }));
                    } else {
                      onUpdateChatModel(activeIndex, "temperature", num);
                    }
                  }}
                  step="0.1"
                  type="number"
                  value={String(isAddingNew ? (newModel.temperature ?? 1) : activeModel.temperature)}
                />
              </Field>

              <Field htmlFor={isAddingNew ? "new-chat-top-p" : `chat-top-p-${activeIndex}`} label="Top P">
                <input
                  disabled={busy}
                  id={isAddingNew ? "new-chat-top-p" : `chat-top-p-${activeIndex}`}
                  onChange={(event) => {
                    const val = event.target.value;
                    const num = val === "" ? null : Number.parseFloat(val);
                    if (isAddingNew) {
                      setNewModel(prev => ({ ...prev, top_p: num }));
                    } else {
                      onUpdateChatModel(activeIndex, "top_p", num);
                    }
                  }}
                  placeholder="Optional"
                  step="0.1"
                  type="number"
                  value={isAddingNew ? (newModel.top_p == null ? "" : String(newModel.top_p)) : (activeModel.top_p == null ? "" : String(activeModel.top_p))}
                />
              </Field>

              <Field htmlFor={isAddingNew ? "new-chat-thinking" : `chat-thinking-${activeIndex}`} label="Enable Thinking">
                <select
                  disabled={busy}
                  id={isAddingNew ? "new-chat-thinking" : `chat-thinking-${activeIndex}`}
                  onChange={(event) => {
                    const val = event.target.value;
                    const bool = val === "" ? null : val === "true";
                    if (isAddingNew) {
                      setNewModel(prev => ({ ...prev, enable_thinking: bool }));
                    } else {
                      onUpdateChatModel(activeIndex, "enable_thinking", bool);
                    }
                  }}
                  value={
                    (isAddingNew ? newModel.enable_thinking : activeModel.enable_thinking) == null
                      ? ""
                      : (isAddingNew ? newModel.enable_thinking : activeModel.enable_thinking)
                        ? "true"
                        : "false"
                  }
                >
                  <option value="">Provider default</option>
                  <option value="true">Enabled</option>
                  <option value="false">Disabled</option>
                </select>
              </Field>
            </div>
          )}
        </SectionCard>
      </div>
    </Modal>
  );
}
