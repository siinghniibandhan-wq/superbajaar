import { pickVariant, selectedKeyFor } from "./variantOptions.js";

// Customer-facing variant chooser. Uses the display style saved in Catalogue
// (pill buttons, circles, tiles, plain text, colour swatches). No dropdown.
export default function VariantOptionPicker({ groups, variants, selected, onSelect, productName = "" }) {
  return <div className="storefront-option-groups" aria-label={"Choose options for " + productName}>
    {groups.map(group => {
      const currentKey = selectedKeyFor(selected, group.code);
      const currentLabel = group.options.find(option => option.key === currentKey)?.label || "";
      const style = group.displayType;
      return <div className="storefront-option-group" key={group.code}>
        <span className="storefront-option-label">{group.name}{currentLabel ? ": " : ""}<b>{currentLabel}</b></span>
        <div className={"storefront-option-list is-" + style} role="radiogroup" aria-label={group.name}>
          {group.options.map(option => {
            const active = option.key === currentKey;
            const isSwatch = (style === "colour" || style === "colour_chip") && option.hex;
            return <button type="button" role="radio" aria-checked={active} aria-label={option.label} title={option.label}
              key={option.key} className={"storefront-option" + (active ? " is-selected" : "")}
              onClick={() => { const chosen = pickVariant(variants, selected, group.code, option.key); if (chosen) onSelect(chosen); }}>
              {isSwatch && <i className="storefront-option-swatch" style={{ background: option.hex }} aria-hidden="true" />}
              {(!isSwatch || style === "colour_chip") && <span>{option.label}</span>}
            </button>;
          })}
        </div>
      </div>;
    })}
  </div>;
}
