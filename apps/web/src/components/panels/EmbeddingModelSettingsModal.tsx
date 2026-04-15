import { useEffect, useState } from "react";

import { Button, Field, Modal, SectionCard } from "@/components/common";
import { createEmptyEmbeddingModel } from "@/lib/model-settings";
import type { EmbeddingModelConfig, ModelSettingsDocument } from "@/types/chat";

interface EmbeddingModelSettingsModalProps {
  busy: boolean;
  open: boolean;
  settings: ModelSettingsDocument;
  onAddEmbeddingModel: (initial?: Partial<EmbeddingModelConfig>) => void;
  onChangeActiveEmbeddingModel: (name: string) => void;
  onClose: () => void;
  onRemoveEmbeddingModel: (index: number) => void;
  onSave: (doc?: ModelSettingsDocument) => void | Promise<void>;
  onUpdateEmbeddingModel: <Key extends keyof EmbeddingModelConfig>(
    index: number,
    key: Key,
    value: EmbeddingModelConfig[Key]
  ) => void;
}

export function EmbeddingModelSettingsModal({
  busy,
  open,
  settings,
  onAddEmbeddingModel,
  onChangeActiveEmbeddingModel,
  onClose,
  onRemoveEmbeddingModel,
  onSave,
  onUpdateEmbeddingModel,
}: EmbeddingModelSettingsModalProps) {
  const [selectedModelIndex, setSelectedModelIndex] = useState(0);
  const [isAddingNew, setIsAddingNew] = useState(false);
  const [newModel, setNewModel] = useState<Partial<EmbeddingModelConfig>>(createEmptyEmbeddingModel(1));

  useEffect(() => {
    if (!open) {
      return;
    }
    if (settings.embedding_models.length === 0) {
      setIsAddingNew(true);
      setSelectedModelIndex(-1);
      setNewModel(createEmptyEmbeddingModel(1));
      return;
    }
    if (!isAddingNew) {
      const activeIndex = settings.embedding_models.findIndex((item) => item.name === settings.active_embedding_model);
      setSelectedModelIndex(activeIndex >= 0 ? activeIndex : 0);
    }
  }, [isAddingNew, open, settings.active_embedding_model, settings.embedding_models]);

  const activeModel = settings.embedding_models[selectedModelIndex] ?? settings.embedding_models[0] ?? null;
  const activeIndex = selectedModelIndex < settings.embedding_models.length ? selectedModelIndex : 0;

  const isNameDuplicate = (name: string, skipIndex?: number) =>
    settings.embedding_models.some((item, index) => index !== skipIndex && item.name.trim() === name.trim());

  return (
    <Modal
      description="Edit embedding model definitions stored in the root models.json file."
      onClose={onClose}
      open={open}
      panelClassName="modal__panel--wide"
      title="Embedding Model Settings"
    >
      <div className="model-settings-page">
        <SectionCard
          description={isAddingNew ? "Configure the new embedding model." : "Configure the selected embedding model."}
          title={isAddingNew ? "New Embedding Model" : "Embedding Model Settings"}
          actions={
            <div style={{ display: "flex", gap: "8px" }}>
              {isAddingNew ? (
                <>
                  <Button
                    disabled={busy || !newModel.name?.trim() || isNameDuplicate(newModel.name)}
                    onClick={() => {
                      const finalModel = createEmptyEmbeddingModel(settings.embedding_models.length + 1, newModel);
                      const nextSettings = {
                        ...settings,
                        embedding_models: [...settings.embedding_models, finalModel],
                        active_embedding_model: finalModel.name,
                      };
                      onAddEmbeddingModel(newModel);
                      onChangeActiveEmbeddingModel(finalModel.name);
                      setIsAddingNew(false);
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
                      if (settings.embedding_models.length === 0) {
                        onClose();
                        return;
                      }
                      setIsAddingNew(false);
                    }}
                    size="sm"
                    variant="ghost"
                  >
                    Cancel
                  </Button>
                </>
              ) : activeModel ? (
                <>
                  <Button
                    disabled={busy || !activeModel.name.trim() || isNameDuplicate(activeModel.name, activeIndex)}
                    onClick={() => {
                      void onSave();
                    }}
                    size="sm"
                    variant="primary"
                  >
                    Save
                  </Button>
                  <Button
                    disabled={busy}
                    onClick={() => {
                      if (!window.confirm("Are you sure you want to remove this embedding model?")) {
                        return;
                      }
                      const nextModels = [...settings.embedding_models];
                      nextModels.splice(activeIndex, 1);
                      const nextActiveIndex = Math.max(0, activeIndex - 1);
                      const nextActiveName = nextModels[nextActiveIndex]?.name ?? null;
                      onRemoveEmbeddingModel(activeIndex);
                      onChangeActiveEmbeddingModel(nextActiveName ?? "");
                      setSelectedModelIndex(nextActiveIndex);
                      void onSave({
                        ...settings,
                        embedding_models: nextModels,
                        active_embedding_model: nextActiveName,
                      });
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
            <Field htmlFor="embedding-model-list" label="Selected Model">
              <select
                disabled={busy}
                id="embedding-model-list"
                onChange={(event) => {
                  const value = event.target.value;
                  if (value === "ADD_NEW") {
                    setIsAddingNew(true);
                    setSelectedModelIndex(-1);
                    setNewModel(createEmptyEmbeddingModel(settings.embedding_models.length + 1));
                    return;
                  }
                  setIsAddingNew(false);
                  const index = Number.parseInt(value, 10);
                  setSelectedModelIndex(index);
                  onChangeActiveEmbeddingModel(settings.embedding_models[index]?.name ?? "");
                }}
                value={isAddingNew || settings.embedding_models.length === 0 ? "ADD_NEW" : String(activeIndex)}
              >
                {settings.embedding_models.map((item, index) => (
                  <option key={`${item.name}-${index}`} value={String(index)}>
                    {item.name || "Unnamed Embedding Model"}
                  </option>
                ))}
                <option value="ADD_NEW">[+] Add Embedding Model</option>
              </select>
            </Field>
          </div>

          {(isAddingNew || activeModel) && (
            <div className="form-grid form-grid--two">
              <Field htmlFor={isAddingNew ? "new-embedding-name" : `embedding-name-${activeIndex}`} label="Display Name">
                <input
                  disabled={busy}
                  id={isAddingNew ? "new-embedding-name" : `embedding-name-${activeIndex}`}
                  onChange={(event) => {
                    const value = event.target.value;
                    if (isAddingNew) {
                      setNewModel((current) => ({ ...current, name: value }));
                      return;
                    }
                    onUpdateEmbeddingModel(activeIndex, "name", value);
                    if (settings.active_embedding_model === activeModel?.name) {
                      onChangeActiveEmbeddingModel(value);
                    }
                  }}
                  type="text"
                  value={isAddingNew ? (newModel.name ?? "") : (activeModel?.name ?? "")}
                />
              </Field>

              <Field htmlFor={isAddingNew ? "new-embedding-model" : `embedding-model-${activeIndex}`} label="Request Model">
                <input
                  disabled={busy}
                  id={isAddingNew ? "new-embedding-model" : `embedding-model-${activeIndex}`}
                  onChange={(event) => {
                    const value = event.target.value;
                    if (isAddingNew) {
                      setNewModel((current) => ({ ...current, model: value }));
                      return;
                    }
                    onUpdateEmbeddingModel(activeIndex, "model", value);
                  }}
                  type="text"
                  value={isAddingNew ? (newModel.model ?? "") : (activeModel?.model ?? "")}
                />
              </Field>

              <Field htmlFor={isAddingNew ? "new-embedding-base-url" : `embedding-base-url-${activeIndex}`} label="Base URL">
                <input
                  disabled={busy}
                  id={isAddingNew ? "new-embedding-base-url" : `embedding-base-url-${activeIndex}`}
                  onChange={(event) => {
                    const value = event.target.value;
                    if (isAddingNew) {
                      setNewModel((current) => ({ ...current, base_url: value }));
                      return;
                    }
                    onUpdateEmbeddingModel(activeIndex, "base_url", value);
                  }}
                  type="text"
                  value={isAddingNew ? (newModel.base_url ?? "") : (activeModel?.base_url ?? "")}
                />
              </Field>

              <Field htmlFor={isAddingNew ? "new-embedding-api-key" : `embedding-api-key-${activeIndex}`} label="API Key">
                <input
                  disabled={busy}
                  id={isAddingNew ? "new-embedding-api-key" : `embedding-api-key-${activeIndex}`}
                  onChange={(event) => {
                    const value = event.target.value;
                    if (isAddingNew) {
                      setNewModel((current) => ({ ...current, api_key: value }));
                      return;
                    }
                    onUpdateEmbeddingModel(activeIndex, "api_key", value);
                  }}
                  type="password"
                  value={isAddingNew ? (newModel.api_key ?? "") : (activeModel?.api_key ?? "")}
                />
              </Field>

              <Field
                htmlFor={isAddingNew ? "new-embedding-batch-size" : `embedding-batch-size-${activeIndex}`}
                label="Batch Size"
              >
                <input
                  disabled={busy}
                  id={isAddingNew ? "new-embedding-batch-size" : `embedding-batch-size-${activeIndex}`}
                  min={1}
                  onChange={(event) => {
                    const rawValue = event.target.value.trim();
                    const value = rawValue ? Number.parseInt(rawValue, 10) : null;
                    const nextValue = Number.isInteger(value) && value && value > 0 ? value : null;
                    if (isAddingNew) {
                      setNewModel((current) => ({ ...current, batch_size: nextValue }));
                      return;
                    }
                    onUpdateEmbeddingModel(activeIndex, "batch_size", nextValue);
                  }}
                  placeholder="Optional"
                  step={1}
                  type="number"
                  value={isAddingNew ? (newModel.batch_size ?? "") : (activeModel?.batch_size ?? "")}
                />
              </Field>
            </div>
          )}
        </SectionCard>
      </div>
    </Modal>
  );
}
