import type { ModelConfig } from "../../lib/api/types";

interface ModelSelectorProps {
  models: ModelConfig[];
  value: string;
  loading: boolean;
  onChange: (modelId: string) => void;
}

export function ModelSelector({ models, value, loading, onChange }: ModelSelectorProps) {
  const selected = models.find((model) => model.id === value) ?? null;

  return (
    <section className="model-panel" aria-label="Model settings">
      <div>
        <h2>Model Settings</h2>
        <p>Pick a model based on your machine performance and quality needs.</p>
      </div>
      <label className="field">
        <span>Model</span>
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={loading || models.length === 0}
        >
          {models.map((model) => (
            <option key={model.id} value={model.id}>
              {model.name} - {model.label}
            </option>
          ))}
        </select>
      </label>
      {selected ? (
        <dl className="model-meta">
          <div>
            <dt>RAM</dt>
            <dd>{selected.ram_needed}</dd>
          </div>
          <div>
            <dt>Speed</dt>
            <dd>{selected.speed}</dd>
          </div>
          <div>
            <dt>Quality</dt>
            <dd>{selected.quality}</dd>
          </div>
        </dl>
      ) : null}
    </section>
  );
}
