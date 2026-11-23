import { colourOptionLabel, normalizeColourOption } from "./colourOptions.js";
import { displayStylesFor, normalizeDisplayType } from "./attributeDisplay.js";

const SAMPLE = { text: ["S", "M", "L"], colour: [{ name: "Red", hex: "#D6453D" }, { name: "Blue", hex: "#2F6A9F" }, { name: "Green", hex: "#2E8B57" }], image: ["A", "B", "C"] };

/** Shows how the customer will see the attribute: the middle value is drawn as selected. */
export function AttributePreview({ displayType, valueType, values = [] }) {
  const real = (values || []).slice(0, 3);
  const items = real.length ? real : SAMPLE[valueType] || SAMPLE.text;
  const kind = normalizeDisplayType(displayType, valueType);
  if (kind === "text") return <span className="sb-attr-preview-text">{items.map(v => valueType === "colour" ? colourOptionLabel(v) : String(v)).join(" · ")}</span>;
  return <span className={"sb-attr-preview sb-attr-" + kind} aria-hidden="true">
    {items.map((value, index) => {
      const selected = items.length > 1 ? index === 1 : true;
      const colour = valueType === "colour" ? normalizeColourOption(value) : null;
      const label = colour ? colour.name : String(value);
      return <span key={index} className={"sb-attr-opt" + (selected ? " is-selected" : "")}>
        {(kind === "colour" || kind === "colour_chip") && <i className="sb-attr-dot" style={{ backgroundColor: colour?.hex || "#999" }} />}
        {kind.startsWith("image") && <i className="sb-attr-pic" />}
        {kind !== "colour" && !kind.startsWith("image") && <span>{label}</span>}
        {kind === "colour_chip" && <span>{label}</span>}
      </span>;
    })}
  </span>;
}

export default function AttributeDisplayPicker({ valueType, value, values, onChange, disabled = false }) {
  const current = normalizeDisplayType(value, valueType);
  return <fieldset className="sb-form-grid-wide sb-attr-display" disabled={disabled}>
    <legend>How customers see this on the product page</legend>
    <div className="sb-attr-display-grid" role="radiogroup" aria-label="Display style">
      {displayStylesFor(valueType).map(style => <button
        type="button" role="radio" key={style.value} aria-checked={current === style.value}
        className={"sb-attr-display-card" + (current === style.value ? " is-active" : "")}
        onClick={() => onChange(style.value)}
      >
        <strong>{style.label}</strong>
        <AttributePreview displayType={style.value} valueType={valueType} values={values} />
        <small>{style.hint}</small>
      </button>)}
    </div>
    <small className="sb-muted">The highlighted item shows how a selected value looks. Customers tap a value to choose it. There is no dropdown.</small>
  </fieldset>;
}
