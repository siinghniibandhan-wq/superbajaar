import { useEffect, useRef } from "react";

export default function CatalogueModal({
  open = false,
  title,
  className = "",
  onRequestClose,
  footer,
  children,
}) {
  const dialogRef = useRef(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  function handleCancel(event) {
    event.preventDefault();
    onRequestClose?.();
  }

  function handleBackdropClick(event) {
    if (event.target === dialogRef.current) onRequestClose?.();
  }

  return (
    <dialog
      ref={dialogRef}
      className={["sb-modal", className].filter(Boolean).join(" ")}
      aria-label={title}
      onCancel={handleCancel}
      onClick={handleBackdropClick}
    >
      <div className="sb-modal-inner">
        <header className="sb-modal-header">
          <h2>{title}</h2>
          <button
            type="button"
            className="sb-modal-close"
            aria-label="Close dialog"
            onClick={onRequestClose}
          >
            ×
          </button>
        </header>
        <div className="sb-modal-content">{children}</div>
        {footer ? <footer className="sb-modal-footer">{footer}</footer> : null}
      </div>
    </dialog>
  );
}
