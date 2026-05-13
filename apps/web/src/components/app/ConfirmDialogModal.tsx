import { Button, Modal } from "@/components/common";
import type { useChatWorkspace } from "@/hooks/useChatWorkspace";

type ConfirmDialogs = ReturnType<typeof useChatWorkspace>["dialogs"];

interface ConfirmDialogModalProps {
  dialogs: ConfirmDialogs;
}

export function ConfirmDialogModal({ dialogs }: ConfirmDialogModalProps) {
  return (
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
  );
}
