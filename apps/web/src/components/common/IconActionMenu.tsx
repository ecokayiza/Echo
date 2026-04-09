import { EllipsisVerticalIcon } from "@heroicons/react/24/solid";
import { createPortal } from "react-dom";
import { useEffect, useRef, useState, type ComponentType, type MouseEvent, type SVGProps } from "react";

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>;

export interface IconActionMenuItem {
  key: string;
  label: string;
  icon: IconComponent;
  danger?: boolean;
  onSelect: () => void;
}

interface IconActionMenuProps {
  items: IconActionMenuItem[];
  triggerLabel: string;
  disabled?: boolean;
  triggerClassName?: string;
}

export function IconActionMenu({
  items,
  triggerLabel,
  disabled = false,
  triggerClassName = "",
}: IconActionMenuProps) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    function close() {
      setOpen(false);
    }

    function onPointerDown(event: MouseEvent | globalThis.MouseEvent) {
      const target = event.target as Node | null;
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) {
        return;
      }
      close();
    }

    window.addEventListener("mousedown", onPointerDown);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  function openMenu() {
    const trigger = triggerRef.current;
    if (!trigger) {
      return;
    }

    const rect = trigger.getBoundingClientRect();
    const menuWidth = Math.max(88, items.length * 40 + 12);
    const menuHeight = 46;
    const gutter = 8;
    const openDown = window.innerHeight - rect.bottom >= menuHeight || window.innerHeight - rect.bottom > rect.top;

    setPosition({
      top: Math.max(gutter, openDown ? rect.bottom + 6 : rect.top - menuHeight - 6),
      left: Math.min(
        Math.max(rect.right - menuWidth, gutter),
        window.innerWidth - menuWidth - gutter
      ),
    });
    setOpen(true);
  }

  return (
    <>
      <button
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={triggerLabel}
        className={triggerClassName}
        disabled={disabled}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          if (open) {
            setOpen(false);
          } else {
            openMenu();
          }
        }}
        ref={triggerRef}
        type="button"
      >
        <EllipsisVerticalIcon />
      </button>

      {open
        ? createPortal(
            <div
              className="icon-menu__panel"
              ref={panelRef}
              role="menu"
              style={{ top: `${position.top}px`, left: `${position.left}px` }}
            >
              {items.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.key}
                    aria-label={item.label}
                    className={`icon-menu__item${item.danger ? " icon-menu__item--danger" : ""}`}
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      setOpen(false);
                      item.onSelect();
                    }}
                    role="menuitem"
                    title={item.label}
                    type="button"
                  >
                    <Icon />
                  </button>
                );
              })}
            </div>,
            document.body
          )
        : null}
    </>
  );
}
