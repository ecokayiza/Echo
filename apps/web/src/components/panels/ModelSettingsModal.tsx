import { Button, Field, Modal, SectionCard } from "@/components/common";
import type { ChatModelConfig, EmbeddingModelConfig, ModelSettingsDocument } from "@/types/chat";

interface ModelSettingsModalProps {
  busy: boolean;
  open: boolean;
  settings: ModelSettingsDocument;
  onAddChatModel: () => void;
  onAddEmbeddingModel: () => void;
  onChangeActiveChatModel: (name: string) => void;
  onChangeActiveEmbeddingModel: (name: string) => void;
  onClose: () => void;
  onRemoveChatModel: (index: number) => void;
  onRemoveEmbeddingModel: (index: number) => void;
  onSave: () => void | Promise<void>;
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
  onAddEmbeddingModel,
  onChangeActiveChatModel,
  onChangeActiveEmbeddingModel,
  onClose,
  onRemoveChatModel,
  onRemoveEmbeddingModel,
  onSave,
  onUpdateChatModel,
  onUpdateEmbeddingModel,
}: ModelSettingsModalProps) {
  return (
    <Modal
      description="Edit all chat and embedding model definitions stored in the root models.json file."
      footer={
        <>
          <Button disabled={busy} onClick={onClose} variant="ghost">
            Cancel
          </Button>
          <Button
            disabled={busy}
            onClick={() => {
              void onSave();
            }}
            variant="primary"
          >
            Save
          </Button>
        </>
      }
      onClose={onClose}
      open={open}
      panelClassName="modal__panel--wide"
      title="Model Settings"
    >
      <div className="model-settings-page">
        <SectionCard
          description="Choose which saved models are active for chat generation and embedding."
          title="Active Selection"
        >
          <div className="form-grid form-grid--two">
            <Field htmlFor="modal-active-chat-model" label="Active Chat Model">
              <select
                disabled={busy || settings.chat_models.length === 0}
                id="modal-active-chat-model"
                onChange={(event) => {
                  onChangeActiveChatModel(event.target.value);
                }}
                value={settings.active_chat_model ?? ""}
              >
                {settings.chat_models.length > 0 ? (
                  settings.chat_models.map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.name}
                    </option>
                  ))
                ) : (
                  <option value="">No chat models configured</option>
                )}
              </select>
            </Field>

            <Field htmlFor="modal-active-embedding-model" label="Active Embedding Model">
              <select
                disabled={busy || settings.embedding_models.length === 0}
                id="modal-active-embedding-model"
                onChange={(event) => {
                  onChangeActiveEmbeddingModel(event.target.value);
                }}
                value={settings.active_embedding_model ?? ""}
              >
                {settings.embedding_models.length > 0 ? (
                  settings.embedding_models.map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.name}
                    </option>
                  ))
                ) : (
                  <option value="">No embedding models configured</option>
                )}
              </select>
            </Field>
          </div>
        </SectionCard>

        <SectionCard
          actions={
            <Button disabled={busy} onClick={onAddChatModel} size="sm" variant="secondary">
              Add Chat Model
            </Button>
          }
          description="Each entry maps to one selectable chat model profile."
          title="Chat Models"
        >
          <div className="model-config-list">
            {settings.chat_models.map((model, index) => (
              <article className="model-config-card" key={`${model.name}-${index}`}>
                <div className="model-config-card__header">
                  <div>
                    <strong>{model.name}</strong>
                    <p>{model.model ?? "Unconfigured request model"}</p>
                  </div>
                  <Button
                    disabled={busy}
                    onClick={() => {
                      onRemoveChatModel(index);
                    }}
                    size="sm"
                    variant="ghost"
                  >
                    Remove
                  </Button>
                </div>

                <div className="form-grid form-grid--two">
                  <Field htmlFor={`chat-name-${index}`} label="Display Name">
                    <input
                      disabled={busy}
                      id={`chat-name-${index}`}
                      onChange={(event) => {
                        onUpdateChatModel(index, "name", event.target.value);
                      }}
                      type="text"
                      value={model.name}
                    />
                  </Field>

                  <Field htmlFor={`chat-model-${index}`} label="Request Model">
                    <input
                      disabled={busy}
                      id={`chat-model-${index}`}
                      onChange={(event) => {
                        onUpdateChatModel(index, "model", event.target.value);
                      }}
                      type="text"
                      value={model.model ?? ""}
                    />
                  </Field>

                  <Field htmlFor={`chat-base-url-${index}`} label="Base URL">
                    <input
                      disabled={busy}
                      id={`chat-base-url-${index}`}
                      onChange={(event) => {
                        onUpdateChatModel(index, "base_url", event.target.value);
                      }}
                      type="text"
                      value={model.base_url ?? ""}
                    />
                  </Field>

                  <Field htmlFor={`chat-api-key-${index}`} label="API Key">
                    <input
                      disabled={busy}
                      id={`chat-api-key-${index}`}
                      onChange={(event) => {
                        onUpdateChatModel(index, "api_key", event.target.value);
                      }}
                      type="password"
                      value={model.api_key ?? ""}
                    />
                  </Field>

                  <Field htmlFor={`chat-temperature-${index}`} label="Temperature">
                    <input
                      disabled={busy}
                      id={`chat-temperature-${index}`}
                      onChange={(event) => {
                        const value = event.target.value;
                        onUpdateChatModel(index, "temperature", value === "" ? 1 : Number.parseFloat(value));
                      }}
                      step="0.1"
                      type="number"
                      value={String(model.temperature)}
                    />
                  </Field>

                  <Field htmlFor={`chat-top-p-${index}`} label="Top P">
                    <input
                      disabled={busy}
                      id={`chat-top-p-${index}`}
                      onChange={(event) => {
                        const value = event.target.value;
                        onUpdateChatModel(index, "top_p", value === "" ? null : Number.parseFloat(value));
                      }}
                      placeholder="Optional"
                      step="0.1"
                      type="number"
                      value={model.top_p == null ? "" : String(model.top_p)}
                    />
                  </Field>
                </div>

                <Field htmlFor={`chat-thinking-${index}`} label="Enable Thinking">
                  <select
                    disabled={busy}
                    id={`chat-thinking-${index}`}
                    onChange={(event) => {
                      const value = event.target.value;
                      onUpdateChatModel(
                        index,
                        "enable_thinking",
                        value === "" ? null : value === "true"
                      );
                    }}
                    value={
                      model.enable_thinking == null
                        ? ""
                        : model.enable_thinking
                          ? "true"
                          : "false"
                    }
                  >
                    <option value="">Provider default</option>
                    <option value="true">Enabled</option>
                    <option value="false">Disabled</option>
                  </select>
                </Field>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          actions={
            <Button disabled={busy} onClick={onAddEmbeddingModel} size="sm" variant="secondary">
              Add Embedding Model
            </Button>
          }
          description="Embedding profiles are also stored in models.json and can be switched independently."
          title="Embedding Models"
        >
          <div className="model-config-list">
            {settings.embedding_models.map((model, index) => (
              <article className="model-config-card" key={`${model.name}-${index}`}>
                <div className="model-config-card__header">
                  <div>
                    <strong>{model.name}</strong>
                    <p>{model.model ?? "Unconfigured request model"}</p>
                  </div>
                  <Button
                    disabled={busy}
                    onClick={() => {
                      onRemoveEmbeddingModel(index);
                    }}
                    size="sm"
                    variant="ghost"
                  >
                    Remove
                  </Button>
                </div>

                <div className="form-grid form-grid--two">
                  <Field htmlFor={`embedding-name-${index}`} label="Display Name">
                    <input
                      disabled={busy}
                      id={`embedding-name-${index}`}
                      onChange={(event) => {
                        onUpdateEmbeddingModel(index, "name", event.target.value);
                      }}
                      type="text"
                      value={model.name}
                    />
                  </Field>

                  <Field htmlFor={`embedding-model-${index}`} label="Request Model">
                    <input
                      disabled={busy}
                      id={`embedding-model-${index}`}
                      onChange={(event) => {
                        onUpdateEmbeddingModel(index, "model", event.target.value);
                      }}
                      type="text"
                      value={model.model ?? ""}
                    />
                  </Field>

                  <Field htmlFor={`embedding-base-url-${index}`} label="Base URL">
                    <input
                      disabled={busy}
                      id={`embedding-base-url-${index}`}
                      onChange={(event) => {
                        onUpdateEmbeddingModel(index, "base_url", event.target.value);
                      }}
                      type="text"
                      value={model.base_url ?? ""}
                    />
                  </Field>

                  <Field htmlFor={`embedding-api-key-${index}`} label="API Key">
                    <input
                      disabled={busy}
                      id={`embedding-api-key-${index}`}
                      onChange={(event) => {
                        onUpdateEmbeddingModel(index, "api_key", event.target.value);
                      }}
                      type="password"
                      value={model.api_key ?? ""}
                    />
                  </Field>
                </div>
              </article>
            ))}
          </div>
        </SectionCard>
      </div>
    </Modal>
  );
}
