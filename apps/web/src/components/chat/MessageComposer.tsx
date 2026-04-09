import type { RefObject } from "react";

import { Button } from "@/components/common/Button";

interface MessageComposerProps {
  busy: boolean;
  value: string;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export function MessageComposer({
  busy,
  inputRef,
  onChange,
  onSubmit,
  value,
}: MessageComposerProps) {
  return (
    <form
      className="composer"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label className="composer__field" htmlFor="message-draft">
        <span className="sr-only">Message</span>
        <textarea
          autoComplete="off"
          disabled={busy}
          id="message-draft"
          name="message"
          onChange={(event) => {
            onChange(event.target.value);
          }}
          onKeyDown={(event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
              event.preventDefault();
              onSubmit();
            }
          }}
          placeholder="Ask anything. The workflow will decide the next action."
          ref={inputRef}
          rows={4}
          value={value}
        />
      </label>

      <div className="composer__footer">
        <p className="composer__hint">Press Ctrl + Enter to send.</p>
        <Button disabled={busy || value.trim().length === 0} type="submit" variant="primary">
          Send Message
        </Button>
      </div>
    </form>
  );
}
