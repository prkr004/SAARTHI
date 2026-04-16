import { useCallback, useLayoutEffect, useRef, type FormEvent, type KeyboardEvent } from "react";

interface MessageComposerProps {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  context?: "home" | "conversation";
}

export function MessageComposer({
  value,
  disabled,
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
    onSubmit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }

  const submitDisabled = disabled || value.trim().length === 0;
  const placeholder =
    context === "home"
      ? "Ask SAARTHI about RBI regulations, KYC, lending, or policy changes"
      : "Message SAARTHI about RBI compliance...";

  return (
    <form className={`composer composer--${context} ${disabled ? "composer--disabled" : ""}`} onSubmit={handleSubmit}>
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
        />

        <button
          type="submit"
          className="button button--primary button--compact composer-send"
          disabled={submitDisabled}
          aria-label={disabled ? "Waiting for response" : "Send message"}
        >
          <span className="composer-send__label">{disabled ? "Wait" : "Send"}</span>
          <span className="composer-send__icon" aria-hidden="true">
            {disabled ? ".." : "->"}
          </span>
        </button>
      </div>

      <div className="composer-row">
        <span className="composer-hint">Enter to send</span>
        <span className="composer-hint">Shift+Enter for new line</span>
      </div>
    </form>
  );
}
