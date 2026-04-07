import type { FormEvent, KeyboardEvent } from "react";

interface MessageComposerProps {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export function MessageComposer({ value, disabled, onChange, onSubmit }: MessageComposerProps) {
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

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <label htmlFor="chat-input" className="sr-only">
        Ask SAARTHI a question
      </label>
      <textarea
        id="chat-input"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask SAARTHI a question about RBI regulatory guidelines..."
        rows={3}
        disabled={disabled}
      />
      <button type="submit" className="button button--primary" disabled={disabled || value.trim().length === 0}>
        {disabled ? "Thinking..." : "Send"}
      </button>
    </form>
  );
}
