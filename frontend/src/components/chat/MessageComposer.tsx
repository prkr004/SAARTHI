import { useCallback, useLayoutEffect, useRef, type FormEvent, type KeyboardEvent } from "react";

interface MessageComposerProps {
  value: string;
  disabled: boolean;
  isBusy?: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  context?: "home" | "conversation";
}

export function MessageComposer({
  value,
  disabled,
  isBusy = false,
  onChange,
  onSubmit,
  context = "conversation",
}: MessageComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const minHeight = context === "home" ? 74 : 56;
  const maxHeight = context === "home" ? 220 : 176;

  const syncTextareaHeight = useCallback(
    (node?: HTMLTextAreaElement | null) => {
      const textarea = node ?? textareaRef.current;
      if (!textarea) {
        return;
      }

      textarea.style.height = "0px";
      const nextHeight = Math.max(minHeight, Math.min(maxHeight, textarea.scrollHeight));
      textarea.style.height = `${nextHeight}px`;
      textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
    },
    [maxHeight, minHeight],
  );

  useLayoutEffect(() => {
    syncTextareaHeight();
  }, [syncTextareaHeight, value]);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitDisabled) {
      return;
    }
    onSubmit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (submitDisabled) {
        return;
      }
      onSubmit();
    }
  }

  const submitDisabled = disabled || value.trim().length === 0;
  const inputHintId = context === "home" ? "chat-input-hint-home" : "chat-input-hint-conversation";
  const inputBusyId = context === "home" ? "chat-input-busy-home" : "chat-input-busy-conversation";
  const describedBy = isBusy ? `${inputHintId} ${inputBusyId}` : inputHintId;
  const placeholder =
    context === "home"
      ? "Ask SAARTHI about RBI regulations, KYC, lending, or policy changes"
      : "Message SAARTHI about RBI compliance...";

  return (
    <form
      className={`composer composer--${context} ${disabled ? "composer--disabled" : ""}`}
      onSubmit={handleSubmit}
      aria-busy={isBusy}
    >
      <label htmlFor="chat-input" className="sr-only">
        Ask SAARTHI a question
      </label>

      <div className="composer-inner">
        <span className="composer-leading" aria-hidden="true">
          S
        </span>

        <textarea
          ref={textareaRef}
          id="chat-input"
          value={value}
          onChange={(event) => {
            onChange(event.target.value);
            syncTextareaHeight(event.currentTarget);
          }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={1}
          disabled={disabled}
          aria-describedby={describedBy}
        />

        <button
          type="submit"
          className="button button--primary button--compact composer-send"
          disabled={submitDisabled}
          aria-label={isBusy ? "SAARTHI is generating a response" : "Send message"}
        >
          <span className="composer-send__label">{isBusy ? "Thinking" : "Send"}</span>
          <span className="composer-send__icon" aria-hidden="true">
            {isBusy ? ".." : "->"}
          </span>
        </button>
      </div>

      <div className="composer-row" id={inputHintId}>
        <span className="composer-hint">Enter to send</span>
        <span className="composer-hint">Shift+Enter for new line</span>
      </div>

      {isBusy ? (
        <p id={inputBusyId} className="sr-only" role="status" aria-live="polite">
          SAARTHI is preparing a response.
        </p>
      ) : null}
    </form>
  );
}
